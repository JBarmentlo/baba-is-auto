"""Thin stateful convenience wrapper over the pure functional core.

Holds a history of states so undo is just popping the stack. This is what the
MCP server uses.
"""

from __future__ import annotations

from .engine import evaluate, get_next_state
from .loaders import load_intgrid, load_keke
from .render import render_text, to_grid
from .rules import parse_rules
from .board import Board
from .state import Direction, GameState, Status


class Game:
    def __init__(self, source: "str | GameState", fmt: str = "intgrid") -> None:
        if isinstance(source, GameState):
            initial = evaluate(source)
        elif fmt == "intgrid":
            initial = load_intgrid(source)
        elif fmt == "keke":
            initial = load_keke(source)
        else:
            raise ValueError(f"unknown fmt {fmt!r}")
        self._initial = initial
        self._history: list[GameState] = [initial]

    # --- state access --- #
    @property
    def state(self) -> GameState:
        return self._history[-1]

    def status(self) -> Status:
        return self.state.status

    def grid(self) -> list[list[list[str]]]:
        return to_grid(self.state)

    def text(self) -> str:
        return render_text(self.state)

    def rules(self) -> list[tuple[str, str, str]]:
        return list(parse_rules(Board.from_state(self.state)).rules)

    # --- actions --- #
    def do(self, action: Direction) -> GameState:
        self._history.append(get_next_state(self.state, action))
        return self.state

    def undo(self, steps: int = 1) -> GameState:
        for _ in range(steps):
            if len(self._history) > 1:
                self._history.pop()
        return self.state

    def reset(self) -> GameState:
        self._history = [self._initial]
        return self.state
