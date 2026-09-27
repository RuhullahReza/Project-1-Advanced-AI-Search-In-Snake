from __future__ import annotations

import random

from snake_game.engine import AI_ID, GameEngine
from snake_game.models import Direction, GameConfig, SnakeState
from snake_game.strategies import (
    STRATEGY_REGISTRY,
    GreedyStrategy,
    MoveStrategy,
    SafeRandomStrategy,
    register_strategy,
)


def test_safe_random_always_selects_a_legal_move() -> None:
    game = GameEngine(GameConfig(rows=10, columns=10), rng=random.Random(1))
    game.snakes[AI_ID] = SnakeState(AI_ID, [(0, 0), (0, 1), (1, 1)], Direction.UP)
    game.apples = [(9, 9)]
    snapshot = game.snapshot()
    move = SafeRandomStrategy().choose_move(snapshot, AI_ID, random.Random(2))
    assert move in snapshot.legal_moves_for(AI_ID)


def test_greedy_reduces_apple_distance_when_possible() -> None:
    game = GameEngine(GameConfig(rows=10, columns=10), rng=random.Random(1))
    game.snakes[AI_ID] = SnakeState(AI_ID, [(3, 3), (2, 3), (1, 3)], Direction.RIGHT)
    game.apples = [(3, 0), (9, 9)]
    move = GreedyStrategy().choose_move(game.snapshot(), AI_ID, random.Random(2))
    assert move is Direction.UP


def test_trapped_strategies_fall_back_to_current_direction() -> None:
    game = GameEngine(GameConfig(rows=10, columns=10))
    game.snakes[AI_ID] = SnakeState(
        AI_ID,
        [(0, 0), (0, 1), (1, 1), (1, 0)],
        Direction.LEFT,
    )
    game.apples = [(8, 8)]
    snapshot = game.snapshot()
    assert snapshot.legal_moves_for(AI_ID) == ()
    assert SafeRandomStrategy().choose_move(snapshot, AI_ID, random.Random()) is Direction.LEFT
    assert GreedyStrategy().choose_move(snapshot, AI_ID, random.Random()) is Direction.LEFT


def test_registered_custom_strategy_appears_in_registry() -> None:
    @register_strategy("Test Strategy")
    class TestStrategy(MoveStrategy):
        def choose_move(self, snapshot, snake_id, rng):
            return Direction.UP

    assert STRATEGY_REGISTRY["Test Strategy"] is TestStrategy
