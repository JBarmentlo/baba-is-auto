"""FastMCP server exposing the pyBaba "Baba Is You" simulator.

A thin, in-process layer over the ``pyBaba`` pybind11 module. It lets an agent
observe the board grid (not an image), submit moves, check win/lose status,
manage levels, and undo.

The server supports many concurrent **sessions**, each with its own independent
game. Over HTTP, a session is selected by the ``baba_session_id`` request header;
over stdio there is a single implicit session.

Use :func:`create_baba_mcp` to build a configured ``FastMCP`` instance and serve
it however you like (stdio, streamable-http, or by mounting the ASGI app):

    from baba_mcp import create_baba_mcp
    mcp = create_baba_mcp(host="0.0.0.0", port=8000)
    mcp.run(transport="streamable-http")   # or mcp.run() for stdio
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

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

# Header that selects a session over HTTP, and the implicit session id used
# when there is no HTTP request (stdio).
SESSION_HEADER = "baba_session_id"
STDIO_SESSION_ID = "stdio"

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
# Per-session state
# --------------------------------------------------------------------------- #
@dataclass
class SessionState:
    """A single client's independent game.

    ``map_source``/``is_raw``/``history`` keep the session fully reconstructible
    (load + replay) even though a live game object is retained for speed.
    """

    game: pyBaba.Game
    map_name: str  # display name: a filename or "<raw>"
    map_source: str  # filename for built-in maps, or raw contents when is_raw
    is_raw: bool
    history: list[str] = field(default_factory=list)  # action keys since load


# --------------------------------------------------------------------------- #
# Pure helpers (no session/global state)
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


def _new_game_from_map(name: str) -> SessionState:
    """Build a fresh SessionState for a built-in map name."""
    path = _resolve_map(name)
    return SessionState(
        game=pyBaba.Game(str(path)),
        map_name=path.name,
        map_source=path.name,
        is_raw=False,
    )


def _status_str(game: pyBaba.Game) -> str:
    return STATUS.get(game.GetPlayState(), "invalid")


def _state_payload(session: SessionState) -> dict:
    """Build the canonical state payload: the map as-is plus dimensions/status."""
    game = session.game
    gmap = game.GetMap()
    width, height = gmap.GetWidth(), gmap.GetHeight()
    flat = gmap.GetGrid()  # row-major, length width*height; each cell a list of ObjectType
    grid = [
        [[obj.name for obj in flat[y * width + x]] for x in range(width)]
        for y in range(height)
    ]
    return {
        "map": session.map_name,
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
# Server factory
# --------------------------------------------------------------------------- #
def create_baba_mcp(
    *,
    max_sessions: int = 256,
    require_session_header: bool = True,
    **fastmcp_kwargs,
) -> FastMCP:
    """Create a configured FastMCP server wrapping the Baba Is You simulator.

    The returned instance has all tools registered and an isolated, per-instance
    session store. Serve it however you like::

        mcp = create_baba_mcp(host="0.0.0.0", port=8000)
        mcp.run(transport="streamable-http")   # or mcp.run() for stdio

    Args:
        max_sessions: Cap on concurrent in-memory sessions; the oldest is evicted
            (FIFO) when exceeded. An evicted client transparently gets a fresh
            default game on its next call.
        require_session_header: Over HTTP, require the ``baba_session_id`` header
            on state-touching tools (recommended). If False, header-less HTTP
            requests share a single ``"default"`` session.
        **fastmcp_kwargs: Passed to ``FastMCP(...)`` (e.g. host, port,
            streamable_http_path). ``stateless_http`` and ``json_response``
            default to True but may be overridden.
    """
    opts = {"stateless_http": True, "json_response": True, **fastmcp_kwargs}
    mcp = FastMCP("baba-is-you", **opts)

    # Per-instance session store. Insertion-ordered for FIFO eviction.
    sessions: "OrderedDict[str, SessionState]" = OrderedDict()

    # ----- session helpers (close over `mcp` and `sessions`) ----- #
    def _session_id() -> str:
        """Resolve the session id from the request header.

        HTTP: read ``baba_session_id``; required unless require_session_header is
        False (then fall back to "default"). stdio: there is no HTTP request, so
        use the single implicit STDIO_SESSION_ID.
        """
        try:
            request = mcp.get_context().request_context.request
        except Exception:
            request = None  # accessed outside an active request
        if request is None:
            return STDIO_SESSION_ID
        sid = request.headers.get(SESSION_HEADER)
        if sid:
            return sid
        if require_session_header:
            raise ValueError(
                f"Missing required {SESSION_HEADER!r} header. Send a unique value "
                "per concurrent game session."
            )
        return "default"

    def _session(session_id: str) -> SessionState:
        """Return the session, lazily creating it with the default map."""
        sess = sessions.get(session_id)
        if sess is None:
            sess = _new_game_from_map(DEFAULT_MAP)
            sessions[session_id] = sess
            while len(sessions) > max_sessions:
                sessions.popitem(last=False)  # FIFO: drop the oldest session
        else:
            sessions.move_to_end(session_id)  # LRU touch
        return sess

    # --------------------------------- tools --------------------------------- #
    @mcp.tool()
    def list_maps() -> dict:
        """List the names of the built-in maps available to load."""
        # No session needed — enables discovery before a session header is set.
        return {"maps": sorted(p.stem for p in MAPS_DIR.resolve().glob("*.txt"))}

    @mcp.tool()
    def load_map(name: str) -> dict:
        """Load a built-in map by name (e.g. 'simple_map') and start a fresh game.

        Returns the initial board state.
        """
        path = _resolve_map(name)
        sess = _session(_session_id())
        sess.game = pyBaba.Game(str(path))
        sess.map_name = path.name
        sess.map_source = path.name
        sess.is_raw = False
        sess.history = []
        return _state_payload(sess)

    @mcp.tool()
    def load_raw_map(map_contents: str) -> dict:
        """Load a map from raw text in the native format and start a fresh game.

        Format: a 'width height' header line followed by exactly width*height
        integer ObjectType codes (same as the Resources/Maps/*.txt files). The
        contents are validated before loading. Returns the initial board state.
        """
        _validate_raw_map(map_contents)
        sess = _session(_session_id())
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
            tmp.write(map_contents)
            tmp_path = tmp.name
        try:
            sess.game = pyBaba.Game(tmp_path)
        finally:
            os.unlink(tmp_path)
        sess.map_name = "<raw>"
        sess.map_source = map_contents
        sess.is_raw = True
        sess.history = []
        return _state_payload(sess)

    @mcp.tool()
    def reset() -> dict:
        """Reset the current level to its initial state and clear the move history."""
        sess = _session(_session_id())
        sess.game.Reset()
        sess.history = []
        return _state_payload(sess)

    @mcp.tool()
    def get_state() -> dict:
        """Return the current board: a 2D grid of stacked object-type names, plus
        width, height, the map name, and status."""
        return _state_payload(_session(_session_id()))

    @mcp.tool()
    def get_status() -> dict:
        """Return the game status: success (won), dead (lost), in_progress, or invalid."""
        sess = sessions.get(_session_id())  # do not lazily create
        if sess is None:
            return {"status": "no_game"}
        return {"status": _status_str(sess.game), "raw": sess.game.GetPlayState().name}

    @mcp.tool()
    def get_rules() -> dict:
        """Return the currently active rules as object-name triples, e.g. ['BABA','IS','YOU']."""
        sess = _session(_session_id())
        rules = sess.game.GetRuleManager().GetAllRules()
        return {"rules": [_rule_to_names(r) for r in rules]}

    @mcp.tool()
    def do_action(action: str) -> dict:
        """Perform one move: up | down | left | right | idle. Returns the new state."""
        key = action.strip().lower()
        if key not in ACTIONS:
            raise ValueError(f"Invalid action {action!r}. Valid: {VALID_ACTIONS}")
        sess = _session(_session_id())
        sess.game.MovePlayer(ACTIONS[key])
        sess.history.append(key)
        return _state_payload(sess)

    @mcp.tool()
    def do_actions(actions: list[str]) -> dict:
        """Perform a sequence of moves, stopping early if the game is won or lost.

        All actions are validated before any is applied. Returns the final state
        plus 'applied' (how many ran), 'requested', and 'stopped_reason'.
        """
        keys = [a.strip().lower() for a in actions]
        bad = sorted({a for a in keys if a not in ACTIONS})
        if bad:
            raise ValueError(f"Invalid actions {bad}. Valid: {VALID_ACTIONS}")
        sess = _session(_session_id())
        applied = 0
        for key in keys:
            sess.game.MovePlayer(ACTIONS[key])
            sess.history.append(key)
            applied += 1
            if sess.game.GetPlayState() in TERMINAL:
                break
        payload = _state_payload(sess)
        payload.update(
            applied=applied,
            requested=len(keys),
            stopped_reason=payload["status"],
        )
        return payload

    @mcp.tool()
    def undo(steps: int = 1) -> dict:
        """Undo the last N moves (default 1) by resetting and replaying the history.

        The simulator has no native undo; this reconstructs the prior state
        exactly, since moves are deterministic. Returns the new state plus 'undone'.
        """
        if steps < 1:
            raise ValueError(f"steps must be >= 1, got {steps}.")
        sess = _session(_session_id())
        if not sess.history:
            payload = _state_payload(sess)
            payload["undone"] = 0
            payload["message"] = "Nothing to undo."
            return payload
        undone = min(steps, len(sess.history))
        replay = sess.history[:-undone]
        sess.game.Reset()
        for key in replay:
            sess.game.MovePlayer(ACTIONS[key])
        sess.history = replay
        payload = _state_payload(sess)
        payload["undone"] = undone
        return payload

    @mcp.tool()
    def end_session() -> dict:
        """Free the caller's session memory. A later call lazily creates a fresh one."""
        sid = _session_id()
        existed = sessions.pop(sid, None) is not None
        return {"session": sid, "ended": existed}

    @mcp.tool()
    def list_sessions() -> dict:
        """List active sessions (id, current map, move count) for debugging/ops."""
        return {
            "sessions": [
                {"id": sid, "map": s.map_name, "moves": len(s.history)}
                for sid, s in sessions.items()
            ],
            "count": len(sessions),
            "max": max_sessions,
        }

    return mcp


# --------------------------------------------------------------------------- #
# Console entry point (env-driven). Custom servers can import create_baba_mcp.
# --------------------------------------------------------------------------- #
def main() -> None:
    transport = os.environ.get("BABA_MCP_TRANSPORT", "stdio").strip().lower()
    host = os.environ.get("BABA_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("BABA_MCP_PORT", "8000"))
    http_path = os.environ.get("BABA_MCP_HTTP_PATH", "/mcp")

    if transport in ("http", "streamable-http"):
        mcp = create_baba_mcp(host=host, port=port, streamable_http_path=http_path)
        mcp.run(transport="streamable-http")
    elif transport == "stdio":
        create_baba_mcp().run()
    else:
        raise SystemExit(
            f"Unknown BABA_MCP_TRANSPORT={transport!r}; expected 'stdio' or 'http'."
        )


if __name__ == "__main__":
    main()
