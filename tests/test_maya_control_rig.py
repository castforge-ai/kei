"""Task 3 of plan 6, in Maya: the control rig an animator moves by hand, on Kei and on Keira. One mayapy job builds
both characters (tests/maya/check_control_rig.py); the tests read its report. Skipped, with the reason, without Maya."""
import json
import re
from pathlib import Path

import pytest

from kei.apps.maya_controls import joints_from_samples
from kei.characters import load_character, rest_pose
from kei.rig import full_pose, solve
from kei.sample import bake

import mayakit
from maya_poses import POSE, ROLLS

REPO = Path(__file__).resolve().parents[1]
NAMES = ["kei", "keira"]
pytestmark = pytest.mark.maya


@pytest.fixture(scope="module")
def built():
    return mayakit.run_script("check_control_rig.py", repo=str(REPO))


def _kei(name, pose):
    ch = load_character(name)
    return solve(full_pose({**rest_pose(ch), **pose}), ch.proportions)


def _err(maya_joints, kei_joints, names=None):
    names = names or maya_joints.keys()
    return max((max(abs(a - b) for a, b in zip(maya_joints[n], kei_joints[n])), n) for n in names)


def _first(samples, name):
    return joints_from_samples(samples, name)[0]["joints"]


@pytest.mark.parametrize("name", NAMES)
def test_every_joint_is_driven_by_a_control_and_none_is_keyed_by_itself(built, name):
    assert built[name]["undriven"] == []


@pytest.mark.parametrize("name", NAMES)
def test_at_rest_every_control_at_zero_gives_the_rest_pose(built, name):
    err, where = _err(_first(built[name]["rest"], name), _kei(name, {}))
    assert err < 0.001, (where, err)


@pytest.mark.parametrize("name", NAMES)
def test_a_posed_character_matches_kei_s_own_rig(built, name):
    """The values Kei keys put every joint, the fingers' parents, tips and heels where Kei's own rig puts them."""
    ch = load_character(name)
    err, where = _err(_first(built[name]["posed_ik"], name), solve(full_pose(POSE), ch.proportions))
    assert err < 0.001, (where, err)


@pytest.mark.parametrize("name", NAMES)
def test_switching_ik_and_fk_moves_no_hand_or_foot(built, name):
    a, b = _first(built[name]["posed_ik"], name), _first(built[name]["posed_switched"], name)
    ends = ["hand_l", "hand_r", "foot_l", "foot_r", "hand_l_tip", "hand_r_tip", "ball_l_tip", "ball_r_tip"]
    err, where = _err(a, b, ends)
    assert err < 0.001, (where, err)


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("roll", list(ROLLS))
def test_the_foot_roll_turns_as_kei_s_own_foot(built, name, roll):
    ch = load_character(name)
    got = _first(built[name]["rolls"][roll], name)
    err, where = _err(got, solve(full_pose({**rest_pose(ch), **ROLLS[roll]}), ch.proportions))
    assert err < 0.001, (roll, where, err)


@pytest.mark.parametrize("name", NAMES)
def test_the_roll_keeps_its_pivot_on_the_ground(built, name):
    rolls = {k: _first(built[name]["rolls"][k], name) for k in ("heel", "ball", "toe")}
    rest = _first(built[name]["rest"], name)
    for key, point in (("heel", "heel_l"), ("ball", "ball_l"), ("toe", "ball_l_tip")):
        assert abs(rolls[key][point][1] - rest[point][1]) < 0.001, (key, point)


@pytest.mark.parametrize("name", NAMES)
def test_a_walk_keyed_on_the_controls_plays_as_kei_s_own_walk(built, name):
    walk = json.loads((REPO / "examples" / "stepped_walk" / "out_blocking" / "shot.json").read_text())
    ch = load_character(name)
    kei = bake({**walk, "props": {"proportions": ch.proportions}}, "spline")
    got = joints_from_samples(built[name]["walk"], name)
    keys = {k["f"] for k in walk["keys"]}
    worst_key = max(_err(g["joints"], k["joints"]) for g, k in zip(got, kei) if g["f"] in keys)
    worst = max(_err(g["joints"], k["joints"]) for g, k in zip(got, kei))
    assert worst_key[0] < 0.001, worst_key
    assert worst[0] < 0.002, worst


@pytest.mark.parametrize("name", NAMES)
def test_names_colours_and_locks_follow_the_rules(built, name):
    rig = built[name]["map"]
    blue, red, yellow = [0.1, 0.45, 1.0], [1.0, 0.15, 0.15], [1.0, 0.85, 0.1]
    for c in rig["controls"]:
        short = c["name"].split(":")[-1]
        assert re.fullmatch(r"[lrc]_[a-z0-9_]+_ctl", short), short
        colour = built[name]["colours"][c["name"]]
        want = {"l": blue, "r": red, "c": yellow}[short[0]]
        assert max(abs(a - b) for a, b in zip(colour, want)) < 1e-6, short
        assert "visibility" in built[name]["locked"][c["name"]], short
        if c["role"] == "fk":
            assert "translateX" not in c["keyable"] and "scaleX" not in c["keyable"], short
    assert any(c["name"].endswith("l_index_02_fk_ctl") for c in rig["controls"])
    assert built[name]["set_keys"]["clipped"] == []
