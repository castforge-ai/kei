"""The animator keeps one session per stage (Claude Code here; Codex in test_seat_output): later tries resume it."""
from kei.config import SeatSpec
from kei.conductor import _run_animator
from kei.seats import CliSeat, SeatResult, with_session
from kei.state import ShotState

CLAUDE = SeatSpec(name="a", cmd=["claude", "-p", "--output-format", "text"])


def test_a_claude_seat_starts_then_resumes_a_session():
    assert with_session(CLAUDE, "u1", False).cmd[:3] == ["claude", "--session-id", "u1"]
    assert with_session(CLAUDE, "u1", True).cmd[:3] == ["claude", "--resume", "u1"]
    other = SeatSpec(name="o", cmd=["gemini", "-p"])
    assert with_session(other, "u1", False) is other     # Codex has its own session path (test_seat_output)


def test_the_conductor_keeps_the_session_per_stage(monkeypatch):
    seen = []

    def run(self, prompt, workdir):
        seen.append(list(self.spec.cmd))
        return SeatResult(0, "ok")
    monkeypatch.setattr(CliSeat, "run", run)
    st = ShotState(stage="plan")
    _run_animator(CliSeat(CLAUDE), "p", ".", st, "plan")
    sid = st.sessions["plan"]
    _run_animator(CliSeat(CLAUDE), "p", ".", st, "plan")
    _run_animator(CliSeat(CLAUDE), "p", ".", st, "blocking")
    assert seen[0][1:3] == ["--session-id", sid] and seen[1][1:3] == ["--resume", sid]
    assert seen[2][1] == "--session-id" and st.sessions["blocking"] != sid


def test_a_lost_session_starts_afresh(monkeypatch):
    calls = []

    def run(self, prompt, workdir):
        calls.append(list(self.spec.cmd))
        return SeatResult(1, "No conversation found with session ID") if "--resume" in self.spec.cmd \
            else SeatResult(0, "ok")
    monkeypatch.setattr(CliSeat, "run", run)
    st = ShotState(stage="plan", sessions={"plan": "old"})
    assert _run_animator(CliSeat(CLAUDE), "p", ".", st, "plan").exit_code == 0
    assert calls[1][1] == "--session-id" and st.sessions["plan"] != "old"


def test_a_try_records_the_scripts_it_wrote_and_names_the_ones_outside_scratch(monkeypatch, tmp_path):
    def run(self, prompt, workdir):
        (tmp_path / ".kei" / "scratch").mkdir(parents=True, exist_ok=True)
        (tmp_path / ".kei" / "scratch" / "probe.py").write_text("", encoding="utf-8")
        (tmp_path / "fix_keys.py").write_text("", encoding="utf-8")
        return SeatResult(0, "ok")
    monkeypatch.setattr(CliSeat, "run", run)
    (tmp_path / "old.py").write_text("", encoding="utf-8")
    st = ShotState(stage="plan")
    _run_animator(CliSeat(CLAUDE), "p", tmp_path, st, "plan")
    assert st.last_run["scripts"] == 2 and st.last_run["scripts_outside_scratch"] == ["fix_keys.py"]


def test_a_try_that_runs_out_of_time_keeps_its_work_and_is_not_counted(tmp_path, monkeypatch):
    from kei.conductor import MAX_TIMEOUTS, TIMEOUT_NOTE
    from test_conductor import CFG, run_shot, shot
    seen = []

    def run(self, prompt, workdir):
        seen.append((self.spec.timeout_s, prompt))
        return SeatResult(124, "timeout after 1 s")
    monkeypatch.setattr(CliSeat, "run", run)
    from dataclasses import replace
    config = replace(CFG, stage_timeouts={"brief": 77})
    root = shot(tmp_path)
    st = run_shot(root, "a box falls", config, animator=CliSeat(CLAUDE))
    timeouts = [h for h in st.history if h["result"] == "timeout"]
    assert len(timeouts) == MAX_TIMEOUTS and all(h["attempt"] == 1 for h in timeouts)   # not counted as tries
    assert seen[0][0] == 77 and TIMEOUT_NOTE in seen[1][1]                              # its own limit, told to go on


def test_timeouts_are_read_per_stage(tmp_path):
    import pytest
    from kei.config import ConfigError, load_config
    p = tmp_path / "kei.toml"
    p.write_text('[animator]\ncmd = ["x"]\n[timeouts]\nblocking = 5400\n', encoding="utf-8")
    assert load_config(p).stage_timeouts == {"blocking": 5400}
    p.write_text('[animator]\ncmd = ["x"]\n[timeouts]\nwings = 5\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)
