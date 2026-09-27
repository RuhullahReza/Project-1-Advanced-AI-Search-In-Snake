from __future__ import annotations

import random

from snake_game.engine import AI_ID, HUMAN_ID, GameEngine
from snake_game.models import Direction, GameConfig, GameMode, GameStatus, SnakeState


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def engine(mode: GameMode = GameMode.SINGLE, moves: int = 20) -> GameEngine:
    return GameEngine(
        GameConfig(rows=10, columns=10, mode=mode, move_limit=moves),
        rng=random.Random(7),
    )


def test_move_growth_score_and_apple_is_removed_without_respawn() -> None:
    game = engine()
    snake = game.snakes[AI_ID]
    head = snake.body[0]
    game.apples = [(head[0] + 1, head[1])]

    result = game.step(AI_ID, Direction.RIGHT)

    assert result.ate_apple
    assert snake.score == 1
    assert len(snake.body) == 4
    assert game.apples == []
    assert game.finish_reason == "All apples were eaten."


def test_all_configured_apples_spawn_unique_and_off_snakes() -> None:
    game = GameEngine(
        GameConfig(rows=10, columns=10, mode=GameMode.VERSUS, apple_count=20),
        rng=random.Random(7),
    )
    occupied = {part for snake in game.snakes.values() for part in snake.body}
    assert len(game.apples) == 20
    assert len(set(game.apples)) == 20
    assert not set(game.apples) & occupied


def test_wall_collision_applies_penalty_and_finishes() -> None:
    game = engine()
    game.snakes[AI_ID] = SnakeState(AI_ID, [(9, 3), (8, 3), (7, 3)], Direction.RIGHT)

    result = game.step(AI_ID, Direction.RIGHT)

    assert result.collision == "the wall"
    assert game.snakes[AI_ID].score == -1
    assert game.status is GameStatus.FINISHED


def test_self_collision() -> None:
    game = engine()
    game.snakes[AI_ID] = SnakeState(
        AI_ID,
        [(3, 3), (3, 2), (2, 2), (2, 3), (2, 4), (3, 4)],
        Direction.DOWN,
    )
    game.apples = [(8, 8)]

    result = game.step(AI_ID, Direction.LEFT)

    assert result.collision == "itself"


def test_opponent_collision() -> None:
    game = engine(GameMode.VERSUS)
    game.snakes[HUMAN_ID] = SnakeState(
        HUMAN_ID, [(3, 3), (2, 3), (1, 3)], Direction.RIGHT
    )
    game.snakes[AI_ID] = SnakeState(AI_ID, [(4, 3), (5, 3), (6, 3)], Direction.LEFT)
    game.apples = [(8, 8)]

    assert Direction.RIGHT not in game.legal_moves_for(HUMAN_ID)
    result = game.step(HUMAN_ID, Direction.RIGHT)

    assert result.collision == "the other snake"
    assert game.status is GameStatus.FINISHED
    assert game.active_snake_id == HUMAN_ID
    assert game.loser_id == HUMAN_ID
    assert game.winner_id == AI_ID


def test_reversal_is_rejected_without_consuming_turn() -> None:
    game = engine(GameMode.VERSUS)
    before = list(game.snakes[HUMAN_ID].body)

    result = game.step(HUMAN_ID, Direction.LEFT)

    assert not result.accepted
    assert game.snakes[HUMAN_ID].body == before
    assert game.active_snake_id == HUMAN_ID


def test_tail_cell_is_legal_when_it_will_move_away() -> None:
    game = engine()
    game.snakes[AI_ID] = SnakeState(
        AI_ID, [(3, 3), (3, 4), (2, 4), (2, 3)], Direction.UP
    )
    game.apples = [(8, 8)]
    assert Direction.LEFT in game.legal_moves_for(AI_ID)


def test_two_player_round_requires_both_moves() -> None:
    game = engine(GameMode.VERSUS, moves=10)
    game.apples = [(0, 0)]
    assert game.step(HUMAN_ID, Direction.UP).accepted
    assert game.rounds_completed == 0
    assert game.active_snake_id == AI_ID
    assert game.step(AI_ID, Direction.UP).accepted
    assert game.rounds_completed == 1
    assert game.active_snake_id == HUMAN_ID


def test_ai_vs_ai_uses_two_named_ai_players_and_alternating_turns() -> None:
    game = engine(GameMode.AI_VS_AI, moves=10)
    game.apples = [(0, 0)]

    assert game.display_name(HUMAN_ID) == "AI 1"
    assert game.display_name(AI_ID) == "AI 2"
    assert game.active_snake_id == HUMAN_ID
    assert game.step(HUMAN_ID, Direction.RIGHT).accepted
    assert game.active_snake_id == AI_ID
    assert game.step(AI_ID, Direction.LEFT).accepted
    assert game.rounds_completed == 1
    assert game.active_snake_id == HUMAN_ID


def test_move_limit_finishes_and_score_selects_winner() -> None:
    game = engine(GameMode.VERSUS, moves=10)
    game.rounds_completed = 9
    game.snakes[HUMAN_ID].score = 3
    game.snakes[AI_ID].score = 1
    game.apples = [(0, 0)]
    game.step(HUMAN_ID, Direction.UP)
    game.step(AI_ID, Direction.UP)

    assert game.status is GameStatus.FINISHED
    assert game.finish_reason == "Move limit reached."
    assert game.winner_id == HUMAN_ID


def test_equal_scores_are_a_draw() -> None:
    game = engine(GameMode.VERSUS, moves=10)
    game.rounds_completed = 9
    game.apples = [(0, 0)]
    game.step(HUMAN_ID, Direction.UP)
    game.step(AI_ID, Direction.UP)

    assert game.is_draw


def test_collision_is_an_immediate_loss_even_with_a_higher_score() -> None:
    game = engine(GameMode.VERSUS)
    game.snakes[HUMAN_ID] = SnakeState(
        HUMAN_ID, [(9, 2), (8, 2), (7, 2)], Direction.RIGHT, score=10
    )
    game.snakes[AI_ID].score = 0

    game.step(HUMAN_ID, Direction.RIGHT)

    assert game.snakes[HUMAN_ID].score == 9
    assert game.loser_id == HUMAN_ID
    assert game.winner_id == AI_ID
    assert not game.is_draw


def test_strategy_failure_is_an_immediate_multiplayer_loss() -> None:
    game = engine(GameMode.AI_VS_AI)
    game.snakes[HUMAN_ID].score = 10

    game.fail_strategy(HUMAN_ID, "bad output")

    assert game.loser_id == HUMAN_ID
    assert game.winner_id == AI_ID


def test_elapsed_time_excludes_pause_and_freezes_at_finish() -> None:
    clock = FakeClock()
    game = GameEngine(GameConfig(rows=10, columns=10), time_source=clock)
    clock.now = 5
    game.pause()
    clock.now = 15
    assert game.elapsed_time == 5
    game.resume()
    clock.now = 20
    assert game.elapsed_time == 10
    game.snakes[AI_ID] = SnakeState(AI_ID, [(9, 3), (8, 3), (7, 3)], Direction.RIGHT)
    game.step(AI_ID, Direction.RIGHT)
    clock.now = 30
    assert game.elapsed_time == 10


def test_strategy_failure_is_visible_and_safe() -> None:
    game = engine()
    game.fail_strategy(AI_ID, "bad output")
    assert game.status is GameStatus.FINISHED
    assert game.error_message == "bad output"
    assert game.snakes[AI_ID].score == -1
