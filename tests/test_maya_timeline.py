"""Kei sets Maya's time slider to the pass it keys, in the open Maya too, so the user sees what Kei shows."""
import json

from kei.apps import maya_session
from kei.apps.maya_session import Session, save_target
from kei.apps.maya_shot import key_pass, timeline


def test_a_loop_stops_one_frame_short_and_a_shot_shows_every_frame():
    assert timeline({"fps": 30, "loop": True}, 30) == {"start": 0, "end": 29, "fps": 30}
    assert timeline({"fps": 24}, 48) == {"start": 0, "end": 48, "fps": 24}
    assert timeline({}, 12) == {"start": 0, "end": 12, "fps": 24}


def test_keying_in_the_open_maya_sets_the_time_slider_before_the_keys(tmp_path, monkeypatch):
    shot = tmp_path / "walk"
    (shot / "out_p1").mkdir(parents=True)
    keys = [{"f": 0, "tangent": "spline", "kei:root_ctl.translateX": 0.0},
            {"f": 30, "tangent": "spline", "kei:root_ctl.translateX": 1.0}]
    (shot / "out_p1" / "shot.json").write_text(json.dumps({"rig": "maya", "fps": 30, "frames": 30, "loop": True,
                                                           "keys": keys}))
    save_target(shot, {"kind": "open", "pid": 7, "start_time": 1.0})
    calls = []

    def host(port, token, tool, inputs=None, timeout=60):
        calls.append((tool, inputs))
        return {"keys": 2, "clipped": []}

    monkeypatch.setattr(maya_session, "locate", lambda target, **f: Session(pid=7, start_time=1.0, port=1, token="t"))
    monkeypatch.setattr(maya_session, "call_host", host)
    key_pass(shot, "p1", mode="spline")
    assert [c[0] for c in calls] == ["set_time", "set_keys", "save_temp_copy"]
    assert calls[0][1] == {"start": 0, "end": 29, "fps": 30}
