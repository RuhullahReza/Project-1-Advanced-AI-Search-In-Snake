import time
import pygame

from snake_game.app import SnakeApp
from snake_game.models import Direction, GameStatus
from snake_game.worker import StrategyWorker


class SlowStrategy:
    def choose_move(self, snapshot, snake_id, rng):
        time.sleep(0.4)
        return Direction.UP


class BrokenStrategy:
    def choose_move(self, snapshot, snake_id, rng):
        raise ValueError("deliberate failure")


class SlowConstructor(SlowStrategy):
    def __init__(self):
        time.sleep(0.4)


class BrokenConstructor:
    def __init__(self):
        raise ValueError("constructor failed")


def test_constructor_is_off_ui_thread_and_ready_move_waits_for_resume(monkeypatch):
    from snake_game.strategies import STRATEGY_REGISTRY
    app = SnakeApp()
    try:
        monkeypatch.setitem(STRATEGY_REGISTRY, "Greedy", SlowConstructor)
        started = time.perf_counter()
        app.start_game()
        print(f"Start with slow constructor: {(time.perf_counter() - started) * 1000:.2f} ms")
        assert time.perf_counter() - started < 0.2
        app._perform_ai_move()
        app.engine.pause()
        deadline = time.monotonic() + 8
        while app.ready_move is None and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert app.ready_move is not None
        assert app.engine.status is GameStatus.PAUSED
        assert app.engine.rounds_completed == 0
        app.engine.resume()
        app.update()
        assert app.engine.rounds_completed == 1
        assert app.ready_move is None
    finally:
        app.close_worker()
        pygame.quit()


def test_timeout_is_enforced_while_paused():
    app = SnakeApp()
    try:
        app.start_game()
        app.worker = StrategyWorker(SlowConstructor, timeout=0.05, construct=True)
        process = app.worker.process
        app._perform_ai_move()
        app.engine.pause()
        time.sleep(0.06)
        app.update()
        assert app.engine.status is GameStatus.FINISHED
        assert "exceeded" in app.engine.error_message
        assert app.worker is None
        process.join(timeout=2)
        assert not process.is_alive()
    finally:
        app.close_worker()
        pygame.quit()


def test_late_result_is_rejected_even_if_ready_before_poll():
    app = SnakeApp()
    app.start_game()
    worker = StrategyWorker(SlowConstructor, timeout=0.05, construct=True)
    try:
        worker.submit(app.engine.snapshot(), "ai", app.engine.rng.getstate())
        assert worker.connection.poll(8)
        assert "exceeded" in worker.poll()[2]
    finally:
        worker.close()
        pygame.quit()


def test_constructor_exception_reaches_game():
    app = SnakeApp()
    try:
        app.start_game()
        app.strategy = BrokenConstructor
        app._perform_ai_move()
        deadline = time.monotonic() + 8
        while app.engine.status is GameStatus.RUNNING and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert "constructor failed" in app.engine.error_message
        assert app.worker is None
    finally:
        app.close_worker()
        pygame.quit()


def test_slow_strategy_keeps_pause_and_setup_responsive():
    app = SnakeApp()
    try:
        app.start_game()
        app.strategy = SlowStrategy()
        dispatched = time.perf_counter()
        app._perform_ai_move()
        print(f"Dispatch: {(time.perf_counter() - dispatched) * 1000:.2f} ms")
        process = app.worker.process
        started = time.perf_counter()
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p))
        assert app.engine.status is GameStatus.PAUSED
        elapsed = time.perf_counter() - started
        print(f"Pause during computation: {elapsed * 1000:.2f} ms")
        assert elapsed < 0.2
        app.update()
        assert app.engine.rounds_completed == 0
        app.return_to_setup()
        process.join(timeout=2)
        assert not process.is_alive()
    finally:
        app.close_worker()
        pygame.quit()


def test_worker_applies_completed_move():
    app = SnakeApp()
    try:
        app.start_game()
        app.strategy = SlowStrategy()
        app._perform_ai_move()
        deadline = time.monotonic() + 10
        while app.engine.rounds_completed == 0 and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)
        assert app.engine.rounds_completed == 1
        assert app.engine.snakes["ai"].direction is Direction.UP
    finally:
        app.close_worker()
        pygame.quit()


def test_worker_timeout_and_exception_are_visible():
    app = SnakeApp()
    try:
        for strategy, timeout, expected in ((SlowStrategy(), 0.01, "exceeded"),
                                             (BrokenStrategy(), 5, "deliberate failure")):
            app.start_game()
            app.worker = StrategyWorker(strategy, timeout=timeout)
            app._perform_ai_move()
            deadline = time.monotonic() + 10
            while app.engine.status is GameStatus.RUNNING and time.monotonic() < deadline:
                app.update()
                time.sleep(0.01)
            assert app.engine.status is GameStatus.FINISHED
            assert expected in app.engine.error_message
            assert app.worker is None
    finally:
        app.close_worker()
        pygame.quit()
