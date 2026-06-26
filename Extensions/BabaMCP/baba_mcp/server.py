"""FastMCP server exposing the canonical Baba Is You engine (the ``baba`` library).

A thin, in-process layer over the pure-Python ``baba`` engine. It lets an agent
observe the board (grid + text render), submit moves, check win/lose status,
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
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import baba
from baba import Direction, Game, Status
from mcp.server.fastmcp import FastMCP
from pydantic import Field

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
_DEFAULT_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = Path(os.environ.get("BABA_REPO_ROOT") or _DEFAULT_ROOT)
MAPS_DIR = Path(os.environ.get("BABA_MAPS_DIR") or (REPO_ROOT / "Resources" / "Maps"))
DEFAULT_MAP = "baba_is_you.txt"

# Header that selects a session over HTTP, and the implicit session id used
# when there is no HTTP request (stdio).
SESSION_HEADER = "baba_session_id"
STDIO_SESSION_ID = "stdio"

# --------------------------------------------------------------------------- #
# Enum maps
# --------------------------------------------------------------------------- #
ACTIONS = {
    "up": Direction.UP,
    "down": Direction.DOWN,
    "left": Direction.LEFT,
    "right": Direction.RIGHT,
    "idle": Direction.NONE,
}
VALID_ACTIONS = sorted(ACTIONS)

STATUS = {
    Status.WON: "success",
    Status.LOST: "dead",
    Status.PLAYING: "in_progress",
}
TERMINAL = (Status.WON, Status.LOST)


# --------------------------------------------------------------------------- #
# Per-session state
# --------------------------------------------------------------------------- #
@dataclass
class SessionState:
    """A single client's independent game (the baba.Game holds its own history)."""

    game: Game
    map_name: str  # "baba_is_you.txt" | "<raw>"

    @property
    def moves(self) -> int:
        return max(0, len(self.game._history) - 1)


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


def _new_game_from_map(name: str) -> SessionState:
    """Build a fresh SessionState for a built-in map name."""
    path = _resolve_map(name)
    return SessionState(game=Game(path.read_text(), fmt="intgrid"), map_name=path.name)


def _status_str(game: Game) -> str:
    return STATUS.get(game.status(), "invalid")


def _state_payload(session: SessionState) -> dict:
    """The canonical state payload: the board (grid + text) + dimensions/status."""
    state = session.game.state
    return {
        "map": session.map_name,
        "width": state.width,
        "height": state.height,
        "grid": baba.to_grid(state),
        "text": baba.render_text(state),
        "status": _status_str(session.game),
    }


def _brief(session: SessionState, **extra) -> dict:
    """Compact result for mutating tools: status only, never the grid."""
    return {"status": _status_str(session.game), **extra}


