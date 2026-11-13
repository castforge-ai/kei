"""After a pass the editor is told to give its memory back, and a refusal never stops the shot."""
import json

from kei.apps.unreal_rig import release_memory
from unrealkit import FakeEditor


def shot_with_sequences(tmp_path):
    shot = tmp_path / "walk_01"
    (shot / "unreal").mkdir(parents=True)
    (shot / "unreal" / "sequences.json").write_text(json.dumps({
        "rig": ["/Game/Kei/walk_01/LS_walk_01_rig_1"], "blocking": ["/Game/Kei/walk_01/LS_walk_01_blocking_1"],
        "p1": ["/Game/Kei/walk_01/LS_walk_01_p1_1", "/Game/Kei/walk_01/LS_walk_01_p1_2"]}))
    return shot


def test_every_kei_sequence_of_the_shot_is_offered_for_unloading_in_one_call(tmp_path):
    shot = shot_with_sequences(tmp_path)
    ed = FakeEditor()
    with ed.server() as fake:
        got = release_memory(ed.client(), shot)
        assert fake.scripts == ["unload_kei"]
    assert len(ed.unloads) == 1 and len(ed.unloads[0]) == 4 and got["gc"] and got["undo_cleared"]


def test_a_refusal_comes_back_as_an_error_and_raises_nothing(tmp_path):
    shot = shot_with_sequences(tmp_path)
    ed = FakeEditor()
    ed.unload_error = "the editor would not unload"
    with ed.server():
        got = release_memory(ed.client(), shot)
    assert "would not unload" in got["error"]


def test_it_can_be_turned_off(tmp_path, monkeypatch):
    monkeypatch.setenv("KEI_UNREAL_CLEANUP", "0")
    shot = shot_with_sequences(tmp_path)
    ed = FakeEditor()
    with ed.server() as fake:
        assert release_memory(ed.client(), shot) is None and fake.scripts == []


def test_the_script_only_touches_kei_assets_and_keeps_unsaved_ones():
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "kei" / "apps" / "unreal_side" / "unload_kei.py").read_text()
    assert 'startswith(KEI_ROOT + "/")' in text and "kept_dirty" in text and "collect_garbage" in text
