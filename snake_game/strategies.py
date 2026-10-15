from __future__ import annotations

from collections import deque
import heapq

from abc import ABC, abstractmethod
from collections.abc import Callable
from random import Random
from tracemalloc import start
from itertools import count

from .models import Direction, GameSnapshot, Position, MinimaxState, SnakeView
from .engine import AI_ID
import time

class SearchMetrics:
    def __init__(self):
        self.reset()

    def reset(self):
        self.states_generated = 0
        self.states_expanded = 0

    def print_metrics(self):
        print("States generated:", self.states_generated)
        print("States expanded:", self.states_expanded)

class AdversarialMetrics:
    def __init__(self):
        self.reset()

    def reset(self):
        self.states_generated = 0 
        self.states_evaluated = 0
        self.number_of_pruned_branch = 0
        self.number_of_cuttof = 0
        self.total_time = 0.0
        self.moves = 0

    def print_metrics(self, name: str, depth: int, snapshot: GameSnapshot, snake_id: str, move: Direction):
        snake = snapshot.snake(snake_id)
        next_head = convert_direction_to_next_move(snake.body[0], move)
        score = snake.score + (1 if next_head in snapshot.apples else 0)
        print(f"algorithm:{name}")
        print(f"depth:{depth}")
        print(f"time:{self.total_time:.3f}s")
        print(f"score:{score}")
        print(f"states_generated:{self.states_generated}")
        print(f"states_evaludatd:{self.states_evaluated}")
        print(f"number_of_pruned_branch:{self.number_of_pruned_branch}")
        print(f"number_of_cuttof:{self.number_of_cuttof}")


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
        self.metrics = SearchMetrics()

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

        # helper statistik
        self.metrics.print_metrics()


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

            # helper statistik
            self.metrics.states_expanded += 1

            visited.add(current)

            if current in apples: # Jika posisi sekarang adalah apple berarti pencarian sudah selesai
                return path

            for direction in Direction:
                next_move = convert_direction_to_next_move(current, direction)
                
                if (in_bound(snapshot, next_move) and # make sure next move masih dalam board
                    next_move not in blocked and # next move bukan body dari ular
                    next_move not in visited): # next move belum pernah di visit

                    stack.append((next_move, path + [next_move]))

                    #helper statistik
                    self.metrics.states_generated += 1

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
        
        apples = set(snapshot.apples)
        start_state = (snake.body[0], snake.direction)
        frontier = []
        counter = count()
        blocked = set(snake.body)
        best_cost = {start_state: 0} # {((koordinat kepala ular), direction): cost}
        # contoh: {(4, 5), direction.UP: 0}

        heapq.heappush(frontier,
                       (
                           0,
                           next(counter),
                           start_state,
                           None
                        ),
                       )

        while frontier:
            current_cost, _, current_state, first_move = heapq.heappop(frontier)

            if current_cost > best_cost[current_state]:
                continue

            head, _ = current_state

            if head in apples:
                return first_move

            for direction in Direction:

                dx, dy = direction.vector
                head_x, head_y = head
                next_move = (head_x + dx, head_y + dy)

                next_state = (next_move, direction)

                free_neighbour_of_next_move = count_free_neighbours(snapshot, next_move, blocked)
                penalty_of_next_move = PENALTY[free_neighbour_of_next_move]
                new_cost = current_cost + 1 + penalty_of_next_move

                if not in_bound(snapshot, next_move) or next_move in blocked:
                    continue

                if next_state not in best_cost or new_cost < best_cost[next_state]:
                    best_cost[next_state] = new_cost

                    if first_move is None:
                        new_first_move = direction
                    else:
                        new_first_move = first_move

                    # new_first_move = direction if first_move is None else first_move

                    heapq.heappush(frontier,
                       (
                           new_cost,
                           next(counter),
                           next_state,
                           new_first_move
                        ),
                       )

        # return rng.choice(legal) # bisa coba pake fallback
        return snake.direction if snake.direction in legal else legal[0] #fallback

