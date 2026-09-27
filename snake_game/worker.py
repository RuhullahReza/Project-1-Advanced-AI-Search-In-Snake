"""Persistent, disposable strategy process: no Pygame access in the worker."""
import multiprocessing as mp
import random
import time


def _run(connection, strategy, construct):
    try:
        while True:
            snapshot, snake_id, rng_state = connection.recv()
            rng = random.Random()
            rng.setstate(rng_state)
            try:
                if construct:
                    strategy = strategy()
                    construct = False
                direction = strategy.choose_move(snapshot, snake_id, rng)
                connection.send((time.monotonic(), (direction, rng.getstate(), "")))
            except Exception as exc:
                connection.send((time.monotonic(), (None, None, f"{type(exc).__name__}: {exc}")))
    except (EOFError, BrokenPipeError, OSError):
        pass
    finally:
        connection.close()


class StrategyWorker:
    def __init__(self, strategy, timeout=5.0, construct=False):
        context = mp.get_context("spawn")
        self.connection, child = context.Pipe()
        self.process = context.Process(target=_run, args=(child, strategy, construct), daemon=True)
        self.pending = False
        self.timeout = timeout
        try:
            self.process.start()
        except Exception:
            self.connection.close()
            raise
        finally:
            child.close()

    def submit(self, snapshot, snake_id, rng_state):
        self.connection.send((snapshot, snake_id, rng_state))
        self.started = time.monotonic()
        self.pending = True

    def poll(self):
        if not self.pending:
            return None
        if self.connection.poll():
            self.pending = False
            try:
                completed, result = self.connection.recv()
                if completed - self.started > self.timeout:
                    return self._timeout_result()
                return result
            except (EOFError, OSError):
                return None, None, "Strategy process exited unexpectedly."
        if not self.process.is_alive():
            self.pending = False
            return None, None, "Strategy process exited unexpectedly."
        if time.monotonic() - self.started >= self.timeout:
            self.pending = False
            return self._timeout_result()
        return None

    def _timeout_result(self):
        return None, None, f"Strategy exceeded {self.timeout:g} seconds. Choose another strategy or simplify its search."

    def close(self):
        self.connection.close()
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=0.1)
