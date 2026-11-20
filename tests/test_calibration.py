"""The checks against the author's verdicts: shots the author judged poor must raise faults, an approved one none.

tests/fixtures/verdicts/ holds shots with the author's blind verdict. Those files are the maintainers' own and are not
in the public repository, so the verdict tests skip there; the approved walk (tests/fixtures/walks/kei_p10_approved.json)
is public and always runs. Each new verdict the author gives belongs in that folder, so every threshold change is
tested against what the author saw. Where the checks rank two poor shots differently from the author, that is
recorded below, not hidden.
"""
import json
from pathlib import Path

import pytest

from kei.body_check import measure
from kei.characters import load_character, on_character
from kei.style import apply

ROOT = Path(__file__).resolve().parent.parent
VERDICTS = sorted((ROOT / "tests" / "fixtures" / "verdicts").glob("*.json"))


def _faults(shot: dict) -> list[dict]:
    ch = load_character("kei")
    report = measure(on_character(shot, ch), "spline", ch.proportions, ch.height)
    apply(report["flags"], None, None)          # judged as realistic: the verdict was on the motion itself
    return [f for f in report["flags"] if not f.get("note")]


@pytest.mark.parametrize("path", VERDICTS, ids=[p.stem for p in VERDICTS])
def test_a_shot_the_author_judged_poor_raises_faults(path):
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["verdict"] == "poor"
    faults = _faults(rec["shot"])
    kinds = {f["check"] for f in faults}
    assert len([f for f in faults if f.get("measure") in NEW]) >= 5, (len(faults), kinds)


NEW = ("spacing_pop_ratio", "arc_wobble_deg", "jolt_g")


def test_the_approved_walk_raises_none_of_the_new_arc_and_jolt_faults():
    walk = json.loads((ROOT / "tests" / "fixtures" / "walks" / "kei_p10_approved.json").read_text(encoding="utf-8"))
    faults = _faults(walk)
    assert not [f for f in faults if f.get("measure") in NEW], faults
    # recorded: the older one-frame kink rule (60 deg) flags this approved walk's hand and toe tips, so pushed may
    # still relax arc kinks (kei.style.PUSH_EXEMPT leaves them out)
    assert [f for f in faults if f.get("measure") == "arc_kink_deg"]


def test_the_known_disagreement_is_recorded():
    """The arc checks find more pops in the shot the author ranked first. Kept visible on purpose."""
    if len(VERDICTS) < 2:
        pytest.skip("the author's verdict fixtures are not in this checkout")
    pops = {}
    for p in VERDICTS:
        rec = json.loads(p.read_text(encoding="utf-8"))
        pops[rec["blind_rank"]] = sum(1 for f in _faults(rec["shot"]) if f.get("measure") == "spacing_pop_ratio")
    assert pops[1] >= pops[2]
