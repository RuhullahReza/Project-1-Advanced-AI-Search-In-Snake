from __future__ import annotations

import random
import time
from collections.abc import Callable

from .models import (
    Direction,
    GameConfig,
    GameMode,
    GameSnapshot,
    GameStatus,
    MoveOutcome,
    Position,
    SnakeState,
    SnakeView,
)

HUMAN_ID = "human"
AI_ID = "ai"


class GameEngine:
    """UI-independent rules engine for turn-based Snake."""

    def __init__(
        self,
        config: GameConfig,
        rng: random.Random | None = None,
        time_source: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self.rng = rng or random.Random()
        self._time_source = time_source
        self.status = GameStatus.RUNNING
        self.rounds_completed = 0
        self.active_snake_id = AI_ID if config.mode is GameMode.SINGLE else HUMAN_ID
        self.finish_reason = ""
        self.error_message = ""
        self.loser_id: str | None = None
        self._started_at = self._time_source()
        self._paused_at: float | None = None
        self._paused_total = 0.0
        self._finished_at: float | None = None
        self.snakes = self._create_snakes()
        self.apples: list[Position] = []
        self._spawn_initial_apples()

    def _create_snakes(self) -> dict[str, SnakeState]:
        y = self.config.rows // 2
        if self.config.mode is GameMode.SINGLE:
            x = self.config.columns // 2
            return {
                AI_ID: SnakeState(
                    AI_ID,
                    [(x, y), (x - 1, y), (x - 2, y)],
                    Direction.RIGHT,
                )
            }

        human_x = max(2, self.config.columns // 4)
        ai_x = min(self.config.columns - 3, 3 * self.config.columns // 4)
        return {
            HUMAN_ID: SnakeState(
                HUMAN_ID,
                [(human_x, y), (human_x - 1, y), (human_x - 2, y)],
                Direction.RIGHT,
            ),
            AI_ID: SnakeState(
                AI_ID,
                [(ai_x, y), (ai_x + 1, y), (ai_x + 2, y)],
                Direction.LEFT,
            ),
        }

    @property
    def rounds_remaining(self) -> int:
        return max(0, self.config.move_limit - self.rounds_completed)

    @property
    def elapsed_time(self) -> float:
        end = self._finished_at
        if end is None:
            end = self._paused_at if self._paused_at is not None else self._time_source()
        return max(0.0, end - self._started_at - self._paused_total)

    @property
    def winner_id(self) -> str | None:
        if self.status is not GameStatus.FINISHED or not self.snakes:
            return None
        if self.loser_id is not None:
            survivors = [
                snake_id for snake_id in self.snakes if snake_id != self.loser_id
            ]
            return survivors[0] if len(survivors) == 1 else None
        best = max(snake.score for snake in self.snakes.values())
        leaders = [snake.snake_id for snake in self.snakes.values() if snake.score == best]
        return leaders[0] if len(leaders) == 1 else None

    @property
    def is_draw(self) -> bool:
        return (
            self.status is GameStatus.FINISHED
            and len(self.snakes) > 1
            and self.winner_id is None
        )

    def pause(self) -> None:
        if self.status is GameStatus.RUNNING:
            self.status = GameStatus.PAUSED
            self._paused_at = self._time_source()

    def resume(self) -> None:
        if self.status is GameStatus.PAUSED and self._paused_at is not None:
            self._paused_total += self._time_source() - self._paused_at
            self._paused_at = None
            self.status = GameStatus.RUNNING

    def toggle_pause(self) -> None:
        if self.status is GameStatus.RUNNING:
            self.pause()
        elif self.status is GameStatus.PAUSED:
            self.resume()

    def legal_moves_for(self, snake_id: str) -> tuple[Direction, ...]:
        snake = self.snakes[snake_id]
        legal: list[Direction] = []
        for direction in Direction:
            if len(snake.body) > 1 and direction is snake.direction.opposite:
                continue
            new_head = self._next_head(snake.body[0], direction)
            growing = new_head in self.apples
            if self._collision_type(snake_id, new_head, growing) is None:
                legal.append(direction)
        return tuple(legal)

    def snapshot(self) -> GameSnapshot:
        views = tuple(
            SnakeView(
                snake.snake_id,
                tuple(snake.body),
                snake.direction,
                snake.score,
            )
            for snake in self.snakes.values()
        )
        legal = tuple(
            (snake_id, self.legal_moves_for(snake_id)) for snake_id in self.snakes
        )
        return GameSnapshot(
            rows=self.config.rows,
            columns=self.config.columns,
            snakes=views,
            apples=tuple(self.apples),
            rounds_completed=self.rounds_completed,
            rounds_remaining=self.rounds_remaining,
            active_snake_id=self.active_snake_id,
            legal_moves=legal,
        )

    def step(self, snake_id: str, direction: Direction) -> MoveOutcome:
        if self.status is not GameStatus.RUNNING:
            return MoveOutcome(False, message="The game is not running.")
        if snake_id != self.active_snake_id:
            return MoveOutcome(False, message="It is not that snake's turn.")
        if not isinstance(direction, Direction):
            return MoveOutcome(False, message="Movement must be a Direction.")

        snake = self.snakes[snake_id]
        if len(snake.body) > 1 and direction is snake.direction.opposite:
            return MoveOutcome(False, message="A snake cannot reverse into its neck.")

        new_head = self._next_head(snake.body[0], direction)
        ate_apple = new_head in self.apples
        collision = self._collision_type(snake_id, new_head, ate_apple)
        if collision is not None:
            snake.score -= 1
            self._finish(
                f"{self.display_name(snake_id)} hit {collision}.",
                loser_id=snake_id,
            )
            return MoveOutcome(True, collision=collision, message=self.finish_reason)

        snake.direction = direction
        snake.body.insert(0, new_head)
        if ate_apple:
            snake.score += 1
            self.apples.remove(new_head)
            if not self.apples:
                self._finish("All apples were eaten.")
                return MoveOutcome(True, ate_apple=True, message=self.finish_reason)
        else:
            snake.body.pop()

        self._advance_turn()
        return MoveOutcome(True, ate_apple=ate_apple)

    def fail_strategy(self, snake_id: str, message: str) -> None:
        if self.status is not GameStatus.RUNNING:
            return
        self.snakes[snake_id].score -= 1
        self.error_message = message
        self._finish(
            f"{self.display_name(snake_id)} strategy failed.",
            loser_id=snake_id,
        )

    def _advance_turn(self) -> None:
        if self.config.mode is GameMode.SINGLE:
            self.rounds_completed += 1
            self.active_snake_id = AI_ID
        elif self.active_snake_id == HUMAN_ID:
            self.active_snake_id = AI_ID
        else:
            self.rounds_completed += 1
            self.active_snake_id = HUMAN_ID

        if self.rounds_completed >= self.config.move_limit:
            self._finish("Move limit reached.")

    def _next_head(self, head: Position, direction: Direction) -> Position:
        dx, dy = direction.vector
        return head[0] + dx, head[1] + dy

    def _collision_type(
        self, snake_id: str, new_head: Position, growing: bool
    ) -> str | None:
        x, y = new_head
        if x < 0 or x >= self.config.columns or y < 0 or y >= self.config.rows:
            return "the wall"

        moving = self.snakes[snake_id]
        own_occupied = moving.body if growing else moving.body[:-1]
        if new_head in own_occupied:
            return "itself"

        for other_id, other in self.snakes.items():
            if other_id != snake_id and new_head in other.body:
                return "the other snake"
        return None

    def _spawn_initial_apples(self) -> None:
        occupied = {part for snake in self.snakes.values() for part in snake.body}
        empty = [
            (x, y)
            for y in range(self.config.rows)
            for x in range(self.config.columns)
            if (x, y) not in occupied
        ]
        count = min(self.config.apple_count, len(empty))
        self.apples = self.rng.sample(empty, count)

    def _finish(self, reason: str, loser_id: str | None = None) -> None:
        if self.status is GameStatus.FINISHED:
            return
        if self.status is GameStatus.PAUSED and self._paused_at is not None:
            self._paused_total += self._time_source() - self._paused_at
            self._paused_at = None
        self.status = GameStatus.FINISHED
        self.finish_reason = reason
        self.loser_id = loser_id
        self._finished_at = self._time_source()

    def display_name(self, snake_id: str) -> str:
        if self.config.mode is GameMode.AI_VS_AI:
            return "AI 1" if snake_id == HUMAN_ID else "AI 2"
        return "Human" if snake_id == HUMAN_ID else "AI"
