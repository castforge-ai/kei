"""Task 9 of plan 7: the bake of an approved Unreal shot, checked bone by bone. A fake editor; the bake itself is
unproven live (the editor refused it for a spawnable on UE 5.8.3), and these tests do not claim otherwise."""
import json

import pytest

from kei.apps.unreal import UnrealError
from kei.apps.unreal_bake import PAIRS, bake_lines, bake_shot, delivery_end, lags
from test_unreal_readback import keyed_shot
from kei.state import ShotState, save_state
from unrealkit import FakeEditor


def following(frame):
    """A baked clip where every ik_ bone sits on its bone."""
    row = {}
    for bone, ik in PAIRS:
        p = [frame * 1.0, 5.0 if "_l" in bone else -5.0, 8.0]
        row[bone] = p
        row[ik] = list(p)
    return row


def done_shot(tmp_path, status="done", loop=False):
    shot = keyed_shot(tmp_path, 12)
    p = shot / "out_blocking" / "shot.json"
    d = json.loads(p.read_text())
    d["loop"] = loop
    p.write_text(json.dumps(d))
    save_state(shot, ShotState(stage="deliver", status=status))
    return shot


def test_a_shot_that_is_not_done_is_refused_before_any_call(tmp_path):
    shot = done_shot(tmp_path, status="needs_approval")
    ed = FakeEditor()
    with ed.server() as fake:
        with pytest.raises(Exception, match="approved shot.*needs_approval"):
            bake_shot(ed.client(), shot, "blocking")
        assert fake.scripts == []


def test_the_calls_are_recorded_and_a_clean_bake_passes(tmp_path):
    shot = done_shot(tmp_path)
    ed = FakeEditor()
    ed.baked = following
    with ed.server() as fake:
        report = bake_shot(ed.client(), shot, "blocking")
        assert fake.scripts == ["dirty", "open_sequence", "bake", "read_bake"]       # 13 frames: one chunk of 15
    assert report["ok"] and report["asset"] == "/Game/Kei/walk_01/A_walk_01_blocking"
    assert ed.saved == ["/Game/Kei/walk_01/A_walk_01_blocking"]    # that asset only
    assert ed.bakes[0]["end"] == 12 and ed.bakes[0]["fps"] == 24 and report["ik_copy"] == "skeleton pose" and ed.bakes[0]["pairs"][0] == ["foot_l", "ik_foot_l"]
    assert json.loads((shot / "out_blocking" / "bake_report.json").read_text())["ok"] is True
    assert bake_lines(report)[-1] == "every ik_ bone follows its bone on every frame"


def test_an_ik_bone_that_lags_on_one_frame_is_reported_with_the_bone_and_the_frame(tmp_path):      # Review Focus 9
    shot = done_shot(tmp_path)
    ed = FakeEditor()

    def lagging(frame):
        row = following(frame)
        if frame == 7:
            row["ik_foot_l"] = [row["foot_l"][0] - 4.0, row["foot_l"][1], row["foot_l"][2]]
        return row
    ed.baked = lagging
    with ed.server():
        report = bake_shot(ed.client(), shot, "blocking")
    assert report["ok"] is False
    assert report["failures"] == [{"bone": "ik_foot_l", "follows": "foot_l", "frame": 7, "off_cm": 4.0}]
    lines = bake_lines(report)
    assert "ik_foot_l does not follow foot_l on frame 7 (4.0 cm off)" in lines
    assert "the asset is kept" in lines[-1]
    assert ed.bakes                                                  # the asset was made and kept, not deleted


def test_a_skeleton_without_an_ik_bone_skips_that_pair_and_says_so(tmp_path):
    shot = done_shot(tmp_path)
    ed = FakeEditor()
    ed.baked = lambda f: {k: v for k, v in following(f).items() if k != "ik_hand_gun"}
    with ed.server():
        report = bake_shot(ed.client(), shot, "blocking")
    assert report["ok"] and report["pairs_skipped"] == [["hand_r", "ik_hand_gun"]]
    assert "not checked: the skeleton has no ik_hand_gun" in bake_lines(report)


