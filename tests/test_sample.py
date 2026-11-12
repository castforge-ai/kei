import json
import math
from pathlib import Path

import pytest

from kei.rig import DEFAULT_POSE
from kei.sample import bake, bake_continuous, normalize_keys, sampler

GOLD = json.loads((Path(__file__).parent / "fixtures" / "rig" / "shots.json").read_text(encoding="utf-8"))["shots"]
SHOTS = {c["name"]: c for c in GOLD}
TOL = 1e-6


def flat(pose):
    out = []
    for c in DEFAULT_POSE:
        v = pose[c]
        out.extend(v if isinstance(v, list) else [v])
    return out


def worst_joint(frames, gold):
    assert [fr["f"] for fr in frames] == [g["f"] for g in gold]
    return max(math.dist(fr["joints"][n], p) for fr, g in zip(frames, gold) for n, p in g["joints"].items())


@pytest.mark.parametrize("case", GOLD, ids=[c["name"] for c in GOLD])
def test_normalize_keys_matches_the_kit(case):
    keys = normalize_keys(case["shot"])
    assert [k["f"] for k in keys] == [k["f"] for k in case["keys"]]
    for k, g in zip(keys, case["keys"]):
        assert k["tangent"] == g["tangent"]
        assert max(abs(a - b) for a, b in zip(flat(k), flat(g))) < 1e-12


@pytest.mark.parametrize("mode", ["step", "linear", "spline"])
@pytest.mark.parametrize("case", GOLD, ids=[c["name"] for c in GOLD])
def test_bake_parity(case, mode):
    assert worst_joint(bake(case["shot"], mode), case[mode]) < TOL


@pytest.mark.parametrize("case", GOLD, ids=[c["name"] for c in GOLD])
def test_bake_continuous_parity(case):
    assert worst_joint(bake_continuous(case["shot"]), case["continuous"]) < TOL


@pytest.mark.parametrize("case", GOLD, ids=[c["name"] for c in GOLD])
def test_sampler_between_frames(case):
    at = sampler(case["shot"], "spline")
    for g in case["between"]:
        assert max(abs(a - b) for a, b in zip(flat(at(g["f"])), flat(g["pose"]))) < 1e-12, g["f"]


def test_golden_shots_cover_the_edge_cases():
    assert {"two_key_loop", "travel_ik"} <= set(SHOTS)
    assert len(SHOTS["two_key_loop"]["shot"]["keys"]) == 2 and SHOTS["two_key_loop"]["shot"]["loop"]
    assert any(k.get("ikR", [0, 0, 0, 0])[3] > 0 for k in SHOTS["travel_ik"]["shot"]["keys"])


def test_bake_default_mode_is_spline():
    for case in GOLD:
        assert worst_joint(bake(case["shot"]), case["spline"]) < TOL, case["name"]


def test_a_missing_channel_carries_over_and_the_first_key_takes_the_stand():
    keys = normalize_keys(SHOTS["reach"]["shot"])
    assert keys[0]["spine"] == DEFAULT_POSE["spine"]
    assert keys[0]["footL"] == DEFAULT_POSE["footL"]
    assert keys[2]["armR"] == [1.6, 0.3, 0.2]
    assert keys[2]["spine"] == [0.3, 0, 0.2]
    # a short list takes the default tail, not the tail of the key before
    assert keys[1]["elbowR"] == [0.4, 0]
    assert keys[2]["footR"] == [0.12, 0.08, 0.2, 0, 0]
    assert keys[2]["rollR"] == [-0.2, 0, 0.6]


def test_travelling_loop_seam_is_not_eased():
    frames = bake_continuous(SHOTS["walk"]["shot"])
    z = [fr["pose"]["root"][2] for fr in frames]
    n = SHOTS["walk"]["shot"]["frames"]
    before, across = z[n - 1] - z[n - 2], z[n + 1] - z[n]
    # the root keeps its forward speed through the seam: no slow in at the last key, no slow out at the first
    assert across > 0.04 and before > 0.04
    assert abs(across - before) < 0.01


def test_step_holds_each_key():
    frames = bake(SHOTS["reach"]["shot"], "step")
    assert frames[7]["pose"]["armR"] == [0.2, 0.1, 0]
    assert frames[8]["pose"]["armR"] == [1.6, 0.3, 0.2]
