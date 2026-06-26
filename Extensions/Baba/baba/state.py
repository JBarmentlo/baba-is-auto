"""The single pydantic game state and the public value types.

Design constraint: the *entire* game state is one pydantic ``GameState``; the
engine is a pure function ``get_next_state(state, action) -> GameState`` that
never mutates its input (see :mod:`baba.engine`).
"""

from __future__ import annotations

from enum import Enum, IntEnum

from pydantic import BaseModel, Field


class Direction(IntEnum):
    """A move/facing direction. Y is down-positive (row 0 at top)."""

    NONE = 0
    UP = 1
    DOWN = 2
    LEFT = 3
    RIGHT = 4

    @property
    def delta(self) -> tuple[int, int]:
        return _DELTA[self]


_DELTA: dict[Direction, tuple[int, int]] = {
    Direction.NONE: (0, 0),
    Direction.UP: (0, -1),
    Direction.DOWN: (0, 1),
    Direction.LEFT: (-1, 0),
    Direction.RIGHT: (1, 0),
}

_FROM_DELTA: dict[tuple[int, int], Direction] = {v: k for k, v in _DELTA.items()}


def direction_from_delta(dx: int, dy: int) -> Direction:
    return _FROM_DELTA.get((dx, dy), Direction.NONE)


class Status(str, Enum):
    """High-level game status."""

    PLAYING = "playing"
    WON = "won"
    LOST = "lost"


class Unit(BaseModel):
    """One entity occupying a tile. Multiple units may stack on a tile.

    For an *object* tile, ``name`` is the canonical noun ("BABA", "ROCK", ...).
    For a *text* tile (``is_text=True``), ``name`` is the word the tile spells
    ("BABA", "IS", "YOU", "AND", "NOT", ...).
    """

    id: int
    name: str
    is_text: bool = False
    x: int
    y: int
    dir: Direction = Direction.RIGHT
    inventory: list[str] = Field(default_factory=list)  # HAS payload (later milestone)

    @property
    def noun(self) -> str:
        """The noun a rule must name to refer to this unit.

        All text tiles are referred to by the noun ``TEXT``; objects by their
        own noun. (Mirrors Baba's "TEXT IS PUSH" default applying to all words.)
        """
        return "TEXT" if self.is_text else self.name


class GameState(BaseModel):
    """The complete game state. Serializable; compared by value."""

    width: int
    height: int
    units: list[Unit] = Field(default_factory=list)
    turn: int = 0
    status: Status = Status.PLAYING
    next_id: int = 1

    model_config = {"frozen": False}
