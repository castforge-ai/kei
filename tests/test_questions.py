"""Any stage, or any critic, can ask the author a question; the answer reaches the animator and the critics."""
import json
import shutil

import pytest

from kei.cli import main
from kei.conductor import run_shot
from kei.critic import critic_prompt, parse_verdict
from kei.render import render_shot
from kei.seats import FakeSeat
from kei.stages import stage_by_id
from kei.state import load_state
from shotkit import write
from test_conductor import CFG, Recorder, shot, stage_of
from test_conductor_critic import PASS, critic

VIEW_Q = {"text": "Watch the blocking ten times at 24 fps: does the seam hitch?",
          "look_at": "out_blocking/blocking_x10.mp4"}


def no_review(stage, shot_dir, changed):
    return []


def test_a_question_at_any_stage_stops_for_an_answer(tmp_path):
    root = shot(tmp_path)

    def fault(sid, n, r):
        if sid == "blocking" and n == 1:
            write(r, "QUESTIONS.md", "Does the seam hitch? Look at out_blocking/blocking.mp4\n")
        return False

    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(fault)), review=no_review)
    assert (state.status, state.stage, state.attempts) == ("needs_answer", "blocking", 0)
    assert state.questions[0]["from"] == "animator"
    assert "out_blocking/blocking.mp4" in state.questions[0]["look_at"]


def test_a_verdict_can_carry_questions_and_sign_off_checks():
    out = json.dumps({"verdict": "pass", "notes": [], "questions": [VIEW_Q],
                      "sign_off": ["Frame 0-12: the box tips without a hitch"]})
    v = parse_verdict("codex", out)
    assert v.passed
    assert v.questions[0]["text"].startswith("Watch the blocking")
    assert v.questions[0]["look_at"] == ["out_blocking/blocking_x10.mp4"]
    assert v.sign_off == ("Frame 0-12: the box tips without a hitch",)


def test_a_critic_question_stops_the_stage_without_a_send_back(tmp_path):
    root = shot(tmp_path)
    asked = json.dumps({"verdict": "send_back", "notes": ["f9: the hips sink late"], "questions": [VIEW_Q]})
    c = critic("c1", lambda t, p: asked if t == "Blocking" else PASS)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[c])
    assert (state.status, state.stage, state.send_backs, state.attempts) == ("needs_answer", "blocking", 0, 0)
    q = state.questions[0]
    assert q["from"] == "critic c1" and q["look_at"] == ["out_blocking/blocking_x10.mp4"]


def test_the_answer_reaches_the_animator_and_the_critics(tmp_path, capsys):
    root = shot(tmp_path)
    asked = json.dumps({"verdict": "pass", "notes": [], "questions": [VIEW_Q]})
    answers = iter([asked])
    c = critic("c1", lambda t, p: next(answers, PASS) if t == "Blocking" else PASS)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[c])
    assert state.status == "needs_answer"
    assert main(["status", str(root)]) == 0
    out = capsys.readouterr().out
    assert "out_blocking/blocking_x10.mp4" in out and "kei answer" in out
    assert main(["answer", str(root), "--text", "Watched ten loops at 24 fps: no hitch at the seam."]) == 0
    rec = Recorder()
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec), critics=[c])
    assert state.status == "needs_approval"
    first = [p for p in rec.prompts if stage_of(p) == "Blocking"][0]
    assert "Watched ten loops at 24 fps: no hitch at the seam." in first
    assert "Watch the blocking ten times" in first
    later = [p for p in c.prompts if "Stage under review: Blocking" in p][-1]
    assert "Watched ten loops at 24 fps: no hitch at the seam." in later


def test_critic_prompt_says_a_recorded_viewing_satisfies_real_rate_rules(tmp_path):
    p = critic_prompt(stage_by_id("blocking"), tmp_path, "a walk", [])
    assert "author viewing at sign-off" in p
    assert "real rate" in p


