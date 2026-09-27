"""Line-oriented alternative for terminal and screen-reader users."""
import argparse
import time

from .engine import AI_ID, HUMAN_ID, GameEngine
from .models import Direction, GameConfig, GameMode, GameStatus
from .strategies import STRATEGY_REGISTRY
from .worker import StrategyWorker


def describe(engine, board=False):
    lines = [f"Round {engine.rounds_completed} of {engine.config.move_limit}. Status: {engine.status.value}."]
    for snake_id, snake in engine.snakes.items():
        name = engine.display_name(snake_id)
        lines.append(f"{name}: score {snake.score}, head {snake.body[0]}, direction {snake.direction.name.lower()}.")
        if board:
            lines.append(f"{name} body, head to tail: {snake.body}.")
    lines.append(f"Apples: {engine.apples}. Coordinates are (column, row), starting at zero at top left.")
    lines.append(f"Active turn: {engine.display_name(engine.active_snake_id)}.")
    if engine.status is GameStatus.FINISHED:
        winner = engine.display_name(engine.winner_id) if engine.winner_id else "draw"
        lines.extend([engine.finish_reason, engine.error_message, f"Winner: {winner}."])
    return "\n".join(line for line in lines if line)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Text-mode Snake. Decisions advance only on command; no timed input required.")
    parser.add_argument("--rows", type=int, default=20)
    parser.add_argument("--columns", type=int, default=20)
    parser.add_argument("--apples", type=int, default=5)
    parser.add_argument("--moves", type=int, default=200)
    parser.add_argument("--speed", type=int, default=4, help="Stored AI speed; text mode advances on command.")
    parser.add_argument("--mode", choices=["single", "versus", "ai-vs-ai"], default="single")
    parser.add_argument("--strategy", choices=list(STRATEGY_REGISTRY), default="Greedy")
    parser.add_argument("--strategy-2", choices=list(STRATEGY_REGISTRY), default="Safe Random")
    args = parser.parse_args(argv)
    try:
        modes = {
            "single": GameMode.SINGLE,
            "versus": GameMode.VERSUS,
            "ai-vs-ai": GameMode.AI_VS_AI,
        }
        config = GameConfig(rows=args.rows, columns=args.columns, apple_count=args.apples,
                            move_limit=args.moves, ai_speed=args.speed,
                            mode=modes[args.mode], strategy_name=args.strategy,
                            secondary_strategy_name=args.strategy_2)
    except ValueError as exc:
        parser.error(str(exc))
    engine = GameEngine(config)
    workers = {}

    def close_workers():
        for worker in workers.values():
            worker.close()
        workers.clear()

    help_text = "Commands: status, board (all body coordinates), up/down/left/right, next (AI turn), restart, help, quit."
    print(help_text)
    print(describe(engine))
    try:
        while True:
            command = input("Command: ").strip().lower()
            if command in ("quit", "exit"):
                break
            if command == "help":
                print(help_text)
                continue
            if command == "restart":
                close_workers()
                engine = GameEngine(config)
            elif command in ("next", "up", "down", "left", "right") and engine.status is GameStatus.RUNNING:
                active_id = engine.active_snake_id
                human_turn = config.mode is GameMode.VERSUS and active_id == HUMAN_ID
                if human_turn:
                    if command == "next":
                        print("Choose up, down, left, or right for the human turn.")
                        continue
                    outcome = engine.step(HUMAN_ID, Direction[command.upper()])
                    if not outcome.accepted:
                        print(outcome.message)
                elif command != "next":
                    print("It is the AI turn. Use next.")
                    continue
                else:
                    try:
                        strategy_name = config.strategy_name
                        if config.mode is GameMode.AI_VS_AI and active_id == AI_ID:
                            strategy_name = config.secondary_strategy_name
                        if active_id not in workers:
                            workers[active_id] = StrategyWorker(
                                STRATEGY_REGISTRY[strategy_name], construct=True
                            )
                        worker = workers[active_id]
                        worker.submit(engine.snapshot(), active_id, engine.rng.getstate())
                        print(f"{engine.display_name(active_id)} thinking.")
                        result = None
                        while result is None:
                            result = worker.poll()
                            time.sleep(0.01)
                        direction, state, error = result
                        if error:
                            raise RuntimeError(error)
                        outcome = engine.step(active_id, direction)
                        if not outcome.accepted:
                            raise ValueError(outcome.message)
                        engine.rng.setstate(state)
                    except Exception as exc:
                        engine.fail_strategy(active_id, f"{type(exc).__name__}: {exc}")
            elif command not in ("status", "board"):
                print(help_text)
            if engine.status is GameStatus.FINISHED:
                close_workers()
            print(describe(engine, board=command == "board"))
    except (EOFError, KeyboardInterrupt):
        print("Session ended.")
    finally:
        close_workers()
