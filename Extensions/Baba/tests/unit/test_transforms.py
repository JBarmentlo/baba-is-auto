"""M1: NOUN IS NOUN transforms + HAS drops."""

from baba import Direction, Status
from tests.dsl import build, obj_pos


def test_basic_transform():
    g = build("R", rules=["ROCK IS BABA"])
    g.do(Direction.NONE)  # a turn applies transforms
    assert obj_pos(g, "ROCK") == []
    assert obj_pos(g, "BABA") == [(0, 0)]


def test_transform_to_empty_deletes():
    g = build("R", rules=["ROCK IS EMPTY"])
    g.do(Direction.NONE)
    assert obj_pos(g, "ROCK") == []
    assert obj_pos(g, "EMPTY") == []


def test_identity_blocks_transform():
    g = build("R", rules=["ROCK IS ROCK", "ROCK IS BABA"])
    g.do(Direction.NONE)
    assert obj_pos(g, "ROCK") == [(0, 0)]  # X IS X protects from X IS BABA
    assert obj_pos(g, "BABA") == []


def test_transform_then_win():
    # rock becomes flag; flag is win; baba walks onto it
    g = build("B.R", rules=["BABA IS YOU", "ROCK IS FLAG", "FLAG IS WIN"])
    g.do(Direction.NONE)  # rock -> flag
    assert obj_pos(g, "FLAG") == [(2, 0)]
    g.do(Direction.RIGHT)
    g.do(Direction.RIGHT)
    assert g.status() is Status.WON


def test_has_drops_on_empty():
    g = build("R", rules=["ROCK IS EMPTY", "ROCK HAS KEY"])
    g.do(Direction.NONE)
    assert obj_pos(g, "ROCK") == []
    assert obj_pos(g, "KEY") == [(0, 0)]  # rock destroyed -> drops key


def test_multi_target_transform():
    g = build("R", rules=["ROCK IS BABA AND KEKE"])
    g.do(Direction.NONE)
    assert obj_pos(g, "ROCK") == []
    assert obj_pos(g, "BABA") == [(0, 0)]
    assert obj_pos(g, "KEKE") == [(0, 0)]
