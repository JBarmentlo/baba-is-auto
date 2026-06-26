"""Rule parsing and queries.

Scans text units left->right (rows) and top->bottom (columns), emitting
``(subject, verb, object)`` rules. Supports ``AND`` chains on both sides and
``A IS B IS C`` chaining. NOT / conditions are a later milestone (M12).

Reference: bab-be-u game/parser.lua + the wiki Rule page (TEXT IS PUSH default).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .board import Board, WUnit
from .vocab import AND_OP, NOUN_SET, PROPERTY_SET, VERBS

Rule = tuple[str, str, str]  # (subject, verb, object)

INFINITE_LOOP_LIMIT = 100
TOO_COMPLEX_LIMIT = 1000


class RuleEngineError(RuntimeError):
    """Raised on the TOO COMPLEX / INFINITE LOOP safety guards."""


def _read_targets(tokens: list[str], i: int, allow_prop: bool) -> tuple[list[str], int]:
    """Read ``X [AND Y]*`` where each X is a noun (and a property if allowed)."""
    out: list[str] = []
    n = len(tokens)
    while i < n:
        w = tokens[i]
        ok = w in NOUN_SET or (allow_prop and w in PROPERTY_SET)
        if not ok:
            break
        out.append(w)
        i += 1
        if (
            i + 1 < n
            and tokens[i] == AND_OP
            and (tokens[i + 1] in NOUN_SET or (allow_prop and tokens[i + 1] in PROPERTY_SET))
        ):
            i += 1  # consume AND, continue the list
            continue
        break
    return out, i


def _parse_line(tokens: list[str]) -> list[Rule]:
    """Parse one contiguous run of text words into rules."""
    rules: list[Rule] = []
    n = len(tokens)
    i = 0
    while i < n:
        subjects, j = _read_targets(tokens, i, allow_prop=False)
        if not subjects or j >= n or tokens[j] not in VERBS:
            i += 1
            continue
        i = j
        while i < n and tokens[i] in VERBS:
            verb = tokens[i]
            i += 1
            objects, i = _read_targets(tokens, i, allow_prop=True)
            if not objects:
                break
            for s in subjects:
                for o in objects:
                    rules.append((s, verb, o))
            # chaining: "A IS B IS C" -> noun objects become next subjects
            noun_objs = [o for o in objects if o in NOUN_SET]
            if i < n and tokens[i] in VERBS and noun_objs:
                subjects = noun_objs
                continue
            break
    return rules


@dataclass
class RuleSet:
    rules: list[Rule] = field(default_factory=list)
    # derived indexes:
    _props: dict[str, set[str]] = field(default_factory=dict)  # noun -> {property}
    transforms: list[tuple[str, str]] = field(default_factory=list)  # (noun, noun)
    has_rules: list[tuple[str, str]] = field(default_factory=list)  # (noun, dropped noun)
    make_rules: list[tuple[str, str]] = field(default_factory=list)  # (noun, made noun)

    def _index(self) -> None:
        self._props.clear()
        self.transforms.clear()
        self.has_rules.clear()
        self.make_rules.clear()
        for s, v, o in self.rules:
            if v == "IS":
                if o in PROPERTY_SET:
                    self._props.setdefault(s, set()).add(o)
                elif o in NOUN_SET:
                    self.transforms.append((s, o))
            elif v == "HAS" and o in NOUN_SET:
                self.has_rules.append((s, o))
            elif v == "MAKE" and o in NOUN_SET:
                self.make_rules.append((s, o))

    # --- queries --- #
    def props_for(self, noun: str) -> set[str]:
        out = set(self._props.get(noun, ()))
        out |= self._props.get("ALL", set())
        return out

    def has_property(self, unit: WUnit, prop: str) -> bool:
        if prop in self._props.get(unit.noun, ()):
            return True
        if prop in self._props.get("ALL", ()):  # ALL applies to objects and text
            return True
        return False

    def nouns_with_property(self, prop: str) -> set[str]:
        return {s for s, props in self._props.items() if prop in props}

    def units_with_property(self, board: Board, prop: str) -> list[WUnit]:
        return [u for u in board.iter_units() if self.has_property(u, prop)]

    def has_rule(self, subject: str, verb: str, obj: str) -> bool:
        for s, v, o in self.rules:
            if (subject in ("?", s)) and (verb in ("?", v)) and (obj in ("?", o)):
                return True
        return False


# default rules that always exist (wiki: Base Rules)
DEFAULT_RULES: list[Rule] = [("TEXT", "IS", "PUSH")]


def parse_rules(board: Board) -> RuleSet:
    """Build the active :class:`RuleSet` from the board's text units."""
    found: list[Rule] = list(DEFAULT_RULES)

    def word_at(x: int, y: int) -> str | None:
        for u in board.tile(x, y):
            if u.is_text:
                return u.name
        return None

    # horizontal runs (left -> right)
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

    # vertical runs (top -> bottom)
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

    # dedupe, preserve order
    seen: set[Rule] = set()
    uniq: list[Rule] = []
    for r in found:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    rs = RuleSet(rules=uniq)
    rs._index()
    return rs
