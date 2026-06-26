"""M3-M7: SINK, DEFEAT, HOT/MELT, OPEN/SHUT, WEAK, MAKE, FLOAT gating."""

from baba import Direction, Status
from tests.dsl import build, obj_pos


def test_sink_destroys_both():
    # baba walks right onto water; both sink
    g = build("BW", rules=["BABA IS YOU", "WALL IS SINK"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == []
    assert obj_pos(g, "WALL") == []


def test_sink_alone_survives():
    g = build("W", rules=["WALL IS SINK"])  # sink alone, nothing to sink
    g.do(Direction.NONE)
    assert obj_pos(g, "WALL") == [(0, 0)]


def test_defeat_kills_you():
    g = build("BS", rules=["BABA IS YOU", "SKULL IS DEFEAT"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == []        # baba defeated
    assert obj_pos(g, "SKULL") == [(1, 0)]  # skull stays
    assert g.status() is Status.LOST


def test_hot_melts():
    g = build("BL", rules=["BABA IS YOU", "BABA IS MELT", "LAVA IS HOT", "LAVA IS PUSH"])
    # baba is melt; lava is hot+push -> push lava, but baba steps where lava was? lava pushed right
    # simpler: baba melt walks onto hot lava (lava not push) -> baba melts
    g2 = build("BL", rules=["BABA IS YOU", "BABA IS MELT", "LAVA IS HOT"])
    g2.do(Direction.RIGHT)
    assert obj_pos(g2, "BABA") == []        # melt + hot tile -> baba melts


def test_open_shut_annihilate():
    g = build("BD", rules=["BABA IS YOU", "BABA IS OPEN", "DOOR IS SHUT"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == []
    assert obj_pos(g, "DOOR") == []


def test_weak_breaks_on_overlap():
    # baba pushes weak rock into a wall -> ... simpler: baba steps onto weak object tile
    g = build("BR", rules=["BABA IS YOU", "ROCK IS WEAK"])
    g.do(Direction.RIGHT)  # baba moves onto rock's tile (rock not push/stop) -> rock weak-breaks
    assert obj_pos(g, "ROCK") == []
    assert obj_pos(g, "BABA") == [(1, 0)]


def test_make_spawns():
    g = build("R", rules=["ROCK MAKE KEY"])
    g.do(Direction.NONE)
    assert obj_pos(g, "KEY") == [(0, 0)]
    assert obj_pos(g, "ROCK") == [(0, 0)]  # rock remains


def test_float_blocks_sink():
    # floating baba does not sink in (non-floating) water
    g = build("BW", rules=["BABA IS YOU", "BABA IS FLOAT", "WALL IS SINK"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == [(1, 0)]   # survived (different float layer)
    assert obj_pos(g, "WALL") == [(1, 0)]


def test_float_same_layer_sinks():
    g = build("BW", rules=["BABA IS YOU", "BABA IS FLOAT", "WALL IS SINK", "WALL IS FLOAT"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == []  # both floating -> same layer -> sink
    assert obj_pos(g, "WALL") == []
