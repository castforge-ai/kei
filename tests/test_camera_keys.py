"""An animated delivery camera: keys that push in, pan and cut, rendered through the delivery path, with staging
notes per setup."""
import json

import pytest

from kei.camera_check import framing
from kei.cli import main
from kei.render import Camera
from kei.sample import ShotError
from test_cameras import WALK, write

BASE = {"yaw_deg": 0, "target_m": [0, 0.95, 0.6], "lens_mm": 35, "distance_m": 6.0, "aspect": "16:9"}


def test_a_locked_camera_has_no_keys_and_is_the_same_on_every_frame():
    cam = Camera.from_plan(BASE)
    assert cam.keys == () and cam.at(0) is cam and cam.at(99) is cam and cam.cuts() == []


def test_keys_ease_between_setups_and_a_cut_holds_then_jumps():
    cam = Camera.from_plan({**BASE, "keys": [{"f": 0}, {"f": 10, "yaw_deg": 40, "lens_mm": 70},
                                              {"f": 20, "yaw_deg": 90, "cut": True}]})
    assert cam.at(0).yaw_deg == 0 and cam.at(10).yaw_deg == pytest.approx(40)
    mid = cam.at(5)
    assert 0 < mid.yaw_deg < 40 and mid.yaw_deg == pytest.approx(20)          # smoothstep is half way at the middle
    assert cam.at(2).yaw_deg < 40 * 0.2                                       # it eases out of the first key
    assert cam.at(10).span < cam.at(0).span                                   # the longer lens frames tighter
    assert cam.at(19).yaw_deg == pytest.approx(40) and cam.at(20).yaw_deg == pytest.approx(90)   # the cut
    assert cam.cuts() == [20] and cam.at(500).yaw_deg == pytest.approx(90)


def test_yaw_turns_the_short_way_round():
    cam = Camera.from_plan({**BASE, "yaw_deg": 350, "keys": [{"f": 0}, {"f": 10, "yaw_deg": 10}]})
    assert cam.at(5).yaw_deg % 360 == pytest.approx(0, abs=1e-6)


@pytest.mark.parametrize("keys,said", [
    ([], "list of camera keys"),
    ([{"f": 4}, {"f": 4}], "after the key before"),
    ([{"f": -1}], "whole frame"),
    ([{"f": 0, "roll_deg": 5}], "not a camera key setting"),
    ([{"f": 0, "aspect": "4:3"}], "not a camera key setting"),
    ([{"f": 0, "cut": "yes"}], "true or false"),
    ([{"f": 0}, {"f": 5, "span_m": 2}], "not a mix"),
])
def test_bad_keys_are_refused_by_name(keys, said):
    with pytest.raises(ShotError, match=said):
        Camera.from_plan({**BASE, "keys": keys})


def test_the_delivery_render_follows_the_keys_and_writes_the_staging_notes(tmp_path, capsys):
    cam = {**BASE, "keys": [{"f": 0}, {"f": 3, "yaw_deg": 180, "cut": True}, {"f": 5, "lens_mm": 15}]}
    write(tmp_path, WALK, cam)
    assert main(["render", str(tmp_path), "blocking", "--camera", "delivery", "--size", "72"]) == 0
    out = capsys.readouterr().out
    rep = json.loads((tmp_path / "out_blocking" / "delivery" / "framing.json").read_text())
    assert "cuts at f3" in out and len(rep["setups"]) == 2
    assert any(n.startswith("crosses the line: the cut at f3") for n in rep["notes"])
    assert any(n.startswith("short setup: f0-2") for n in rep["notes"])
    a = (tmp_path / "out_blocking" / "delivery" / "frames" / "f0002.png").read_bytes()
    b = (tmp_path / "out_blocking" / "delivery" / "frames" / "f0003.png").read_bytes()
    assert a != b


def test_a_camera_too_close_reports_the_frames_out_and_a_wide_one_reports_a_small_figure():
    shot = json.loads(json.dumps(WALK))
    tight = framing(shot, "spline", "kei", Camera.from_plan({**BASE, "lens_mm": 200}))
    assert tight["frames_out"] and tight["notes"][0].startswith("out of frame: f0")
    wide = framing(shot, "spline", "kei", Camera.from_plan({**BASE, "lens_mm": 12, "distance_m": 20}))
    assert not wide["frames_out"] and any(n.startswith("small in frame") for n in wide["notes"])
    good = framing(shot, "spline", "kei", Camera.from_plan({**BASE, "follow": True}))
    assert good["frames_out"] == [] and good["notes"] == []
