"""Task 7 of plan 7: the motion keyed in Unreal comes back in metres, Y up, and kei check runs on it."""
import json
import math

import pytest

from kei.apps.unreal import UnrealError
from kei.apps.unreal_readback import DERIVED, joints_from_bones, read_back
from kei.apps.unreal_rig import save_character
from kei.body_check import check_pass
from kei.rig import BONES
from kei.sample import ShotError
from unrealkit import MANNY, FakeEditor


def standing(f, last=12, facing="y"):
    """The mannequin's bones in rig space, centimetres, Z up, as the editor reports them: it faces +Y and its left is
    +X (facing="x": a character that faces +X, its left on -Y). Standing, the pelvis travelling forward, the left foot
    lifting at the middle of the shot."""
    lift = 10 * math.sin(math.pi * f / last)
    t = 2.0 * f                                    # forward travel

    def at(side, fwd, z):                          # side: + is the character's left
        return (side, fwd, z) if facing == "y" else (fwd, -side, z)
    b = {"root": at(0, t, 0), "pelvis": at(0, t, 95), "spine_01": at(0, t, 105), "spine_02": at(0, t, 115),
         "spine_03": at(0, t, 125), "spine_04": at(0, t, 135), "spine_05": at(0, t, 142), "neck_01": at(0, t, 150),
         "neck_02": at(0, t, 156), "head": at(0, t, 162)}
    for s, y in (("l", 1), ("r", -1)):
        b[f"clavicle_{s}"] = at(y * 6, t, 145)
        b[f"upperarm_{s}"] = at(y * 19, t, 145)
        b[f"lowerarm_{s}"] = at(y * 19, t, 118)
        b[f"hand_{s}"] = at(y * 19, t, 95)
        b[f"thigh_{s}"] = at(y * 9, t, 92)
        b[f"calf_{s}"] = at(y * 9, t, 50)
        z = 8 + (lift if s == "l" else 0)
        b[f"foot_{s}"] = at(y * 9, t, z)
        b[f"ball_{s}"] = at(y * 9, t + 14, z - 5)
    return {k: list(v) for k, v in b.items()}


def keyed_shot(tmp_path, last=12):
    shot = tmp_path / "walk_01"
    out = shot / "out_blocking"
    out.mkdir(parents=True)
    (out / "shot.json").write_text(json.dumps({"rig": "unreal", "fps": 24, "frames": last, "keys": [{"f": 0}]}))
    save_character(shot, MANNY)
    (shot / "unreal").mkdir(exist_ok=True)
    (shot / "unreal" / "sequences.json").write_text(json.dumps({"blocking": ["/Game/Kei/walk_01/LS_walk_01_blocking_1"]}))
    return shot


def test_every_frame_is_read_once_in_order_and_joints_json_is_in_metres_y_up(tmp_path):
    shot = keyed_shot(tmp_path)
    ed = FakeEditor(bones=standing)
    with ed.server() as fake:
        dst = read_back(ed.client(), shot, "blocking", "kei")
        assert fake.scripts == ["open_sequence", "eval_rig"]          # one eval call for every frame, no scrubbing
    data = json.loads(dst.read_text())
    assert [fr["f"] for fr in data["frames"]] == list(range(13))         # chunking covers every frame exactly once
    assert data["source"] == "unreal" and data["derived"] == list(DERIVED) and data["mode"] == "step"
    f6 = data["frames"][6]["joints"]
    assert f6["pelvis"] == pytest.approx([0.0, 0.95, 0.12])              # rig (0, 12, 95) cm: forward 12 cm is Kei z
    assert f6["foot_l"][0] == pytest.approx(-0.09)                       # the left side is Kei's negative x
    assert f6["foot_r"][0] == pytest.approx(0.09)
    assert f6["foot_l"][1] == pytest.approx(0.18)                        # the left foot lifted 10 cm at the middle
    assert data["frame"] == {"left": [1.0, 0.0, 0.0], "forward": [0.0, 1.0, 0.0]}
    assert all(n in f6 for n in (*BONES, *DERIVED, "com"))
    assert f6["head_top"][1] > f6["head"][1] > f6["neck_01"][1]