def test_an_editor_that_refuses_the_bake_gives_a_plain_error_and_no_false_success(tmp_path):
    shot = done_shot(tmp_path)
    ed = FakeEditor()
    ed.bake_error = "the editor could not bake the sequence to an animation: export_anim_sequence returned False"
    with ed.server() as fake:
        with pytest.raises(UnrealError, match="export_anim_sequence returned False"):
            bake_shot(ed.client(), shot, "blocking")
        assert "read_bake" not in fake.scripts
    assert not (shot / "out_blocking" / "bake_report.json").exists()


def test_a_second_bake_takes_a_new_asset_name_and_never_overwrites(tmp_path):
    shot = done_shot(tmp_path)
    ed = FakeEditor()
    ed.baked = following
    with ed.server():
        a = bake_shot(ed.client(), shot, "blocking")["asset"]
        b = bake_shot(ed.client(), shot, "blocking")["asset"]
    assert (a, b) == ("/Game/Kei/walk_01/A_walk_01_blocking", "/Game/Kei/walk_01/A_walk_01_blocking_2")


def test_a_loop_is_baked_one_frame_short_of_its_repeat_of_frame_zero():
    assert delivery_end({"frames": 24, "loop": True}) == 23 and delivery_end({"frames": 24}) == 24


def test_lags_uses_the_tolerance():
    assert lags({"0": {"foot_l": [0, 0, 0], "ik_foot_l": [0.05, 0, 0]}}) == []
    assert lags({"3": {"foot_l": [0, 0, 0], "ik_foot_l": [0.2, 0, 0]}})[0]["frame"] == 3


def test_the_live_numbers_of_the_rig_bake_pass_the_check():
    # foot_l at frame 8 and the pelvis at frame 15, as the live bake gave them (rig space, cm); ik_ bones sit on theirs
    frames = {"8": {"foot_l": [14.09, 19.01, 20.24], "ik_foot_l": [14.09, 19.01, 20.24]},
              "15": {"pelvis": [0.0, 32.28, 95.9], "foot_r": [-14.09, 5.0, 8.24], "ik_foot_r": [-14.09, 5.0, 8.24]}}
    assert lags(frames) == []


def test_the_bake_report_counts_bones_and_says_the_ik_copy_was_done_in_the_rig(tmp_path):
    shot = done_shot(tmp_path)
    ed = FakeEditor()
    ed.baked = following
    with ed.server():
        report = bake_shot(ed.client(), shot, "blocking")
    assert report["bones"] == 161 and report["skipped_bones"] == 185 and report["ik_copy"] == "skeleton pose"
    assert "161 bones written (185 helper bones of the rig are not in the skeleton)" in bake_lines(report)


def test_a_second_performer_is_baked_after_the_character_for_reference_only_once_signed_off(tmp_path):
    shot = done_shot(tmp_path)
    p = shot / "out_blocking" / "shot.json"
    d = json.loads(p.read_text())
    d["performers"] = {"ghost": {"offset_cm": [120, 60, 0], "yaw_deg": -30}}
    p.write_text(json.dumps(d))
    ed = FakeEditor()
    ed.baked = following
    with ed.server():
        report = bake_shot(ed.client(), shot, "blocking")
    assert [b["performer"] for b in ed.bakes] == ["", "ghost"]
    ghost = report["performers"]["ghost"]
    assert ghost["asset"] == "/Game/Kei/walk_01/A_walk_01_blocking_ghost" and ghost["ok"]
    assert ghost["offset_cm"] == [120.0, 60.0, 0.0] and ghost["yaw_deg"] == -30.0
    assert "ghost, baked for reference: /Game/Kei/walk_01/A_walk_01_blocking_ghost" in bake_lines(report)
    save_state(shot, ShotState(stage="deliver", status="needs_approval"))
    with ed.server(), pytest.raises(Exception, match="approved shot"):
        bake_shot(ed.client(), shot, "blocking")
