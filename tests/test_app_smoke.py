from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from snake_game.app import Screen, SnakeApp
from snake_game.models import GameMode, GameStatus


@pytest.mark.parametrize("zoom_steps", [1, 2, 4])
def test_zoom_focus_and_pointer_mapping(zoom_steps):
    app = SnakeApp()
    try:
        app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=640, h=600))
        for _ in range(zoom_steps):
            app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_EQUALS, mod=pygame.KMOD_CTRL))
        assert app.ui_zoom == 1 + zoom_steps * 0.25
        app.draw()
        # Real Tab navigation must reach Start and bring its center into view.
        for _ in range(20):
            app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
            if app.focused == "start":
                break
        rect = app._buttons["start"]
        point = tuple(round(value * app.ui_zoom - pan) for value, pan in zip(rect.center, app.pan))
        assert app.window.get_rect().collidepoint(point)
        app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=point))
        assert app.screen is Screen.GAME
        engine = app.engine
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_0, mod=pygame.KMOD_CTRL))
        assert app.ui_zoom == 1
        assert app.pan == [0, 0]
        assert app.engine is engine
    finally:
        app.close_worker()
        pygame.quit()


def test_enter_at_numeric_boundary_does_not_start_match():
    from dataclasses import replace
    app = SnakeApp()
    try:
        app.config = replace(app.config, rows=39)
        app.focused = "rows_plus"
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        assert app.config.rows == 40
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        assert app.screen is Screen.SETUP
        assert app.config.rows == 39
    finally:
        pygame.quit()


def test_complete_error_details_can_be_scrolled_and_closed():
    app = SnakeApp()
    try:
        app.setup_error = "Diagnostic " * 100 + "FINAL DETAIL"
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1))
        app.draw()
        assert app.details_open
        assert set(app._buttons) == {"details_close"}
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_END))
        assert app.detail_scroll == app.detail_max_scroll > 0
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        assert not app.details_open
        assert app.screen is Screen.SETUP
    finally:
        pygame.quit()


@pytest.mark.parametrize("size", [(640, 600), (800, 700), (1120, 800), (1440, 900)])
def test_resize_preserves_match_and_controls(size) -> None:
    app = SnakeApp()
    try:
        app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=size[0], h=size[1]))
        app.draw()
        assert app.surface.get_size() == size
        assert all(app.surface.get_rect().contains(rect) for rect in app._buttons.values())
        app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=app._buttons["start"].center))
        original = app.engine
        app.draw()
        app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=app._buttons["pause"].center))
        assert app.engine.status is GameStatus.PAUSED
        app.handle_event(pygame.event.Event(pygame.VIDEORESIZE, w=size[0], h=size[1]))
        app.draw()
        assert app.engine is original
        assert set(app._buttons) == {"pause", "setup"}
        assert all(app.surface.get_rect().contains(rect) for rect in app._buttons.values())
    finally:
        pygame.quit()


def test_screen_transitions_pause_restart_and_setup() -> None:
    app = SnakeApp()
    try:
        assert app.screen is Screen.SETUP
        app.start_game()
        assert app.screen is Screen.GAME
        assert app.engine is not None
        original = app.engine
        app.engine.toggle_pause()
        assert app.engine.status is GameStatus.PAUSED
        app.restart_game()
        assert app.engine is not original
        assert app.engine.status is GameStatus.RUNNING
        app.return_to_setup()
        assert app.screen is Screen.SETUP
        assert app.engine is None
        app.draw()
    finally:
        pygame.quit()


def test_keyboard_setup_and_numeric_boundaries() -> None:
    app = SnakeApp()
    try:
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
        assert app.focused == "mode"
        before = app.config.mode
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        assert app.config.mode is not before
        assert app.screen is Screen.SETUP
        app.focused = "moves_plus"
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEUP))
        assert app.config.move_limit == 300
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_END))
        app.draw()
        assert app.config.move_limit == 2000
        assert "moves_plus" not in app._buttons
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_HOME))
        app.draw()
        assert app.config.move_limit == 10
        assert "moves_minus" not in app._buttons
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB, mod=pygame.KMOD_SHIFT))
        assert app.focused in app._buttons
    finally:
        pygame.quit()


def test_pause_modal_blocks_background_and_supports_keyboard() -> None:
    app = SnakeApp()
    try:
        app.start_game()
        original = app.engine
        app.engine.pause()
        app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(950, 670)))
        assert app.engine is original
        assert app.engine.status is GameStatus.PAUSED
        assert set(app._buttons) == {"pause", "setup"}
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
        app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        assert app.engine.status is GameStatus.RUNNING
    finally:
        pygame.quit()


def test_missing_strategy_is_recoverable(monkeypatch) -> None:
    from snake_game.strategies import STRATEGY_REGISTRY

    app = SnakeApp()
    try:
        monkeypatch.delitem(STRATEGY_REGISTRY, "Greedy")
        app.start_game()
        assert app.screen is Screen.SETUP
        assert app.engine is None
        assert "Greedy" in app.setup_error
        app.draw()
        monkeypatch.delitem(STRATEGY_REGISTRY, "Safe Random")
        app.draw()
        assert "strategy" not in app._buttons
    finally:
        pygame.quit()


def test_setup_apple_count_control_changes_configuration() -> None:
    app = SnakeApp()
    try:
        app.draw()
        before = app.config.apple_count
        app.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": app._buttons["apples_plus"].center},
            )
        )
        assert app.config.apple_count == before + 1
    finally:
        pygame.quit()


def test_ai_vs_ai_setup_exposes_two_strategies_and_automates_both_turns() -> None:
    from dataclasses import replace
    import time

    app = SnakeApp()
    try:
        app.draw()
        for expected in (GameMode.VERSUS, GameMode.AI_VS_AI, GameMode.SINGLE):
            app.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    {"button": 1, "pos": app._buttons["mode"].center},
                )
            )
            assert app.config.mode is expected

        app.config = replace(
            app.config,
            mode=GameMode.AI_VS_AI,
            rows=10,
            columns=10,
            ai_speed=10,
        )
        app.draw()
        assert "strategy" in app._buttons
        assert "secondary_strategy" in app._buttons
        primary = app.config.strategy_name
        secondary = app.config.secondary_strategy_name
        app.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"button": 1, "pos": app._buttons["secondary_strategy"].center},
            )
        )
        assert app.config.strategy_name == primary
        assert app.config.secondary_strategy_name != secondary

        app.start_game()
        deadline = time.monotonic() + 10
        while app.engine.rounds_completed == 0 and time.monotonic() < deadline:
            app.last_ai_move_ms = 0
            app.update()
            time.sleep(0.01)

        assert app.engine.rounds_completed == 1
        assert app.worker is not None
        assert app.secondary_worker is not None
        assert app._stat_rows()[0][1].startswith("AI 1")
    finally:
        app.close_worker()
        pygame.quit()
