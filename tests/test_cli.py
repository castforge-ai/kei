import json
import sys

from kei.cli import main
from kei.state import ShotState, load_state, save_state

CRITIC = '\n[[critics]]\nname = "c"\ncmd = %s\n' % json.dumps([sys.executable, "-c", "pass"])


def cfg(tmp_path, body, critic=True):
    p = tmp_path / "kei.toml"
    p.write_text(body + (CRITIC if critic else ""), encoding="utf-8")
    return str(p)


def test_status_of_a_new_shot(tmp_path, capsys):
    assert main(["status", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "brief" in out and "0" in out and "running" in out


def test_bad_config_is_one_line_and_exit_1(tmp_path, capsys):
    c = cfg(tmp_path, '[animator]\ncmd = ["x"]\n[limits]\nmax_attempts = 0\n')
    assert main(["run", str(tmp_path), "--request", "x", "--config", c]) == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "max_attempts" in text and "Traceback" not in text


def test_run_stops_for_a_human_with_exit_2(tmp_path, capsys):
    shot = tmp_path / "shot"
    shot.mkdir()
    c = cfg(tmp_path, "[animator]\ncmd = %s\n[limits]\nmax_attempts = 1\n" % json.dumps([sys.executable, "-c", "pass"]))
    assert main(["run", str(shot), "--request", "a box falls", "--config", c]) == 2
    out = capsys.readouterr().out
    assert "brief: needs_human" in out
    assert any(line.startswith("- P1") for line in out.splitlines())


def test_run_prints_questions_and_exits_3(tmp_path, capsys):
    shot = tmp_path / "shot"
    shot.mkdir()
    script = "open('QUESTIONS.md', 'w').write('Which hand holds the sword?')"
    c = cfg(tmp_path, "[animator]\ncmd = %s\n" % json.dumps([sys.executable, "-c", script]))
    assert main(["run", str(shot), "--request", "a sword swing", "--config", c]) == 3
    assert "Which hand holds the sword?" in capsys.readouterr().out


def test_answer_resumes_a_paused_shot(tmp_path):
    save_state(tmp_path, ShotState(status="needs_answer", request="a sword swing"))
    (tmp_path / "QUESTIONS.md").write_text("Which hand?", encoding="utf-8")
    assert main(["answer", str(tmp_path), "--text", "the right hand"]) == 0
    s = load_state(tmp_path)
    assert s.status == "running"
    assert s.request == "a sword swing"
    assert s.answers[-1]["answer"] == "the right hand" and s.answers[-1]["question"] == "Which hand?"
    assert not (tmp_path / "QUESTIONS.md").exists()


def test_answer_on_a_shot_that_did_not_ask(tmp_path, capsys):
    assert main(["answer", str(tmp_path), "--text", "x"]) == 1
    assert "Traceback" not in capsys.readouterr().out


def test_retry_resumes_a_shot_that_stopped_for_a_human(tmp_path, capsys):
    save_state(tmp_path, ShotState(stage="rig", attempts=3, status="needs_human", request="a box falls"))
    assert main(["retry", str(tmp_path)]) == 0
    s = load_state(tmp_path)
    assert (s.stage, s.attempts, s.status) == ("rig", 0, "running")
    assert s.history[-1]["result"] == "retry"


def test_retry_on_a_running_shot_is_refused(tmp_path, capsys):
    assert main(["retry", str(tmp_path)]) == 1
    assert "Traceback" not in capsys.readouterr().out


def test_status_shows_send_backs(tmp_path, capsys):
    save_state(tmp_path, ShotState(stage="plan", send_backs=2, request="x"))
    assert main(["status", str(tmp_path)]) == 0
    assert "send-backs: 2" in capsys.readouterr().out


def test_retry_resets_send_backs(tmp_path):
    save_state(tmp_path, ShotState(stage="plan", attempts=0, send_backs=3, status="needs_human", request="x"))
    assert main(["retry", str(tmp_path)]) == 0
    s = load_state(tmp_path)
    assert (s.attempts, s.send_backs, s.status) == (0, 0, "running")


def test_run_without_a_critic_is_one_line_and_exit_1(tmp_path, capsys):
    shot = tmp_path / "shot"
    shot.mkdir()
    c = cfg(tmp_path, "[animator]\ncmd = %s\n" % json.dumps([sys.executable, "-c", "pass"]), critic=False)
    assert main(["run", str(shot), "--request", "a box falls", "--config", c]) == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "critic" in text and "Traceback" not in text


def test_status_piped_prints_any_character(tmp_path):
    """Piped on Windows, stdout is the ANSI code page, which has no arrow: status must still print it."""
    import os
    import subprocess
    save_state(tmp_path, ShotState(stage="plan", status="needs_human",
                                   history=[{"stage": "plan", "result": "fail", "misses": ["f9 → f12: the hips sink"]}]))
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env["PYTHONIOENCODING"] = "cp1252"   # the ANSI code page a Windows pipe gets, on every system
    r = subprocess.run([sys.executable, "-c", "import sys; from kei.cli import main; sys.exit(main(sys.argv[1:]))",
                        "status", str(tmp_path)], capture_output=True, env=env)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert "the hips sink" in r.stdout.decode("utf-8", "replace")
