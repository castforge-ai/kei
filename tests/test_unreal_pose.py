"""kei unreal pose: a frame of an animation in the project onto the character's Control Rig, read back as keys."""
import contextlib
import json

import pytest

from kei.apps.unreal import NeedsHuman
from kei.apps.unreal_pose import asset_path, keys_for_rig, pose_from_anim, pose_path, within
from kei.apps.unreal_rig import read_rig
from kei.sample import ShotError
from unrealkit import MANNY, FakeEditor, canned_rig

IDLE = "/Game/Characters/Mannequins/Anims/MM_Idle"


@contextlib.contextmanager
def ready(tmp_path):
    shot = tmp_path / "idle_01"
    shot.mkdir()
    ed = FakeEditor()
    with ed.server() as fake:
        read_rig(ed.client(), shot, MANNY)
        fake.scripts.clear()
        yield shot, ed, fake


def test_the_pose_is_loaded_in_a_sequence_of_keis_own_checked_saved_and_written_as_keys(tmp_path):
    with ready(tmp_path) as (shot, ed, fake):
        r = pose_from_anim(ed.client(), shot, IDLE, 0)
        assert fake.scripts == ["make_sequence", "dirty", "load_pose", "save_asset"]
    assert ed.poses[0]["anim"] == IDLE and ed.poses[0]["frame"] == 0
    assert r["sequence"] == "/Game/Kei/idle_01/LS_idle_01_pose_1" and ed.saved == [r["sequence"]]
    assert r["matches"] is True and r["check"]["mean_deg"] == 0.24
    written = json.loads(pose_path(shot, IDLE, 0).read_text())
    assert written["keys"] == r["keys"] and pose_path(shot, IDLE, 0).name == "pose_MM_Idle_f0.json"


def test_keys_cover_every_keyable_channel_of_the_rig_and_leave_out_locked_and_unknown_controls(tmp_path):
    with ready(tmp_path) as (shot, ed, fake):
        keys = pose_from_anim(ed.client(), shot, IDLE, 0)["keys"]
    assert keys["foot_l_ik_ctrl.rotation.z"] == 30.0 and keys["pelvis_ctrl.location.x"] == 1.0
    assert keys["spine_blend.value"] == 0.25
    assert not any(k.startswith("hand_l_fk_ctrl.") for k in keys)          # locked in the rig
    assert not any(k.startswith("not_in_rig_ctrl.") for k in keys)
    assert sum(k.startswith("foot_l_ik_ctrl.") for k in keys) == 9


def test_a_user_asset_made_dirty_stops_for_a_human(tmp_path):
    with ready(tmp_path) as (shot, ed, fake):
        ed.user_dirty = "/Game/Levels/Map"
        with pytest.raises(NeedsHuman):
            pose_from_anim(ed.client(), shot, IDLE, 0)
    assert ed.saved == []


def test_a_loose_pose_is_reported_not_hidden(tmp_path):
    with ready(tmp_path) as (shot, ed, fake):
        ed.pose_check = {"bones": 90, "mean_deg": 4.0, "pelvis_relative_cm": {"head": 6.0}}
        r = pose_from_anim(ed.client(), shot, IDLE, 0)
    assert r["matches"] is False


def test_a_shot_with_no_rig_read_is_refused(tmp_path):
    with pytest.raises(ShotError):
        pose_from_anim(None, tmp_path, IDLE, 0)


def test_git_bash_mangled_asset_paths_are_taken_from_the_content_root():
    assert asset_path("C:/Program Files/Git/Game/Char/as_idle") == "/Game/Char/as_idle"
    assert asset_path("/Game/Char/as_idle") == "/Game/Char/as_idle"
    assert asset_path("as_idle") == "as_idle"


def test_within_needs_both_limits():
    assert within({"mean_deg": 0.5, "pelvis_relative_cm": {"head": 1.9}})
    assert not within({"mean_deg": 1.5, "pelvis_relative_cm": {}})
    assert not within({"mean_deg": 0.5, "pelvis_relative_cm": {"hand_r": 2.5}})
    assert not within({})


def test_keys_for_rig_keeps_bools():
    rig = {"controls": [{"name": "ik_on", "type": "bool", "channels": ["value"], "locked": False}]}
    assert keys_for_rig({"ik_on": {"value": True}}, rig) == {"ik_on.value": True}
