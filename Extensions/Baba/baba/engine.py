"""The pure-functional turn core: ``get_next_state(state, action) -> GameState``.

Builds a transient mutable :class:`~baba.board.Board` from the immutable
``GameState``, runs the turn pipeline, and returns a brand-new ``GameState``.
The input ``state`` is never mutated.

M0 pipeline: reparse -> player move -> reparse -> evaluate win/lose. Later
milestones insert autonomous MOVE, transforms (convert_units), the ordered
EFFECTS pass (update_units), FALL, TELE, etc. between these steps, each followed
by a reparse (see plan / bab-be-u movement.lua:859-890).
"""

from __future__ import annotations

from .board import Board
from .effects import compute_status, convert_units
from .movement import move_you
from .rules import INFINITE_LOOP_LIMIT, parse_rules
from .state import Direction, GameState


def _emit(board: Board, turn: int) -> GameState:
    rules = parse_rules(board)
    status = compute_status(board, rules)
    return GameState(
        width=board.width,
        height=board.height,
        units=board.to_units(),
        turn=turn,
        status=status,
        next_id=board.next_id,
    )


def get_next_state(state: GameState, action: Direction) -> GameState:
    """Advance one turn. Pure: returns a new state, never mutates ``state``."""
    board = Board.from_state(state)

    rules = parse_rules(board)
    move_you(board, rules, action)
    # (later: autonomous MOVE/SHIFT, moveBlock/TELE, fall)

    # transforms: reparse then convert, to a fixpoint (transforms can form rules)
    for _ in range(INFINITE_LOOP_LIMIT):
        rules = parse_rules(board)
        if not convert_units(board, rules):
            break
    # (later: update_units EFFECTS pass)

    return _emit(board, state.turn + 1)


def evaluate(state: GameState) -> GameState:
    """Return ``state`` with its ``status`` recomputed (no movement)."""
    board = Board.from_state(state)
    return GameState(
        width=board.width,
        height=board.height,
        units=board.to_units(),
        turn=state.turn,
        status=compute_status(board, parse_rules(board)),
        next_id=board.next_id,
    )
