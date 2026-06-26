"""Assert our vocabulary tables still match the C++ .def enum ordering."""

import re
from pathlib import Path

import pytest

from baba import vocab

DEF_DIR = Path(__file__).resolve().parents[4] / "Includes/baba-is-auto/Enums"


def _names(deffile: str) -> list[str]:
    text = (DEF_DIR / deffile).read_text()
    return re.findall(r"X\(([A-Z0-9_]+)\)", text)


@pytest.mark.skipif(not DEF_DIR.exists(), reason="C++ enum .def files not present")
def test_vocab_matches_def_files():
    assert vocab.NOUNS == _names("NounType.def")
    assert vocab.OPS == _names("OpType.def")
    assert vocab.PROPERTIES == _names("PropertyType.def")
    icons = _names("IconType.def")
    assert icons == ["ICON_" + n for n in vocab.NOUNS]


def test_intgrid_codes():
    assert vocab.intgrid_code(4) == ("BABA", True)      # noun text
    assert vocab.intgrid_code(67) == ("IS", True)       # op
    assert vocab.intgrid_code(77) == ("YOU", True)      # property
    assert vocab.intgrid_code(114) == ("BABA", False)   # ICON_BABA object
    assert vocab.intgrid_code(132) is None              # ICON_EMPTY floor
    assert vocab.intgrid_code(0) is None                # marker
    assert vocab.ICON_EMPTY_CODE == 132
