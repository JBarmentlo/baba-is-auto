"""Movement resolution: STOP blocking, PUSH chains, bounds.

PULL / SWAP / SHIFT / slide are later milestones. Reference: bab-be-u
game/movement.lua (canMove / trymove / push chain).
"""

from __future__ import annotations

from .board import Board, WUnit
from .rules import RuleSet
from .state import Direction, direction_from_delta

_OPP = {
    Direction.UP: Direction.DOWN, Direction.DOWN: Direction.UP,
    Direction.LEFT: Direction.RIGHT, Direction.RIGHT: Direction.LEFT,
    Direction.NONE: Direction.NONE,
}


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


def _pull_behind(board: Board, ox: int, oy: int, dx: int, dy: int, rules: RuleSet) -> None:
    """Pull PULL units trailing behind a unit that just left tile (ox,oy)."""
    bx, by = ox - dx, oy - dy
    while board.in_bounds(bx, by):
        pulls = [u for u in board.tile(bx, by) if rules.has_property(u, "PULL")]
        if not pulls:
            break
        for u in pulls:
            board.move(u, u.x + dx, u.y + dy)
            u.dir = direction_from_delta(dx, dy)
        bx, by = bx - dx, by - dy


def move_unit(board: Board, u: WUnit, dx: int, dy: int, rules: RuleSet) -> bool:
    """Try to move ``u`` by (dx,dy), pushing/swapping/pulling. Returns success."""
    if (dx, dy) == (0, 0):
        return False
    ox, oy = u.x, u.y
    nx, ny = ox + dx, oy + dy
    if not board.in_bounds(nx, ny):
        return False

    if rules.has_property(u, "SWAP"):
        for o in board.tile(nx, ny):  # swap places with whatever is ahead
            board.move(o, ox, oy)
        board.move(u, nx, ny)
        u.dir = direction_from_delta(dx, dy)
        _pull_behind(board, ox, oy, dx, dy, rules)
        return True

    chain: list[WUnit] = []
    seen: set[int] = set()
    if not _can_enter(board, nx, ny, dx, dy, rules, chain, seen):
        return False
    for o in chain:  # farthest-first so tiles are vacated in order
        board.move(o, o.x + dx, o.y + dy)
        o.dir = direction_from_delta(dx, dy)
    board.move(u, nx, ny)
    u.dir = direction_from_delta(dx, dy)
    _pull_behind(board, ox, oy, dx, dy, rules)
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


def run_auto_moves(board: Board, rules: RuleSet) -> None:
    """M2 MOVE: each MOVE unit steps in its facing dir; reverses if blocked."""
    movers = sorted(
        (u for u in board.iter_units() if rules.has_property(u, "MOVE")), key=lambda u: u.id
    )
    for u in movers:
        if u.removed:
            continue
        if u.dir == Direction.NONE:
            u.dir = Direction.RIGHT
        dx, dy = u.dir.delta
        if not move_unit(board, u, dx, dy, rules):
            u.dir = _OPP[u.dir]
            dx, dy = u.dir.delta
            move_unit(board, u, dx, dy, rules)


def run_shift(board: Board, rules: RuleSet) -> None:
    """M9 SHIFT: each SHIFT unit moves units sharing its tile in its facing dir."""
    shifts = sorted(
        (u for u in board.iter_units() if rules.has_property(u, "SHIFT")), key=lambda u: u.id
    )
    for s in shifts:
        if s.removed or s.dir == Direction.NONE:
            continue
        dx, dy = s.dir.delta
        for o in board.tile(s.x, s.y):
            if o is not s and not o.removed:
                move_unit(board, o, dx, dy, rules)


def fall_block(board: Board, rules: RuleSet) -> None:
    """M10 FALL: FALL units fall (+y) until none can move. Settles stacks."""
    for _ in range(1000):
        moved = False
        fallers = sorted(
            (u for u in board.iter_units() if rules.has_property(u, "FALL")),
            key=lambda u: -u.y,  # lowest first so they settle in order
        )
        for u in fallers:
            if not u.removed and move_unit(board, u, 0, 1, rules):
                moved = True
        if not moved:
            break
