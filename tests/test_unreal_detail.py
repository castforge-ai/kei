"""The fingers and toes come back with the body: their curl and lift, and the flags a wrong control sign leaves."""
import json
import math

from kei.apps.unreal_detail import DETAIL_BONES, measure
from kei.apps.unreal_readback import read_back
from test_unreal_readback import keyed_shot, standing
from unrealkit import FakeEditor


def finger(curl_deg, base=(0.0, 0.0, 0.0)):
    """A finger chain in Kei metres, lying along +z, its joints bent about the x axis; positive bends toward -y
    (the rest hand's own curl)."""
    pts, d, a = [base], 0.03, 0.0
    for _ in range(3):
        a += math.radians(curl_deg)
        x, y, z = pts[-1]
        pts.append((x, y - d * math.sin(a), z + d * math.cos(a)))
    return dict(zip(("index_metacarpal_l", "index_01_l", "index_02_l", "index_03_l"), pts))


def foot(lift_deg):
    """A left foot on the floor, with its index toe raised by lift_deg."""
    a = math.radians(lift_deg)
    return {"foot_l": (0.0, 0.08, 0.0), "ball_l": (0.0, 0.0, 0.14),
            "indextoe_01_l": (0.0, 0.0, 0.15), "indextoe_02_l": (0.0, 0.03 * math.sin(a), 0.15 + 0.03 * math.cos(a))}


def test_the_mannequin_finger_and_toe_bones_are_asked_for_on_both_sides():
    for b in ("index_metacarpal_l", "pinky_03_r", "thumb_01_l", "bigtoe_02_r", "littletoe_01_l"):
        assert b in DETAIL_BONES


def test_a_finger_closing_past_its_rest_curl_is_positive_and_bent_backward_is_negative_and_flagged():
    rest = finger(15)
    r = measure([{"f": 0, "bones": finger(15)}, {"f": 1, "bones": finger(40)}, {"f": 2, "bones": finger(-20)}], rest)
    rows = dict((f, v) for f, v in r["curl"]["index_02_l"])
    assert rows[0] == 15.0 and rows[1] == 40.0 and rows[2] == -20.0
    assert [f["part"] for f in r["flags"]] == ["index_01_l", "index_02_l"]
    assert "wrong way" in r["flags"][0]["what"] and r["flags"][0]["frames"] == [2, 2]


def test_a_toe_lift_is_measured_against_the_foot_and_a_flick_is_told_from_digging_in():
    rest = foot(0)
    up = measure([{"f": 0, "bones": foot(20)}], rest)
    assert up["lift"]["indextoe_l"][0][1] == 20.0 and up["flags"] == []
    down = measure([{"f": 3, "bones": foot(-15)}], rest)
    assert down["summary"]["lift_range"]["indextoe_l"] == [-15.0, -15.0]
    assert "dig in" in down["flags"][0]["what"]                     # the toe tip is at the floor
    air = {n: (x, y + 0.1, z) for n, (x, y, z) in foot(-15).items()}
    assert "flick" in measure([{"f": 3, "bones": air}], rest)["flags"][0]["what"]


def test_the_readback_writes_the_detail_beside_the_joints_and_never_into_them(tmp_path):
    shot = keyed_shot(tmp_path)

    def with_hands(f):
        b = standing(f)
        for n, (x, y, z) in finger(15 + f).items():           # Kei metres to the mannequin's rig centimetres
            b[n] = [-x * 100, z * 100, y * 100 + 90]
        return b
    ed = FakeEditor(bones=with_hands)
    with ed.server():
        dst = read_back(ed.client(), shot, "blocking", "kei")
    data = json.loads(dst.read_text())
    assert "index_02_l" not in data["frames"][0]["joints"] and "index_02_l" in data["frames"][0]["detail"]
    report = json.loads((shot / "out_blocking" / "hands_toes.json").read_text())
    assert report["curl"]["index_02_l"][-1][1] > report["curl"]["index_02_l"][0][1]   # closes as f grows