@register_strategy("GreedyBFS")
class GreedyBFSStrategy(MoveStrategy):
    def choose_move(
        self, snapshot: GameSnapshot, snake_id: str, rng: Random
    ) -> Direction:
        legal = snapshot.legal_moves_for(snake_id)
        snake = snapshot.snake(snake_id)
        
        if not legal or not snapshot.apples:
            return snake.direction
        
        apples = set(snapshot.apples)
        start_state = (snake.body[0], snake.direction)
        frontier = []
        counter = count()
        blocked = set(snake.body)
        visited = {start_state} # {((koordinat kepala ular), direction)}
        # contoh: {((4, 5), direction.UP)}

        distance_start = 999
        for apple in apples:
            if manhattan_distance(snake.body[0], apple) < distance_start:
                distance_start = manhattan_distance(snake.body[0], apple)

        heapq.heappush(frontier,
                       (
                           distance_start,
                           next(counter),
                           start_state,
                           None
                        ),
                       )

        while frontier:
            _, _, current_state, first_move = heapq.heappop(frontier)
            head, _ = current_state

            if head in apples:
                return first_move

            for direction in Direction:
                dx, dy = direction.vector
                head_x, head_y = head
                next_move = (head_x + dx, head_y + dy)
                next_state = (next_move, direction)

                distance = 999
                for apple in apples:
                    if manhattan_distance(next_move, apple) < distance:
                        distance = manhattan_distance(next_move, apple)

                if not in_bound(snapshot, next_move) or next_move in blocked:
                    continue

                if next_state in visited:
                    continue

                visited.add(next_state)
                
                if first_move is None:
                    new_first_move = direction
                else:
                    new_first_move = first_move

                # new_first_move = direction if first_move is None else first_move

                heapq.heappush(frontier,
                    (
                        distance,
                        next(counter),
                        next_state,
                        new_first_move
                    ),
                    )

        # return rng.choice(legal) # bisa coba pake fallback
        return snake.direction if snake.direction in legal else legal[0] #fallback
            

@register_strategy("A*")
class AStarStrategy(MoveStrategy):
    def __init__(self):
        super().__init__()
        self.metrics = SearchMetrics()

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
        print(f"Pop: {next_path}")

        # helper statistik
        self.metrics.print_metrics()


        return convert_next_path_to_legal_direction(next_path, head, legal)

    def _a_star(self, 
             snapshot: GameSnapshot, 
             start: Position,
             blocked, apples: set[Position]) -> list[Position] | None:
        
        h_start = min(
            manhattan_distance(start, apple)
            for apple in apples
        )

        queue = [(h_start, 0, start, [start])]
        visited = set()
        g_score = {}

        while queue:
            f, cost, current, path = heapq.heappop(queue)
            print(f"Current: {current}, f: {f}, g: {cost}, Path: {path}")
            print(f"g_score: {g_score}")
            
            if current in visited:
                continue

            visited.add(current)
            print(f"Visited: {visited}")

            if current in apples:
                print(f"Found apple at {current}, path: {path}")
                return path

            # helper statistik
            self.metrics.states_expanded += 1

            for direction in Direction:
                next_move = convert_direction_to_next_move(current, direction)

                if (in_bound(snapshot, next_move) and # next move harus dalam board
                    next_move not in blocked and # next move bukan ke body ular
                    next_move not in visited): # next move belum pernah di visit

                    # helper statistik
                    self.metrics.states_generated += 1

                    h = 5000
                    # ambil distance terkecil
                    for apple in apples:
                        new_distance = manhattan_distance(next_move, apple)
                        h = min(h, new_distance)

                    free_neighbour_of_next_move = count_free_neighbours(snapshot, next_move, blocked)
                    
                    # semakin sedikit valid move dari next move semakin besar penalty
                    penalty_of_next_move = PENALTY[free_neighbour_of_next_move] 
                    g = cost + 1 + penalty_of_next_move

                    if(next_move in g_score and g >= g_score[next_move]):
                        continue
                    else:
                        g_score[next_move] = g
                        f = g + h
                        heapq.heappush(queue, (f, g, next_move, path + [next_move]))

        return None

    
