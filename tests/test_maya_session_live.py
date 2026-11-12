"""Task 8 of plan 6 with Maya: a shot keyed in an "open" Maya (mayapy running the real Kei host, standing in for the
user's window) and its rig read through the host; the user's file stays the same on disk and in the session."""
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from kei.apps.maya import app_dir, maya_env
from kei.apps.maya_session import Question, choose_target, find_sessions, save_target
from kei.apps.maya_shot import key_pass, setup_shot
from kei.apps.maya_stage import open_rig

import mayakit

REPO = Path(__file__).resolve().parents[1]
WALK = json.loads((REPO / "examples" / "stepped_walk" / "out_blocking" / "shot.json").read_text())
pytestmark = pytest.mark.maya


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    py = mayakit.mayapy()
    d = tmp_path_factory.mktemp("live")
    root = d / "sessions"
    folder = app_dir()
    folder.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([str(py), str(REPO / "tests" / "maya" / "host_in_batch.py"), str(d), str(root)],
                            env=maya_env(folder), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    end = time.time() + 240
    while time.time() < end and not list(root.glob("*/session.json")):
        assert proc.poll() is None, proc.stdout.read()[-2000:]
        time.sleep(0.5)
    old = os.environ.get("KEI_MAYA_SESSIONS")
    os.environ["KEI_MAYA_SESSIONS"] = str(root)          # Kei finds the stand-in session where it wrote its file
    try:
        yield from _drive(py, d, root, proc)
    finally:
        if old is None:
            os.environ.pop("KEI_MAYA_SESSIONS", None)
        else:
            os.environ["KEI_MAYA_SESSIONS"] = old
        (d / "stop").write_text("")       # never leave the stand-in Maya running
        if proc.poll() is None:
            proc.communicate(timeout=120)


def _drive(py, d, root, proc):
    sessions, hostless = find_sessions(root, maya_pids=lambda: [])
    user = d / "user.ma"
    before = hashlib.sha256(user.read_bytes()).hexdigest()
    shot = d / "shot"
    q = choose_target(sessions, hostless)
    save_target(shot, q.choices[0])
    open_rig(shot, sessions[0])
    (shot / "out_p1").mkdir(parents=True)
    (shot / "out_p1" / "shot.json").write_text(json.dumps(WALK))
    report = key_pass(shot, "p1", mode="step", mayapy=py)
    open_rig(shot, sessions[0])           # read again after the keys: the user's undo queue must not change
    # a second pass on top: it must replace the first in Maya, the same as the background keys of that pass
    second = json.loads(json.dumps(WALK))
    for k in second["keys"]:
        k["root"] = [k["root"][0] + 0.05, k["root"][1] - 0.03, k["root"][2]]
        k["head"] = [0.2, 0.0, 0.4]
        k["legSL"] = 1.05
    (shot / "out_p2").mkdir()
    (shot / "out_p2" / "shot.json").write_text(json.dumps(second))
    report2 = key_pass(shot, "p2", mode="step", mayapy=py)
    bg = d / "bg"
    setup_shot(bg, character="kei", mayapy=py)
    (bg / "out_p2").mkdir()
    (bg / "out_p2" / "shot.json").write_text(json.dumps(second))
    key_pass(bg, "p2", mode="step", mayapy=py)
    # the session finder looks again, as Kei does at each question
    again = find_sessions(root, maya_pids=lambda: [])[0]
    (d / "stop").write_text("")
    out = proc.communicate(timeout=120)[0]
    yield {"q": q, "shot": shot, "bg": bg, "report2": report2, "report": report, "user": user, "before": before, "again": again,
           "state": (d / "state.txt").read_text() if (d / "state.txt").exists() else out[-2000:], "proc": proc}


def test_the_question_names_the_open_scene_with_its_rig_and_unsaved_changes(live):
    q = live["q"]
    assert isinstance(q, Question)
    assert "user.ma" in q.text and "rig kei" in q.text and "unsaved changes" in q.text


def test_the_pass_is_keyed_in_the_open_session_on_its_own_layer(live):
    r = live["report"]
    assert r["target"] == "open" and r["layer"] == "kei_p1" and r["clipped"] == []
    assert "frames 0 to 12" in r["said"]
    copy = (live["shot"] / "out_p1" / "scene.ma").read_text(errors="replace")
    assert "kei_p1" in copy
    assert json.loads((live["shot"] / "out_p1" / "joints.json").read_text())["source"] == "maya"


def test_the_user_s_file_and_session_stay_as_they_were(live):
    assert hashlib.sha256(live["user"].read_bytes()).hexdigest() == live["before"]
    scene, modified, ty, last_undo = live["state"].split("|")
    assert scene.endswith("user.ma") and modified == "True" and float(ty) == 3.0
    assert last_undo == "kei_set_keys"     # the last undoable step is a pass of keys: no nudge after it
    assert live["proc"].returncode == 0


def test_the_session_is_found_again_and_the_rig_was_read_through_the_host(live):
    assert len(live["again"]) == 1
    ctl = json.loads((live["shot"] / "rig" / "maya_controls.json").read_text())
    assert ctl["namespace"] == "kei" and any(c["name"] == "kei:l_foot_ik_ctl" for c in ctl["controls"])


def test_a_second_pass_in_the_open_session_replaces_the_first_as_in_the_background(live):
    """Each pass is an override layer and the other kei_ layers are muted, so pass 2 does not stack on pass 1 and a
    channel whose rest is not zero (ikFk 1, stretch 1, ballAngle 34.4) is not doubled."""
    open_ = json.loads((live["shot"] / "out_p2" / "joints.json").read_text())["frames"]
    back = json.loads((live["bg"] / "out_p2" / "joints.json").read_text())["frames"]
    worst = max((max(abs(a - b) for a, b in zip(o["joints"][n], g["joints"][n])), o["f"], n)
                for o, g in zip(open_, back) for n in g["joints"])
    assert worst[0] < 0.001, worst