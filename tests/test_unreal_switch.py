"""kei unreal switch: the matched switch is written into the pass only when the editor measured it within MATCH_CM,
with the old mode pinned on the frame before and the new mode and the switch on the frame (tested live 2026-11-20 on
CR_Mannequin_Body, UE 5.8: both arms and a leg, both ways, 0.0 cm at the switch)."""
import json

import pytest

from kei.apps import unreal_switch
from kei.sample import ShotError


def _shot(tmp_path):
    d = tmp_path / "s" / "out_p1"
    d.mkdir(parents=True)
    (d / "shot.json").write_text(json.dumps({"rig": "unreal", "fps": 24, "frames": 20, "keys": [
        {"f": 0, "tangent": "spline", "upperarm_l_fk_ctrl.rotation.z": 0.0},
        {"f": 20, "tangent": "spline", "upperarm_l_fk_ctrl.rotation.z": 40.0}]}))
    return tmp_path / "s"


def _editor(monkeypatch, gap=0.0, was_ik=False):
    calls = []

    def run(client, name, inp):
        calls.append((name, inp))
        if name != "match_switch.py":
            return {}
        return {"gap_cm": gap, "was_ik": was_ik,
                "values": {"hand_l_ik_ctrl": {"location.x": 1.5, "rotation.z": 3.0, "scale.x": 1.0},
                           "arm_l_fk_ik_switch": {"value": True}},
                "hold": {"9": {"upperarm_l_fk_ctrl": {"rotation.z": 18.0}},
                         "10": {"upperarm_l_fk_ctrl": {"rotation.z": 20.0}}}}
    monkeypatch.setattr(unreal_switch, "run_script", run)
    monkeypatch.setattr(unreal_switch, "pass_sequence", lambda shot, p: "/Game/Kei/s/LS_s_p1_1")
    monkeypatch.setattr(unreal_switch, "tick", lambda: None)
    return calls


def test_a_matched_switch_pins_the_old_mode_and_keys_the_new_one(tmp_path, monkeypatch):
    root = _shot(tmp_path)
    calls = _editor(monkeypatch)
    r = unreal_switch.switch(None, root, "p1", "arm_l", "ik", 10)
    assert r["written"] and r["controls"] == ["hand_l_ik_ctrl"]
    keys = {k["f"]: k for k in json.loads((root / "out_p1" / "shot.json").read_text())["keys"]}
    assert keys[9]["arm_l_fk_ik_switch.value"] is False and keys[9]["upperarm_l_fk_ctrl.rotation.z"] == 18.0
    assert keys[10]["arm_l_fk_ik_switch.value"] is True and keys[10]["hand_l_ik_ctrl.location.x"] == 1.5
    assert keys[10]["upperarm_l_fk_ctrl.rotation.z"] == 20.0 and "hand_l_ik_ctrl.scale.x" not in keys[10]
    assert [c[0] for c in calls] == ["open_sequence.py", "match_switch.py"]


def test_a_gap_over_the_limit_writes_nothing(tmp_path, monkeypatch):
    root = _shot(tmp_path)
    before = (root / "out_p1" / "shot.json").read_text()
    _editor(monkeypatch, gap=3.2)
    r = unreal_switch.switch(None, root, "p1", "arm_l", "ik", 10)
    assert not r["written"] and "3.20 cm" in r["why"]
    assert (root / "out_p1" / "shot.json").read_text() == before


def test_a_limb_already_in_that_mode_writes_nothing(tmp_path, monkeypatch):
    root = _shot(tmp_path)
    _editor(monkeypatch, was_ik=True)
    r = unreal_switch.switch(None, root, "p1", "arm_l", "ik", 10)
    assert not r["written"] and "already IK" in r["why"]


def test_bad_limb_and_mode_are_refused(tmp_path):
    root = _shot(tmp_path)
    with pytest.raises(ShotError, match="arm_l"):
        unreal_switch.switch(None, root, "p1", "neck", "ik", 10)
    with pytest.raises(ShotError, match="ik or fk"):
        unreal_switch.switch(None, root, "p1", "arm_l", "both", 10)
