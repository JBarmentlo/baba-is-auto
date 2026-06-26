"""Tiny ascii DSL for authored engine tests.

``build(grid, rules=[...])`` places object tiles from an ascii grid and spawns
the given rules as text rows beneath the play area, returning a Game.

Grid legend (objects): B=BABA R=ROCK W=WALL F=FLAG K=KEKE S=SKULL L=LAVA
G=GRASS D=DOOR Y=KEY X=BOX T=TILE  ; '.'/' ' = empty.
Rules are plain strings like "BABA IS YOU" / "BABA IS YOU AND WIN" / "ROCK IS PUSH".
"""

from __future__ import annotations

from baba import GameState, Unit, evaluate
from baba.game import Game

GRID_CHARS = {
    "B": "BABA", "R": "ROCK", "W": "WALL", "F": "FLAG", "K": "KEKE",
    "S": "SKULL", "L": "LAVA", "G": "GRASS", "D": "DOOR", "Y": "KEY",
    "X": "BOX", "T": "TILE", "O": "ROCK",
}


def build(grid: str, rules: list[str] | None = None) -> Game:
    rules = rules or []
    rows = [r for r in grid.split("\n")]
    while rows and rows[0].strip() == "":
        rows.pop(0)
    while rows and rows[-1].strip() == "":
        rows.pop()
    grid_h = len(rows)
    grid_w = max((len(r) for r in rows), default=0)

    rule_tokens = [r.split() for r in rules]
    rule_w = max((len(t) for t in rule_tokens), default=0)
    width = max(grid_w, rule_w, 1)
    height = grid_h + len(rule_tokens)

    units: list[Unit] = []
    nid = 1
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            name = GRID_CHARS.get(ch)
            if name is None:
                continue
            units.append(Unit(id=nid, name=name, is_text=False, x=x, y=y))
            nid += 1
    for i, toks in enumerate(rule_tokens):
        y = grid_h + i
        for x, word in enumerate(toks):
            units.append(Unit(id=nid, name=word, is_text=True, x=x, y=y))
            nid += 1

    state = GameState(width=width, height=height, units=units, next_id=nid)
    return Game(evaluate(state))


def names_at(g: Game, x: int, y: int) -> list[str]:
    return [u.name for u in g.state.units if u.x == x and u.y == y and not u.is_text]


def obj_pos(g: Game, name: str) -> list[tuple[int, int]]:
    return [(u.x, u.y) for u in g.state.units if u.name == name and not u.is_text]
