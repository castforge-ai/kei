import json
import math
from pathlib import Path

import pytest

from kei.rig import BONES, DEFAULT_POSE, PROPORTIONS, bone_lengths, over_reach, solve

GOLD = json.loads((Path(__file__).parent / "fixtures" / "rig" / "poses.json").read_text(encoding="utf-8"))
TOL = 1e-6


def dist(a, b):
    return math.dist(a, b)


def test_constants_match_the_kit():
    assert list(BONES) == GOLD["bones"]
    assert DEFAULT_POSE == GOLD["default"]
    assert PROPORTIONS == GOLD["proportions"]


def test_enough_golden_poses():
    assert len(GOLD["poses"]) >= 12


def test_golden_poses_cover_the_edge_branches():
    names = {p["name"] for p in GOLD["poses"]}
    # foot heading blend and past vertical, IK with no FK bend plane, the antiparallel knee pole transport
    assert {"foot_pitch_80", "foot_pitch_100", "arm_ik_straight_elbow", "ankle_above_hip"} <= names
    sweep = [p for p in GOLD["poses"] if p["name"].startswith("knee_sweep_pitch_")]
    assert len(sweep) >= 9 and all(abs(p["pose"]["footL"][3] - 0.6) < 1e-12 for p in sweep)


def test_knee_sweep_with_a_pitched_foot_does_not_flip():
    sweep = sorted((p for p in GOLD["poses"] if p["name"].startswith("knee_sweep_pitch_")),
                   key=lambda p: p["pose"]["footL"][2])
    knees = [solve(p["pose"])["calf_l"] for p in sweep]
    assert all(dist(a, b) < 0.1 for a, b in zip(knees, knees[1:]))


@pytest.mark.parametrize("case", GOLD["poses"], ids=[p["name"] for p in GOLD["poses"]])
def test_golden_parity(case):
    joints = solve(case["pose"], case.get("proportions"))
    assert set(case["joints"]) <= set(joints)
    worst = max(dist(joints[n], p) for n, p in case["joints"].items())
    assert worst < TOL, case["name"]
    assert abs(over_reach(case["pose"], case.get("proportions")) - case["over"]) < TOL


@pytest.mark.parametrize("case", GOLD["poses"], ids=[p["name"] for p in GOLD["poses"]])
def test_bone_lengths_are_constant(case):
    for name, (now, rest) in bone_lengths(case["pose"], case.get("proportions")).items():
        assert abs(now - rest) < 1e-6, (case["name"], name, now, rest)


def test_length_scale_changes_the_length():
    lengths = bone_lengths({**DEFAULT_POSE, "legSL": 1.2, "armSR": 0.8, "sq": 0.7})
    assert abs(lengths["thigh_l"][0] - PROPORTIONS["thigh"] * 1.2) < 1e-9
    assert abs(lengths["upperarm_r"][0] - PROPORTIONS["upperarm"] * 0.8) < 1e-9
    assert abs(lengths["spine_03"][0] - PROPORTIONS["spine"][2] * 0.7) < 1e-9


def test_a_partial_pose_takes_the_default_stand():
    assert solve({"yaw": 0.4}) == solve({**DEFAULT_POSE, "yaw": 0.4})


def test_short_channels_take_the_default_tail():
    full = solve({**DEFAULT_POSE, "footL": [-0.1, 0.08, 0.2, 0, 0]})
    assert solve({"footL": [-0.1, 0.08, 0.2]}) == full


def test_foot_out_of_reach_straightens_toward_the_target():
    pose = {**DEFAULT_POSE, "root": [0, 1.0, 0], "footL": [-0.1, 0.08, 2.5, 0, 0]}
    j = solve(pose)
    assert all(math.isfinite(v) for p in j.values() for v in p)
    reach = PROPORTIONS["thigh"] + PROPORTIONS["calf"]
    assert abs(dist(j["thigh_l"], j["foot_l"]) - (reach - 1e-4)) < 1e-9
    assert over_reach(pose) > 1.0
    # straight: the knee is on the hip to ankle line (the rig keeps 0.1 mm of bend, so the knee never locks)
    hip, knee, ankle = j["thigh_l"], j["calf_l"], j["foot_l"]
    assert abs(dist(hip, knee) + dist(knee, ankle) - dist(hip, ankle)) < 2e-4
    # toward the target: the ankle lies on the hip to target line
    tgt = pose["footL"][:3]
    u = [t - h for t, h in zip(tgt, hip)]
    v = [a - h for a, h in zip(ankle, hip)]
    cos = sum(a * b for a, b in zip(u, v)) / (math.hypot(*u) * math.hypot(*v))
    assert cos > 1 - 1e-12


def test_foot_on_the_hip_does_not_fail():
    j = solve({**DEFAULT_POSE, "footL": [-0.1, 0.95, 0, 0, 0]})
    assert all(math.isfinite(v) for p in j.values() for v in p)


def test_no_knee_flip_when_the_ankle_passes_the_hip():
    knees, prev = [], None
    for i in range(-40, 41):
        z = i / 100
        j = solve({**DEFAULT_POSE, "root": [0, 0.9, 0], "footL": [-0.1, 0.3, z, 0, 0]})
        hip, knee, ankle = j["thigh_l"], j["calf_l"], j["foot_l"]
        # the knee bends forward of the hip to ankle line
        line = [a - h for a, h in zip(ankle, hip)]
        to_knee = [k - h for k, h in zip(knee, hip)]
        t = sum(a * b for a, b in zip(line, to_knee)) / sum(a * a for a in line)
        off = [k - (h + t * l) for k, h, l in zip(knee, hip, line)]
        assert off[2] > 0, z
        if prev is not None:
            assert dist(knee, prev) < 0.03, z
        prev = knee
        knees.append(knee)


def test_com_lies_inside_the_figure():
    c = solve(DEFAULT_POSE)["com"]
    assert 0.8 < c[1] < 1.2 and abs(c[0]) < 0.05
