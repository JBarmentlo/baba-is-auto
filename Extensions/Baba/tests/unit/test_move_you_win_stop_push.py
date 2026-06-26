"""M0 mechanics: YOU movement, WIN, STOP, PUSH, plus purity & undo."""

from baba import Direction, Status, get_next_state
from tests.dsl import build, names_at, obj_pos


def test_you_moves_right():
    g = build("B..", rules=["BABA IS YOU"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == [(1, 0)]


def test_you_blocked_by_bounds():
    g = build("B", rules=["BABA IS YOU"])
    g.do(Direction.LEFT)
    assert obj_pos(g, "BABA") == [(0, 0)]


def test_stop_blocks():
    g = build("BW.", rules=["BABA IS YOU", "WALL IS STOP"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == [(0, 0)]  # wall blocks, baba stays


def test_wall_not_stop_is_passable():
    # without WALL IS STOP the wall object doesn't block (and isn't push)
    g = build("BW.", rules=["BABA IS YOU"])
    g.do(Direction.RIGHT)
    assert (1, 0) in obj_pos(g, "BABA")


def test_push_rock():
    g = build("BR..", rules=["BABA IS YOU", "ROCK IS PUSH"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == [(1, 0)]
    assert obj_pos(g, "ROCK") == [(2, 0)]


def test_push_chain_two_rocks():
    g = build("BRR.", rules=["BABA IS YOU", "ROCK IS PUSH"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == [(1, 0)]
    assert sorted(obj_pos(g, "ROCK")) == [(2, 0), (3, 0)]


def test_push_blocked_by_wall():
    g = build("BRW", rules=["BABA IS YOU", "ROCK IS PUSH", "WALL IS STOP"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == [(0, 0)]   # rock can't push into wall
    assert obj_pos(g, "ROCK") == [(1, 0)]


def test_push_blocked_by_bounds():
    g = build("..BR", rules=["BABA IS YOU", "ROCK IS PUSH"])  # rock at right edge
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == [(2, 0)]
    assert obj_pos(g, "ROCK") == [(3, 0)]


def test_win_on_flag():
    g = build("B.F", rules=["BABA IS YOU", "FLAG IS WIN"])
    g.do(Direction.RIGHT)
    assert g.status() is Status.PLAYING
    g.do(Direction.RIGHT)
    assert g.status() is Status.WON


def test_lost_when_no_you():
    g = build("F", rules=["FLAG IS WIN"])  # no YOU anywhere
    assert g.status() is Status.LOST


def test_get_next_state_is_pure():
    g = build("B..", rules=["BABA IS YOU"])
    s0 = g.state
    s1 = get_next_state(s0, Direction.RIGHT)
    babas0 = [(u.x, u.y) for u in s0.units if u.name == "BABA" and not u.is_text]
    babas1 = [(u.x, u.y) for u in s1.units if u.name == "BABA" and not u.is_text]
    assert babas0 == [(0, 0)]  # original unchanged
    assert babas1 == [(1, 0)]
    assert s0.turn == 0 and s1.turn == 1


def test_undo():
    g = build("B..", rules=["BABA IS YOU"])
    g.do(Direction.RIGHT)
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == [(2, 0)]
    g.undo()
    assert obj_pos(g, "BABA") == [(1, 0)]
    g.undo()
    assert obj_pos(g, "BABA") == [(0, 0)]


def test_transform_rule_parses_but_inert_in_m0():
    # NOUN IS NOUN should not crash even before transforms are implemented
    g = build("B.", rules=["BABA IS YOU", "BABA IS KEKE"])
    g.do(Direction.RIGHT)  # must not raise
    assert g.status() in (Status.PLAYING, Status.WON, Status.LOST)
