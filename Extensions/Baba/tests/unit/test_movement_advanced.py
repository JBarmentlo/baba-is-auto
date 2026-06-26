"""M2/M8/M9/M10/M11: MOVE, PULL, SHIFT, FALL, SWAP."""

from baba import Direction
from tests.dsl import build, obj_pos


def test_move_autonomous_steps():
    g = build("K...", rules=["KEKE IS MOVE"])  # keke faces right by default
    g.do(Direction.NONE)
    assert obj_pos(g, "KEKE") == [(1, 0)]
    g.do(Direction.NONE)
    assert obj_pos(g, "KEKE") == [(2, 0)]


def test_move_reverses_at_wall():
    g = build("K.W", rules=["KEKE IS MOVE", "WALL IS STOP"])
    g.do(Direction.NONE)  # right to (1,0)
    assert obj_pos(g, "KEKE") == [(1, 0)]
    g.do(Direction.NONE)  # blocked by wall -> reverse, move left
    assert obj_pos(g, "KEKE") == [(0, 0)]


def test_pull_trails():
    # baba moves right; rock behind (to the left) is pulled along
    g = build("RB..", rules=["BABA IS YOU", "ROCK IS PULL"])
    g.do(Direction.RIGHT)
    assert obj_pos(g, "BABA") == [(2, 0)]
    assert obj_pos(g, "ROCK") == [(1, 0)]


def test_shift_conveyor():
    # baba sits on a shift tile facing right -> gets shifted right
    g = build("", rules=["BABA IS YOU", "TILE IS SHIFT"])
    # place baba and tile on same cell via a custom state is awkward in DSL;
    # use overlap by transform: skip — instead test shift moves a co-located object.
    # Build: tile object and baba object on same tile not expressible; use MOVE-like check.
    # Minimal: a SHIFT tile with a rock on it moves the rock.
    from baba import GameState, Unit, evaluate
    from baba.game import Game
    units = [
        Unit(id=1, name="TILE", is_text=False, x=1, y=0),
        Unit(id=2, name="ROCK", is_text=False, x=1, y=0),
        Unit(id=3, name="TILE", is_text=True, x=0, y=1),
        Unit(id=4, name="IS", is_text=True, x=1, y=1),
        Unit(id=5, name="SHIFT", is_text=True, x=2, y=1),
    ]
    g = Game(evaluate(GameState(width=4, height=2, units=units, next_id=6)))
    g.do(Direction.NONE)
    assert (2, 0) in obj_pos(g, "ROCK")  # rock shifted right by the tile


def test_fall_gravity():
    g = build(
        "B.\n..\n..",
        rules=["BABA IS YOU", "BABA IS FALL"],
    )
    g.do(Direction.NONE)
    # baba falls toward bottom (max y within grid+rule rows). It should be lower than y=0.
    ys = [y for (x, y) in obj_pos(g, "BABA")]
    assert ys and min(ys) > 0


def test_swap():
    g = build("BR", rules=["BABA IS YOU", "BABA IS SWAP", "ROCK IS STOP"])
    g.do(Direction.RIGHT)  # swap past the (stop) rock
    assert obj_pos(g, "BABA") == [(1, 0)]
    assert obj_pos(g, "ROCK") == [(0, 0)]
