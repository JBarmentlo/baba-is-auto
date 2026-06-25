"""FastMCP server exposing the pyBaba "Baba Is You" simulator.

A thin, in-process layer over the ``pyBaba`` pybind11 module. It owns a single
"current game" and lets an agent observe the board grid (not an image), submit
moves, check win/lose status, manage levels, and undo.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from threading import Lock

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
# server.py lives at <repo>/Extensions/BabaMCP/baba_mcp/server.py -> parents[3]
_DEFAULT_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = Path(os.environ.get("BABA_REPO_ROOT") or _DEFAULT_ROOT)
MAPS_DIR = Path(os.environ.get("BABA_MAPS_DIR") or (REPO_ROOT / "Resources" / "Maps"))
DEFAULT_MAP = "baba_is_you.txt"

# The pyBaba extension is built in place at the repo root (setup.py build_ext
# --inplace). Make it importable regardless of the launch directory.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pyBaba  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

# --------------------------------------------------------------------------- #
# Enum maps
# --------------------------------------------------------------------------- #
ACTIONS = {
    "up": pyBaba.Direction.UP,
    "down": pyBaba.Direction.DOWN,
    "left": pyBaba.Direction.LEFT,
    "right": pyBaba.Direction.RIGHT,
    "idle": pyBaba.Direction.NONE,
}
VALID_ACTIONS = sorted(ACTIONS)

STATUS = {
    pyBaba.PlayState.WON: "success",
    pyBaba.PlayState.LOST: "dead",
    pyBaba.PlayState.PLAYING: "in_progress",
    pyBaba.PlayState.INVALID: "invalid",
}
TERMINAL = (pyBaba.PlayState.WON, pyBaba.PlayState.LOST)

# --------------------------------------------------------------------------- #
# Current-game state (single global, guarded by a lock)
# --------------------------------------------------------------------------- #
_game: pyBaba.Game | None = None
_map_name: str | None = None
_history: list[str] = []  # action keys applied since the current map was loaded
_lock = Lock()

mcp = FastMCP("baba-is-you")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _resolve_map(name: str) -> Path:
    """Resolve a map name (with or without .txt) to a path inside MAPS_DIR."""
    fname = name if name.endswith(".txt") else f"{name}.txt"
    path = (MAPS_DIR / fname).resolve()
    maps_dir = MAPS_DIR.resolve()
    if path.parent != maps_dir or not path.is_file():
        available = sorted(p.stem for p in maps_dir.glob("*.txt"))
        raise ValueError(f"Unknown map {name!r}. Available: {available}")
    return path


def _ensure_game() -> pyBaba.Game:
    """Return the current game, lazily loading the default map on first use."""
    global _game, _map_name, _history
    if _game is None:
        _game = pyBaba.Game(str(_resolve_map(DEFAULT_MAP)))
        _map_name = DEFAULT_MAP
        _history = []
    return _game


def _status_str(game: pyBaba.Game) -> str:
    return STATUS.get(game.GetPlayState(), "invalid")


def _state_payload(game: pyBaba.Game) -> dict:
    """Build the canonical state payload: the map as-is plus dimensions/status."""
    gmap = game.GetMap()
    width, height = gmap.GetWidth(), gmap.GetHeight()
    flat = gmap.GetGrid()  # row-major, length width*height; each cell a list of ObjectType
    grid = [
        [[obj.name for obj in flat[y * width + x]] for x in range(width)]
        for y in range(height)
    ]
    return {
        "map": _map_name,
        "width": width,
        "height": height,
        "grid": grid,
        "status": _status_str(game),
    }


def _rule_to_names(rule: pyBaba.Rule) -> list[str]:
    """Render a Rule as a list of object-type name strings, e.g. ['BABA','IS','YOU']."""
    names: list[str] = []
    for obj in rule.objects:
        types = obj.GetTypes()
        names.append(types[0].name if types else "EMPTY")
    return names


def _validate_raw_map(map_contents: str) -> None:
    """Validate the native int-grid map format before handing it to pyBaba."""
    tokens = map_contents.split()
    if len(tokens) < 2:
        raise ValueError(
            "Map must start with a 'width height' header followed by width*height integers."
        )
    try:
        width, height = int(tokens[0]), int(tokens[1])
    except ValueError:
        raise ValueError(f"Header must be two integers 'width height', got {tokens[:2]!r}.")
    if width <= 0 or height <= 0:
        raise ValueError(f"width and height must be positive, got {width}x{height}.")
    cells = tokens[2:]
    expected = width * height
    if len(cells) != expected:
        raise ValueError(
            f"Expected {expected} cell values for a {width}x{height} map, got {len(cells)}."
        )
    for i, tok in enumerate(cells):
        try:
            int(tok)
        except ValueError:
            raise ValueError(f"Cell value at index {i} is not an integer: {tok!r}.")


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
def list_maps() -> dict:
    """List the names of the built-in maps available to load."""
    return {"maps": sorted(p.stem for p in MAPS_DIR.resolve().glob("*.txt"))}


@mcp.tool()
def load_map(name: str) -> dict:
    """Load a built-in map by name (e.g. 'simple_map') and start a fresh game.

    Returns the initial board state.
    """
    global _game, _map_name, _history
    with _lock:
        path = _resolve_map(name)
        _game = pyBaba.Game(str(path))
        _map_name = path.name
        _history = []
        return _state_payload(_game)


@mcp.tool()
def load_raw_map(map_contents: str) -> dict:
    """Load a map from raw text in the native format and start a fresh game.

    Format: a 'width height' header line followed by exactly width*height integer
    ObjectType codes (same as the Resources/Maps/*.txt files). The contents are
    validated before loading. Returns the initial board state.
    """
    global _game, _map_name, _history
    _validate_raw_map(map_contents)
    with _lock:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp:
            tmp.write(map_contents)
            tmp_path = tmp.name
        try:
            _game = pyBaba.Game(tmp_path)
        finally:
            os.unlink(tmp_path)
        _map_name = "<raw>"
        _history = []
        return _state_payload(_game)


@mcp.tool()
def reset() -> dict:
    """Reset the current level to its initial state and clear the move history."""
    global _history
    with _lock:
        game = _ensure_game()
        game.Reset()
        _history = []
        return _state_payload(game)


@mcp.tool()
def get_state() -> dict:
    """Return the current board: a 2D grid of stacked object-type names, plus
    width, height, the map name, and status."""
    with _lock:
        return _state_payload(_ensure_game())


@mcp.tool()
def get_status() -> dict:
    """Return the game status: success (won), dead (lost), in_progress, or invalid."""
    with _lock:
        if _game is None:
            return {"status": "no_game"}
        return {"status": _status_str(_game), "raw": _game.GetPlayState().name}


@mcp.tool()
def get_rules() -> dict:
    """Return the currently active rules as object-name triples, e.g. ['BABA','IS','YOU']."""
    with _lock:
        game = _ensure_game()
        rules = game.GetRuleManager().GetAllRules()
        return {"rules": [_rule_to_names(r) for r in rules]}


@mcp.tool()
def do_action(action: str) -> dict:
    """Perform one move: up | down | left | right | idle. Returns the new state."""
    key = action.strip().lower()
    if key not in ACTIONS:
        raise ValueError(f"Invalid action {action!r}. Valid: {VALID_ACTIONS}")
    with _lock:
        game = _ensure_game()
        game.MovePlayer(ACTIONS[key])
        _history.append(key)
        return _state_payload(game)


@mcp.tool()
def do_actions(actions: list[str]) -> dict:
    """Perform a sequence of moves, stopping early if the game is won or lost.

    All actions are validated before any is applied. Returns the final state plus
    'applied' (how many ran), 'requested', and 'stopped_reason'.
    """
    keys = [a.strip().lower() for a in actions]
    bad = sorted({a for a in keys if a not in ACTIONS})
    if bad:
        raise ValueError(f"Invalid actions {bad}. Valid: {VALID_ACTIONS}")
    with _lock:
        game = _ensure_game()
        applied = 0
        for key in keys:
            game.MovePlayer(ACTIONS[key])
            _history.append(key)
            applied += 1
            if game.GetPlayState() in TERMINAL:
                break
        payload = _state_payload(game)
        payload.update(
            applied=applied,
            requested=len(keys),
            stopped_reason=payload["status"],
        )
        return payload


@mcp.tool()
def undo(steps: int = 1) -> dict:
    """Undo the last N moves (default 1) by resetting and replaying the history.

    The simulator has no native undo; this reconstructs the prior state exactly,
    since moves are deterministic. Returns the new state plus 'undone'.
    """
    global _history
    if steps < 1:
        raise ValueError(f"steps must be >= 1, got {steps}.")
    with _lock:
        game = _ensure_game()
        if not _history:
            payload = _state_payload(game)
            payload["undone"] = 0
            payload["message"] = "Nothing to undo."
            return payload
        undone = min(steps, len(_history))
        replay = _history[:-undone]
        game.Reset()
        for key in replay:
            game.MovePlayer(ACTIONS[key])
        _history = replay
        payload = _state_payload(game)
        payload["undone"] = undone
        return payload


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
