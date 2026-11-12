import re

from kei.conductor import run_shot as _run_shot
from kei.config import Config, SeatSpec
from kei.seats import FakeSeat, SeatResult
from kei.state import ShotState, load_state, save_state
from shotkit import STAGE_WRITERS, write

IDS = list(STAGE_WRITERS)
CFG = Config(animator=SeatSpec(name="fake", cmd=["unused"]), max_attempts=3)


def run_shot(*args, review=None, **kwargs):
    """These tests are about the stages and the gates; a critic that always passes stands in for the panel."""
    return _run_shot(*args, review=review or (lambda stage, shot_dir, changed: []), **kwargs)


def stage_of(prompt):
    return re.search(r"^Stage: (.+)$", prompt, re.M).group(1)


TITLES = {"Brief": "brief", "Rig evaluation": "rig", "Weight evaluation": "weight",
          "Understanding score": "understanding", "Reference search": "references", "Study": "study",
          "Plan": "plan", "Blocking": "blocking", "Breakdowns, spline and polish": "passes",
          "All the checks": "checks", "Self-review": "self_review", "Delivery": "deliver"}


class Recorder:
    """A fake animator that does each stage's work, with optional faults."""

    def __init__(self, fault=None):
        self.prompts = []
        self.fault = fault or (lambda sid, n, root: False)

    def __call__(self, prompt, root):
        self.prompts.append(prompt)
        sid = TITLES[stage_of(prompt)]
        n = sum(1 for p in self.prompts if TITLES[stage_of(p)] == sid)
        if not self.fault(sid, n, root):
            STAGE_WRITERS[sid](root)
        return SeatResult(0, "done")


def shot(tmp_path):
    root = tmp_path / "shots" / "box_fall"
    root.mkdir(parents=True)
    return root


def passed(state):
    return [h["stage"] for h in state.history if h["result"] == "pass"]


def test_runs_every_stage_in_order(tmp_path):
    root = shot(tmp_path)
    state = run_shot(root, "a box falls off a table", CFG, animator=FakeSeat("fake", Recorder()))
    assert state.status == "needs_approval"
    assert passed(state) == IDS


def test_gate_refusal_retries_with_the_misses(tmp_path):
    root = shot(tmp_path)

    def fault(sid, n, r):
        if sid == "plan" and n == 1:
            write(r, "plan/plan.json", '{"keys": [{"f": 0, "function": "slip"}]}')
            return True   # no plan sheet on the first try
        return False

    rec = Recorder(fault)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec))
    plan_prompts = [p for p in rec.prompts if stage_of(p) == "Plan"]
    assert "The gate refused the last attempt" in plan_prompts[1]
    assert re.search(r"^- P7", plan_prompts[1], re.M)
    assert state.status == "needs_approval"


def test_stops_for_a_human_after_max_attempts(tmp_path):
    root = shot(tmp_path)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(lambda sid, n, r: sid == "rig")))
    assert state.status == "needs_human"
    assert state.stage == "rig"
    assert [h["result"] for h in state.history if h["stage"] == "rig"] == ["fail", "fail", "fail"]


def test_seat_failure_counts_as_an_attempt(tmp_path):
    root = shot(tmp_path)
    seat = FakeSeat("fake", lambda p, r: SeatResult(127, "command not found: claude"))
    state = run_shot(root, "a box falls", CFG, animator=seat)
    assert state.status == "needs_human"
    assert state.history[0]["result"] == "seat_error"
    assert "command not found: claude" in state.history[0]["misses"]


def test_resume_continues_at_the_saved_stage(tmp_path):
    root = shot(tmp_path)
    for sid in IDS[:6]:
        STAGE_WRITERS[sid](root)
    save_state(root, ShotState(stage="plan", attempts=1, request="a box falls"))
    rec = Recorder()
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec))
    assert stage_of(rec.prompts[0]) == "Plan"


def test_review_notes_send_the_stage_back(tmp_path):
    root = shot(tmp_path)
    calls = []

    def review(stage, shot_dir, changed):
        if stage.id == "blocking":
            calls.append(1)
            return ["arc of the hips is straight"] if len(calls) == 1 else []
        return []

    rec = Recorder()
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec), review=review)
    blocking = [p for p in rec.prompts if stage_of(p) == "Blocking"]
    assert "arc of the hips is straight" in blocking[1]
    assert state.status == "needs_approval"


def test_question_at_the_start_pauses_for_an_answer(tmp_path):
    root = shot(tmp_path)

    def fault(sid, n, r):
        if sid == "brief":
            write(r, "QUESTIONS.md", "Which hand holds the sword?\n")
        return False

    state = run_shot(root, "a sword swing", CFG, animator=FakeSeat("fake", Recorder(fault)))
    assert (state.status, state.stage, state.attempts) == ("needs_answer", "brief", 0)


def test_a_question_after_the_start_also_waits_for_the_author(tmp_path):
    root = shot(tmp_path)

    def fault(sid, n, r):
        if sid == "blocking" and n == 1:
            write(r, "QUESTIONS.md", "Should the box spin?\n")
        return False

    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(fault)))
    assert (root / "QUESTIONS.md").exists()
    assert (state.status, state.stage, state.attempts) == ("needs_answer", "blocking", 0)


def test_no_stage_is_ever_skipped(tmp_path):
    root = shot(tmp_path)
    rec = Recorder()

    def everything_at_once(prompt, r):
        rec.prompts.append(prompt)
        if stage_of(prompt) == "Brief":
            for sid in IDS:
                STAGE_WRITERS[sid](r)
        return SeatResult(0, "done")

    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", everything_at_once))
    assert passed(state) == IDS
    assert len(rec.prompts) == 12


def test_a_finished_shot_is_left_alone(tmp_path):
    root = shot(tmp_path)
    save_state(root, ShotState(stage="deliver", status="done"))
    rec = Recorder()
    state = run_shot(root, "x", CFG, animator=FakeSeat("fake", rec))
    assert state.status == "done" and rec.prompts == []
    assert load_state(root).status == "done"