def test_sign_off_checks_wait_on_the_approval_checklist(tmp_path, capsys):
    root = shot(tmp_path)
    marked = json.dumps({"verdict": "pass", "notes": [],
                         "sign_off": ["Frame 9-12: the landing reads heavy at full speed"]})
    c = critic("c1", lambda t, p: marked if t == "Blocking" else PASS)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[c])
    assert state.status == "needs_approval"
    assert main(["status", str(root)]) == 0
    out = capsys.readouterr().out
    assert "Before you approve" in out and "Frame 9-12: the landing reads heavy at full speed" in out
    assert out.count("the landing reads heavy") == 1   # one item, however many critics or tries marked it


def test_answer_clears_the_questions_and_records_the_reply(tmp_path):
    root = shot(tmp_path)

    def fault(sid, n, r):
        if sid == "rig" and n == 1:
            write(r, "QUESTIONS.md", "Which rig?\n")
        return False

    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(fault)), review=no_review)
    assert main(["answer", str(root), "--text", "Kei's own rig"]) == 0
    s = load_state(root)
    assert s.status == "running" and s.questions == []
    assert s.answers[-1]["answer"] == "Kei's own rig" and "Which rig?" in s.answers[-1]["question"]
    assert not (root / "QUESTIONS.md").exists()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_a_loop_render_writes_the_ten_loop_mp4(tmp_path):
    from test_render import ffmpeg_frames
    src = tmp_path / "shot.json"
    src.write_text(json.dumps({"rig": "v4", "fps": 24, "frames": 4, "loop": True,
                               "keys": [{"f": 0, "yaw": 0.2}, {"f": 2, "yaw": -0.2}, {"f": 4, "yaw": 0.2}]}),
                   encoding="utf-8")
    out = render_shot(src, tmp_path / "out", "step", size=60, name="blocking")
    assert out["loops"] == tmp_path / "out" / "blocking_x10.mp4"
    assert len(ffmpeg_frames(out["loops"], 120, 120)) == 40


GOOD = "Frame 13-18: the left hand's arc looks off"


@pytest.mark.parametrize("check, why", [
    (GOOD, None),
    ("Frames 3-4: the heel lands soft", None),
    ("Frame 7: the head stays level", None),
    ("the left hand's arc looks off", "Frame"),
    ("Frame 13-18: BLK42 the left hand's arc looks off", "rule"),
    ("Frame 13-18: the arc in out_p35/playback_x10.mp4 looks off", "file"),
    ("Frame 13-18: critic codex thinks the arc looks off", "critic"),
    ("Frame 13-18: watch the left hand and the right hand and the head and the hips", "12 words"),
])
def test_the_sign_off_wording(check, why):
    from kei.checklist import check_wording
    got = check_wording(check)
    assert (got is None) if why is None else (why in got)


def test_a_critic_with_badly_worded_checks_is_asked_once_more(tmp_path):
    root = shot(tmp_path)
    bad = json.dumps({"verdict": "pass", "notes": [], "sign_off": ["BLK42: play out_blocking/blocking_x10.mp4"]})
    good = json.dumps({"verdict": "pass", "notes": [], "sign_off": ["Frame 9-12: the landing reads heavy"]})
    answers = iter([bad, good])
    c = critic("c1", lambda t, p: next(answers, PASS) if t == "Blocking" else PASS)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[c])
    assert state.status == "needs_approval"
    assert [i["check"] for i in state.sign_off] == ["Frame 9-12: the landing reads heavy"]
    retry = [p for p in c.prompts if "Stage under review: Blocking" in p][1]
    assert "BLK42: play out_blocking/blocking_x10.mp4" in retry and "12 words" in retry


def test_a_critic_that_keeps_the_wrong_wording_sends_the_stage_back_naming_why(tmp_path):
    from kei.critic import panel_review
    from kei.stages import stage_by_id
    bad = json.dumps({"verdict": "pass", "notes": [], "sign_off": ["BLK42: play out_blocking/blocking_x10.mp4"]})
    c = critic("c1", lambda t, p: bad)
    panel = panel_review(stage_by_id("blocking"), shot(tmp_path), "a box falls", [c])
    assert len(c.prompts) == 2 and panel.sign_off == []
    assert any("c1" in n and "sign-off" in n for n in panel)
