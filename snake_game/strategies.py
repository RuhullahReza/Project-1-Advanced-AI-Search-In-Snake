from __future__ import annotations

from collections import deque
import heapq


from abc import ABC, abstractmethod
from collections.abc import Callable
from random import Random

from .models import Direction, GameSnapshot, Position


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
             ) -> list[Position] | None:

        stack = [(start, [start])]
        visited = set()

        while stack:
            current, path = stack.pop()
            if current in visited:
                continue
            
            visited.add(current)
                        
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
             ) -> list[Position] | None:
        
        queue = deque([(start, [start])])
        visited = {start}

        while queue:
            current, path = queue.popleft()
            if current in apples:
                return path

            for direction in Direction:
                dx, dy = direction.vector
                head_x, head_y = current
                next_move = (head_x + dx, head_y + dy)

                if (
                    in_bound(snapshot, next_move) and
                    next_move not in blocked and
                    next_move not in visited
                ):
                    visited.add(next_move)
                    queue.append((next_move, path + [next_move]))

        return None

PENALTY = {4: 0, 3: 1, 2: 2, 1: 5, 0: 6}

@register_strategy("UCS")
class UCSStrategy(MoveStrategy):
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

        path = self._ucs(snapshot, head, apples, body)
        if not path:
            return snake.direction if snake.direction in legal else legal[0]

        next_move = path[1]

        return convert_next_path_to_direction(next_move, head, legal)

    def _ucs(self, 
             snapshot: GameSnapshot, 
             start: Position, 
             apples: set[Position], 
             blocked: set[Position]
             ) -> list[Position] | None:
        
        queue = [(0, start, [start])] # (cost, current cell, path)
        visited = set()

        while queue:
            cost, current, path = heapq.heappop(queue)
            if current in visited:
                continue
            
            visited.add(current)

            if current in apples:
                return path

            head_x, head_y = current
            for direction in Direction:
                dx, dy = direction.vector
                next_move = (head_x + dx, head_y + dy)
                if (
                    in_bound(snapshot, next_move) and
                    next_move not in blocked and
                    next_move not in visited
                ):
                    free_neighbour_of_next_move = count_free_neighbours(snapshot, next_move, blocked)

                    penalty_of_next_move = PENALTY[free_neighbour_of_next_move]
                    new_cost = cost + 1 + penalty_of_next_move

                    heapq.heappush(queue, (new_cost, next_move, path + [next_move]))

        return None


@register_strategy("Greedy Best-First Search")
class GreedyBFSStrategy(MoveStrategy):
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

        path = self._greedy_bfs(snapshot, head, apples, body)
        if not path:
            return snake.direction if snake.direction in legal else legal[0]

        next_move = path[1]

        return convert_next_path_to_direction(next_move, head, legal)

    def _greedy_bfs(self, 
             snapshot: GameSnapshot, 
             start: Position, 
             apples: set[Position], 
             blocked: set[Position]
             ) -> list[Position] | None:
        
        queue = [(0, start, [start])] # (heuristic value, current cell, path)
        visited = {start}

        while queue:
            _, current, path = heapq.heappop(queue)
            if current in apples:
                return path

            for direction in Direction:
                dx, dy = direction.vector
                head_x, head_y = current
                next_move = (head_x + dx, head_y + dy)

                if (
                    in_bound(snapshot, next_move) and
                    next_move not in blocked and
                    next_move not in visited
                ):
                    min_distance = 5000
                    for apple in apples:
                        distance = manhattan_distance(next_move, apple)
                        min_distance = min(min_distance, distance)

                    visited.add(next_move)
                    heapq.heappush(queue, (min_distance, next_move, path + [next_move]))

        return None

@register_strategy("A*")
class AStarStrategy(MoveStrategy):
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

        path = self._a_star(snapshot, head, apples, body)
        if not path:
            return snake.direction if snake.direction in legal else legal[0]

        next_move = path[1]

        return convert_next_path_to_direction(next_move, head, legal)

    def _a_star(self, 
             snapshot: GameSnapshot, 
             start: Position, 
             apples: set[Position], 
             blocked: set[Position]
             ) -> list[Position] | None:
        
        queue = [(0, 0, start, [start])] # (f, g, current cell, path)
        visited = set()

        while queue:
            _, cost, current, path = heapq.heappop(queue)
            if current in visited:
                continue
            
            visited.add(current)

            if current in apples:
                return path

            head_x, head_y = current
            for direction in Direction:
                dx, dy = direction.vector
                next_move = (head_x + dx, head_y + dy)
                if (
                    in_bound(snapshot, next_move) and
                    next_move not in blocked and
                    next_move not in visited
                ):
                    h = 5000
                    for apple in apples:
                        distance = manhattan_distance(next_move, apple)
                        h = min(h, distance)

                    free_neighbour_of_next_move = count_free_neighbours(snapshot, next_move, blocked)

                    penalty_of_next_move = PENALTY[free_neighbour_of_next_move]
                    g = cost + 1 + penalty_of_next_move

                    f = g + h

                    heapq.heappush(queue, (f, g, next_move, path + [next_move]))

        return None
    
def in_bound(snapshot: GameSnapshot, pos: Position) -> bool:
    # Cek apakah position masih valid berada di dalam board
    x, y = pos
    return 0 <= x < snapshot.columns and 0 <= y < snapshot.rows

def convert_next_path_to_direction(next_move, head: Position, legal_move: tuple[Direction, ...]) -> Direction:
    # next_move dan head berupa (column, row)
    # untuk bisa di convert jadi direction perlu dicari selisih column dan row
    direction_x = next_move[0] - head[0]
    direction_y = next_move[1] - head[1]

    for direction in legal_move:
        if direction.vector == (direction_x, direction_y):
            return direction

    # fallback ketika next move ilegal
    return legal_move[0]

def count_free_neighbours(snapshot: GameSnapshot, pos: Position, blocked: set[Position]) -> int:
    x, y = pos
    count = 0
    for direction in Direction:
        direction_x, direction_y = direction.vector
        neighbour = (x + direction_x, y + direction_y)
        if in_bound(snapshot, neighbour) and neighbour not in blocked:
            count += 1

    return count

def manhattan_distance(pos: Position, target: Position) -> int:
    return abs(target[0] - pos[0]) + abs(target[1] - pos[1])
