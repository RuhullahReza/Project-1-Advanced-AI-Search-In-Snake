from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

Position = tuple[int, int]


class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)

    @property
    def vector(self) -> Position:
        return self.value

    @property
    def opposite(self) -> "Direction":
        return {
            Direction.UP: Direction.DOWN,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
            Direction.RIGHT: Direction.LEFT,
        }[self]


class GameMode(Enum):
    SINGLE = "Single Player (AI)"
    VERSUS = "Human vs AI"
    AI_VS_AI = "AI vs AI"


class GameStatus(Enum):
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"


@dataclass(frozen=True)
class GameConfig:
    rows: int = 20
    columns: int = 20
    move_limit: int = 200
    ai_speed: int = 4
    apple_count: int = 5
    mode: GameMode = GameMode.SINGLE
    strategy_name: str = "Greedy"
    secondary_strategy_name: str = "Safe Random"

    def __post_init__(self) -> None:
        if not 10 <= self.rows <= 40 or not 10 <= self.columns <= 40:
            raise ValueError("Grid rows and columns must be between 10 and 40.")
        if not 10 <= self.move_limit <= 2000:
            raise ValueError("Move limit must be between 10 and 2000.")
        if not 1 <= self.ai_speed <= 10:
            raise ValueError("AI speed must be between 1 and 10 moves per second.")
        if not 1 <= self.apple_count <= 20:
            raise ValueError("Apple count must be between 1 and 20.")


@dataclass
class SnakeState:
    snake_id: str
    body: list[Position]
    direction: Direction
    score: int = 0


@dataclass(frozen=True)
class SnakeView:
    snake_id: str
    body: tuple[Position, ...]
    direction: Direction
    score: int


@dataclass(frozen=True)
class GameSnapshot:
    rows: int
    columns: int
    snakes: tuple[SnakeView, ...]
    apples: tuple[Position, ...]
    rounds_completed: int
    rounds_remaining: int
    active_snake_id: str
    legal_moves: tuple[tuple[str, tuple[Direction, ...]], ...]

    def snake(self, snake_id: str) -> SnakeView:
        for snake in self.snakes:
            if snake.snake_id == snake_id:
                return snake
        raise KeyError(f"Unknown snake: {snake_id}")

    def legal_moves_for(self, snake_id: str) -> tuple[Direction, ...]:
        for candidate_id, moves in self.legal_moves:
            if candidate_id == snake_id:
                return moves
        return ()


@dataclass(frozen=True)
class MoveOutcome:
    accepted: bool
    ate_apple: bool = False
    collision: str | None = None
    message: str = ""
