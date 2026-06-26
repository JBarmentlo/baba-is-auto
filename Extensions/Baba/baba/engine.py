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
from .effects import compute_status, convert_units, update_portals, update_units
from .movement import fall_block, move_you, run_auto_moves, run_shift
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

    # movement stages (reparse between, since moving text changes rules)
    rules = parse_rules(board)
    move_you(board, rules, action)              # player input
    rules = parse_rules(board)
    run_auto_moves(board, rules)                # MOVE
    rules = parse_rules(board)
    run_shift(board, rules)                     # SHIFT
    rules = parse_rules(board)
    update_portals(board, rules)               # TELE
    rules = parse_rules(board)
    fall_block(board, rules)                    # FALL / gravity

    # transforms: reparse then convert, to a fixpoint (transforms can form rules)
    for _ in range(INFINITE_LOOP_LIMIT):
        rules = parse_rules(board)
        if not convert_units(board, rules):
            break

    # EFFECTS pass (SINK/WEAK/HOT-MELT/DEFEAT/OPEN-SHUT/MAKE)
    rules = parse_rules(board)
    update_units(board, rules)

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
