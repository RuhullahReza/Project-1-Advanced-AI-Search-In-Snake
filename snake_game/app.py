from __future__ import annotations

import random
from dataclasses import replace
from enum import Enum

import pygame

from .engine import AI_ID, HUMAN_ID, GameEngine
from .models import Direction, GameConfig, GameMode, GameStatus
from .strategies import STRATEGY_REGISTRY, MoveStrategy
from .worker import StrategyWorker

WINDOW_SIZE = (1120, 800)
MIN_WINDOW_SIZE = (640, 600)
FPS = 60

BACKGROUND = (10, 15, 28)
PANEL = (21, 29, 48)
PANEL_LIGHT = (31, 43, 67)
GRID_LINE = (34, 48, 66)
TEXT = (232, 240, 248)
MUTED = (142, 160, 180)
CYAN = (52, 211, 235)
GREEN = (72, 214, 139)
BLUE = (75, 145, 255)
RED = (255, 83, 112)
YELLOW = (255, 205, 86)

SETTINGS = {
    "rows": ("rows", 10, 40, 1),
    "cols": ("columns", 10, 40, 1),
    "apples": ("apple_count", 1, 20, 1),
    "moves": ("move_limit", 10, 2000, 10),
    "speed": ("ai_speed", 1, 10, 1),
}


class Screen(Enum):
    SETUP = "setup"
    GAME = "game"
    RESULTS = "results"


