"""Task 8 of plan 6, the conductor: a Maya shot asks where to animate when Maya is open, kei answer picks by number,
and an open Maya that stops answering mid-pass stops the shot with paused_machine. No Maya needed."""
import dataclasses
import json

import pytest

from kei.apps import maya_stage
from kei.apps.maya_side.kei_host import Host
from kei.apps.maya_side.kei_tools import tool_entry
from kei.cli import main
from kei.conductor import run_shot as _run_shot
from kei.seats import FakeSeat, SeatResult
from kei.state import load_state
from test_conductor import CFG, shot

MAYA = dataclasses.replace(CFG, app="maya")


def run_shot(*args, **kwargs):
    return _run_shot(*args, review=lambda stage, shot_dir, changed: [], **kwargs)


@pytest.fixture
def host(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    info = {"maya_version": "2027", "scene": "C:/shots/user.ma", "unsaved": True, "rigs": ["kei:kei_rig"]}
    from kei.apps.maya_side.kei_host import session_root
    h = Host({"scene_info": tool_entry(lambda: info, "read")}, executor=lambda fn: fn(), session_dir=session_root(),
             info=lambda: info)
    h.start()
    monkeypatch.setattr("kei.apps.maya_session.kei_proc.maya_pids", lambda: [])
    yield h
    h.stop()


def test_a_maya_shot_with_maya_open_asks_where_before_any_stage_runs(tmp_path, host, capsys):
    root = shot(tmp_path)
    ran = []
    state = run_shot(root, "a walk", MAYA, animator=FakeSeat("fake", lambda p, r: ran.append(p) or SeatResult(0, "")))
    assert state.status == "needs_answer" and ran == []
    q = state.questions[0]
    assert q["kind"] == "maya_target" and "C:/shots/user.ma" in q["text"] and "unsaved changes" in q["text"]
    assert main(["status", str(root)]) == 0
    assert "Where should Kei animate" in capsys.readouterr().out


def test_kei_answer_takes_the_choice_by_number_and_refuses_one_out_of_range(tmp_path, host, capsys):
    root = shot(tmp_path)
    run_shot(root, "a walk", MAYA, animator=FakeSeat("fake", lambda p, r: SeatResult(0, "")))
    assert main(["answer", str(root), "--text", "7"]) == 1
    assert "from 1 to 2" in "".join(capsys.readouterr())
    assert load_state(root).status == "needs_answer"
    assert main(["answer", str(root), "--text", "1"]) == 0
    target = json.loads((root / "maya" / "target.json").read_text())
    assert target["kind"] == "open" and target["pid"] == host.state["pid"] and "token" not in target


def test_the_background_setting_never_asks(tmp_path, host, monkeypatch):
    root = shot(tmp_path)
    monkeypatch.setattr(maya_stage, "setup_shot", lambda *a, **k: (root / "maya" / "scene.ma").write_text("//"))
    cfg = dataclasses.replace(MAYA, maya_session="background")
    state = run_shot(root, "a walk", cfg, animator=FakeSeat("fake", lambda p, r: SeatResult(0, "")))
    assert state.status != "needs_answer"
    assert json.loads((root / "maya" / "target.json").read_text()) == {"kind": "background"}


def test_an_open_maya_that_stops_answering_mid_pass_pauses_the_shot_for_the_machine(tmp_path, monkeypatch):
    root = shot(tmp_path)
    monkeypatch.setattr(maya_stage, "prepare", lambda shot_dir, config: None)

    def animator(prompt, shot_dir):
        maya_stage.stop_for_machine(shot_dir, "Maya stopped answering while keying blocking")
        return SeatResult(0, "")
    state = run_shot(root, "a walk", MAYA, animator=FakeSeat("fake", animator))
    assert (state.status, state.attempts) == ("paused_machine", 0)
    assert "stopped answering" in state.history[-1]["misses"][0]
    assert not (root / "maya" / "PAUSED.md").exists()


def test_kei_run_app_maya_records_the_user_s_scene_to_copy(tmp_path):
    root = tmp_path / "s"
    scene = tmp_path / "mine.ma"
    scene.write_text("//Maya ASCII")
    maya_stage.record_source(root, scene)
    assert maya_stage.source_scene(root) == scene.resolve()
    assert maya_stage.wants_maya(root, "kei")


def test_the_background_setup_builds_the_character_plan_md_names_over_the_config_s(tmp_path, monkeypatch):
    root = shot(tmp_path)
    (root / "PLAN.md").write_text("# a walk\n\nCharacter: keira\n", encoding="utf-8")
    maya_stage.save_target(root, {"kind": "background"})
    asked = []
    monkeypatch.setattr(maya_stage, "setup_shot", lambda shot_dir, **k: asked.append(k["character"]))
    assert maya_stage.prepare(root, dataclasses.replace(MAYA, character="kei")) is None
    assert asked == ["keira"]