@register_strategy("IDA*")
class IDAStarStrategy(MoveStrategy):

    def __init__(self):
        super().__init__()
        self.metrics = SearchMetrics()

    def choose_move(
        self, snapshot: GameSnapshot, snake_id: str, rng: Random
    ) -> Direction:

        # helper statistik
        # self.metrics.reset()

        legal = snapshot.legal_moves_for(snake_id)
        snake = snapshot.snake(snake_id)

        if not legal or not snapshot.apples:
            return snake.direction

        head = snake.body[0]
        body = set(snake.body)
        apples = set(snapshot.apples)

        path = self._ida_star(snapshot, head, body, apples)

        if not path or len(path) < 2:
            if snake.direction in legal:
                return snake.direction
            else:
                return legal[0]

        next_path = path[1]

        # helper statistik
        self.metrics.print_metrics()
        print(f"IDA* next position: {next_path}")

        return convert_next_path_to_legal_direction(
            next_path, head, legal
        )

    def _ida_star(
        self,
        snapshot: GameSnapshot,
        start: Position,
        blocked: set[Position],
        apples: set[Position],
    ) -> list[Position] | None:

        # treshold awal pakai manhattan
        threshold = min(
            manhattan_distance(start, apple)
            for apple in apples
        )

        while True:

            path = [start]
            path_set = {start}

            result, next_threshold = self._dfs(
                snapshot,
                start,
                blocked,
                apples,
                0,
                path,
                path_set,
                threshold,
            )

            if result is not None:
                return result

            if next_threshold is None:
                return None

            threshold = next_threshold

    def _dfs(
        self,
        snapshot: GameSnapshot,
        current: Position,
        blocked: set[Position],
        apples: set[Position],
        g: int,
        path: list[Position],
        path_set: set[Position],
        threshold: int,
    ) -> tuple[list[Position] | None, int | None]:

        h = min(
            manhattan_distance(current, apple)
            for apple in apples
        )

        f = g + h
        if f > threshold:
            return None, f

        if current in apples:
            return path.copy(), None

        # helper statistik
        self.metrics.states_expanded += 1

        smallest_threshold = None

        for direction in Direction:

            next_move = convert_direction_to_next_move(
                current, direction
            )

            if (
                not in_bound(snapshot, next_move)
                or next_move in blocked
                or next_move in path_set
            ):
                continue

            # helper statistik
            self.metrics.states_generated += 1

            new_g = g + 1

            path.append(next_move)
            path_set.add(next_move)

            result, next_threshold = self._dfs(
                snapshot,
                next_move,
                blocked,
                apples,
                new_g,
                path,
                path_set,
                threshold,
            )

            path.pop()
            path_set.remove(next_move)

            if result is not None:
                return result, None

            if next_threshold is not None:
                if smallest_threshold is None or next_threshold < smallest_threshold:
                    smallest_threshold = next_threshold

        return None, smallest_threshold
    
MAX_DEPTH = 8
WIN_SCORE = 10000

@register_strategy("Minimax")
class MinimaxStrategy(MoveStrategy):
    def __init__(self):
        self.metrics = AdversarialMetrics()

    def choose_move(
        self, snapshot: GameSnapshot, snake_id: str, rng: Random
    ) -> Direction:
        if snapshot.rounds_completed == 0:
            self.metrics.reset()

        t0 = time.perf_counter()

        legal = snapshot.legal_moves_for(snake_id)
        our_snake = snapshot.snake(snake_id)
        if not legal or not snapshot.apples:
            return our_snake.direction

        # Asumsi hanya ada 1 lawan dalam game
        other = [snake for snake in snapshot.snakes if snake.snake_id != snake_id]
        opponent = other[0] if len(other) > 0 else None

        if opponent is None: # jika tidak ada lawan, fallback ke random move
            return rng.choice(legal)

        current_player_id = our_snake.snake_id
        opponent_id = opponent.snake_id

        root = build_minimax_state(snapshot)

        values = []
        for move in legal:
            child_node = apply_move(root, current_player_id, move)
            self.metrics.states_generated += 1
            value = self._minimax(child_node, MAX_DEPTH - 1, opponent_id, current_player_id, opponent_id)
            values.append(value)

        best_value = max(values)
        best_moves = [move for move, value in zip(legal, values) if value == best_value]
        
        chosen = rng.choice(best_moves)
        self.metrics.total_time += time.perf_counter() - t0
        self.metrics.moves += 1
        self.metrics.print_metrics("Minimax", MAX_DEPTH, snapshot, snake_id, chosen)
        
        return chosen
        
    def _minimax(self, 
                state: MinimaxState, 
                depth: int, 
                current_turn: str, # id snake mana yang lagi jalan
                current_player, opponent: str) -> int:  # id snake

        result = terminal_value(state, current_player)
        if result is not None:
            self.metrics.states_evaluated += 1
            # game selesai return hasil
            return result

        moves = legal_moves(state, current_turn)
        if len(moves) == 0:
            self.metrics.states_evaluated += 1
            if current_turn == current_player:
                # tidak ada move yang bisa di ambil current player
                return -WIN_SCORE
            else:
                # tidak ada move yang bisa di ambil lawan
                return +WIN_SCORE

        if depth == 0:
            self.metrics.states_evaluated += 1
            return evaluate(state, current_player)

        if current_turn == current_player:
            next_turn = opponent
        else:
            next_turn = current_player

        values = []
        for move in moves:
            child_node = apply_move(state, current_turn, move)
            self.metrics.states_generated += 1
            node_value = self._minimax(child_node, depth-1, next_turn, current_player, opponent)
            values.append(node_value)

        if current_turn == current_player:
            return max(values)

        return min(values)

