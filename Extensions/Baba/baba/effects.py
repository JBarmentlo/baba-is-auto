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
