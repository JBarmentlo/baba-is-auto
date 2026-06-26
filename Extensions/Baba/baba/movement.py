"""Movement resolution: STOP blocking, PUSH chains, bounds.

PULL / SWAP / SHIFT / slide are later milestones. Reference: bab-be-u
game/movement.lua (canMove / trymove / push chain).
"""

from __future__ import annotations

from .board import Board, WUnit
from .rules import RuleSet
from .state import Direction, direction_from_delta


def _can_enter(
    board: Board, nx: int, ny: int, dx: int, dy: int, rules: RuleSet,
    chain: list[WUnit], seen: set[int],
) -> bool:
    """Can something enter tile (nx,ny) moving by (dx,dy)?

    Recursively verifies PUSH units ahead can shift; STOP (non-push) blocks.
    Pushed units are appended to ``chain`` farthest-first.
    """
    if not board.in_bounds(nx, ny):
        return False
    occ = board.tile(nx, ny)
    for o in occ:
        if rules.has_property(o, "STOP") and not rules.has_property(o, "PUSH"):
            return False
    for o in occ:
        if rules.has_property(o, "PUSH") and o.id not in seen:
            if not _can_enter(board, o.x + dx, o.y + dy, dx, dy, rules, chain, seen):
                return False
            seen.add(o.id)
            chain.append(o)
    return True


def move_unit(board: Board, u: WUnit, dx: int, dy: int, rules: RuleSet) -> bool:
    """Try to move ``u`` by (dx,dy), pushing what it must. Returns success."""
    if (dx, dy) == (0, 0):
        return False
    chain: list[WUnit] = []
    seen: set[int] = set()
    if not _can_enter(board, u.x + dx, u.y + dy, dx, dy, rules, chain, seen):
        return False
    for o in chain:  # farthest-first so tiles are vacated in order
        board.move(o, o.x + dx, o.y + dy)
        o.dir = direction_from_delta(dx, dy)
    board.move(u, u.x + dx, u.y + dy)
    u.dir = direction_from_delta(dx, dy)
    return True


def move_you(board: Board, rules: RuleSet, action: Direction) -> None:
    """Apply the player's input: every YOU unit attempts to move in ``action``."""
    dx, dy = action.delta
    if (dx, dy) == (0, 0):
        return
    yous = [u for u in board.iter_units() if rules.has_property(u, "YOU")]
    # frontmost-first along the move axis so a column of YOU units flows cleanly
    yous.sort(key=lambda u: -(u.x * dx + u.y * dy))
    for u in yous:
        if not u.removed:
            move_unit(board, u, dx, dy, rules)
