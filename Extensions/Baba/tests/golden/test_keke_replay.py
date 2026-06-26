"""Golden corpus ratchet: replay each Keke level's recorded solution.

Per level: passes if the solution wins under the current engine, else xfail.
A summary test asserts the total win-count never drops below BASELINE — bump
BASELINE as milestones land so the corpus is a regression ratchet.

Baselines:  M0 (you/win/stop/push) = 150 / 201.  M1 (+transforms/HAS) = 162 / 201.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baba import Direction, Status
from baba.game import Game

# _refs is a sibling of the repo: <workspace>/baba/_refs
KEKE_DIR = (
    Path(__file__).resolve().parents[5] / "_refs/KekeCompetition/Keke_JS/json_levels"
)
PACKS = ["demo_LEVELS.json", "test_LEVELS.json", "full_biy_LEVELS.json"]
BASELINE = 162  # min Keke levels whose solution must still win (ratchet; bump per milestone)

_DIR = {"u": Direction.UP, "d": Direction.DOWN, "l": Direction.LEFT,
        "r": Direction.RIGHT, "s": Direction.NONE}


def _load_levels():
    out = []
    if not KEKE_DIR.exists():
        return out
    for pack in PACKS:
        p = KEKE_DIR / pack
        if not p.exists():
            continue
        for lvl in json.loads(p.read_text()).get("levels", []):
            if lvl.get("ascii") and lvl.get("solution"):
                out.append((pack, lvl))
    return out


_LEVELS = _load_levels()


def _replay_wins(lvl) -> bool:
    g = Game(lvl["ascii"], fmt="keke")
    for ch in lvl["solution"].strip().lower():
        if ch in _DIR:
            g.do(_DIR[ch])
            if g.status() is Status.WON:
                return True
    return g.status() is Status.WON


@pytest.mark.skipif(not _LEVELS, reason="Keke corpus not present")
@pytest.mark.parametrize(
    "pack,lvl", _LEVELS, ids=[f"{p.split('_')[0]}:{l['id']}" for p, l in _LEVELS]
)
def test_keke_solution(pack, lvl):
    if not _replay_wins(lvl):
        pytest.xfail("solution not solved at current milestone")


@pytest.mark.skipif(not _LEVELS, reason="Keke corpus not present")
def test_keke_winrate_ratchet():
    wins = sum(_replay_wins(lvl) for _, lvl in _LEVELS)
    assert wins >= BASELINE, f"Keke win-rate regressed: {wins} < {BASELINE}"
