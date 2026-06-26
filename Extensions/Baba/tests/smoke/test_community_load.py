"""Smoke: every community level loads + survives one turn without crashing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baba import Direction
from baba.game import Game

CANDIDATES = [
    Path("/mnt/vast/data-to-ala/joep/baba/baba_community_levels.jsonl"),
    Path("/mnt/vast/data-to-ala/joep/baba/baba_alphababa.jsonl"),
]


def _load_rows():
    rows = []
    for p in CANDIDATES:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                mc = d.get("map_content")
                if mc:
                    rows.append((p.name, d.get("instance_id", "?"), mc))
    return rows


_ROWS = _load_rows()


@pytest.mark.skipif(not _ROWS, reason="community level datasets not present")
@pytest.mark.parametrize(
    "fname,iid,map_content", _ROWS, ids=[f"{n}:{i}" for n, i, _ in _ROWS]
)
def test_community_level_loads_and_steps(fname, iid, map_content):
    g = Game(map_content, fmt="intgrid")
    assert g.state.width > 0 and g.state.height > 0
    # one turn in each direction must not raise
    for d in (Direction.RIGHT, Direction.NONE):
        g.do(d)
