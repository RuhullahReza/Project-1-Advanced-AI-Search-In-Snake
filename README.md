# Turn-Based Snake

A configurable Snake environment for experimenting with AI movement strategies.
It combines a responsive Pygame interface, a deterministic game engine, an
optional text interface, and an isolated worker process for safe AI execution.

The project supports three match types:

- **Single Player (AI):** watch one AI-controlled snake play automatically.
- **Human vs AI:** alternate turns against the selected AI strategy.
- **AI vs AI:** compare two independently selected strategies in one match.

## Features

- Adjustable grid, apple count, move limit, and AI speed
- Built-in **Greedy** and **Safe Random** strategies
- Independent AI 1 and AI 2 strategy selection in AI vs AI mode
- Simple registry for adding custom movement strategies
- Responsive layout for large and compact windows
- Interface zoom from 100% to 200%
- Keyboard navigation and a line-oriented text mode
- Pause, restart, results, and detailed error dialogs
- Five-second strategy timeout to keep the interface responsive
- Automated tests for rules, strategies, workers, and UI state changes

## Requirements

- Python 3.11 or newer
- Pygame 2.5 or newer

## Quick start

From PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m snake_game
```

If PowerShell blocks activation, the virtual environment can be used directly:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m snake_game
```

## Match setup

| Setting | Default | Range | Description |
| --- | ---: | ---: | --- |
| Game mode | Single Player | — | Single Player, Human vs AI, or AI vs AI |
| Rows | 20 | 10–40 | Arena height |
| Columns | 20 | 10–40 | Arena width |
| Apples | 5 | 1–20 | Apples placed when the match starts |
| Move limit | 200 | 10–2000 | Maximum number of completed rounds |
| AI speed | 4 moves/s | 1–10 | Automated move frequency |
| Strategy | Greedy | — | Registered AI movement method |

Apples do not respawn after they are eaten. Eating an apple adds one point. A
wall, self, or opponent collision subtracts one point and ends the match. In a
multiplayer match, the snake that collides loses immediately. When a match ends
without a collision, the highest score wins; equal scores produce a draw.

In AI vs AI mode, AI 1 controls the blue snake and moves first. AI 2 controls
the green snake. One move from each AI counts as a completed round, and both
strategy instances retain their own state throughout the match.

## Controls

### Setup screen

| Input | Action |
| --- | --- |
| `Tab` / `Shift+Tab` | Move between controls |
| `Enter` / `Space` | Activate the focused control |
| Arrow keys | Adjust a numeric setting by one step |
| `Page Up` / `Page Down` | Adjust a numeric setting by ten steps |
| `Home` / `End` | Jump to the minimum or maximum value |
| `Enter` with nothing focused | Start the match |

### During a match

| Input | Action |
| --- | --- |
| Arrow keys / `WASD` | Commit the human move in Human vs AI mode |
| `Space` / `P` | Pause or resume |
| `R` | Restart with the current configuration |
| `Esc` | Return to setup |
| `F1` | Open full details when an error is shown |

### Window and accessibility

| Input | Action |
| --- | --- |
| `Ctrl` + `+` / `-` | Change interface zoom in 25% steps |
| `Ctrl` + `0` | Reset zoom to 100% |
| Mouse wheel | Scroll enlarged content vertically |
| `Shift` + mouse wheel | Scroll enlarged content horizontally |
| `Ctrl` + arrow keys | Pan the enlarged interface |

The window can be resized down to 640×600. At compact sizes, match information
moves below the board. Keyboard focus is automatically brought into view when
the enlarged interface needs scrolling.

## Text interface

Text mode provides a line-oriented alternative to the graphical canvas:

```powershell
python -m snake_game --text
python -m snake_game --text --mode versus
python -m snake_game --text --mode ai-vs-ai --strategy Greedy --strategy-2 "Safe Random"
python -m snake_game --text --help
```

Available commands:

| Command | Purpose |
| --- | --- |
| `status` | Show scores, positions, round, and active turn |
| `board` | Show all snake segments and apple coordinates |
| `up`, `down`, `left`, `right` | Submit a human move |
| `next` | Run the current AI turn, including either side in AI vs AI mode |
| `restart` | Restart with the same configuration |
| `help` | Show the command list |
| `quit` | End the session |

Text mode waits for each command and does not use timed input. Native Windows
screen-reader interoperability has not been verified, but all game state and
strategy errors are available as terminal text.

## Add an AI strategy

Add a class to `snake_game/strategies.py`, inherit from `MoveStrategy`, and
register it with a unique display name:

```python
from snake_game.models import Direction
from snake_game.strategies import MoveStrategy, register_strategy


@register_strategy("My Strategy")
class MyStrategy(MoveStrategy):
    def choose_move(self, snapshot, snake_id, rng) -> Direction:
        legal_moves = snapshot.legal_moves_for(snake_id)
        if legal_moves:
            return legal_moves[0]
        return snapshot.snake(snake_id).direction
```

The registered name appears automatically in the setup screen and text-mode
strategy choices.

### Strategy contract

`choose_move` receives:

- `snapshot`: an immutable view of the arena, snakes, scores, apples, rounds,
  active snake, and legal moves
- `snake_id`: the snake that must move
- `rng`: the supplied random-number generator for reproducible decisions

The body segments of both the controlled snake and its opponent are treated as
obstacles when legal moves are calculated. Following standard Snake rules, the
controlled snake may move into its current tail cell when it is not growing,
because the tail moves away during the same turn. All opponent body segments
remain obstacles. The legal moves stored in a snapshot apply only to that
snapshot's current state and must be recalculated after every move.

The method must return a `Direction`. Direct reversals, invalid return values,
exceptions, and decisions that exceed five seconds end the run with a visible
error instead of crashing the application.

Keep strategy classes at module scope. AI strategies are constructed and run in
separate processes so Windows must be able to import each class. Strategy
instances remain alive between decisions, allowing each AI to keep internal
state.

## Project structure

```text
snake_game/
├── __main__.py     Application entry point
├── app.py          Pygame interface and interaction handling
├── engine.py       Turn order, movement, scoring, and collisions
├── models.py       Configuration, enums, and immutable snapshots
├── strategies.py   Strategy interface, registry, and built-in strategies
├── text_app.py     Line-oriented interface
└── worker.py       Isolated AI strategy process and timeout handling

tests/
├── test_app_smoke.py
├── test_engine.py
├── test_strategies.py
├── test_text_app.py
└── test_worker.py
```

The engine does not depend on Pygame. Both interfaces use the same engine and
models, while the worker owns strategy execution. This separation makes game
rules testable without opening a window.

## Run the tests

```powershell
python -m pytest
```

For a headless environment, set Pygame's dummy video driver first:

```powershell
$env:SDL_VIDEODRIVER = "dummy"
python -m pytest
```

The test suite covers movement and collisions, scoring, turn alternation,
strategy registration, timeout behavior, text-mode commands, responsive layout,
keyboard navigation, zoom, and modal interactions.
