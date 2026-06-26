"""Rendering helpers: structured grid + human-readable text display."""

from __future__ import annotations

from .state import GameState
from .vocab import glyph


def to_grid(state: GameState) -> list[list[list[str]]]:
    """``rows[y][x]`` = list of stacked names. Text tiles are suffixed ``_TEXT``
    so callers can distinguish the word "BABA" from the object BABA."""
    grid: list[list[list[str]]] = [
        [[] for _ in range(state.width)] for _ in range(state.height)
    ]
    for u in state.units:
        if 0 <= u.y < state.height and 0 <= u.x < state.width:
            grid[u.y][u.x].append(u.name + "_TEXT" if u.is_text else u.name)
    return grid


def _cell_token(state: GameState, cells: dict) -> str:
    pass  # unused; kept for clarity


def render_text(state: GameState) -> str:
    """A readable monospaced board. Text tiles show their word; objects show a
    glyph; empty tiles show ``.``. Columns are padded to align."""
    # pick a token per cell: prefer text word, else object glyph, else empty
    top: list[list[str]] = [["." for _ in range(state.width)] for _ in range(state.height)]
    # objects first, then text overwrites (words are the salient thing to read)
    for u in sorted(state.units, key=lambda u: (u.is_text, u.id)):
        if not (0 <= u.y < state.height and 0 <= u.x < state.width):
            continue
        top[u.y][u.x] = u.name if u.is_text else glyph(u.name)
    width = max((len(tok) for row in top for tok in row), default=1)
    lines = [" ".join(tok.ljust(width) for tok in row).rstrip() for row in top]
    return "\n".join(lines)
