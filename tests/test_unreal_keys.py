"""Task 6 of plan 7: a pass keys the character's controls in Kei's own sequence and touches no user asset."""
import contextlib
import json

import pytest

from kei.apps.unreal import NeedsHuman
from kei.apps.unreal_keys import apply_keys, parse_keys
from kei.apps.unreal_rig import read_rig
from kei.sample import ShotError
from unrealkit import MANNY, FakeEditor, canned_rig


def shot_with(tmp_path, keys, rig="unreal", frames=24, name="blocking"):
    shot = tmp_path / "walk_01"
    out = shot / f"out_{name}"
    out.mkdir(parents=True)
    (out / "shot.json").write_text(json.dumps({"rig": rig, "fps": 24, "frames": frames, "keys": keys}))
    return shot


@contextlib.contextmanager
def ready(tmp_path, keys, **kw):
    """A shot whose rig was read, a fake editor running, and the script log cleared."""
    shot = shot_with(tmp_path, keys, **kw)
    ed = FakeEditor()
    with ed.server() as fake:
        read_rig(ed.client(), shot, MANNY)
        fake.scripts.clear()
        yield shot, ed, fake


KEYS = [{"f": 0, "foot_l_ik_ctrl.location.z": 0.0, "pelvis_ctrl.location.z": 90.0},
        {"f": 12, "foot_l_ik_ctrl.location.z": 8.0, "spine_blend.value": 0.5}]


def test_the_calls_are_recorded_in_order_make_dirty_keys_dirty_save_by_path(tmp_path):
    with ready(tmp_path, KEYS) as (shot, ed, fake):
        report = apply_keys(ed.client(), shot, "blocking")
        assert fake.scripts == ["make_sequence", "dirty", "set_keys", "dirty", "save_asset"]      # both key frames in one call
        assert ed.batches == [2]
    assert ed.saved == ["/Game/Kei/walk_01/LS_walk_01_blocking_1"] and ed.save_all_calls == 0
    assert report["keys"] == 2 and report["saved"] == ed.saved[0] and report["tangents"] == "set"
    assert json.loads((shot / "out_blocking" / "unreal_report.json").read_text()) == report
    assert [k["tangent"] for k in ed.keys] == ["step", "step"]          # blocking is stepped
    assert ed.keys[1]["controls"] == {"foot_l_ik_ctrl": {"location.z": 8.0}, "spine_blend": {"value": 0.5}}
    assert ed.keys[1]["types"] == {"foot_l_ik_ctrl": "euler_transform", "spine_blend": "float"}


def test_a_later_pass_is_spline_by_default_and_a_key_may_name_its_tangent(tmp_path):
    keys = [{"f": 0, "pelvis_ctrl.location.z": 90.0}, {"f": 6, "tangent": "flat", "pelvis_ctrl.location.z": 92.0}]
    with ready(tmp_path, keys, name="spline") as (shot, ed, fake):
        apply_keys(ed.client(), shot, "spline")
    assert [k["tangent"] for k in ed.keys] == ["spline", "flat"]


@pytest.mark.parametrize("key, match", [
    ({"f": 3, "hand_l_fk_ctrl.location.x": 1.0}, r"hand_l_fk_ctrl is locked"),
    ({"f": 3, "foot_l_ik_ctrl.shear.x": 1.0}, r"foot_l_ik_ctrl has no channel shear\.x"),
    ({"f": 3, "nose_ctrl.location.x": 1.0}, r"nose_ctrl.location.x names no control"),
    ({"f": 3, "spine_blend.value": "high"}, r"needs a number"),
    ({"f": 3, "tangent": "bounce", "pelvis_ctrl.location.z": 1}, r"tangent is one of"),
    ({"pelvis_ctrl.location.z": 1}, r'needs a frame "f"')])
def test_a_locked_or_missing_control_or_channel_is_refused_naming_it_and_nothing_is_keyed(tmp_path, key, match):   # Focus 7
    with ready(tmp_path, [{"f": 0, "pelvis_ctrl.location.z": 90.0}, key]) as (shot, ed, fake):
        with pytest.raises(ShotError, match=match):
            apply_keys(ed.client(), shot, "blocking")
        assert fake.scripts == []
    assert ed.keys == [] and ed.saved == []


def test_a_user_package_dirty_after_the_keys_stops_the_shot_and_saves_nothing(tmp_path):     # Review Focus 1
    with ready(tmp_path, KEYS) as (shot, ed, fake):
        ed.user_dirty = "/Game/Sequences/MyCinematic"
        with pytest.raises(NeedsHuman, match="/Game/Sequences/MyCinematic"):
            apply_keys(ed.client(), shot, "blocking")
        assert "save_asset" not in fake.scripts
    assert ed.saved == []
    assert not (shot / "out_blocking" / "unreal_report.json").exists()


