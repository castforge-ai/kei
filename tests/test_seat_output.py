"""A seat's answer apart from its warnings, its token use read from Claude Code's JSON, and the totals per shot."""
import json
import sys

from kei.config import SeatSpec
from kei.seats import CliSeat, SeatResult, keep_run, run_totals, unwrap_json

CLAUDE_JSON = json.dumps({"type": "result", "result": '{"verdict": "pass", "notes": []}', "session_id": "x",
                          "usage": {"input_tokens": 2, "cache_read_input_tokens": 100,
                                    "cache_creation_input_tokens": 30, "output_tokens": 95}})


def test_claude_json_gives_the_reply_and_the_tokens():
    text, usage = unwrap_json(CLAUDE_JSON)
    assert text == '{"verdict": "pass", "notes": []}'
    assert usage == {"input": 2, "cache_read": 100, "cache_write": 30, "output": 95}


def test_plain_text_and_other_json_stay_as_they_are():
    assert unwrap_json("hello") == ("hello", None)
    assert unwrap_json('{"verdict": "pass", "notes": []}') == ('{"verdict": "pass", "notes": []}', None)


def script(tmp_path, body):
    p = tmp_path / "seat.py"
    p.write_text(body, encoding="utf-8")
    return CliSeat(SeatSpec(name="s", cmd=[sys.executable, str(p)]))


def test_warnings_on_stderr_stay_out_of_a_good_answer(tmp_path):
    seat = script(tmp_path, "import sys\nsys.stderr.write('warning: deprecated flag\\n')\n"
                            "print('{\"verdict\": \"pass\", \"notes\": []}')\n")
    r = seat.run("prompt", tmp_path)
    assert r.exit_code == 0 and "warning" not in r.output and "deprecated" in r.stderr


def test_a_failed_run_keeps_its_error_in_the_output(tmp_path):
    seat = script(tmp_path, "import sys\nsys.stderr.write('Error: usage limit reached\\n')\nsys.exit(1)\n")
    r = seat.run("prompt", tmp_path)
    assert r.exit_code == 1 and "usage limit" in r.output


def test_runs_add_up_per_shot(tmp_path):
    keep_run(tmp_path, "plan-animator", "p" * 10, SeatResult(0, "a", "", {"input": 5, "output": 7}), 30.0)
    keep_run(tmp_path, "critic-c", "p", SeatResult(0, "b", "warn"), 12.5)
    assert run_totals(tmp_path) == {"runs": 2, "seconds": 42.5, "tokens": {"input": 5, "output": 7}}
    assert (tmp_path / ".kei" / "runs" / "critic-c-1.err.txt").read_text(encoding="utf-8") == "warn"


CODEX = "\n".join(json.dumps(e) for e in [
    {"type": "thread.started", "thread_id": "01a1-thread"}, {"type": "turn.started"},
    {"type": "item.completed", "item": {"id": "i0", "type": "error", "message": "skills shortened"}},
    {"type": "item.completed", "item": {"id": "i1", "type": "agent_message", "text": '{"verdict": "pass", "notes": []}'}},
    {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 3}}])


def test_codex_events_give_the_reply_the_tokens_and_the_thread():
    from kei.seats import codex_events
    assert codex_events(CODEX) == ('{"verdict": "pass", "notes": []}', {"input": 10, "cache_read": 4, "output": 3},
                                   "01a1-thread")
    assert codex_events("plain text") == ("plain text", None, "")


def test_codex_resume_keeps_the_flags_resume_takes_and_turns_the_sandbox_into_config():
    from kei.seats import with_session
    spec = SeatSpec(name="g", cmd=["codex", "exec", "-m", "gpt", "--sandbox", "workspace-write", "--add-dir", "..",
                                   "--skip-git-repo-check", "-"])
    assert with_session(spec, "", False).cmd[:3] == ["codex", "exec", "--json"]
    cmd = with_session(spec, "01a1", True).cmd
    assert cmd[:3] == ["codex", "exec", "resume"] and cmd[-2:] == ["01a1", "-"]
    assert 'sandbox_mode="workspace-write"' in cmd and 'sandbox_workspace_write.writable_roots=[".."]' in cmd
    assert "--sandbox" not in cmd and "--add-dir" not in cmd and ["-m", "gpt"] == cmd[3:5]


def test_a_codex_animator_resumes_the_thread_of_its_first_try(tmp_path, monkeypatch):
    import kei.seats as seats
    from kei.conductor import _run_animator_seat
    from kei.state import ShotState
    import uuid
    from kei.seats import NO_SESSION, with_session
    runs = []

    def fake_run(self, prompt, workdir):
        runs.append(list(self.spec.cmd))
        return SeatResult(0, "done", "", None, "01a1-thread")
    monkeypatch.setattr(seats.CliSeat, "run", fake_run)
    state = ShotState(stage="blocking", status="running", request="a walk")
    animator = seats.CliSeat(SeatSpec(name="g", cmd=["codex", "exec", "--skip-git-repo-check", "-"]))
    for _ in range(2):
        _run_animator_seat(animator, "p", tmp_path, state, "blocking", seats.CliSeat, NO_SESSION, uuid, with_session)
    assert state.sessions["blocking"] == "01a1-thread"
    assert runs[0][:3] == ["codex", "exec", "--json"] and runs[1][:3] == ["codex", "exec", "resume"]
