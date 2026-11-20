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


def free(shot):
    """The kit's own tangents, unclamped: the parity tests compare against its output."""
    return {**shot, "tangents": "free"}


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
    assert worst_joint(bake(free(case["shot"]), mode), case[mode]) < TOL


@pytest.mark.parametrize("case", GOLD, ids=[c["name"] for c in GOLD])
def test_bake_continuous_parity(case):
    assert worst_joint(bake_continuous(free(case["shot"])), case["continuous"]) < TOL


@pytest.mark.parametrize("case", GOLD, ids=[c["name"] for c in GOLD])
def test_sampler_between_frames(case):
    at = sampler(free(case["shot"]), "spline")
    for g in case["between"]:
        assert max(abs(a - b) for a, b in zip(flat(at(g["f"])), flat(g["pose"]))) < 1e-12, g["f"]


def test_golden_shots_cover_the_edge_cases():
    assert {"two_key_loop", "travel_ik"} <= set(SHOTS)
    assert len(SHOTS["two_key_loop"]["shot"]["keys"]) == 2 and SHOTS["two_key_loop"]["shot"]["loop"]
    assert any(k.get("ikR", [0, 0, 0, 0])[3] > 0 for k in SHOTS["travel_ik"]["shot"]["keys"])


def test_bake_default_mode_is_spline():
    for case in GOLD:
        assert worst_joint(bake(free(case["shot"])), case["spline"]) < TOL, case["name"]


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


HOLD = {"rig": "v4", "fps": 24, "frames": 30, "loop": False, "keys": [
    {"f": 0, "root": [0, 0.98, 0]}, {"f": 12, "root": [0, 0.60, 0]}, {"f": 20, "root": [0, 0.70, 0]},
    {"f": 24, "root": [0, 0.70, 0]}, {"f": 30, "root": [0, 0.98, 0]}]}


def test_a_held_pose_stays_held_on_the_spline():
    frames = bake(HOLD, "spline")
    assert all(abs(frames[f]["pose"]["root"][1] - 0.70) < 1e-9 for f in range(20, 25))
    old = bake(free(HOLD), "spline")
    assert min(old[f]["pose"]["root"][1] for f in range(20, 25)) < 0.69, "the free tangents dip: the old behaviour"


def test_no_frame_passes_beyond_its_two_keys():
    frames = bake(HOLD, "spline")
    keys = [k["f"] for k in HOLD["keys"]]
    vals = {k["f"]: k["root"][1] for k in HOLD["keys"]}
    for a, b in zip(keys, keys[1:]):
        lo, hi = sorted((vals[a], vals[b]))
        assert all(lo - 1e-9 <= frames[f]["pose"]["root"][1] <= hi + 1e-9 for f in range(a, b + 1)), (a, b)


def test_a_peak_eases_flat_and_a_move_stays_smooth():
    shot = {"rig": "v4", "fps": 24, "frames": 20, "loop": False, "keys": [
        {"f": 0, "root": [0, 0.9, 0]}, {"f": 10, "root": [0, 1.1, 0]}, {"f": 20, "root": [0, 0.9, 0]}]}
    y = [fr["pose"]["root"][1] for fr in bake(shot, "spline")]
    assert max(y) == pytest.approx(1.1) and y[9] < 1.1 and y[11] < 1.1
    assert all(b >= a for a, b in zip(y[:11], y[1:11]))


def _loop(keys, frames=12, **extra):
    from kei.sample import sampler
    shot = {"rig": "v4", "fps": 24, "frames": frames, "loop": True, "keys": keys, **extra}
    return sampler(shot, "spline")


def test_a_loop_whose_first_key_is_late_wraps_instead_of_holding():
    at = _loop([{"f": 3, "yaw": 0.0}, {"f": 9, "yaw": 0.6}])
    before = [at(f)["yaw"] for f in range(0, 4)]
    after = [at(f)["yaw"] for f in range(9, 13)]
    assert len(set(round(v, 6) for v in before)) > 1          # frames 0-2 move toward the first key, no hold
    assert after[0] == 0.6 and 0.0 < after[1] < 0.6           # past the last key the curve heads back
    assert abs(at(12)["yaw"] - at(0)["yaw"]) < 1e-9           # the loop meets itself


def test_a_closed_loop_plays_as_before():
    at = _loop([{"f": 0, "yaw": 0.2}, {"f": 6, "yaw": -0.2}, {"f": 12, "yaw": 0.2}])
    assert at(0)["yaw"] == 0.2 and at(6)["yaw"] == -0.2 and abs(at(12)["yaw"] - 0.2) < 1e-9


def test_open_loop_tangents_use_the_neighbour_across_the_wrap():
    at = _loop([{"f": 2, "yaw": 0.0}, {"f": 6, "yaw": 0.5}, {"f": 10, "yaw": 0.0}])
    # f2 and f10 are both 0 with the peak between them: the curve dips below 0 nowhere across the wrap
    assert all(at(f)["yaw"] >= -1e-9 for f in range(0, 13))


def test_a_shot_baked_twice_is_baked_once_and_each_caller_gets_its_own_copy(monkeypatch):
    import kei.sample as sample
    shot = SHOTS["two_key_loop"]["shot"]
    calls = []
    real = sample._lift
    monkeypatch.setattr(sample, "_lift", lambda s: calls.append(1) or real(s))
    sample._BAKED.clear()
    a = sample.bake(shot)
    a[0]["joints"]["head"] = (9, 9, 9)
    b = sample.bake(shot)
    assert len(calls) == 1 and b[0]["joints"]["head"] != (9, 9, 9)
    sample.bake({**shot, "frames": 8, "loop": False})
    assert len(calls) == 2
