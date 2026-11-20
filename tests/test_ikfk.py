"""Matched IK and FK switching: a pole channel per arm, an FK leg, matched switches with no snap, and Maya's switch
following Kei's."""
import json
import math
import random

import pytest

from kei.cli import main
from kei.ikfk import MATCH_TOL, match
from kei.rig import solve
from kei.sample import bake

ARM = {"armL": [0.6, 0.3, 0.1], "elbowL": [0.9, 0.1], "footR": [0.12, 0.1, 0.15, 0, 0], "kneeR": 0.1}


def test_the_new_channels_off_change_nothing():
    plain = solve(ARM)
    off = solve({**ARM, "poleL": [1, 2, 3, 0], "legFKR": [0.4, 0.1, 0, 0.6, 0]})
    assert all(math.dist(plain[n], off[n]) < 1e-12 for n in plain)


def test_the_pole_channel_aims_the_elbow_and_keeps_the_wrist_on_its_target():
    base = {**ARM, "ikL": [-0.3, 1.1, 0.35, 1.0]}
    out = solve({**base, "poleL": [-1.5, 1.0, -0.2, 1.0]})
    inn = solve({**base, "poleL": [0.5, 1.0, 0.3, 1.0]})
    assert math.dist(out["hand_l"], (-0.3, 1.1, 0.35)) < 1e-3 and math.dist(inn["hand_l"], (-0.3, 1.1, 0.35)) < 1e-3
    assert out["lowerarm_l"][0] < inn["lowerarm_l"][0] - 0.05          # the elbow follows the pole out to the left


def test_an_fk_leg_puts_the_knee_and_ankle_where_its_angles_say():
    bent = solve({"legFKL": [0.8, 0, 0, 1.2, 1.0]})
    straight = solve({"legFKL": [0.0, 0, 0, 0.0, 1.0]})
    hip_y = straight["thigh_l"][1]
    assert straight["foot_l"][1] < hip_y - 0.8 and abs(straight["foot_l"][2] - straight["thigh_l"][2]) < 1e-6
    assert bent["calf_l"][2] > bent["thigh_l"][2] + 0.2                # the thigh swings forward
    assert bent["foot_l"][2] < bent["calf_l"][2]                       # the shin folds back under the knee


@pytest.mark.parametrize("limb,to,extra", [
    ("armL", "ik", {}), ("armL", "fk", {"ikL": [-0.3, 1.1, 0.35, 1], "poleL": [-0.6, 1.0, 0.0, 1]}),
    ("legR", "fk", {}), ("legR", "ik", {"legFKR": [0.5, 0.1, 0.05, 0.8, 1]}),
    ("armR", "ik", {"armR": [-0.4, 0.5, -0.2], "elbowR": [1.3, 0.3]}),
    ("legL", "fk", {"footL": [-0.15, 0.3, 0.3, 0.2, 0.1], "rollL": [0.2, 0, 0.6]}),
])
def test_every_switch_matches_the_pose_it_switches_from(limb, to, extra):
    pose = {**ARM, **extra}
    got, rep = match(pose, None, limb, to)
    assert rep["matched"] and rep["gap_m"] <= MATCH_TOL
    before, after = solve(pose), solve({**pose, **got})
    for n in ("hand_l", "hand_r", "foot_l", "foot_r", "calf_l", "calf_r", "lowerarm_l", "lowerarm_r"):
        assert math.dist(before[n], after[n]) < 0.003, n


def test_random_poses_match_both_ways():
    rnd = random.Random(7)
    for _ in range(8):
        pose = {"armL": [rnd.uniform(-0.5, 1.2), rnd.uniform(0, 0.8), rnd.uniform(-0.3, 0.3)],
                "elbowL": [rnd.uniform(0.2, 1.6), rnd.uniform(-0.3, 0.3)]}
        ik, rep = match(pose, None, "armL", "ik")
        assert rep["matched"]
        back, rep2 = match({**pose, **ik}, None, "armL", "fk")
        assert rep2["matched"], rep2


def _shot(tmp_path):
    shot = {"rig": "v4", "fps": 24, "frames": 20, "keys": [
        {"f": 0, "armL": [0.1, 0.1, 0], "elbowL": [0.3, 0]},
        {"f": 20, "armL": [1.0, 0.4, 0.1], "elbowL": [1.2, 0.1]}]}
    d = tmp_path / "s" / "out_p1"
    d.mkdir(parents=True)
    (d / "shot.json").write_text(json.dumps(shot))
    return tmp_path / "s", shot


def test_kei_keys_match_switches_with_no_snap(tmp_path, capsys):
    root, shot = _shot(tmp_path)
    before = bake(shot, "spline")
    assert main(["keys", str(root), "p1", "match", "--frame", "10", "--channel", "armL", "--value", "ik"]) == 0
    assert "matched within" in capsys.readouterr().out
    new = json.loads((root / "out_p1" / "shot.json").read_text())
    k9, k10 = (next(k for k in new["keys"] if k["f"] == f) for f in (9, 10))
    assert k10["ikL"][3] == 1.0 and k10["poleL"][3] == 1.0 and k9.get("ikL", [0, 0, 0, 0])[3] == 0
    after = bake(new, "spline")
    for f in (9, 10):
        a, b = before[f]["joints"], after[f]["joints"]
        assert math.dist(a["hand_l"], b["hand_l"]) < 0.003 and math.dist(a["lowerarm_l"], b["lowerarm_l"]) < 0.003


def test_match_refuses_a_bad_limb(tmp_path, capsys):
    root, _ = _shot(tmp_path)
    assert main(["keys", str(root), "p1", "match", "--frame", "10", "--channel", "neck", "--value", "ik"]) == 1
    assert "the limb is one of armL, armR, legL, legR" in capsys.readouterr().err


def test_mayas_switch_follows_keis_weights():
    from kei.apps.maya_controls import pose_to_controls
    from test_maya_controls_map import _rig
    rig = _rig()
    plain = pose_to_controls({}, rig)
    switched = pose_to_controls({"ikL": [-0.3, 1.1, 0.35, 1.0], "legFKR": [0.4, 0, 0, 0.6, 1.0]}, rig)
    key = lambda d, name: next(v for k, v in d.items() if k.endswith(name))   # noqa: E731
    assert key(plain, "l_arm_settings_ctl.ikFk") == 0.0 and key(plain, "r_leg_settings_ctl.ikFk") == 1.0
    assert key(switched, "l_arm_settings_ctl.ikFk") == 1.0 and key(switched, "r_leg_settings_ctl.ikFk") == 0.0
    assert key(switched, "r_foot_ik_ctl.translateY") != key(plain, "r_foot_ik_ctl.translateY")