class SnakeApp:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Turn-Based Snake")
        desktop = pygame.display.get_desktop_sizes()[0]
        initial = tuple(max(minimum, min(preferred, available - margin))
                        for minimum, preferred, available, margin in
                        zip(MIN_WINDOW_SIZE, WINDOW_SIZE, desktop, (80, 100)))
        self.window = pygame.display.set_mode(initial, pygame.RESIZABLE)
        self.ui_zoom = 1.0
        self.pan = [0, 0]
        self.surface = pygame.Surface(initial)
        self.clock = pygame.time.Clock()
        self.font_small = pygame.font.Font(None, 24)
        self.font = pygame.font.Font(None, 30)
        self.font_large = pygame.font.Font(None, 48)
        self.font_title = pygame.font.Font(None, 68)
        self.screen = Screen.SETUP
        self.config = GameConfig()
        self.engine: GameEngine | None = None
        self.strategy: type[MoveStrategy] | MoveStrategy | None = None
        self.secondary_strategy: type[MoveStrategy] | MoveStrategy | None = None
        self.last_ai_move_ms = 0
        self.running = True
        self._buttons: dict[str, pygame.Rect] = {}
        self.focused: str | None = None
        self.setup_error = ""
        self.details_open = False
        self.detail_scroll = 0
        self.detail_max_scroll = 0
        self.worker: StrategyWorker | None = None
        self.secondary_worker: StrategyWorker | None = None
        self.ready_move = None
        self.secondary_ready_move = None

    def _resize_canvas(self) -> None:
        size = tuple(max(minimum, round(length / self.ui_zoom))
                     for minimum, length in zip(MIN_WINDOW_SIZE, self.window.get_size()))
        self.surface = pygame.Surface(size)
        self._clamp_pan()

    def _clamp_pan(self) -> None:
        for axis in (0, 1):
            maximum = max(0, round(self.surface.get_size()[axis] * self.ui_zoom) - self.window.get_size()[axis])
            self.pan[axis] = max(0, min(maximum, self.pan[axis]))

    def _reveal_focus(self) -> None:
        if self.focused not in self._buttons:
            return
        rect = self._buttons[self.focused].inflate(12, 12)
        for axis, (start, end) in enumerate(((rect.left, rect.right), (rect.top, rect.bottom))):
            low, high = round(start * self.ui_zoom), round(end * self.ui_zoom)
            length = self.window.get_size()[axis]
            if high > self.pan[axis] + length:
                self.pan[axis] = high - length
            if low < self.pan[axis]:
                self.pan[axis] = low
        self._clamp_pan()

    def _canvas_point(self, point):
        return tuple(round((value + offset) / self.ui_zoom) for value, offset in zip(point, self.pan))

    def _present(self) -> None:
        size = tuple(round(length * self.ui_zoom) for length in self.surface.get_size())
        scaled = self.surface if self.ui_zoom == 1 else pygame.transform.smoothscale(self.surface, size)
        self.window.fill(BACKGROUND)
        self.window.blit(scaled, (-self.pan[0], -self.pan[1]))
        width, height = self.window.get_size()
        vertical = size[1] > height
        horizontal = size[0] > width
        if vertical:
            track = pygame.Rect(width - 10, 8, 4, height - (24 if horizontal else 16))
            thumb = max(28, round(track.height * height / size[1]))
            travel = track.height - thumb
            y = track.top + round(self.pan[1] / (size[1] - height) * travel)
            pygame.draw.rect(self.window, PANEL_LIGHT, track, border_radius=2)
            pygame.draw.rect(self.window, MUTED, (track.x, y, track.width, thumb), border_radius=2)
        if horizontal:
            track = pygame.Rect(8, height - 10, width - (24 if vertical else 16), 4)
            thumb = max(28, round(track.width * width / size[0]))
            travel = track.width - thumb
            x = track.left + round(self.pan[0] / (size[0] - width) * travel)
            pygame.draw.rect(self.window, PANEL_LIGHT, track, border_radius=2)
            pygame.draw.rect(self.window, MUTED, (x, track.y, thumb, track.height), border_radius=2)

    def close_worker(self) -> None:
        self.ready_move = None
        self.secondary_ready_move = None
        if self.worker is not None:
            self.worker.close()
            self.worker = None
        if self.secondary_worker is not None:
            self.secondary_worker.close()
            self.secondary_worker = None

    def start_game(self) -> None:
        try:
            strategy = STRATEGY_REGISTRY[self.config.strategy_name]
            secondary_strategy = (
                STRATEGY_REGISTRY[self.config.secondary_strategy_name]
                if self.config.mode is GameMode.AI_VS_AI
                else None
            )
        except Exception as exc:
            self.setup_error = f"Cannot start strategy: {type(exc).__name__}: {exc}"
            return
        self.close_worker()
        self.engine = GameEngine(self.config, rng=random.Random())
        self.strategy = strategy
        self.secondary_strategy = secondary_strategy
        self.last_ai_move_ms = pygame.time.get_ticks()
        self.screen = Screen.GAME
        self.focused = None
        self.setup_error = ""

    def restart_game(self) -> None:
        self.start_game()

    def return_to_setup(self) -> None:
        self.close_worker()
        self.engine = None
        self.strategy = None
        self.secondary_strategy = None
        self.screen = Screen.SETUP
        self.focused = None

    def run(self) -> None:
        try:
            while self.running:
                for event in pygame.event.get():
                    self.handle_event(event)
                self.update()
                self.draw()
                pygame.display.flip()
                self.clock.tick(FPS)
        finally:
            self.close_worker()
            pygame.quit()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.close_worker()
            self.running = False
            return
        if event.type == pygame.VIDEORESIZE:
            size = (max(MIN_WINDOW_SIZE[0], event.w), max(MIN_WINDOW_SIZE[1], event.h))
            self.window = pygame.display.set_mode(size, pygame.RESIZABLE)
            self._resize_canvas()
            return
        if event.type == pygame.KEYDOWN and getattr(event, "mod", 0) & pygame.KMOD_CTRL:
            if event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_0):
                delta = -0.25 if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS) else 0.25
                self.ui_zoom = 1.0 if event.key == pygame.K_0 else max(1.0, min(2.0, self.ui_zoom + delta))
                self._resize_canvas()
                self.draw()
                self._reveal_focus()
                pygame.display.set_caption(f"Turn-Based Snake · {self.ui_zoom:.0%} · Ctrl +/- zoom · Ctrl+0 reset · Ctrl+arrows scroll")
                return
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                axis = 0 if event.key in (pygame.K_LEFT, pygame.K_RIGHT) else 1
                self.pan[axis] += -80 if event.key in (pygame.K_LEFT, pygame.K_UP) else 80
                self._clamp_pan()
                return
        if event.type == pygame.MOUSEWHEEL:
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                self.pan[0] -= event.y * 60
            else:
                self.pan[1] -= event.y * 60
                self.pan[0] -= event.x * 60
            self._clamp_pan()
            return
        if event.type == pygame.MOUSEBUTTONDOWN:
            event = pygame.event.Event(event.type, {**event.dict, "pos": self._canvas_point(event.pos)})
        # Refresh hit targets for the current state, including transitions within
        # one event batch. Modal controls exclusively own pointer and Tab input.
        self.draw()
        if self.focused and self.focused not in self._buttons:
            base, _, suffix = self.focused.rpartition("_")
            alternate = base + ("_minus" if suffix == "plus" else "_plus")
            self.focused = alternate if alternate in self._buttons else next(iter(self._buttons), None)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F1 and (self.setup_error or (self.engine and self.engine.error_message)):
                self.details_open = not self.details_open
                self.detail_scroll = 0
                self.focused = None
                return
            if self.details_open:
                if event.key == pygame.K_ESCAPE:
                    self.details_open = False
                    self.focused = None
                elif event.key in (pygame.K_PAGEDOWN, pygame.K_DOWN):
                    self.detail_scroll = min(self.detail_max_scroll, self.detail_scroll + 3)
                elif event.key in (pygame.K_PAGEUP, pygame.K_UP):
                    self.detail_scroll = max(0, self.detail_scroll - 3)
                elif event.key == pygame.K_HOME:
                    self.detail_scroll = 0
                elif event.key == pygame.K_END:
                    self.detail_scroll = self.detail_max_scroll
                return
            keys = list(self._buttons)
            if event.key == pygame.K_TAB and keys:
                reverse = bool(getattr(event, "mod", 0) & pygame.KMOD_SHIFT)
                index = keys.index(self.focused) if self.focused in keys else (0 if reverse else -1)
                self.focused = keys[(index + (-1 if reverse else 1)) % len(keys)]
                self._reveal_focus()
                return
            if self.screen is Screen.SETUP and self._adjust_setting(event):
                return
            if event.key in (pygame.K_RETURN, pygame.K_SPACE) and self.focused in self._buttons:
                event = pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN, button=1,
                    pos=self._buttons[self.focused].center,
                )
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.details_open:
                if self._hit("details_close", event.pos):
                    self.details_open = False
                return
            self.focused = next((key for key, rect in self._buttons.items() if rect.collidepoint(event.pos)), None)
        if self.screen is Screen.SETUP:
            self._handle_setup_event(event)
        else:
            self._handle_game_event(event)

    def _adjust_setting(self, event: pygame.event.Event) -> bool:
        key = (self.focused or "").rsplit("_", 1)[0]
        if key not in SETTINGS:
            return False
        field, minimum, maximum, step = SETTINGS[key]
        value = getattr(self.config, field)
        if event.key == pygame.K_HOME:
            value = minimum
        elif event.key == pygame.K_END:
            value = maximum
        elif event.key in (pygame.K_LEFT, pygame.K_DOWN, pygame.K_RIGHT, pygame.K_UP,
                           pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            sign = -1 if event.key in (pygame.K_LEFT, pygame.K_DOWN, pygame.K_PAGEDOWN) else 1
            multiplier = 10 if event.key in (pygame.K_PAGEUP, pygame.K_PAGEDOWN) else 1
            value += sign * step * multiplier
        else:
            return False
        self.config = replace(self.config, **{field: max(minimum, min(maximum, value))})
        # Keep focus on an enabled control when reaching a boundary.
        self.focused = f"{key}_plus" if value <= minimum else f"{key}_minus" if value >= maximum else self.focused
        return True

    def _handle_setup_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            self.start_game()
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        pos = event.pos
        if self._hit("mode", pos):
            modes = list(GameMode)
            index = (modes.index(self.config.mode) + 1) % len(modes)
            self.config = replace(self.config, mode=modes[index])
        elif self._hit("rows_minus", pos):
            self.config = replace(self.config, rows=max(10, self.config.rows - 1))
        elif self._hit("rows_plus", pos):
            self.config = replace(self.config, rows=min(40, self.config.rows + 1))
        elif self._hit("cols_minus", pos):
            self.config = replace(self.config, columns=max(10, self.config.columns - 1))
        elif self._hit("cols_plus", pos):
            self.config = replace(self.config, columns=min(40, self.config.columns + 1))
        elif self._hit("apples_minus", pos):
            self.config = replace(self.config, apple_count=max(1, self.config.apple_count - 1))
        elif self._hit("apples_plus", pos):
            self.config = replace(self.config, apple_count=min(20, self.config.apple_count + 1))
        elif self._hit("moves_minus", pos):
            self.config = replace(self.config, move_limit=max(10, self.config.move_limit - 10))
        elif self._hit("moves_plus", pos):
            self.config = replace(self.config, move_limit=min(2000, self.config.move_limit + 10))
        elif self._hit("speed_minus", pos):
            self.config = replace(self.config, ai_speed=max(1, self.config.ai_speed - 1))
        elif self._hit("speed_plus", pos):
            self.config = replace(self.config, ai_speed=min(10, self.config.ai_speed + 1))
        elif self._hit("strategy", pos):
            self._cycle_strategy("strategy_name")
        elif self._hit("secondary_strategy", pos):
            self._cycle_strategy("secondary_strategy_name")
        elif self._hit("start", pos):
            self.start_game()

    def _cycle_strategy(self, field: str) -> None:
        names = list(STRATEGY_REGISTRY)
        if not names:
            return
        current = getattr(self.config, field)
        index = (names.index(current) + 1) % len(names) if current in names else 0
        self.config = replace(self.config, **{field: names[index]})
        self.setup_error = ""

    def _handle_game_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.return_to_setup()
                return
            if event.key == pygame.K_r:
                self.restart_game()
                return
            if event.key in (pygame.K_SPACE, pygame.K_p) and self.engine:
                self.engine.toggle_pause()
                self.last_ai_move_ms = pygame.time.get_ticks()
                return
            if (
                self.engine
                and self.engine.config.mode is GameMode.VERSUS
                and self.engine.status is GameStatus.RUNNING
                and self.engine.active_snake_id == HUMAN_ID
            ):
                direction = {
                    pygame.K_UP: Direction.UP,
                    pygame.K_w: Direction.UP,
                    pygame.K_DOWN: Direction.DOWN,
                    pygame.K_s: Direction.DOWN,
                    pygame.K_LEFT: Direction.LEFT,
                    pygame.K_a: Direction.LEFT,
                    pygame.K_RIGHT: Direction.RIGHT,
                    pygame.K_d: Direction.RIGHT,
                }.get(event.key)
                if direction is not None:
                    outcome = self.engine.step(HUMAN_ID, direction)
                    if outcome.accepted:
                        self.last_ai_move_ms = pygame.time.get_ticks()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._hit("pause", event.pos) and self.engine:
                self.engine.toggle_pause()
                self.last_ai_move_ms = pygame.time.get_ticks()
            elif self._hit("restart", event.pos):
                self.restart_game()
            elif self._hit("setup", event.pos):
                self.return_to_setup()

    def update(self) -> None:
        if not self.engine:
            return
        if self.engine.status is GameStatus.FINISHED:
            self.close_worker()
            self.screen = Screen.RESULTS
            return
        snake_id = self.engine.active_snake_id
        worker, ready_move = self._worker_state(snake_id)
        if worker is not None and (worker.pending or ready_move is not None):
            self._perform_ai_move(snake_id)
            return
        if self.engine.status is not GameStatus.RUNNING:
            return
        if snake_id == HUMAN_ID and self.config.mode is not GameMode.AI_VS_AI:
            return

        now = pygame.time.get_ticks()
        interval = 1000 / self.config.ai_speed
        if now - self.last_ai_move_ms < interval:
            return
        self.last_ai_move_ms = now
        self._perform_ai_move(snake_id)
        if self.engine.status is GameStatus.FINISHED:
            self.screen = Screen.RESULTS

    def _worker_state(self, snake_id: str):
        secondary = self.config.mode is GameMode.AI_VS_AI and snake_id == AI_ID
        if secondary:
            return self.secondary_worker, self.secondary_ready_move
        return self.worker, self.ready_move

    def _set_worker(self, snake_id: str, worker: StrategyWorker | None) -> None:
        if self.config.mode is GameMode.AI_VS_AI and snake_id == AI_ID:
            self.secondary_worker = worker
        else:
            self.worker = worker

    def _set_ready_move(self, snake_id: str, result) -> None:
        if self.config.mode is GameMode.AI_VS_AI and snake_id == AI_ID:
            self.secondary_ready_move = result
        else:
            self.ready_move = result

    def _strategy_for(self, snake_id: str):
        if self.config.mode is GameMode.AI_VS_AI and snake_id == AI_ID:
            return self.secondary_strategy
        return self.strategy

    def _perform_ai_move(self, snake_id: str | None = None) -> None:
        assert self.engine is not None
        snake_id = snake_id or self.engine.active_snake_id
        strategy = self._strategy_for(snake_id)
        assert strategy is not None
        worker, ready_move = self._worker_state(snake_id)
        try:
            if worker is None:
                worker = StrategyWorker(strategy, construct=isinstance(strategy, type))
                self._set_worker(snake_id, worker)
            if not worker.pending and ready_move is None:
                worker.submit(self.engine.snapshot(), snake_id, self.engine.rng.getstate())
                return
            result = ready_move if ready_move is not None else worker.poll()
            if result is None:
                return
            direction, rng_state, error = result
            if error:
                raise RuntimeError(error)
            if self.engine.status is GameStatus.PAUSED:
                self._set_ready_move(snake_id, result)
                return
            self._set_ready_move(snake_id, None)
            self.engine.rng.setstate(rng_state)
        except Exception as exc:
            if self.engine.status is GameStatus.PAUSED:
                self.engine.resume()
            self.engine.fail_strategy(snake_id, f"{type(exc).__name__}: {exc}")
            self.close_worker()
            return
        self.last_ai_move_ms = pygame.time.get_ticks()
        if not isinstance(direction, Direction):
            self.engine.fail_strategy(snake_id, "Strategy returned a value that is not a Direction.")
            return
        snake = self.engine.snapshot().snake(snake_id)
        if len(snake.body) > 1 and direction is snake.direction.opposite:
            self.engine.fail_strategy(snake_id, "Strategy attempted a direct reversal.")
            return
        self.engine.step(snake_id, direction)

    def draw(self) -> None:
        self.surface.fill(BACKGROUND)
        self._buttons.clear()
        if self.screen is Screen.SETUP:
            self._draw_setup()
        else:
            self._draw_game()
        if self.details_open:
            message = self.setup_error or (self.engine.error_message if self.engine else "")
            self._overlay("ERROR DETAILS", message, [("BACK (ESC)", "details_close", PANEL_LIGHT)])
        self._present()

    def _draw_setup(self) -> None:
        width, height = self.surface.get_size()
        compact = height < 760
        center = width // 2
        title_y = 36 if compact else 62
        self._text("TURN-BASED SNAKE", (center, title_y), self.font_large if width < 800 else self.font_title, CYAN, center=True)
        self._text(
            "Configure the arena, then let your movement strategy compete.",
            (center, title_y + 40),
            self.font_small if width < 800 else self.font,
            MUTED,
            center=True,
        )
        top = 100 if compact else 140
        ai_vs_ai = self.config.mode is GameMode.AI_VS_AI
        pitch = (47 if compact else 57) if ai_vs_ai else (52 if compact else 65)
        panel = pygame.Rect(center - 305, top, 610, 448 if compact else 565)
        pygame.draw.rect(self.surface, PANEL, panel, border_radius=18)
        pygame.draw.rect(self.surface, PANEL_LIGHT, panel, 2, border_radius=18)

        first = top + (4 if compact and ai_vs_ai else 12 if compact else 20 if ai_vs_ai else 30)
        self._setting_row("Game mode", self.config.mode.value, first, "mode", cycle=True)
        self._setting_row("Rows", str(self.config.rows), first + pitch, "rows")
        self._setting_row("Columns", str(self.config.columns), first + pitch * 2, "cols")
        self._setting_row("Apples", str(self.config.apple_count), first + pitch * 3, "apples")
        self._setting_row("Move limit", str(self.config.move_limit), first + pitch * 4, "moves")
        self._setting_row("AI speed", f"{self.config.ai_speed} moves/s", first + pitch * 5, "speed")
        strategy_label = "AI 1 strategy" if ai_vs_ai else "Movement strategy"
        self._setting_row(
            strategy_label, self.config.strategy_name, first + pitch * 6, "strategy", cycle=True
        )
        button_row = 7
        if ai_vs_ai:
            self._setting_row(
                "AI 2 strategy",
                self.config.secondary_strategy_name,
                first + pitch * 7,
                "secondary_strategy",
                cycle=True,
            )
            button_row = 8
        self._button(
            "START MATCH",
            pygame.Rect(center - 175, first + pitch * button_row + 10, 350, 48),
            "start",
            GREEN,
        )
        line_height = self.font_small.get_linesize()
        second_line_y = height - line_height // 2 - 8
        first_line_y = second_line_y - line_height - 4
        self._text(
            "Tab: focus · Enter/Space: select · Arrows: adjust",
            (center, first_line_y),
            self.font_small,
            MUTED,
            center=True,
        )
        self._text(
            "PgUp/PgDn: steps · Home/End: limits · Ctrl +/-: zoom",
            (center, second_line_y),
            self.font_small,
            MUTED,
            center=True,
        )
        if self.setup_error:
            error_y = first + pitch * button_row
            self._text(
                self._fit_text(self.setup_error, self.font_small, 430) + " [F1: details]",
                (center, error_y),
                self.font_small,
                RED,
                center=True,
            )

    def _setting_row(
        self, label: str, value: str, y: int, key: str, cycle: bool = False
    ) -> None:
        offset = self.surface.get_width() // 2 - 560
        self._text(label, (300 + offset, y + (44 - self.font.get_height()) // 2), self.font, TEXT)
        if cycle:
            self._button(value, pygame.Rect(530 + offset, y, 285, 44), key, BLUE,
                         enabled=key not in ("strategy", "secondary_strategy") or bool(STRATEGY_REGISTRY))
            return
        field, minimum, maximum, _ = SETTINGS[key]
        current = getattr(self.config, field)
        self._button("−", pygame.Rect(580 + offset, y, 48, 44), f"{key}_minus", PANEL_LIGHT, enabled=current > minimum)
        self._text(value, (692 + offset, y + 21), self.font, CYAN, center=True)
        self._button("+", pygame.Rect(765 + offset, y, 48, 44), f"{key}_plus", PANEL_LIGHT, enabled=current < maximum)

    def _draw_game(self) -> None:
        if not self.engine:
            return
        width, height = self.surface.get_size()
        stacked = width < 900 or height < 700
        board_area = pygame.Rect(20, 90, width - 40 if stacked else width - 325, height - 330 if stacked else height - 110)
        cell = min(
            board_area.width // self.config.columns,
            board_area.height // self.config.rows,
        )
        width = cell * self.config.columns
        height = cell * self.config.rows
        board = pygame.Rect(
            board_area.x + (board_area.width - width) // 2,
            board_area.y + (board_area.height - height) // 2,
            width,
            height,
        )
        pygame.draw.rect(self.surface, (12, 22, 34), board)
        for x in range(self.config.columns + 1):
            px = board.x + x * cell
            pygame.draw.line(self.surface, GRID_LINE, (px, board.y), (px, board.bottom))
        for y in range(self.config.rows + 1):
            py = board.y + y * cell
            pygame.draw.line(self.surface, GRID_LINE, (board.x, py), (board.right, py))

        for apple in self.engine.apples:
            self._draw_apple(board, cell, apple)

        colors = {HUMAN_ID: BLUE, AI_ID: GREEN}
        for snake_id, snake in self.engine.snakes.items():
            self._draw_snake(board, cell, snake.body, snake.direction, colors[snake_id])

        self._draw_header()
        self._draw_sidebar()
        if self.engine.status is GameStatus.PAUSED:
            self._overlay(
                "PAUSED",
                "Elapsed time is stopped while the match is paused.",
                [("RESUME", "pause", YELLOW), ("SETUP", "setup", PANEL_LIGHT)],
            )
        elif self.screen is Screen.RESULTS:
            self._draw_result_overlay()

    def _draw_header(self) -> None:
        width = self.surface.get_width()
        self._text("TURN-BASED SNAKE", (20, 20), self.font_large, CYAN)
        self._text(self.config.mode.value, (20, 58) if width < 900 else (width - 285, 38), self.font_small if width < 900 else self.font, MUTED)

    def _draw_sidebar(self) -> None:
        assert self.engine is not None
        interactive = self.engine.status is GameStatus.RUNNING
        width, height = self.surface.get_size()
        if width < 900 or height < 700:
            panel = pygame.Rect(20, height - 220, width - 40, 200)
            pygame.draw.rect(self.surface, PANEL, panel, border_radius=16)
            column_width = (panel.width - 32) // 3
            for index, (label, value) in enumerate(self._stat_rows()):
                x = panel.x + 16 + index % 3 * column_width
                y = panel.y + 14 + index // 3 * 56
                self._text(label, (x, y), self.font_small, MUTED)
                value_font = (
                    self.font_small
                    if label == "STRATEGIES"
                    or (label == "SCORE" and self.config.mode is not GameMode.SINGLE)
                    else self.font
                )
                self._text(
                    self._fit_text(value, value_font, column_width - 12),
                    (x, y + 23),
                    value_font,
                    TEXT,
                )
            for index, (label, key, color) in enumerate((("PAUSE", "pause", YELLOW), ("RESTART", "restart", BLUE), ("SETUP", "setup", PANEL_LIGHT))):
                self._button(label, pygame.Rect(panel.x + 16 + index * column_width, panel.bottom - 60, column_width - 12, 44), key, color, enabled=interactive)
            return
        panel = pygame.Rect(width - 285, 90, 265, height - 110)
        pygame.draw.rect(self.surface, PANEL, panel, border_radius=16)
        x = panel.x + 25
        self._text("MATCH", (x, 118), self.font, CYAN)
        y = 162
        for label, value in self._stat_rows():
            self._text(label, (x, y), self.font_small, MUTED)
            value_font = (
                self.font_small
                if label == "STRATEGIES"
                or (label == "SCORE" and self.config.mode is not GameMode.SINGLE)
                else self.font
            )
            self._text(self._fit_text(value, value_font, 215), (x, y + 25), value_font, TEXT)
            y += min(66, (panel.height - 250) // 6)
        self._button(
            "RESUME" if self.engine.status is GameStatus.PAUSED else "PAUSE",
            pygame.Rect(x, panel.bottom - 170, 215, 44),
            "pause",
            YELLOW,
            enabled=interactive,
        )
        self._button("RESTART", pygame.Rect(x, panel.bottom - 116, 215, 44), "restart", BLUE, enabled=interactive)
        self._button("SETUP", pygame.Rect(x, panel.bottom - 62, 215, 44), "setup", PANEL_LIGHT, enabled=interactive)

    def _stat_rows(self) -> list[tuple[str, str]]:
        assert self.engine is not None
        if self.config.mode is GameMode.SINGLE:
            score = f"AI: {self.engine.snakes[AI_ID].score}"
        elif self.config.mode is GameMode.AI_VS_AI:
            score = (
                f"AI 1: {self.engine.snakes[HUMAN_ID].score}  |  "
                f"AI 2: {self.engine.snakes[AI_ID].score}"
            )
        else:
            score = (
                f"Human: {self.engine.snakes[HUMAN_ID].score}  |  "
                f"AI: {self.engine.snakes[AI_ID].score}"
            )
        active_id = self.engine.active_snake_id
        active = self.engine.display_name(active_id)
        active_worker, _ = self._worker_state(active_id)
        if active_worker is not None and active_worker.pending:
            active += " thinking..."
        if self.engine.status is GameStatus.FINISHED:
            active = "Finished"
        elif self.engine.status is GameStatus.PAUSED:
            active += " (paused)"
        strategy = self.config.strategy_name
        strategy_label = "STRATEGY"
        if self.config.mode is GameMode.AI_VS_AI:
            strategy = f"{self.config.strategy_name} / {self.config.secondary_strategy_name}"
            strategy_label = "STRATEGIES"
        return [
            ("SCORE", score),
            ("ROUND", f"{self.engine.rounds_completed} / {self.config.move_limit}"),
            ("REMAINING", str(self.engine.rounds_remaining)),
            ("ELAPSED", self._format_time(self.engine.elapsed_time)),
            ("ACTIVE TURN", active),
            (strategy_label, strategy),
        ]

    def _draw_result_overlay(self) -> None:
        assert self.engine is not None
        if self.config.mode is GameMode.SINGLE:
            title = "RUN COMPLETE"
            subtitle = f"Final score: {self.engine.snakes[AI_ID].score}"
        elif self.engine.is_draw:
            title = "DRAW"
            subtitle = "Both snakes finished with the same score."
        else:
            title = self.engine.display_name(self.engine.winner_id).upper() + " WINS"
            if self.engine.loser_id is not None:
                loser = self.engine.display_name(self.engine.loser_id)
                subtitle = f"{loser} was eliminated."
            else:
                subtitle = "Highest final score wins."
        if self.engine.error_message:
            subtitle = self.engine.error_message
        self._overlay(
            title,
            f"{self.engine.finish_reason}  {subtitle}",
            [("RESTART", "restart", BLUE), ("SETUP", "setup", PANEL_LIGHT)],
        )

    def _overlay(
        self,
        title: str,
        subtitle: str,
        actions: list[tuple[str, str, tuple[int, int, int]]],
    ) -> None:
        self._buttons.clear()
        width, height = self.surface.get_size()
        cx, cy = width // 2, height // 2
        shade = pygame.Surface((width, height), pygame.SRCALPHA)
        shade.fill((3, 7, 15, 195))
        self.surface.blit(shade, (0, 0))
        card = pygame.Rect(0, 0, min(650, width - 32), 285)
        card.center = (cx, cy)
        pygame.draw.rect(self.surface, PANEL, card, border_radius=18)
        pygame.draw.rect(self.surface, CYAN, card, 2, border_radius=18)
        self._text(title, (cx, cy - 86), self.font_title if width >= 800 else self.font_large, CYAN, center=True)
        lines = self._wrap_text(subtitle, self.font_small, card.width - 64)
        self.detail_max_scroll = max(0, len(lines) - 3)
        offset = min(self.detail_scroll, self.detail_max_scroll) if self.details_open else 0
        visible = lines[offset:offset + 3]
        if len(lines) > 3 and not self.details_open:
            visible[-1] = self._fit_text(visible[-1] + "...", self.font_small, card.width - 64)
        first_y = cy - 22 - (len(visible) - 1) * 12
        for index, line in enumerate(visible):
            self._text(line, (cx, first_y + index * 24), self.font_small, TEXT, center=True)
        button_width = 190
        gap = 18
        total_width = len(actions) * button_width + (len(actions) - 1) * gap
        x = cx - total_width // 2
        for label, key, color in actions:
            self._button(label, pygame.Rect(x, cy + 29, button_width, 48), key, color)
            x += button_width + gap
        hint = "Tab: focus · Enter: select · R: restart · Esc: setup"
        if self.engine and self.engine.status is GameStatus.PAUSED:
            hint = "P: resume · Tab: focus · Enter: select · Esc: setup"
        if self.engine and self.engine.error_message:
            hint = "F1: full error · R: restart · Esc: setup"
        if self.details_open:
            hint = f"PgUp/PgDn: scroll · Esc: back · Lines {offset + 1}–{offset + len(visible)} / {len(lines)}"
        self._text(hint, (cx, cy + 108), self.font_small, MUTED, center=True)

    def _draw_cell(
        self,
        board: pygame.Rect,
        cell_size: int,
        position: tuple[int, int],
        color: tuple[int, int, int],
        inset: int,
    ) -> None:
        x, y = position
        rect = pygame.Rect(
            board.x + x * cell_size + inset,
            board.y + y * cell_size + inset,
            cell_size - inset * 2,
            cell_size - inset * 2,
        )
        pygame.draw.rect(self.surface, color, rect, border_radius=max(1, cell_size // 5))

    def _draw_snake(
        self,
        board: pygame.Rect,
        cell_size: int,
        body: list[tuple[int, int]],
        direction: Direction,
        color: tuple[int, int, int],
    ) -> None:
        """Draw one continuous snake, then add a directional face to its head."""
        centers = [self._cell_center(board, cell_size, part) for part in body]
        connector_width = max(4, int(cell_size * 0.72))
        for first, second in zip(centers, centers[1:]):
            pygame.draw.line(self.surface, color, first, second, connector_width)

        inset = max(1, cell_size // 8)
        for part in reversed(body):
            self._draw_cell(board, cell_size, part, color, inset)
        self._draw_head_details(centers[0], cell_size, direction)

    def _draw_head_details(
        self,
        center: tuple[int, int],
        cell_size: int,
        direction: Direction,
    ) -> None:
        dx, dy = direction.vector
        perpendicular = (-dy, dx)
        forward = cell_size * 0.18
        sideways = cell_size * 0.20
        eye_radius = max(2, cell_size // 9)
        pupil_radius = max(1, eye_radius // 2)

        for side in (-1, 1):
            eye = (
                round(center[0] + dx * forward + perpendicular[0] * sideways * side),
                round(center[1] + dy * forward + perpendicular[1] * sideways * side),
            )
            pygame.draw.circle(self.surface, (245, 250, 255), eye, eye_radius)
            pupil = (
                round(eye[0] + dx * eye_radius * 0.35),
                round(eye[1] + dy * eye_radius * 0.35),
            )
            pygame.draw.circle(self.surface, (12, 18, 28), pupil, pupil_radius)

        tongue_start = (
            round(center[0] + dx * cell_size * 0.35),
            round(center[1] + dy * cell_size * 0.35),
        )
        tongue_end = (
            round(center[0] + dx * cell_size * 0.68),
            round(center[1] + dy * cell_size * 0.68),
        )
        tongue_width = max(2, cell_size // 12)
        pygame.draw.line(self.surface, RED, tongue_start, tongue_end, tongue_width)
        fork = max(2, cell_size // 8)
        fork_back = (
            tongue_end[0] - round(dx * fork),
            tongue_end[1] - round(dy * fork),
        )
        for side in (-1, 1):
            fork_end = (
                fork_back[0] + perpendicular[0] * fork * side,
                fork_back[1] + perpendicular[1] * fork * side,
            )
            pygame.draw.line(self.surface, RED, tongue_end, fork_end, tongue_width)

    def _draw_apple(
        self,
        board: pygame.Rect,
        cell_size: int,
        position: tuple[int, int],
    ) -> None:
        center = self._cell_center(board, cell_size, position)
        radius = max(3, int(cell_size * 0.31))
        pygame.draw.circle(self.surface, RED, center, radius)
        pygame.draw.circle(
            self.surface,
            (255, 145, 156),
            (center[0] - radius // 3, center[1] - radius // 3),
            max(1, radius // 4),
        )
        stem_top = (center[0] + 1, center[1] - radius - max(1, radius // 3))
        pygame.draw.line(
            self.surface,
            (125, 82, 50),
            (center[0], center[1] - radius + 1),
            stem_top,
            max(1, cell_size // 12),
        )
        leaf = pygame.Rect(
            center[0] + 1,
            center[1] - radius - max(2, radius // 3),
            max(3, radius),
            max(2, radius // 2),
        )
        pygame.draw.ellipse(self.surface, GREEN, leaf)

    @staticmethod
    def _cell_center(
        board: pygame.Rect, cell_size: int, position: tuple[int, int]
    ) -> tuple[int, int]:
        return (
            board.x + position[0] * cell_size + cell_size // 2,
            board.y + position[1] * cell_size + cell_size // 2,
        )

    def _button(
        self,
        label: str,
        rect: pygame.Rect,
        key: str,
        color: tuple[int, int, int],
        enabled: bool = True,
    ) -> None:
        if enabled:
            self._buttons[key] = rect
        mouse_over = enabled and rect.collidepoint(self._canvas_point(pygame.mouse.get_pos()))
        fill = tuple(min(255, component + 18) for component in color) if mouse_over else color
        if not enabled:
            fill = PANEL
        pygame.draw.rect(self.surface, fill, rect, border_radius=9)
        if enabled and self.focused == key:
            pygame.draw.rect(self.surface, TEXT, rect.inflate(8, 8), 2, border_radius=12)
        foreground = BACKGROUND if color in (BLUE, GREEN, YELLOW, CYAN) and enabled else TEXT if enabled else MUTED
        self._text(self._fit_text(label, self.font_small, rect.width - 20), rect.center, self.font_small, foreground, center=True)

    @staticmethod
    def _wrap_text(value: str, font: pygame.font.Font, width: int) -> list[str]:
        """Wrap at words, splitting long identifiers when necessary."""
        lines: list[str] = []
        line = ""
        for word in value.split():
            if line and font.size(line + " " + word)[0] > width:
                lines.append(line)
                line = ""
            while font.size(word)[0] > width:
                end = 1
                while end < len(word) and font.size(word[:end + 1])[0] <= width:
                    end += 1
                lines.append(word[:end])
                word = word[end:]
            line = (line + " " + word).strip()
        if line:
            lines.append(line)
        return lines or [""]

    @staticmethod
    def _fit_text(value: str, font: pygame.font.Font, width: int) -> str:
        if font.size(value)[0] <= width:
            return value
        while value and font.size(value + "...")[0] > width:
            value = value[:-1]
        return value + "..."

    def _text(
        self,
        value: str,
        position: tuple[int, int],
        font: pygame.font.Font,
        color: tuple[int, int, int],
        center: bool = False,
    ) -> None:
        rendered = font.render(value, True, color)
        rect = rendered.get_rect(center=position) if center else rendered.get_rect(topleft=position)
        self.surface.blit(rendered, rect)

    def _hit(self, key: str, position: tuple[int, int]) -> bool:
        return key in self._buttons and self._buttons[key].collidepoint(position)

    @staticmethod
    def _format_time(seconds: float) -> str:
        total = int(seconds)
        return f"{total // 60:02d}:{total % 60:02d}"


def main() -> None:
    SnakeApp().run()


if __name__ == "__main__":
    main()