def _validate_raw_map(map_contents: str) -> None:
    """Validate the native int-grid map format before loading (clear errors)."""
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
    """Create a configured FastMCP server wrapping the canonical Baba engine.

    Args:
        max_sessions: Cap on concurrent in-memory sessions (FIFO eviction).
        require_session_header: Over HTTP, require the ``baba_session_id`` header
            on state-touching tools. If False, header-less HTTP shares "default".
        **fastmcp_kwargs: Passed to ``FastMCP(...)`` (host, port, ...).
    """
    opts = {"stateless_http": True, "json_response": True, **fastmcp_kwargs}
    mcp = FastMCP("baba-is-you", **opts)

    sessions: "OrderedDict[str, SessionState]" = OrderedDict()

    def _session_id() -> str:
        try:
            request = mcp.get_context().request_context.request
        except Exception:
            request = None
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
        sess = sessions.get(session_id)
        if sess is None:
            sess = _new_game_from_map(DEFAULT_MAP)
            sessions[session_id] = sess
            while len(sessions) > max_sessions:
                sessions.popitem(last=False)
        else:
            sessions.move_to_end(session_id)
        return sess

    # --------------------------------- tools --------------------------------- #
    @mcp.tool()
    def list_maps() -> dict:
        """List the names of the built-in maps available to load."""
        return {"maps": sorted(p.stem for p in MAPS_DIR.resolve().glob("*.txt"))}

    @mcp.tool()
    def load_map(
        name: Annotated[
            str,
            Field(description="Built-in map name, with or without '.txt' (e.g. "
                  "'simple_map'). Use list_maps to discover names."),
        ],
    ) -> dict:
        """Load a built-in map by name and start a fresh game for this session.

        Does NOT return the board — call get_state to see it. Returns width/height
        and status.
        """
        path = _resolve_map(name)
        sess = _session(_session_id())
        sess.game = Game(path.read_text(), fmt="intgrid")
        sess.map_name = path.name
        st = sess.game.state
        return _brief(sess, width=st.width, height=st.height)

    @mcp.tool()
    def load_raw_map(
        map_contents: Annotated[
            str,
            Field(description="Native map text: a 'width height' header line "
                  "followed by exactly width*height integer ObjectType codes "
                  "(same format as Resources/Maps/*.txt)."),
        ],
    ) -> dict:
        """Load a map from raw text in the native format and start a fresh game.

        Validated before loading. Does NOT return the board — call get_state.
        Returns width/height and status.
        """
        _validate_raw_map(map_contents)
        sess = _session(_session_id())
        sess.game = Game(map_contents, fmt="intgrid")
        sess.map_name = "<raw>"
        st = sess.game.state
        return _brief(sess, width=st.width, height=st.height)

    @mcp.tool()
    def reset() -> dict:
        """Reset the current level to its initial state and clear move history.

        Does NOT return the board — call get_state. Returns the status.
        """
        sess = _session(_session_id())
        sess.game.reset()
        return _brief(sess)

    @mcp.tool()
    def get_state() -> dict:
        """Return the current board.

        The only tool that returns the board: 'grid' (rows[y][x] = stacked names;
        text tiles suffixed '_TEXT'), a human-readable 'text' render, plus 'width',
        'height', 'map', 'status'.
        """
        return _state_payload(_session(_session_id()))

    @mcp.tool()
    def get_status() -> dict:
        """Return the game status: success (won), dead (lost), in_progress."""
        sess = sessions.get(_session_id())  # do not lazily create
        if sess is None:
            return {"status": "no_game"}
        return {"status": _status_str(sess.game), "raw": sess.game.status().value}

    @mcp.tool()
    def get_rules() -> dict:
        """Return the active rules as object-name triples, e.g. ['BABA','IS','YOU']."""
        sess = _session(_session_id())
        return {"rules": [list(r) for r in sess.game.rules()]}

    @mcp.tool()
    def do_action(
        action: Annotated[
            str,
            Field(description="One move: 'up', 'down', 'left', 'right', or 'idle' "
                  "(case-insensitive)."),
        ],
    ) -> dict:
        """Perform a single move for this session.

        Does NOT return the board — call get_state. Returns the status.
        """
        key = action.strip().lower()
        if key not in ACTIONS:
            raise ValueError(f"Invalid action {action!r}. Valid: {VALID_ACTIONS}")
        sess = _session(_session_id())
        sess.game.do(ACTIONS[key])
        return _brief(sess)

    @mcp.tool()
    def do_actions(
        actions: Annotated[
            list[str],
            Field(description="Ordered list of moves, each 'up'/'down'/'left'/"
                  "'right'/'idle' (case-insensitive). Applied in order; stops "
                  "early if the game is won or lost."),
        ],
    ) -> dict:
        """Perform a sequence of moves, stopping early on win/loss.

        All actions validated first. Does NOT return the board — call get_state.
        Returns status and 'applied' (how many ran) vs 'requested'.
        """
        keys = [a.strip().lower() for a in actions]
        bad = sorted({a for a in keys if a not in ACTIONS})
        if bad:
            raise ValueError(f"Invalid actions {bad}. Valid: {VALID_ACTIONS}")
        sess = _session(_session_id())
        applied = 0
        for key in keys:
            sess.game.do(ACTIONS[key])
            applied += 1
            if sess.game.status() in TERMINAL:
                break
        return _brief(sess, applied=applied, requested=len(keys))

    @mcp.tool()
    def undo(
        steps: Annotated[
            int, Field(description="Number of moves to undo (default 1).", ge=1)
        ] = 1,
    ) -> dict:
        """Undo the last N moves (default 1).

        Native, exact undo (pops the state history). Does NOT return the board —
        call get_state. Returns the status and 'undone' count.
        """
        if steps < 1:
            raise ValueError(f"steps must be >= 1, got {steps}.")
        sess = _session(_session_id())
        before = sess.moves
        if before == 0:
            return _brief(sess, undone=0, message="Nothing to undo.")
        sess.game.undo(steps)
        return _brief(sess, undone=before - sess.moves)

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
                {"id": sid, "map": s.map_name, "moves": s.moves}
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
