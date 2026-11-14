"""Task 5 of plan 7: read the character's Control Rig and probe it, against a fake editor."""
import json

import pytest

from kei.apps.unreal import NeedsHuman
from kei.apps.unreal_rig import (check_dirty, kei_folder, load_rig, new_sequence, read_rig, sequences, shot_name,
                                 unrestored)
from unrealkit import MANNY, FakeEditor


def test_the_rig_file_has_every_keyable_control_and_the_units(tmp_path):
    shot = tmp_path / "walk_01"
    ed = FakeEditor()
    with ed.server():
        rig = read_rig(ed.client(), shot, MANNY)
    assert [c["name"] for c in rig["controls"]] == ["foot_l_ik_ctrl", "foot_r_ik_ctrl", "pelvis_ctrl",
                                                    "hand_l_fk_ctrl", "spine_blend"]
    assert rig["units"] == {"length": "cm", "angle": "deg", "up": "z"}
    assert rig["claireon"]["protocol_version"] == "2025-03-26"
    assert rig["frame"] == {"left": [1.0, 0.0, 0.0], "forward": [0.0, 1.0, 0.0]}      # from the thighs at rest
    assert load_rig(shot) == json.loads((shot / "rig" / "unreal_rig.json").read_text())
    md = (shot / "rig" / "unreal_rig.md").read_text()
    assert md.startswith("Rig: Manny's Control Rig") and "5 keyable controls" in md
    assert [c for c in rig["controls"] if c["name"] == "hand_l_fk_ctrl"][0]["locked"] is True


def test_a_probe_that_leaves_a_value_changed_stops_with_needs_human_naming_the_control(tmp_path):   # Review Focus 2
    ed = FakeEditor()
    ed.leave_changed = "pelvis_ctrl"
    with ed.server():
        with pytest.raises(NeedsHuman, match=r"pelvis_ctrl.*undo or reload.*without saving"):
            read_rig(ed.client(), tmp_path / "walk_01", MANNY)
    assert not (tmp_path / "walk_01" / "rig" / "unreal_rig.json").exists()


def test_no_save_call_is_made_by_the_rig_read_and_only_kei_scripts_run(tmp_path):
    ed = FakeEditor()
    with ed.server() as fake:
        read_rig(ed.client(), tmp_path / "walk_01", MANNY)
    assert ed.saved == [] and ed.save_all_calls == 0
    assert fake.scripts == ["make_sequence", "dirty", "read_rig"]


def test_the_probe_sequence_is_under_kei_s_folder_only(tmp_path):
    ed = FakeEditor()
    with ed.server():
        read_rig(ed.client(), tmp_path / "walk_01", MANNY)
    assert list(ed.sequences) == ["/Game/Kei/walk_01/LS_walk_01_rig_1"]


def test_unrestored_compares_within_a_tolerance():
    assert unrestored({"a": [0, 0, 1]}, {"a": [0.00005, 0, 1]}) == []
    assert unrestored({"a": [0, 0, 1]}, {"a": [0.0002, 0, 1]}) == ["a"]
    assert unrestored({"a": [0]}, {}) == ["a"]


def test_a_control_rig_with_no_keyable_control_is_refused(tmp_path):
    ed = FakeEditor()
    ed.rig = {**ed.rig, "controls": [], "before": {}, "after": {}}
    with ed.server():
        with pytest.raises(NeedsHuman, match="no keyable controls"):
            read_rig(ed.client(), tmp_path / "walk_01", MANNY)


def test_a_new_sequence_per_attempt_takes_the_next_number_and_never_reuses_a_name(tmp_path):
    ed = FakeEditor()
    shot = tmp_path / "walk_01"
    with ed.server():
        c = ed.client()
        a = new_sequence(c, shot, "blocking", MANNY, 24, 24)
        b = new_sequence(c, shot, "blocking", MANNY, 24, 24, copy_from=a)
        assert (a, b) == ("/Game/Kei/walk_01/LS_walk_01_blocking_1", "/Game/Kei/walk_01/LS_walk_01_blocking_2")
        assert ed.sequences[b]["copy_from"] == a
        # a name taken by an earlier run of another shot folder with the same name: Kei goes on to the next number
        (shot / "unreal" / "sequences.json").unlink()
        c2 = new_sequence(c, shot, "blocking", MANNY, 24, 24)
        assert c2.endswith("_blocking_3")
    assert sequences(shot) == {"blocking": [c2]}
    placed = json.loads((shot / "unreal" / "placed.json").read_text(encoding="utf-8"))
    assert placed["sequence"] == c2 and placed["at_cm"] == [370.0, -20.0, 0.0]
    assert placed["level"] == "/Game/ThirdPerson/ThirdPersonMap"


def test_check_dirty_names_a_user_asset_and_allows_kei_s_own():
    folder = kei_folder(__import__("pathlib").Path("walk_01"))
    check_dirty([], [folder + "/LS_x_1"], folder)
    check_dirty(["/Game/Maps/Open"], ["/Game/Maps/Open", folder + "/LS_x_1"], folder)    # dirty before: not Kei's doing
    with pytest.raises(NeedsHuman, match="/Game/Maps/Level"):
        check_dirty([], ["/Game/Maps/Level", folder + "/LS_x_1"], folder)
    with pytest.raises(NeedsHuman):
        check_dirty([], ["/Game/Kei/other_shot/LS_y"], folder)


def test_shot_names_are_safe_asset_names():
    assert shot_name(__import__("pathlib").Path("walk 01-a")) == "walk_01_a"
    assert shot_name(__import__("pathlib").Path("2d_walk")) == "S_2d_walk"
