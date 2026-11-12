"""The author-approved walks (Kei pass p10, Keira pass p8, copied as fixtures) keyed through the Maya control rig play
back as Kei's own bake: within 1 mm on the keys and 2 mm on every frame, the loop seam included."""
import json
import shutil
from pathlib import Path

import pytest

from kei.apps.maya_shot import key_pass, setup_shot
from kei.characters import load_character
from kei.sample import bake_continuous

import mayakit

FIX = Path(__file__).resolve().parent / "fixtures" / "walks"
WALKS = {"kei": "kei_walk_personality_p10.json", "keira": "keira_walk_personality_p8.json"}
pytestmark = pytest.mark.maya


@pytest.fixture(scope="module")
def keyed(tmp_path_factory):
    py = mayakit.mayapy()
    out = {}
    for name, fixture in WALKS.items():
        d = tmp_path_factory.mktemp(name)
        shot = json.loads((FIX / fixture).read_text(encoding="utf-8"))
        setup_shot(d, character=name, fps=shot.get("fps") or 24, mayapy=py)
        (d / "out_p1").mkdir()
        shutil.copyfile(FIX / fixture, d / "out_p1" / "shot.json")
        key_pass(d, "p1", mode="spline", mayapy=py)
        out[name] = (shot, json.loads((d / "out_p1" / "joints.json").read_text())["frames"])
    return out


@pytest.mark.parametrize("name", list(WALKS))
def test_the_approved_walk_plays_in_maya_as_kei_s_own(keyed, name):
    shot, maya = keyed[name]
    ch = load_character(name)
    kei = bake_continuous({**shot, "props": {**(shot.get("props") or {}), "proportions": ch.proportions}})
    keys = {int(k["f"]) for k in shot["keys"]}
    errs = [(max(abs(a - b) for a, b in zip(m["joints"][n], k["joints"][n])), m["f"], n)
            for m, k in zip(maya, kei) for n in k["joints"]]
    assert len(maya) == shot["frames"] + 1
    assert max(e for e in errs if e[1] in keys)[0] < 0.001, max(e for e in errs if e[1] in keys)
    assert max(errs)[0] < 0.002, max(errs)
