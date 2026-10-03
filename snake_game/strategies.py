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
    def __init__(self):
        self.committed_apple: Position | None = None
        self.path: list[Position] = []

    def choose_move(
        self, snapshot: GameSnapshot, snake_id: str, rng: Random
    ) -> Direction:
        legal = snapshot.legal_moves_for(snake_id)
        snake = snapshot.snake(snake_id)
        if not legal or not snapshot.apples:
            return snake.direction

        head = snake.body[0]
        body = set(snake.body)
        apples = set(snapshot.apples)

        # Setiap tick, ambil move yang sudah pernah di compute selama apple masih ada
        if self.committed_apple in apples and self.path: 
            next_path = self.path[0]
            next_move = path_to_direction(next_path, head, legal)
            if next_move: 
                self.path = self.path[1:]
                return next_move

            self.path = []

        path = self._dfs(snapshot, head, body, apples)
        if not path:
            return snake.direction if snake.direction in legal else legal[0]

        next_path = path[1]
        self.path = path[2:]
        self.committed_apple = path[-1]

        return convert_next_path_to_legal_direction(next_path, head, legal)


    def _dfs(self, 
             snapshot: GameSnapshot, 
             start: Position, 
             blocked, apples: set[Position]) -> list[Position] | None:

        stack = [(start, [start])] # tupple berisi posisi sekarang dan path
        visited = set() # set dari position yang sudah di visit

        while stack:
            current, path = stack.pop()

            if current in visited:
                continue

            visited.add(current)

            if current in apples: # Jika posisi sekarang adalah apple berarti pencarian sudah selesai
                return path

            for direction in Direction:
                next_move = convert_direction_to_next_move(current, direction)
                
                if (in_bound(snapshot, next_move) and # make sure next move masih dalam board
                    next_move not in blocked and # next move bukan body dari ular
                    next_move not in visited): # next move belum pernah di visit

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
        body = set(snake.body)
        apples = set(snapshot.apples)

        path = self._bfs(snapshot, head, body, apples)
        if not path:
            return snake.direction if snake.direction in legal else legal[0]

        next_path = path[1]
        return convert_next_path_to_legal_direction(next_path, head, legal)

    def _bfs(self, 
             snapshot: GameSnapshot, 
             start: Position, 
             blocked, apples: set[Position]) -> list[Position] | None:

        queue = deque([(start, [start])]) # queue menyimpan current position dan path
        visited = {start}

        while queue:
            current, path = queue.popleft()
         
            if current in apples:
                return path

            for direction in Direction:
                next_move = convert_direction_to_next_move(current, direction)
                            
                if (in_bound(snapshot, next_move) and # next move harus dalam board
                    next_move not in blocked and # next move bukan ke body ular
                    next_move not in visited): # next move belum pernah di visit

                    queue.append((next_move, path + [next_move]))
                    visited.add(next_move)

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
        body = set(snake.body)
        apples = set(snapshot.apples)

        path = self._ucs(snapshot, head, body, apples)
        if not path:
            return snake.direction if snake.direction in legal else legal[0]

        next_path = path[1]

        return convert_next_path_to_legal_direction(next_path, head, legal)

    def _ucs(self, 
             snapshot: GameSnapshot, 
             start: Position, 
             blocked, apples: set[Position]) -> list[Position] | None:

        queue = [(0, start, [start])] # queue menyimpan cost, current position, dan path
        visited = set()

        while queue:
            cost, current, path = heapq.heappop(queue)

            if current in visited:
                continue

            visited.add(current)

            if current in apples:
                return path

            for direction in Direction:
                next_move = convert_direction_to_next_move(current, direction)
                
                if (in_bound(snapshot, next_move) and # next move harus dalam board
                    next_move not in blocked and # next move bukan ke body ular
                    next_move not in visited): # next move belum pernah di visit

                        free_neighbour_of_next_move = count_free_neighbours(snapshot, next_move, blocked)

                        # semakin sedikit valid move dari next move semakin besar penalty
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
        body = set(snake.body)
        apples = set(snapshot.apples)
        
        path = self._greedy_bfs(snapshot, head, body, apples)
        if not path:
            return snake.direction if snake.direction in legal else legal[0]

        next_path = path[1]

        return convert_next_path_to_legal_direction(next_path, head, legal)

    def _greedy_bfs(self, 
                    snapshot: GameSnapshot,
                    start: Position,
                    blocked, apples: list[Position]) -> list[Position] | None:

        queue = [(0, start, [start])] # tupple berisi cost, current position, dan path
        visited = {start}

        while queue:
            _, current, path = heapq.heappop(queue)

            if current in apples:
                return path

            for direction in Direction:
                next_move = convert_direction_to_next_move(current, direction)

                if (in_bound(snapshot, next_move) and # next move harus dalam board
                    next_move not in blocked and # next move bukan ke body ular
                    next_move not in visited): # next move belum pernah di visit

                    min_distance = 5000
                    # ambil distance terkecil
                    for apple in apples:
                        new_distance = manhattan_distance(next_move, apple)
                        min_distance = min(min_distance, new_distance)

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
        body = set(snake.body)
        apples = set(snapshot.apples)
        
        path = self._a_star(snapshot, head, body, apples)
        if not path:
            return snake.direction if snake.direction in legal else legal[0]

        next_path = path[1]

        return convert_next_path_to_legal_direction(next_path, head, legal)

    def _a_star(self, 
             snapshot: GameSnapshot, 
             start: Position,
             blocked, apples: set[Position]) -> list[Position] | None:
        
        queue = [(0, 0, start, [start])] # queue menyimpan f, g, current position, dan path
        visited = set()

        while queue:
            _, cost, current, path = heapq.heappop(queue)

            if current in visited:
                continue

            visited.add(current)

            if current in apples:
                return path

            for direction in Direction:
                next_move = convert_direction_to_next_move(current, direction)

                if (in_bound(snapshot, next_move) and # next move harus dalam board
                    next_move not in blocked and # next move bukan ke body ular
                    next_move not in visited): # next move belum pernah di visit

                    h = 5000
                    # ambil distance terkecil
                    for apple in apples:
                        new_distance = manhattan_distance(next_move, apple)
                        h = min(h, new_distance)

                    free_neighbour_of_next_move = count_free_neighbours(snapshot, next_move, blocked)
                    
                    # semakin sedikit valid move dari next move semakin besar penalty
                    penalty_of_next_move = PENALTY[free_neighbour_of_next_move] 
                    g = cost + 1 + penalty_of_next_move

                    f = g + h

                    heapq.heappush(queue, (f, g, next_move, path + [next_move]))

        return None
    
