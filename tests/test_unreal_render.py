"""Task 8 of plan 7: views and playback of an Unreal pass, drawn by Kei's renderer on the joints Unreal gave back."""
import json

import pytest

from kei.apps import unreal_render
from kei.apps.unreal_readback import read_back
from kei.apps.unreal_render import render_pass
from kei.sample import ShotError
from test_unreal_readback import keyed_shot, standing
from unrealkit import FakeEditor


def joints_for(tmp_path, last=6, loop=False):
    shot = keyed_shot(tmp_path, last)
    p = shot / "out_blocking" / "shot.json"
    d = json.loads(p.read_text())
    d["keys"] = [{"f": 0}, {"f": 3}, {"f": last}]
    d["loop"] = loop
    p.write_text(json.dumps(d))
    ed = FakeEditor(bones=lambda f: standing(f, last))
    with ed.server():
        read_back(ed.client(), shot, "blocking", "kei")
    return shot


def test_the_kei_renderer_writes_the_same_files_as_a_pass_on_kei_s_own_rig(tmp_path):
    shot = joints_for(tmp_path)
    r = render_pass(shot, "blocking", size=64)
    out = shot / "out_blocking"
    assert [p.name for p in r["frames"]] == [f"f{i:04d}.png" for i in range(7)]
    assert all((out / "frames" / p.name).stat().st_size > 100 for p in r["frames"])
    assert [p.name for p in r["stills"]] == ["key_f0000.png", "key_f0003.png", "key_f0006.png"]
    assert (out / "keys.png").stat().st_size > 100
    assert r["playback"].name in ("blocking.mp4", "blocking.gif") and r["playback"].is_file()


def test_the_pass_records_which_renderer_drew_it(tmp_path):
    shot = joints_for(tmp_path)
    (shot / "out_blocking" / "unreal_report.json").write_text(json.dumps({"keys": 3}))
    render_pass(shot, "blocking", size=64)
    rep = json.loads((shot / "out_blocking" / "unreal_report.json").read_text())
    assert rep["keys"] == 3 and rep["views"]["renderer"] == "kei" and rep["views"]["frames"] == 7


def test_capture_from_the_editor_is_refused_in_plain_words_and_never_replaced_in_silence(tmp_path):
    shot = joints_for(tmp_path)
    assert unreal_render.CAPTURE_ENABLED is False
    with pytest.raises(ShotError, match="not built yet"):
        render_pass(shot, "blocking", size=64, renderer="unreal")


def test_a_pass_with_no_joints_is_refused_plainly(tmp_path):
    shot = keyed_shot(tmp_path)
    with pytest.raises(ShotError, match="kei unreal key"):
        render_pass(shot, "blocking", size=64)
