"""Level loaders: our int-grid ObjectType format (primary) and Keke ascii (tests)."""

from __future__ import annotations

from .engine import evaluate
from .state import GameState, Unit
from .vocab import intgrid_code


def load_intgrid(text: str) -> GameState:
    """Load our native format: a ``"W H"`` header then ``W*H`` ObjectType ints
    (one per cell, row-major). Markers / ICON_EMPTY become no unit."""
    toks = text.split()
    if len(toks) < 2:
        raise ValueError("int-grid map needs a 'W H' header")
    width, height = int(toks[0]), int(toks[1])
    cells = toks[2:]
    if len(cells) != width * height:
        raise ValueError(
            f"expected {width * height} cells for {width}x{height}, got {len(cells)}"
        )
    units: list[Unit] = []
    nid = 1
    for idx, c in enumerate(cells):
        mapping = intgrid_code(int(c))
        if mapping is None:
            continue
        name, is_text = mapping
        units.append(Unit(id=nid, name=name, is_text=is_text, x=idx % width, y=idx // width))
        nid += 1
    state = GameState(width=width, height=height, units=units, next_id=nid)
    return evaluate(state)


# --- Keke ascii legend (KekeCompetition Keke_JS) --- #
# lowercase = object, uppercase = noun-word, digits = op/property words.
_KEKE: dict[str, tuple[str, bool] | None] = {
    " ": None, ".": None,
    "_": ("WALL", False),  # border edge -> treat as wall object
    "b": ("BABA", False), "B": ("BABA", True),
    "s": ("SKULL", False), "S": ("SKULL", True),
    "f": ("FLAG", False), "F": ("FLAG", True),
    "o": ("TILE", False), "O": ("TILE", True),
    "a": ("GRASS", False), "A": ("GRASS", True),
    "l": ("LAVA", False), "L": ("LAVA", True),
    "r": ("ROCK", False), "R": ("ROCK", True),
    "w": ("WALL", False), "W": ("WALL", True),
    "k": ("KEKE", False), "K": ("KEKE", True),
    "g": ("BOG", False), "G": ("BOG", True),     # Keke "goop" -> BOG
    "v": ("LOVE", False), "V": ("LOVE", True),
    "1": ("IS", True), "2": ("YOU", True), "3": ("WIN", True), "4": ("DEFEAT", True),
    "5": ("PUSH", True), "6": ("STOP", True), "7": ("MOVE", True), "8": ("HOT", True),
    "9": ("MELT", True), "0": ("SINK", True),
}


def load_keke(ascii_map: str) -> GameState:
    """Load a Keke-format ascii level (for golden tests)."""
    rows = ascii_map.split("\n")
    while rows and rows[-1] == "":
        rows.pop()
    height = len(rows)
    width = max((len(r) for r in rows), default=0)
    units: list[Unit] = []
    nid = 1
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            mapping = _KEKE.get(ch)
            if mapping is None:
                continue
            name, is_text = mapping
            units.append(Unit(id=nid, name=name, is_text=is_text, x=x, y=y))
            nid += 1
    state = GameState(width=width, height=height, units=units, next_id=nid)
    return evaluate(state)