@register_strategy("Alpha beta pruning")
class ABPruningStrategy(MoveStrategy):
    def __init__(self):
        self.metrics = AdversarialMetrics()

    def choose_move(
        self, snapshot: GameSnapshot, snake_id: str, rng: Random
    ) -> Direction:
        if snapshot.rounds_completed == 0:
            self.metrics.reset()

        t0 = time.perf_counter()                                

        legal = snapshot.legal_moves_for(snake_id)
        our_snake = snapshot.snake(snake_id)
        if not legal or not snapshot.apples:
            return our_snake.direction

        # Asumsi hanya ada 1 lawan dalam game
        other = [snake for snake in snapshot.snakes if snake.snake_id != snake_id]
        opponent = other[0] if len(other) > 0 else None

        if opponent is None: # jika tidak ada lawan, fallback ke random move
            return rng.choice(legal)

        current_player_id = our_snake.snake_id
        opponent_id = opponent.snake_id

        root = build_minimax_state(snapshot)

        best = -float('inf')
        values = []
        for move in legal:
            child_node = apply_move(root, current_player_id, move)
            self.metrics.states_generated += 1
            value = self._alpha_beta(child_node, MAX_DEPTH - 1, opponent_id, current_player_id, opponent_id, best - 1, float('inf'))
            values.append(value)
            best = max(best, value)

        best_value = max(values)
        best_moves = [move for move, value in zip(legal, values) if value == best_value]

        chosen = rng.choice(best_moves)                     
        self.metrics.total_time += time.perf_counter() - t0        
        self.metrics.moves += 1                                    
        self.metrics.print_metrics("Alpha Beta Prunning",MAX_DEPTH, snapshot, snake_id, chosen)  
        
        return chosen
        
    def _alpha_beta(self, 
                state: MinimaxState, 
                depth: int, 
                current_turn: str, # id snake mana yang lagi jalan
                current_player, opponent: str,
                alpha: int, beta: int
                ) -> int:  # id snake

        result = terminal_value(state, current_player)
        if result is not None:
            self.metrics.states_evaluated += 1
            # game selesai
            return result

        moves = legal_moves(state, current_turn)
        if len(moves) == 0:
            self.metrics.states_evaluated += 1
            if current_turn == current_player:
                # tidak ada move yang bisa di ambil current player
                return -WIN_SCORE
            else:
                # tidak ada move yang bisa di ambil lawan
                return +WIN_SCORE
            
        if depth == 0:
            self.metrics.states_evaluated += 1
            return evaluate(state, current_player)

        if current_turn == current_player:
            next_turn = opponent
            best = -float('inf')
            for i, move in enumerate(moves):
                child_node = apply_move(state, current_turn, move)
                self.metrics.states_generated += 1
                value = self._alpha_beta(child_node, depth - 1, next_turn, current_player, opponent, alpha, beta)
                best = max(best, value)
                alpha = max(alpha, best)
                if alpha >= beta:
                    self.metrics.number_of_cuttof += 1
                    self.metrics.number_of_pruned_branch += len(moves) - i - 1
                    break

            return best
        else:
            next_turn = current_player
            best = float('inf')
            for i, move in enumerate(moves):
                child_node = apply_move(state, current_turn, move)
                self.metrics.states_generated += 1
                value = self._alpha_beta(child_node, depth - 1, next_turn, current_player, opponent, alpha, beta)
                best = min(best, value)
                beta = min(beta, best)
                if alpha >= beta:
                    self.metrics.number_of_cuttof += 1
                    self.metrics.number_of_pruned_branch += len(moves) - i - 1
                    break

            return best
    
