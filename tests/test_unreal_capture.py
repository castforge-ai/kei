"""The real-mesh capture test: pose, wait a tick, shoot three views, say in words whether it looks drawn."""
import json

from kei.apps.unreal_capture import MIN_SHOWN, capture_test, middle_key_frame
from unrealkit import FakeEditor


def shot_with_pass(tmp_path):
    shot = tmp_path / "idle_01"
    (shot / "unreal").mkdir(parents=True)
    (shot / "unreal" / "sequences.json").write_text(json.dumps({"p1": ["/Game/Kei/idle_01/LS_idle_01_p1_1"]}))
    (shot / "out_p1").mkdir()
    (shot / "out_p1" / "shot.json").write_text(json.dumps({"frames": 150, "keys": [{"f": 0}, {"f": 34}, {"f": 88}, {"f": 150}]}))
    return shot


def test_the_middle_key_frame_is_the_default():
    assert middle_key_frame({"keys": [{"f": 0}, {"f": 34}, {"f": 88}, {"f": 150}]}) == 88
    assert middle_key_frame({"frames": 40, "keys": []}) == 20


def test_the_pose_is_set_before_the_shoot_and_three_views_come_back(tmp_path):
    shot = shot_with_pass(tmp_path)
    ed = FakeEditor()
    with ed.server() as fake:
        got = capture_test(ed.client(), shot, "p1")
        assert fake.scripts == ["capture_frame", "capture_frame"]
    assert [c["stage"] for c in ed.captures] == ["pose", "shoot"] and ed.captures[0]["frame"] == 88
    assert {v["name"] for v in ed.captures[1]["views"]} == {"front", "side", "three_quarter"}
    assert got["looks_drawn"] and len(got["files"]) == 3 and (shot / "out_p1" / "mesh_test").is_dir()


def test_a_black_picture_is_reported_as_not_drawn(tmp_path):
    shot = shot_with_pass(tmp_path)
    ed = FakeEditor()
    ed.capture_shown = MIN_SHOWN / 2
    with ed.server():
        got = capture_test(ed.client(), shot, "p1", frame=34)
    assert not got["looks_drawn"] and ed.captures[0]["frame"] == 34


def test_the_script_shows_only_the_character_and_removes_what_it_adds():
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "kei" / "apps" / "unreal_side" / "capture_frame.py").read_text()
    assert "PRM_USE_SHOW_ONLY_LIST" in text and "destroy_actor" in text and "set_dirty_flag(False)" in text
    assert text.index("import math") < text.index("def _main")