def in_bound(snapshot: GameSnapshot, pos: Position) -> bool:
    # Cek apakah position masih valid berada di dalam board
    x, y = pos
    return 0 <= x < snapshot.columns and 0 <= y < snapshot.rows

def convert_next_path_to_legal_direction(next_move, head: Position, legal_move: tuple[Direction, ...]) -> Direction:
    direction = path_to_direction(next_move, head, legal_move)
    if not direction:
        return legal_move[0]
    
    return direction

def path_to_direction(next_move, head: Position, legal_move: tuple[Direction, ...]) -> Direction | None:
    # next_move dan head berupa (column, row)
    # untuk bisa di convert jadi direction perlu dicari selisih column dan row
    direction_x = next_move[0] - head[0]
    direction_y = next_move[1] - head[1]

    for direction in legal_move:
        if direction.vector == (direction_x, direction_y):
            return direction
    
    return None
    

def convert_direction_to_next_move(head: Position, direction: Direction) -> Position:
    # direction berupa UP, DOWN, LEFT, RIGHT
    dx, dy = direction.vector
    head_x, head_y = head

    return (head_x + dx, head_y + dy)

def count_free_neighbours(snapshot: GameSnapshot, pos: Position, blocked: set[Position]) -> int:
    count = 0
    for direction in Direction:
        neighbour = convert_direction_to_next_move(pos, direction)
        if in_bound(snapshot, neighbour) and neighbour not in blocked:
            count += 1

    return count

def manhattan_distance(pos: Position, target: Position) -> int:
    return abs(target[0] - pos[0]) + abs(target[1] - pos[1])