def test_a_pose_a_limit_held_back_is_in_the_report_as_asked_versus_reached(tmp_path):
    with ready(tmp_path, KEYS) as (shot, ed, fake):
        ed.clip = ("foot_l_ik_ctrl", "location.z", 5.0)
        report = apply_keys(ed.client(), shot, "blocking")
    assert report["clipped"] == [
        {"control": "foot_l_ik_ctrl", "channel": "location.z", "asked": 0.0, "reached": 5.0, "f": 0},
        {"control": "foot_l_ik_ctrl", "channel": "location.z", "asked": 8.0, "reached": 5.0, "f": 12}]


def test_each_attempt_is_a_new_sequence_and_never_the_old_name(tmp_path):
    with ready(tmp_path, KEYS) as (shot, ed, fake):
        a = apply_keys(ed.client(), shot, "blocking")["sequence"]
        b = apply_keys(ed.client(), shot, "blocking")["sequence"]
    assert (a[-1], b[-1]) == ("1", "2") and list(ed.sequences).count(a) == 1


def test_a_shot_with_no_rig_read_or_another_rig_is_refused_plainly(tmp_path):
    shot = shot_with(tmp_path, KEYS)
    ed = FakeEditor()
    with ed.server():
        with pytest.raises(ShotError, match="no rig read yet"):
            apply_keys(ed.client(), shot, "blocking")
    with pytest.raises(ShotError, match='"rig": "unreal"'):
        parse_keys({"rig": "v4", "keys": []}, canned_rig(), "step")


def test_keys_at_one_frame_merge():
    keys = parse_keys({"rig": "unreal", "keys": [{"f": 1, "pelvis_ctrl.location.z": 1},
                                                 {"f": 1, "pelvis_ctrl.location.y": 2}]}, canned_rig(), "step")
    assert keys == [{"f": 1, "tangent": "step", "controls": {"pelvis_ctrl": {"location.z": 1, "location.y": 2}}}]


def test_many_key_frames_go_in_few_calls_so_the_project_is_not_flooded_with_audit_files(tmp_path):
    from kei.apps.unreal_keys import BATCH
    keys = [{"f": n * 2, "pelvis_ctrl.location.z": 90.0 + n} for n in range(40)]
    with ready(tmp_path, keys, name="long") as (shot, ed, fake):
        report = apply_keys(ed.client(), shot, "long")
    assert report["keys"] == 40 and len(ed.keys) == 40
    assert ed.batches == [BATCH, BATCH, 40 - 2 * BATCH] and fake.scripts.count("set_keys") == 3
    assert [k["frame"] for k in ed.keys] == [n * 2 for n in range(40)]          # in order, none lost


def test_a_clipped_value_is_reported_with_its_frame_from_inside_a_batch(tmp_path):
    keys = [{"f": 0, "foot_l_ik_ctrl.location.z": 0.0}, {"f": 12, "foot_l_ik_ctrl.location.z": 9.0}]
    with ready(tmp_path, keys, name="clip") as (shot, ed, fake):
        ed.clip = ("foot_l_ik_ctrl", "location.z", 5.0)
        report = apply_keys(ed.client(), shot, "clip")
    assert [c["f"] for c in report["clipped"]] == [0, 12] and report["clipped"][1]["reached"] == 5.0


def test_full_body_poses_are_split_so_no_call_passes_claireons_script_limit(tmp_path):
    """A pose from kei unreal pose keys every channel: 15 such frames in one call broke Claireon's 64 KiB limit."""
    from kei.apps.unreal_keys import INPUT_BUDGET, batches
    controls = {f"c{i}_ctrl": {f"rotation.{a}": 12.3456 for a in "xyz"} for i in range(400)}
    keys = [{"f": f, "tangent": "spline", "controls": controls} for f in range(15)]
    types = {c: "euler_transform" for c in controls}
    out = batches(keys, types)
    assert all(len(json.dumps(b)) <= INPUT_BUDGET + 2000 for b in out)
    keyed = {}
    for b in out:
        for item in b:
            keyed.setdefault(item["frame"], {}).update(item["controls"])
    assert keyed == {f: controls for f in range(15)}          # nothing lost, nothing doubled


def test_one_frame_larger_than_a_call_is_split_by_control_at_the_same_frame():
    from kei.apps.unreal_keys import batches
    controls = {f"c{i}_ctrl": {"location.x": 1.0} for i in range(50)}
    out = batches([{"f": 7, "tangent": "step", "controls": controls}], {c: "euler_transform" for c in controls},
                  budget=300)
    assert len(out) > 1 and all(i["frame"] == 7 and i["tangent"] == "step" for b in out for i in b)
    assert sum(len(i["controls"]) for b in out for i in b) == 50
