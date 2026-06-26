"""Internal mutable working board used during a single turn.

Built from a :class:`~baba.state.GameState`, mutated by the turn pipeline, then
serialized back to a fresh ``GameState``. Plain dataclasses (not pydantic) for
speed and in-place mutation — pydantic is only the public boundary type.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import Direction, GameState, Unit


@dataclass
class WUnit:
    """Working unit (mutable counterpart of :class:`~baba.state.Unit`)."""

    id: int
    name: str
    is_text: bool
    x: int
    y: int
    dir: Direction = Direction.RIGHT
    inventory: list[str] = field(default_factory=list)
    removed: bool = False

    @property
    def noun(self) -> str:
        return "TEXT" if self.is_text else self.name


class Board:
    """A mutable board with positional/name/id indexes."""

    def __init__(self, width: int, height: int, next_id: int = 1) -> None:
        self.width = width
        self.height = height
        self.next_id = next_id
        self.units: list[WUnit] = []
        self._by_tile: dict[tuple[int, int], list[WUnit]] = {}
        self._by_name: dict[str, list[WUnit]] = {}
        self._by_id: dict[int, WUnit] = {}

    # --- construction / serialization --- #
    @classmethod
    def from_state(cls, state: GameState) -> "Board":
        b = cls(state.width, state.height, state.next_id)
        for u in state.units:
            b._insert(
                WUnit(u.id, u.name, u.is_text, u.x, u.y, u.dir, list(u.inventory))
            )
        return b

    def to_units(self) -> list[Unit]:
        out: list[Unit] = []
        for u in self.units:
            if u.removed:
                continue
            out.append(
                Unit(
                    id=u.id,
                    name=u.name,
                    is_text=u.is_text,
                    x=u.x,
                    y=u.y,
                    dir=u.dir,
                    inventory=list(u.inventory),
                )
            )
        return out

    # --- index maintenance --- #
    def _insert(self, u: WUnit) -> WUnit:
        self.units.append(u)
        self._by_tile.setdefault((u.x, u.y), []).append(u)
        self._by_name.setdefault(u.name, []).append(u)
        self._by_id[u.id] = u
        return u

    def add(
        self, name: str, x: int, y: int, *, is_text: bool = False,
        dir: Direction = Direction.RIGHT, inventory: list[str] | None = None,
    ) -> WUnit:
        u = WUnit(self.next_id, name, is_text, x, y, dir, list(inventory or []))
        self.next_id += 1
        return self._insert(u)

    def remove(self, u: WUnit) -> None:
        if u.removed:
            return
        u.removed = True
        tile = self._by_tile.get((u.x, u.y))
        if tile and u in tile:
            tile.remove(u)
        named = self._by_name.get(u.name)
        if named and u in named:
            named.remove(u)
        self._by_id.pop(u.id, None)
        # keep in self.units; filtered out in to_units / iter_units

    def move(self, u: WUnit, x: int, y: int) -> None:
        old = self._by_tile.get((u.x, u.y))
        if old and u in old:
            old.remove(u)
        u.x, u.y = x, y
        self._by_tile.setdefault((x, y), []).append(u)

    # --- queries --- #
    def tile(self, x: int, y: int) -> list[WUnit]:
        return list(self._by_tile.get((x, y), ()))

    def by_name(self, name: str) -> list[WUnit]:
        return [u for u in self._by_name.get(name, ()) if not u.removed]

    def iter_units(self):
        return (u for u in self.units if not u.removed)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height
