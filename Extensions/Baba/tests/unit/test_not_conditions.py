"""M12: NOT negation + conditions (ON / NEAR / FACING / LONELY)."""

from baba import Direction, Status
from tests.dsl import build, obj_pos


def test_not_removes_property():
    # BABA IS YOU but BABA IS NOT YOU cancels -> no YOU -> lost
    g = build("B", rules=["BABA IS YOU", "BABA IS NOT YOU"])
    assert g.status() is Status.LOST


def test_not_blocks_push():
    # ROCK IS PUSH but ROCK IS NOT PUSH -> rock not pushable -> baba blocked? rock just not push,
    # nothing else -> baba walks onto rock tile (not stop) -> baba moves, rock stays
    g = build("BR.", rules=["BABA IS YOU", "ROCK IS PUSH", "ROCK IS NOT PUSH"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "ROCK") == [(1, 0)]  # not pushed
    assert obj_pos(g, "BABA") == [(1, 0)]  # overlaps (rock isn't stop)


def test_cond_on():
    # BABA ON FLAG IS WIN: baba (you) becomes win only while standing on a flag.
    g = build("B.F", rules=["BABA IS YOU", "BABA ON FLAG IS WIN"])
    assert g.status() is Status.PLAYING
    g.do(Direction.RIGHT)
    assert g.status() is Status.PLAYING   # not on flag yet
    g.do(Direction.RIGHT)                  # baba steps onto flag -> ON true -> win
    assert obj_pos(g, "BABA") == [(2, 0)]
    assert g.status() is Status.WON


def test_cond_on_false_without_operand():
    g = build("B.F", rules=["BABA IS YOU", "BABA ON ROCK IS WIN"])  # no rock anywhere
    g.do(Direction.RIGHT)
    g.do(Direction.RIGHT)
    assert g.status() is Status.PLAYING   # never on a rock -> never win


def test_lonely():
    # baba isolated (far from the rule text rows) -> LONELY holds -> win
    g = build("B\n.\n.\n.", rules=["BABA IS YOU", "BABA LONELY IS WIN"])
    assert g.status() is Status.WON


def test_lonely_false_when_adjacent():
    g = build("BR", rules=["BABA IS YOU", "BABA LONELY IS WIN"])  # rock adjacent
    assert g.status() is Status.PLAYING
