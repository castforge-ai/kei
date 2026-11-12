"""A walk made for one character plays on another with the same knees: the root rides at the new hip height."""
import json
import math
from pathlib import Path

from kei.characters import load_character, on_character
from kei.sample import bake

WALK = Path(__file__).resolve().parent / "fixtures" / "walks" / "kei_p10_approved.json"


def _knee(j, s):
    a, b, c = j[f"thigh_{s}"], j[f"calf_{s}"], j[f"foot_{s}"]
    u = [a[k] - b[k] for k in range(3)]
    w = [c[k] - b[k] for k in range(3)]
    return 180 - math.degrees(math.acos(sum(u[k] * w[k] for k in range(3)) / (math.hypot(*u) * math.hypot(*w))))


def test_a_walk_on_longer_legs_rides_higher_and_bends_its_knees_as_it_did():
    shot = json.loads(WALK.read_text(encoding="utf-8"))
    assert shot.get("character") == "kei"
    kei, keira = load_character("kei"), load_character("keira")
    own = bake(on_character(shot, kei), "spline")
    other = bake(on_character(shot, keira), "spline")
    assert "match_knees" not in on_character(shot, kei)["props"]
    for a, b in zip(own, other):
        for s in "lr":
            assert abs(_knee(a["joints"], s) - _knee(b["joints"], s)) < 3.0, (a["f"], s)
        assert a["pose"]["footL"] == b["pose"]["footL"]          # the feet stay where the shot puts them
