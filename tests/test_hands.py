"""Fingers in the rig: bone names, the curl split, the spread, the presets and the palm plane."""
import math

import pytest

from kei import hands
from kei.rig import (ALL_BONES, BONES, DEFAULT_POSE, FINGER_BONES, FINGER_POSE, PARENTS, PoseError, check_channels,
                     full_pose, skeleton, solve)

FINGERS = ("index", "middle", "ring", "pinky")


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def unit(a):
    n = math.sqrt(dot(a, a))
    return tuple(x / n for x in a)


def angle(a, b):
    return math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b)))))


def direction(B, name):
    return sub(B[name].tail, B[name].head)


def test_finger_bones_have_the_mannequin_names_under_the_hand():
    for s in "lr":
        for f in FINGERS:
            assert PARENTS[f"{f}_metacarpal_{s}"] == f"hand_{s}"
            assert PARENTS[f"{f}_01_{s}"] == f"{f}_metacarpal_{s}"
            assert PARENTS[f"{f}_02_{s}"] == f"{f}_01_{s}"
            assert PARENTS[f"{f}_03_{s}"] == f"{f}_02_{s}"
        assert PARENTS[f"thumb_01_{s}"] == f"hand_{s}"
        assert PARENTS[f"thumb_02_{s}"] == f"thumb_01_{s}"
        assert PARENTS[f"thumb_03_{s}"] == f"thumb_02_{s}"
    assert len(FINGER_BONES) == 2 * (4 * 4 + 3)
    assert ALL_BONES == BONES + FINGER_BONES
    assert set(PARENTS) == set(ALL_BONES)


def test_every_parent_comes_before_its_child():
    seen = set()
    for b in ALL_BONES:
        assert PARENTS[b] is None or PARENTS[b] in seen, b
        seen.add(b)


def test_fingers_are_additions_the_rig4_joints_do_not_move():
    pose = {**DEFAULT_POSE, "armR": [0.8, 0.4, 0.2], "fingersR": hands.preset("fist")}
    assert solve(pose) == solve({**DEFAULT_POSE, "armR": [0.8, 0.4, 0.2]})
    B = skeleton(pose)
    j = solve(pose)
    for n in BONES:
        assert math.dist(B[n].head, j[n]) < 1e-12, n


def test_the_finger_channels_are_checked():
    check_channels({"fingersL": [0.5, 0.2], "fingersR": hands.preset("open")})
    with pytest.raises(PoseError, match="fingersL"):
        check_channels({"fingersL": [0.1] * 11})
    with pytest.raises(PoseError, match="fingersR"):
        check_channels({"fingersR": "fist"})
    assert full_pose({})["fingersL"] == FINGER_POSE["fingersL"]
    assert len(FINGER_POSE["fingersL"]) == 10


def test_the_chains_are_joined():
    B = skeleton({"fingersL": hands.preset("fist"), "fingersR": hands.preset("ok")})
    for n in FINGER_BONES:
        p = PARENTS[n]
        if not p.startswith("hand_"):
            assert math.dist(B[n].head, B[p].tail) < 1e-12, n


def test_finger_lengths_do_not_change_with_the_pose():
    a = skeleton({"fingersR": hands.preset("open")})
    b = skeleton({"fingersR": hands.preset("fist"), "armR": [1.2, 0.3, 0.5], "handR": [0.5, 0.2]})
    for n in FINGER_BONES:
        la, lb = math.dist(a[n].head, a[n].tail), math.dist(b[n].head, b[n].tail)
        assert abs(la - lb) < 1e-9, n


def test_bone_frames_are_orthonormal_with_y_along_the_bone():
    B = skeleton({"fingersR": hands.preset("ok"), "fingersL": hands.preset("point")})
    for n in ALL_BONES:
        X, Y, Z = B[n].frame
        for a in (X, Y, Z):
            assert abs(dot(a, a) - 1) < 1e-9, n
        assert abs(dot(X, Y)) < 1e-9 and abs(dot(Y, Z)) < 1e-9 and abs(dot(X, Z)) < 1e-9, n
        d = sub(B[n].tail, B[n].head)
        if dot(d, d) > 1e-12:
            assert angle(d, Y) < 1e-6, n


@pytest.mark.parametrize("side", "LR")
def test_a_curl_splits_one_two_one_and_a_half(side):
    s = side.lower()
    curl = 1.2
    B = skeleton({f"fingers{side}": [0, 0] + [curl, 0] * 4})
    rest = skeleton({f"fingers{side}": [0] * 10})
    for f in FINGERS:
        # the knuckle: the proximal phalanx against where it points with no curl
        mcp = angle(direction(rest, f"{f}_01_{s}"), direction(B, f"{f}_01_{s}"))
        pip = angle(direction(B, f"{f}_01_{s}"), direction(B, f"{f}_02_{s}"))
        dip = angle(direction(B, f"{f}_02_{s}"), direction(B, f"{f}_03_{s}"))
        assert abs(mcp - curl / 4.5) < 1e-9, f
        assert abs(pip - curl * 2 / 4.5) < 1e-9 and abs(dip - curl * 1.5 / 4.5) < 1e-9, f