def in_bound(snapshot: GameSnapshot | MinimaxState, pos: Position) -> bool:
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

def build_minimax_state(snapshot: GameSnapshot) -> MinimaxState:
    snakes: dict[str, SnakeView] = {}
    for snake in snapshot.snakes:
        snakes[snake.snake_id] = snake

    return MinimaxState(snakes, snapshot.apples, snapshot.rounds_remaining, snapshot.rows, snapshot.columns)

def legal_moves(state: MinimaxState, snake_id: str) -> list[Direction]:
    snake = state.snakes[snake_id]
    head = snake.body[0]
    legal: list[Direction] = []

    for direction in Direction:
        # tidak bisa mundur
        if len(snake.body) > 1 and direction is snake.direction.opposite:
            continue

        # snake bergerak ke posisi baru
        new_head = convert_direction_to_next_move(head, direction)

        # tidak boleh keluar board
        if not in_bound(state, new_head):
            continue

        # tidak boleh bergerak ke body sendiri:
        growing = new_head in state.apples
        if growing: # ketika head ada di apple body bertambah panjang 1 cell
            own_blocked = snake.body
        else: # ketika bergerak maju ekor nya berpindah 1 cell
            own_blocked = snake.body[:-1]

        if new_head in own_blocked:
            continue

        # tidak boleh nabrak ular lain
        hit_other = False
        for other_id, other_snake in state.snakes.items():
            if other_id != snake_id and new_head in other_snake.body:
                hit_other = True

        if hit_other:
            continue

        legal.append(direction)

    return legal

def apply_move(state: MinimaxState, snake_id: str, direction: Direction) -> MinimaxState:
    snake = state.snakes[snake_id]
    new_head = convert_direction_to_next_move(snake.body[0], direction)

    growing = new_head in state.apples
    if growing:
        # ketika head ada di apple body bertambah panjang 1 cell
        new_body = (new_head,) + snake.body

        # apples berkurang
        new_apples = tuple(apple for apple in state.apples if apple != new_head)

    else:
        # ketika bergerak maju ekor nya berpindah 1 cell
        new_body = (new_head,) + snake.body[:-1]

        new_apples = state.apples

    new_score = snake.score + 1 if growing else snake.score
    new_snake = SnakeView(snake_id, new_body, direction, new_score)

    new_snakes = state.snakes.copy()
    new_snakes[snake_id] = new_snake # replace state snake ke state terbaru

    new_rounds = state.rounds_remaining
    if snake_id == AI_ID:
        # round berkurang setelah human dan AI selesai bergerak
        new_rounds = new_rounds - 1

    return MinimaxState(new_snakes, new_apples, new_rounds, state.rows, state.columns)

def terminal_value(state: MinimaxState, snake_id: str) -> int | None:
    current_player, opponent = get_current_and_opponent_snake(state, snake_id)

    if len(state.apples) == 0 or state.rounds_remaining <= 0:
        if current_player.score > opponent.score:
            return WIN_SCORE
        if current_player.score < opponent.score:
            return -WIN_SCORE
        return 0

    return None

def evaluate(state: MinimaxState, snake_id: str) -> int:
    current_player, opponent = get_current_and_opponent_snake(state, snake_id)

    score = 100 * (current_player.score - opponent.score)

    current_apple_distance = 5000
    opponent_apple_distance = 5000

    for apple in state.apples:
        current_distance = manhattan_distance(current_player.body[0], apple)
        opponent_distance = manhattan_distance(opponent.body[0], apple)

        current_apple_distance = min(current_apple_distance, current_distance)
        opponent_apple_distance = min(opponent_apple_distance, opponent_distance)

    return score + (opponent_apple_distance - current_apple_distance)

def get_current_and_opponent_snake(state: MinimaxState, snake_id: str) -> list[SnakeView]:
    other = [snake for snake in state.snakes.values() if snake.snake_id != snake_id]
    current_player = state.snakes[snake_id]
    opponent = other[0]

    return current_player, opponent