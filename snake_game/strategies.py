from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from random import Random

from .models import Direction, GameSnapshot, Position

from collections import deque


class MoveStrategy(ABC):
    """Base class for every automated snake movement method."""

    @abstractmethod
    def choose_move(
        self, snapshot: GameSnapshot, snake_id: str, rng: Random
    ) -> Direction:
        """Return the direction for ``snake_id`` for the current turn."""


STRATEGY_REGISTRY: dict[str, type[MoveStrategy]] = {}


def register_strategy(name: str) -> Callable[[type[MoveStrategy]], type[MoveStrategy]]:
    """Register a strategy class so it appears in the setup-screen dropdown."""

    def decorator(strategy_class: type[MoveStrategy]) -> type[MoveStrategy]:
        if not name.strip():
            raise ValueError("Strategy names cannot be empty.")
        STRATEGY_REGISTRY[name] = strategy_class
        return strategy_class

    return decorator


def create_strategy(name: str) -> MoveStrategy:
    try:
        return STRATEGY_REGISTRY[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown strategy: {name}") from exc


@register_strategy("Safe Random")
class SafeRandomStrategy(MoveStrategy):
    def choose_move(
        self, snapshot: GameSnapshot, snake_id: str, rng: Random
    ) -> Direction:
        legal = snapshot.legal_moves_for(snake_id)
        if legal:
            return rng.choice(legal)
        return snapshot.snake(snake_id).direction


@register_strategy("Greedy")
class GreedyStrategy(MoveStrategy):
    def choose_move(
        self, snapshot: GameSnapshot, snake_id: str, rng: Random
    ) -> Direction:
        legal = snapshot.legal_moves_for(snake_id)
        snake = snapshot.snake(snake_id)
        if not legal or not snapshot.apples:
            return snake.direction

        head_x, head_y = snake.body[0]

        def distance(direction: Direction) -> int:
            dx, dy = direction.vector
            new_x, new_y = head_x + dx, head_y + dy
            return min(
                abs(new_x - apple_x) + abs(new_y - apple_y)
                for apple_x, apple_y in snapshot.apples
            )

        best_distance = min(distance(direction) for direction in legal)
        best_moves = [direction for direction in legal if distance(direction) == best_distance]
        return rng.choice(best_moves)

@register_strategy("DFS")
class DFSStrategy(MoveStrategy):
    def choose_move(
        self, snapshot: GameSnapshot, snake_id: str, rng: Random
    ) -> Direction:
        legal = snapshot.legal_moves_for(snake_id)
        snake = snapshot.snake(snake_id)
        if not legal or not snapshot.apples:
            return snake.direction

        head = snake.body[0]
        body = set(snake.body) # for fast body lookup
        apples = set(snapshot.apples) # for fast apple lookup

        path = self._dfs(snapshot, head, apples, body)
        if not path:
            return snake.direction if snake.direction in legal else legal[0]

        next_move = path[1]
        
        return convert_next_path_to_direction(next_move, head, legal)

    def _dfs(self, 
             snapshot: GameSnapshot, 
             start: Position, 
             apples: set[Position], 
             blocked: set[Position]
             ) -> Position| None:

        # stack berisi titik awal dan urutan path menuju apple pertama yang ditemukan
        stack = [(start, [start])]
        visited = set(start)

        while stack:
            current, path = stack.pop()
            if current in apples:
                return path

            for direction in Direction:
                dx, dy = direction.vector # value dari vector berupa tuple 2 integer antara -1 0 1
                head_x, head_y = current
                next_move = (head_x + dx, head_y + dy)

                if (
                    in_bound(snapshot, next_move) and
                    next_move not in blocked and
                    next_move not in visited
                ):
                    visited.add(next_move)
                    stack.append((next_move, path + [next_move]))

        return None

@register_strategy("BFS")
class BFSStrategy(MoveStrategy):
    def choose_move(
        self, snapshot: GameSnapshot, snake_id: str, rng: Random
    ) -> Direction:
        legal = snapshot.legal_moves_for(snake_id)
        snake = snapshot.snake(snake_id)
        if not legal or not snapshot.apples:
            return snake.direction

        head = snake.body[0]
        body = set(snake.body) # for fast body lookup
        apples = set(snapshot.apples) # for fast apple lookup

        path = self._bfs(snapshot, head, apples, body)
        if not path:
            return snake.direction if snake.direction in legal else legal[0]

        next_move = path[1]

        return convert_next_path_to_direction(next_move, head, legal)

    def _bfs(self, 
             snapshot: GameSnapshot, 
             start: Position, 
             apples: set[Position], 
             blocked: set[Position]
             ) -> Position| None:

        # stack berisi titik awal dan urutan path menuju apple pertama yang ditemukan
        stack = deque([(start, [start])])
        visited = set(start)

        while stack:
            current, path = stack.popleft()
            if current in apples:
                return path

            for direction in Direction:
                dx, dy = direction.vector # value dari vector berupa tuple 2 integer antara -1 0 1
                head_x, head_y = current
                next_move = (head_x + dx, head_y + dy)

                if (
                    in_bound(snapshot, next_move) and
                    next_move not in blocked and
                    next_move not in visited
                ):
                    visited.add(next_move)
                    stack.append((next_move, path + [next_move]))

        return None


def in_bound(snapshot: GameSnapshot, pos: Position) -> bool:
    # Cek apakah position masih valid berada di dalam board
    x, y = pos
    return 0 <= x < snapshot.columns and 0 <= y < snapshot.rows

def convert_next_path_to_direction(next_move, head: Position, legal_move: tuple[Position]) -> Direction:
    # next_move dan head berupa (column, row)
    # untuk bisa di convert jadi direction perlu dicari selisih column dan row
    direction_x = next_move[0] - head[0]
    direction_y = next_move[1] - head[1]

    for direction in legal_move:
        if direction.vector == (direction_x, direction_y):
            return direction

    # fallback ketika tidak ada legal move
    return legal_move[0]