def palm_side(B, s, point):
    """How far a point lies on the palm side of the palm plane (through the knuckles, normal toward the palm)."""
    X, Y, Z = B[f"hand_{s}"].frame
    sg = 1 if s == "r" else -1
    palm = tuple(sg * v for v in X)
    return dot(sub(point, B[f"middle_01_{s}"].head), palm)


@pytest.mark.parametrize("side", "lr")
def test_a_curl_bends_toward_the_palm(side):
    B = skeleton({f"fingers{side.upper()}": [0, 0] + [1.5, 0] * 4})
    for f in FINGERS:
        assert palm_side(B, side, B[f"{f}_03_{side}"].tail) > 0.02, f


@pytest.mark.parametrize("side", "lr")
def test_no_fingertip_goes_through_the_palm_in_a_fist(side):
    B = skeleton({f"fingers{side.upper()}": hands.preset("fist")})
    for f in FINGERS:
        tip = B[f"{f}_03_{side}"].tail
        assert palm_side(B, side, tip) > 0.005, f
        # and the fist is closed: the tip comes back behind its own knuckle line
        Y = B[f"hand_{side}"].frame[1]
        assert dot(sub(tip, B[f"{f}_01_{side}"].head), Y) < 0.01, f


def spread_angle(B, s):
    return angle(direction(B, f"index_01_{s}"), direction(B, f"pinky_01_{s}"))


def test_spread_fans_the_fingers():
    a = spread_angle(skeleton({"fingersR": [0] * 10}), "r")
    b = spread_angle(skeleton({"fingersR": [0, 0, 0, 0.3, 0, 0.3, 0, 0.3, 0, 0.3]}), "r")
    c = spread_angle(skeleton({"fingersR": [0, 0, 0, -0.1, 0, -0.1, 0, -0.1, 0, -0.1]}), "r")
    assert c < a < b
    assert b - a > 0.3


def test_the_hands_mirror():
    B = skeleton({"fingersL": hands.preset("ok"), "fingersR": hands.preset("ok")})
    for n in FINGER_BONES:
        if n.endswith("_l"):
            l, r = B[n].tail, B[n[:-2] + "_r"].tail
            assert abs(l[0] + r[0]) < 1e-9 and abs(l[1] - r[1]) < 1e-9 and abs(l[2] - r[2]) < 1e-9, n


def test_the_thumb_opposes_toward_the_palm():
    a = skeleton({"fingersR": [0, 0] + [0] * 8})
    b = skeleton({"fingersR": [0, 1.0] + [0] * 8})
    assert palm_side(b, "r", b["thumb_03_r"].tail) > palm_side(a, "r", a["thumb_03_r"].tail) + 0.02


def test_presets():
    assert set(hands.PRESETS) == {"relaxed", "open", "fist", "point", "ok", "palm-up"}
    for name in hands.PRESETS:
        v = hands.preset(name)
        assert len(v) == 10 and all(isinstance(x, float) for x in v)
        check_channels({"fingersL": v})
    assert hands.hand_pose("fist", "L") == {"fingersL": hands.preset("fist")}
    assert hands.hand_pose("open", "both") == {"fingersL": hands.preset("open"), "fingersR": hands.preset("open")}
    with pytest.raises(ValueError, match="claw"):
        hands.preset("claw")
    assert FINGER_POSE["fingersL"] == hands.preset("relaxed")


def test_ok_closes_the_ring_and_point_points():
    B = skeleton({"fingersR": hands.preset("ok"), "fingersL": hands.preset("point")})
    assert math.dist(B["index_03_r"].tail, B["thumb_03_r"].tail) < 0.02
    # point: the index straight, the others curled
    straight = angle(direction(B, "index_01_l"), direction(B, "index_03_l"))
    assert straight < 0.1
    for f in ("middle", "ring", "pinky"):
        assert palm_side(B, "l", B[f"{f}_03_l"].tail) > 0.01


def test_relaxed_matches_the_measured_relaxed_hand():
    """A relaxed real hand reads the knuckle 15 to 21 deg, the middle joint 33 to 40 and the tip 25 to 31."""
    v = hands.preset("relaxed")
    curl = v[4]      # the middle finger
    mcp, pip, dip = (math.degrees(curl * k / 4.5) for k in (1, 2, 1.5))
    assert 15 <= mcp <= 21 and 33 <= pip <= 40 and 25 <= dip <= 31
