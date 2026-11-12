"""A usage limit or a seat that cannot start pauses the stage; it never burns a try."""
import subprocess
import sys

from kei.cli import main
from kei.conductor import run_shot as _run_shot
from kei.config import Config, SeatSpec
from kei.seats import CliSeat, FakeSeat, SeatResult, pause_kind
from kei.state import load_state
from test_conductor import CFG, Recorder, shot, stage_of
from test_conductor_critic import PASS, critic

LIMIT = "You've hit your 5-hour limit · resets 12pm (America/Toronto)"


def run_shot(*args, review=None, **kwargs):
    return _run_shot(*args, review=review or (lambda stage, shot_dir, changed: []), **kwargs)


def test_usage_and_launch_messages_are_recognised():
    assert pause_kind(SeatResult(1, LIMIT)) == "usage"
    assert pause_kind(SeatResult(1, 'API Error: 429 {"type":"error","error":{"type":"rate_limit_error"}}')) == "usage"
    assert pause_kind(SeatResult(1, "Error: rate_limit exceeded")) == "usage"
    assert pause_kind(SeatResult(3221225794, "")) == "machine"
    assert pause_kind(SeatResult(-1073741502, "")) == "machine"
    assert pause_kind(SeatResult(1, "the stage failed")) is None
    assert pause_kind(SeatResult(0, "rate limit is a word an animator may write")) is None


def test_a_usage_limit_pauses_without_burning_a_try(tmp_path):
    root = shot(tmp_path)
    calls = []
    state = run_shot(root, "a box falls", CFG,
                     animator=FakeSeat("fake", lambda p, r: calls.append(p) or SeatResult(1, LIMIT)))
    assert (state.status, state.stage, state.attempts) == ("paused_usage", "brief", 0)
    assert len(calls) == 1
    assert state.history[-1]["result"] == "paused_usage"


def test_a_launch_failure_pauses_for_the_machine(tmp_path):
    root = shot(tmp_path)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", lambda p, r: SeatResult(3221225794, "")))
    assert (state.status, state.attempts) == ("paused_machine", 0)


def test_a_seat_that_does_not_start_is_a_machine_pause(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError(1455, "the paging file is too small")
    monkeypatch.setattr(subprocess, "Popen", boom)
    r = CliSeat(SeatSpec(name="s", cmd=[sys.executable, "-c", "pass"])).run("x", tmp_path)
    assert pause_kind(r) == "machine"
    assert "could not start" in r.output


def test_kei_run_resumes_a_paused_stage(tmp_path):
    root = shot(tmp_path)
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", lambda p, r: SeatResult(1, LIMIT)))
    rec = Recorder()
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec))
    assert state.status == "needs_approval"
    assert stage_of(rec.prompts[0]) == "Brief"
    assert [h["result"] for h in state.history if h["stage"] == "brief"][-2:] == ["resume", "pass"]


def test_a_critic_usage_limit_pauses_and_keeps_the_send_backs(tmp_path):
    root = shot(tmp_path)
    limited = critic("c1", lambda t, p: PASS)
    limited.action = lambda p, r: SeatResult(1, LIMIT)
    state = _run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[limited])
    assert (state.status, state.stage, state.send_backs, state.attempts) == ("paused_usage", "plan", 0, 0)


def test_status_says_why_it_stopped_in_plain_words(tmp_path, capsys):
    root = shot(tmp_path)
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", lambda p, r: SeatResult(1, LIMIT)))
    assert main(["status", str(root)]) == 0
    out = capsys.readouterr().out
    assert "usage or rate limit" in out and "not counted" in out and "kei run" in out


def test_run_exits_5_on_a_pause_and_needs_no_request_to_resume(tmp_path, capsys):
    root = tmp_path / "shot"
    root.mkdir()
    script = "import sys; print(\"You've hit your 5-hour limit\"); sys.exit(1)"
    c = tmp_path / "kei.toml"
    import json
    c.write_text("[animator]\ncmd = %s\n[[critics]]\nname = \"c\"\ncmd = %s\n" % (
        json.dumps([sys.executable, "-c", script]), json.dumps([sys.executable, "-c", "pass"])), encoding="utf-8")
    assert main(["run", str(root), "--request", "a box falls", "--config", str(c)]) == 5
    assert "usage or rate limit" in capsys.readouterr().out
    assert main(["run", str(root), "--config", str(c)]) == 5
    assert load_state(root).request == "a box falls"


def test_a_pause_at_review_resumes_at_review_without_rerunning_the_animator(tmp_path):
    root = shot(tmp_path)
    limited = critic("c1", lambda t, p: PASS)
    limited.action = lambda p, r: SeatResult(1, LIMIT)
    _run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[limited])
    rec = Recorder()
    state = _run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec), critics=[critic("c2", lambda t, p: PASS)])
    assert state.status == "needs_approval"
    assert stage_of(rec.prompts[0]) == "Blocking"
