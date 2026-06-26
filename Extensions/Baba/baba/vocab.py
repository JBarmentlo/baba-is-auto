"""Canonical Baba vocabulary + the mapping to/from our int-grid ``ObjectType``
codes and to display glyphs.

The ordering below mirrors the C++ ``ObjectType`` enum
(``Includes/baba-is-auto/Enums/{NounType,OpType,PropertyType,IconType}.def``):

    0           NOUN_TYPE marker
    1..65       NOUNS (text)
    66          OP_TYPE marker
    67..75      OPS (text)
    76          PROPERTY_TYPE marker
    77..109     PROPERTIES (text)
    110         ICON_TYPE marker
    111..175    ICONS (objects)  -- ICON_<noun> parallels NOUNS

A test (tests/unit/test_vocab.py) asserts these lists still match the .def files.
"""

from __future__ import annotations

# fmt: off
NOUNS = [
    "ALGAE", "ALL", "ANNI", "BABA", "BAT", "BELT", "BIRD", "BOG", "BOLT", "BOX",
    "BRICK", "BUBBLE", "BUG", "CAKE", "CLIFF", "CLOUD", "COG", "CRAB", "CURSOR",
    "DOOR", "DUST", "EMPTY", "FENCE", "FIRE", "FLAG", "FLOWER", "FOLIAGE", "FRUIT",
    "FUNGUS", "GHOST", "GRASS", "GROUP", "HAND", "HEDGE", "ICE", "IMAGE", "JELLY",
    "KEKE", "KEY", "LAVA", "LEAF", "LEVEL", "LINE", "LOVE", "ME", "MOON", "ORB",
    "PILLAR", "PIPE", "ROBOT", "ROCK", "ROCKET", "ROSE", "RUBBLE", "SKULL", "STAR",
    "STATUE", "SUN", "TEXT", "TILE", "TREE", "UFO", "VIOLET", "WALL", "WATER",
]
OPS = ["IS", "HAS", "MAKE", "AND", "NOT", "ON", "NEAR", "FACING", "LONELY"]
PROPERTIES = [
    "YOU", "STOP", "PUSH", "PULL", "SWAP", "TELE", "MOVE", "FALL", "SHIFT", "WIN",
    "DEFEAT", "SINK", "HOT", "MELT", "SHUT", "OPEN", "WEAK", "FLOAT", "MORE", "UP",
    "DOWN", "LEFT", "RIGHT", "WORD", "BEST", "SLEEP", "RED", "BLUE", "HIDE", "BONUS",
    "END", "DONE", "SAFE",
]
# fmt: on

VERBS = {"IS", "HAS", "MAKE"}
CONDITIONS = {"ON", "NEAR", "FACING", "LONELY"}
NOT_OP = "NOT"
AND_OP = "AND"

NOUN_SET = set(NOUNS)
PROPERTY_SET = set(PROPERTIES)
TEXT_WORDS = NOUN_SET | set(OPS) | PROPERTY_SET  # every word that can be a text tile

# --- ObjectType int-grid offsets (mirror GameEnums.hpp) --- #
_NOUN_BASE = 1  # codes 1..65
_OP_BASE = 67  # codes 67..75
_PROP_BASE = 77  # codes 77..109
_ICON_BASE = 111  # codes 111..175
ICON_EMPTY_CODE = _ICON_BASE + NOUNS.index("EMPTY")  # 132 -- floor filler, no unit


def intgrid_code(code: int) -> tuple[str, bool] | None:
    """Map an ``ObjectType`` int to ``(canonical_name, is_text)`` or ``None``.

    ``None`` => no unit (a type marker, or the ICON_EMPTY floor).
    """
    if _NOUN_BASE <= code < _NOUN_BASE + len(NOUNS):
        return NOUNS[code - _NOUN_BASE], True
    if _OP_BASE <= code < _OP_BASE + len(OPS):
        return OPS[code - _OP_BASE], True
    if _PROP_BASE <= code < _PROP_BASE + len(PROPERTIES):
        return PROPERTIES[code - _PROP_BASE], True
    if _ICON_BASE <= code < _ICON_BASE + len(NOUNS):
        name = NOUNS[code - _ICON_BASE]
        if name == "EMPTY":
            return None  # floor filler
        return name, False
    return None  # marker (0/66/76/110) or out of range


# --- display glyphs for render_text --- #
# Objects -> a single char. Text tiles render as their word (handled in render.py).
GLYPHS: dict[str, str] = {
    "EMPTY": ".",
    "BABA": "B",
    "KEKE": "k",
    "ME": "m",
    "ROBOT": "ro",
    "WALL": "#",
    "ROCK": "r",
    "FLAG": "F",
    "WATER": "~",
    "LAVA": "L",
    "SKULL": "s",
    "KEY": "-",
    "DOOR": "D",
    "GRASS": '"',
    "TILE": ",",
    "FLOWER": "*",
    "TREE": "T",
    "FRUIT": "o",
    "BOX": "x",
    "ICE": "i",
    "STAR": "+",
    "LOVE": "<",
    "MOON": "(",
    "SUN": "O",
    "BOLT": "/",
    "BELT": "=",
    "PILLAR": "I",
    "HEDGE": "h",
    "FENCE": "f",
    "CLIFF": "^",
}


def glyph(name: str) -> str:
    """Display glyph for an object name (fallback: lowercased first letter)."""
    return GLYPHS.get(name, name[0].lower() if name else "?")
