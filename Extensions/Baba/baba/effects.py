"""Post-movement effects and win/lose evaluation.

M0 implements win/lose only. Transforms (NOUN IS NOUN), SINK, DEFEAT, HOT/MELT,
OPEN/SHUT, WEAK, MAKE, HAS-drops, FLOAT gating, etc. arrive in later milestones
via the handlers stubbed here. Reference: bab-be-u game/unit.lua updateUnits()
(effect order) + convertUnits() (transforms).
"""

from __future__ import annotations

from collections import defaultdict

from .board import Board, WUnit
from .rules import RuleSet
from .state import Status


def drop_has(board: Board, unit: WUnit, rules: RuleSet) -> None:
    """When ``unit`` is destroyed, spawn what its noun HAS (X HAS Y).

    Reference: bab-be-u dropGotUnit. EMPTY targets drop nothing.
    """
    for s, o in rules.has_rules:
        if s == unit.noun and o != "EMPTY":
            board.add(o, unit.x, unit.y, is_text=False, dir=unit.dir)


def convert_units(board: Board, rules: RuleSet) -> bool:
    """Apply NOUN IS NOUN transforms. Returns True if anything changed.

    - ``X IS X`` makes X immune to other transforms (identity).
    - ``X IS EMPTY`` destroys X (and fires its HAS-drops).
    - ``X IS Y`` (+ optionally Z) replaces each X with one unit per target.
    Reference: bab-be-u convertUnits().
    """
    targets: dict[str, set[str]] = defaultdict(set)
    identity: set[str] = set()
    for s, o in rules.transforms:
        if s == o:
            identity.add(s)
        else:
            targets[s].add(o)
    if not targets:
        return False

    changed = False
    for u in list(board.iter_units()):
        noun = u.noun
        if noun in identity:
            continue
        tgs = targets.get(noun)
        if not tgs:
            continue
        changed = True
        if "EMPTY" in tgs:
            drop_has(board, u, rules)
        board.remove(u)
        for t in tgs:
            if t == "EMPTY":
                continue
            board.add(t, u.x, u.y, is_text=False, dir=u.dir)  # target is an object noun
    return changed


def same_float(board: Board, rules: RuleSet, a, b) -> bool:
    """Whether two units share a FLOAT layer (interact). M0: FLOAT not yet
    implemented, so everything is on the same layer."""
    af = rules.has_property(a, "FLOAT")
    bf = rules.has_property(b, "FLOAT")
    return af == bf


def _destroy(board: Board, unit: WUnit, rules: RuleSet) -> None:
    drop_has(board, unit, rules)
    board.remove(unit)


def _tiles(board: Board) -> dict[tuple[int, int], list[WUnit]]:
    d: dict[tuple[int, int], list[WUnit]] = {}
    for u in board.iter_units():
        d.setdefault((u.x, u.y), []).append(u)
    return d


def update_units(board: Board, rules: RuleSet) -> bool:
    """The ordered destructive/creative EFFECTS pass. Returns True if changed.

    Order (bab-be-u): SINK, WEAK, HOT/MELT, DEFEAT, OPEN/SHUT, MAKE. All
    interactions are FLOAT-gated via :func:`same_float`. WIN is handled in
    :func:`compute_status`. HAS-drops fire on every destruction.
    """
    changed = False
    has = rules.has_property
    sf = lambda a, b: same_float(board, rules, a, b)

    # SINK: a tile with a SINK unit + another (float-compatible) unit -> both gone
    for cell in _tiles(board).values():
        sinks = [u for u in cell if has(u, "SINK")]
        if not sinks:
            continue
        doomed: set[int] = set()
        for u in cell:
            for s in sinks:
                if s is not u and sf(u, s):
                    doomed.add(u.id)
                    doomed.add(s.id)
        for u in cell:
            if u.id in doomed and not u.removed:
                _destroy(board, u, rules)
                changed = True

    # WEAK: destroyed when sharing a tile with any other (float-compatible) unit
    for cell in _tiles(board).values():
        if len(cell) < 2:
            continue
        for u in cell:
            if has(u, "WEAK") and any(o is not u and sf(u, o) for o in cell):
                _destroy(board, u, rules)
                changed = True

    # HOT/MELT: a MELT unit on a tile with a HOT unit -> melt destroyed
    for cell in _tiles(board).values():
        hots = [u for u in cell if has(u, "HOT")]
        if not hots:
            continue
        for u in cell:
            if has(u, "MELT") and any(sf(u, h) for h in hots) and not u.removed:
                _destroy(board, u, rules)
                changed = True

    # DEFEAT: a YOU unit on a tile with a DEFEAT unit -> you destroyed
    for cell in _tiles(board).values():
        defeats = [u for u in cell if has(u, "DEFEAT")]
        if not defeats:
            continue
        for u in cell:
            if has(u, "YOU") and any(sf(u, d) for d in defeats) and not u.removed:
                _destroy(board, u, rules)
                changed = True

    # OPEN/SHUT: pair off OPEN with SHUT on the same tile -> both destroyed
    for cell in _tiles(board).values():
        opens = [u for u in cell if has(u, "OPEN") and not has(u, "SHUT")]
        shuts = [u for u in cell if has(u, "SHUT") and not has(u, "OPEN")]
        i = 0
        for o in opens:
            while i < len(shuts):
                s = shuts[i]
                i += 1
                if not s.removed and not o.removed and sf(o, s):
                    _destroy(board, o, rules)
                    _destroy(board, s, rules)
                    changed = True
                    break

    # MAKE: each X-noun unit spawns a Y object on its tile
    if rules.make_rules:
        for s, o in rules.make_rules:
            if o == "EMPTY":
                continue
            for u in [u for u in board.iter_units() if u.noun == s]:
                board.add(o, u.x, u.y, is_text=False)
                changed = True

    return changed


def update_portals(board: Board, rules: RuleSet) -> None:
    """M11 TELE: units sharing a TELE tile hop to the next TELE tile (reading
    order, cycling). FLOAT-gated against the teleporter."""
    teles = [u for u in board.iter_units() if rules.has_property(u, "TELE")]
    tiles: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for u in sorted(teles, key=lambda u: (u.y, u.x)):
        if (u.x, u.y) not in seen:
            seen.add((u.x, u.y))
            tiles.append((u.x, u.y))
    if len(tiles) < 2:
        return
    idx = {t: i for i, t in enumerate(tiles)}
    moved: set[int] = set()
    for (tx, ty) in tiles:
        cell = board.tile(tx, ty)
        tele_here = [u for u in cell if rules.has_property(u, "TELE")]
        riders = [
            u for u in cell
            if u.id not in moved
            and not rules.has_property(u, "TELE")
            and any(same_float(board, rules, u, t) for t in tele_here)
        ]
        if not riders:
            continue
        dest = tiles[(idx[(tx, ty)] + 1) % len(tiles)]
        for u in riders:
            board.move(u, dest[0], dest[1])
            moved.add(u.id)


def compute_status(board: Board, rules: RuleSet) -> Status:
    """WON if a YOU overlaps a WIN (same float layer); LOST if no YOU exists."""
    yous = [u for u in board.iter_units() if rules.has_property(u, "YOU")]
    if not yous:
        return Status.LOST
    win_units = [u for u in board.iter_units() if rules.has_property(u, "WIN")]
    win_by_tile: dict[tuple[int, int], list] = {}
    for w in win_units:
        win_by_tile.setdefault((w.x, w.y), []).append(w)
    for u in yous:
        for w in win_by_tile.get((u.x, u.y), ()):
            if w is u or same_float(board, rules, u, w):
                return Status.WON
    return Status.PLAYING