def test_the_joints_match_the_editor_s_own_evaluation_within_a_millimetre(tmp_path):    # Review Focus 8
    shot = keyed_shot(tmp_path)
    ed = FakeEditor(bones=standing)
    with ed.server():
        data = json.loads(read_back(ed.client(), shot, "blocking", "kei").read_text())
    for fr in data["frames"]:
        ue = standing(fr["f"])
        for n in BONES:
            want = (-ue[n][0] / 100, ue[n][2] / 100, ue[n][1] / 100)     # mannequin: left +X, forward +Y
            assert fr["joints"][n] == pytest.approx(want, abs=1e-3)


def test_kei_check_reads_the_unreal_joints_like_any_other_pass(tmp_path):
    shot = keyed_shot(tmp_path)
    ed = FakeEditor(bones=standing)
    with ed.server():
        read_back(ed.client(), shot, "blocking", "kei")
    report = json.loads(check_pass(shot, "blocking", "kei").read_text())
    assert report["joints_from"] == "unreal" and report["frames"] == 12
    assert "flags" in report and report["mode"] == "step"


def test_a_character_that_faces_plus_x_reads_back_the_same_kei_joints(tmp_path):
    a = json.loads(read_one(tmp_path / "a", standing).read_text())
    b = json.loads(read_one(tmp_path / "b", lambda f: standing(f, facing="x")).read_text())
    assert b["frame"] == {"left": [0.0, -1.0, 0.0], "forward": [1.0, 0.0, 0.0]}
    for fa, fb in zip(a["frames"], b["frames"]):
        for n in fa["joints"]:
            assert fb["joints"][n] == pytest.approx(fa["joints"][n], abs=1e-5)


def read_one(root, bones):
    root.mkdir()
    shot = keyed_shot(root)
    ed = FakeEditor(bones=bones)
    with ed.server():
        return read_back(ed.client(), shot, "blocking", "kei")


def test_the_frame_comes_from_the_rig_file_and_falls_back_to_the_eval_rest_pose(tmp_path):
    shot = keyed_shot(tmp_path)
    (shot / "rig").mkdir()
    (shot / "rig" / "unreal_rig.json").write_text(json.dumps({"frame": {"left": [0, -1, 0], "forward": [1, 0, 0]}}))
    ed = FakeEditor(bones=lambda f: standing(f, facing="x"))
    with ed.server():
        data = json.loads(read_back(ed.client(), shot, "blocking", "kei").read_text())
    assert data["frame"]["left"] == [0, -1, 0]
    (shot / "rig" / "unreal_rig.json").unlink()
    with ed.server():
        data = json.loads(read_back(ed.client(), shot, "blocking", "kei").read_text())
    assert data["frame"]["left"] == pytest.approx([0, -1, 0])          # found from the thighs in the first eval


def test_the_eval_refuses_a_sequence_that_is_not_open_and_says_so(tmp_path):
    shot = keyed_shot(tmp_path)
    ed = FakeEditor(bones=standing)
    ed.open_sequence = lambda inp: {"sequence": inp["sequence"], "reopened": False}      # the editor did not open it
    with ed.server():
        with pytest.raises(UnrealError, match="not the one open"):
            read_back(ed.client(), shot, "blocking", "kei")


def test_a_character_without_the_mannequin_bone_names_is_refused_naming_them():
    b = standing(0)
    del b["thigh_l"]
    with pytest.raises(ShotError, match="thigh_l"):
        joints_from_bones(b)


def test_a_pass_never_keyed_is_refused_plainly(tmp_path):
    shot = keyed_shot(tmp_path)
    (shot / "unreal" / "sequences.json").write_text("{}")
    ed = FakeEditor(bones=standing)
    with ed.server():
        with pytest.raises(ShotError, match="kei unreal key"):
            read_back(ed.client(), shot, "blocking", "kei")


