"""Rule parsing and queries.

Scans text units left->right (rows) and top->bottom (columns), emitting rules of
``[NOT] NOUN (COND [NOT] NOUN | LONELY)*  VERB  [NOT] (PROP|NOUN) (AND ...)``.
Supports ``AND`` chains, ``A IS B IS C`` chaining, ``NOT`` negation, and the
conditions ``ON / NEAR / FACING / LONELY``. ``TEXT IS PUSH`` is a default rule.

Conditions/NOT are resolved into a per-unit effective-property map at parse time
(parse_rules has the board), so ``has_property(unit, prop)`` stays board-free for
callers. Reference: bab-be-u game/parser.lua + the wiki Rule/Conditions pages.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .board import Board, WUnit
from .vocab import AND_OP, CONDITIONS, NOT_OP, NOUN_SET, PROPERTY_SET, VERBS

Rule = tuple[str, str, str]  # display form (subject, verb, object[, "NOT "+])

INFINITE_LOOP_LIMIT = 100
TOO_COMPLEX_LIMIT = 1000


class RuleEngineError(RuntimeError):
    """Raised on the TOO COMPLEX / INFINITE LOOP safety guards."""


@dataclass
class Cond:
    name: str  # ON | NEAR | FACING | LONELY
    operand: str | None = None
    neg: bool = False


@dataclass
class ParsedRule:
    subject: str
    verb: str
    obj: str
    subj_neg: bool = False
    obj_neg: bool = False
    conds: list[Cond] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# line parser
# --------------------------------------------------------------------------- #
def _read_subject(tokens, i):
    """Read ``[NOT] NOUN (COND [NOT] NOUN | LONELY)*``. Returns (subject|None, i)."""
    n = len(tokens)
    neg = False
    if i < n and tokens[i] == NOT_OP:
        neg = True
        i += 1
    if i >= n or tokens[i] not in NOUN_SET:
        return None, i
    noun = tokens[i]
    i += 1
    conds: list[Cond] = []
    while i < n and tokens[i] in CONDITIONS:
        cname = tokens[i]
        i += 1
        if cname == "LONELY":
            conds.append(Cond("LONELY"))
            continue
        cneg = False
        if i < n and tokens[i] == NOT_OP:
            cneg = True
            i += 1
        if i < n and tokens[i] in NOUN_SET:
            conds.append(Cond(cname, tokens[i], cneg))
            i += 1
        else:
            break
    return (noun, neg, conds), i


def _read_objects(tokens, i):
    """Read ``[NOT] (PROP|NOUN) (AND [NOT] (PROP|NOUN))*``. Returns (list, i)."""
    out: list[tuple[str, bool]] = []
    n = len(tokens)
    while i < n:
        neg = False
        j = i
        if tokens[j] == NOT_OP:
            neg = True
            j += 1
        if j < n and (tokens[j] in PROPERTY_SET or tokens[j] in NOUN_SET):
            out.append((tokens[j], neg))
            i = j + 1
            if i < n and tokens[i] == AND_OP:
                i += 1
                continue
            break
        break
    return out, i


def _parse_line(tokens: list[str]) -> list[ParsedRule]:
    rules: list[ParsedRule] = []
    n = len(tokens)
    i = 0
    while i < n:
        subj, j = _read_subject(tokens, i)
        if subj is None or j >= n or tokens[j] not in VERBS:
            i += 1
            continue
        noun, sneg, conds = subj
        i = j
        subjects = [(noun, sneg, conds)]
        # subject AND chains (share conditions of the clause)
        # (parsed simply: re-handled below per verb-clause)
        while i < n and tokens[i] in VERBS:
            verb = tokens[i]
            i += 1
            objs, i = _read_objects(tokens, i)
            if not objs:
                break
            for (sn, sg, cs) in subjects:
                for (o, og) in objs:
                    rules.append(ParsedRule(sn, verb, o, sg, og, list(cs)))
            noun_objs = [o for (o, og) in objs if o in NOUN_SET and not og]
            if i < n and tokens[i] in VERBS and noun_objs:
                subjects = [(o, False, []) for o in noun_objs]
                continue
            break
    return rules


# --------------------------------------------------------------------------- #
# condition evaluation
# --------------------------------------------------------------------------- #
def _eval_cond(board: Board, unit: WUnit, cond: Cond) -> bool:
    if cond.name == "LONELY":
        for o in board.tile(unit.x, unit.y):
            if o is not unit:
                return cond.neg
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if any(True for _ in board.tile(unit.x + dx, unit.y + dy)):
                return cond.neg
        return not cond.neg
    z = cond.operand
    if cond.name == "ON":
        hit = any(o is not unit and o.noun == z for o in board.tile(unit.x, unit.y))
    elif cond.name == "NEAR":
        hit = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if any(o is not unit and o.noun == z for o in board.tile(unit.x + dx, unit.y + dy)):
                    hit = True
    elif cond.name == "FACING":
        from .state import Direction
        ddx, ddy = unit.dir.delta if isinstance(unit.dir, Direction) else (0, 0)
        hit = any(o.noun == z for o in board.tile(unit.x + ddx, unit.y + ddy))
    else:
        hit = True
    return (not hit) if cond.neg else hit


# --------------------------------------------------------------------------- #
# RuleSet
# --------------------------------------------------------------------------- #
@dataclass
class RuleSet:
    parsed: list[ParsedRule] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)  # display triples
    transforms: list[tuple[str, str]] = field(default_factory=list)
    has_rules: list[tuple[str, str]] = field(default_factory=list)
    make_rules: list[tuple[str, str]] = field(default_factory=list)
    _pos: dict[str, set[str]] = field(default_factory=dict)  # unconditional positive props
    _unit_props: dict[int, set[str]] = field(default_factory=dict)  # per-unit effective props

    def _index(self, board: Board) -> None:
        neg: dict[str, set[str]] = {}
        cond_rules: list[ParsedRule] = []
        for r in self.parsed:
            if r.conds:
                cond_rules.append(r)
                continue
            if r.verb == "IS":
                if r.obj in PROPERTY_SET:
                    (neg if r.obj_neg else self._pos).setdefault(r.subject, set()).add(r.obj)
                elif r.obj in NOUN_SET and not r.obj_neg and not r.subj_neg:
                    self.transforms.append((r.subject, r.obj))
            elif r.verb == "HAS" and r.obj in NOUN_SET:
                self.has_rules.append((r.subject, r.obj))
            elif r.verb == "MAKE" and r.obj in NOUN_SET:
                self.make_rules.append((r.subject, r.obj))

        # per-unit effective properties (unconditional first, then conditional)
        for u in board.iter_units():
            props = set(self._pos.get(u.noun, ())) | set(self._pos.get("ALL", ()))
            props -= neg.get(u.noun, set())
            props -= neg.get("ALL", set())
            for r in cond_rules:
                if r.verb != "IS" or r.obj not in PROPERTY_SET:
                    continue
                if r.subject not in (u.noun, "ALL"):
                    continue
                if all(_eval_cond(board, u, c) for c in r.conds):
                    if r.obj_neg:
                        props.discard(r.obj)
                    else:
                        props.add(r.obj)
            self._unit_props[u.id] = props

    # --- queries --- #
    def props_for(self, noun: str) -> set[str]:
        return set(self._pos.get(noun, ())) | set(self._pos.get("ALL", ()))

    def has_property(self, unit: WUnit, prop: str) -> bool:
        cached = self._unit_props.get(unit.id)
        if cached is not None:
            return prop in cached
        # fallback for units created after parse (no conditions/NOT applied)
        return prop in self.props_for(unit.noun)

    def nouns_with_property(self, prop: str) -> set[str]:
        return {n for n, props in self._pos.items() if prop in props}

    def units_with_property(self, board: Board, prop: str) -> list[WUnit]:
        return [u for u in board.iter_units() if self.has_property(u, prop)]

    def has_rule(self, subject: str, verb: str, obj: str) -> bool:
        for s, v, o in self.rules:
            if (subject in ("?", s)) and (verb in ("?", v)) and (obj in ("?", o.replace("NOT ", ""))):
                return True
        return False


DEFAULT_RULES = [ParsedRule("TEXT", "IS", "PUSH")]


def parse_rules(board: Board) -> RuleSet:
    found: list[ParsedRule] = list(DEFAULT_RULES)

    def word_at(x: int, y: int) -> str | None:
        for u in board.tile(x, y):
            if u.is_text:
                return u.name
        return None

    for y in range(board.height):
        run: list[str] = []
        for x in range(board.width):
            w = word_at(x, y)
            if w is None:
                if run:
                    found += _parse_line(run)
                    run = []
            else:
                run.append(w)
        if run:
            found += _parse_line(run)

    for x in range(board.width):
        run = []
        for y in range(board.height):
            w = word_at(x, y)
            if w is None:
                if run:
                    found += _parse_line(run)
                    run = []
            else:
                run.append(w)
        if run:
            found += _parse_line(run)

    if len(found) > TOO_COMPLEX_LIMIT:
        raise RuleEngineError("TOO COMPLEX")

    # dedupe parsed rules; build display triples
    seen: set[tuple] = set()
    parsed: list[ParsedRule] = []
    triples: list[Rule] = []
    for r in found:
        key = (r.subject, r.subj_neg, r.verb, r.obj, r.obj_neg,
               tuple((c.name, c.operand, c.neg) for c in r.conds))
        if key in seen:
            continue
        seen.add(key)
        parsed.append(r)
        triples.append((r.subject, r.verb, ("NOT " + r.obj) if r.obj_neg else r.obj))

    rs = RuleSet(parsed=parsed, rules=triples)
    rs._index(board)
    return rs
