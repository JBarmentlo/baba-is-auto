"""baba — a pure-functional canonical Baba Is You engine.

Core: the whole game is one pydantic :class:`GameState`, advanced by the pure
function :func:`get_next_state`. :class:`Game` is a stateful convenience wrapper
(history -> undo) used by the MCP.
"""

from .state import Direction, GameState, Status, Unit
from .engine import evaluate, get_next_state
from .loaders import load_intgrid, load_keke
from .render import render_text, to_grid
from .rules import RuleEngineError
from .game import Game


def parse_rules(state: GameState) -> list[tuple[str, str, str]]:
    """Return the active rules of a state as ``(subject, verb, object)`` triples."""
    from .board import Board
    from .rules import parse_rules as _pr

    return list(_pr(Board.from_state(state)).rules)


__all__ = [
    "Direction",
    "GameState",
    "Status",
    "Unit",
    "Game",
    "get_next_state",
    "evaluate",
    "load_intgrid",
    "load_keke",
    "render_text",
    "to_grid",
    "parse_rules",
    "RuleEngineError",
]
