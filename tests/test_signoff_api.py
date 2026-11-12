"""approve, note and reject as functions: the one code path the kei commands and the review page share."""
import json

import pytest

from kei.book import load_rules
from kei.cli import main
from kei.state import ShotState, load_state, save_state
from test_cli import cfg
from test_conductor import shot


def waiting(tmp_path, status="needs_approval"):
    root = shot(tmp_path)
    save_state(root, ShotState(stage="deliver", status=status, request="a box falls",
                               approved_plan={"plan/plan.json": "abc"}))
    return root


def make_round(root, n):
    from reviewkit import fake_round
    fake_round(root, f"r{n}", f"p{n}")


def test_approve_from_needs_approval(tmp_path):
    from kei.signoff import approve_shot
    root = waiting(tmp_path)
    s = approve_shot(root)
    assert s.status == "done" and s.history[-1]["result"] == "approved"
    assert load_state(root).status == "done"


@pytest.mark.parametrize("status", ["running", "needs_answer", "needs_human", "done", "paused_usage",
                                    "paused_machine", "rejected"])
def test_approve_refused_from_every_other_status(tmp_path, status):
    from kei.signoff import SignOffError, approve_shot
    root = waiting(tmp_path, status)
    with pytest.raises(SignOffError, match=status):
        approve_shot(root)
    assert load_state(root).status == status


def test_approve_of_a_round_that_is_not_the_latest_is_refused(tmp_path):
    from kei.signoff import SignOffError, approve_shot
    root = waiting(tmp_path)
    make_round(root, 1)
    make_round(root, 2)
    with pytest.raises(SignOffError, match="r2"):
        approve_shot(root, "r1")
    assert load_state(root).status == "needs_approval"
    assert approve_shot(root, "r2").status == "done"
    assert load_state(root).history[-1]["round"] == "r2"


def test_approve_of_a_round_that_does_not_exist_is_refused(tmp_path):
    from kei.signoff import SignOffError, approve_shot
    root = waiting(tmp_path)
    with pytest.raises(SignOffError):
        approve_shot(root, "r1")
    assert load_state(root).status == "needs_approval"


def test_note_adds_a_lesson_and_keeps_the_drawings_in_history(tmp_path):
    from kei.signoff import note_shot
    root = waiting(tmp_path)
    lessons = tmp_path / "lessons.local.md"
    s, lesson = note_shot(root, "the feet slide", "passes", lessons, ["review/r1/drawings/f0003_side.png"])
    assert lesson == "local.1"
    assert (s.stage, s.status, s.attempts, s.send_backs) == ("passes", "running", 0, 0)
    h = load_state(root).history[-1]
    assert h["result"] == "note" and h["lesson"] == "local.1" and h["misses"] == ["the feet slide"]
    assert h["drawings"] == ["review/r1/drawings/f0003_side.png"]
    assert [r.id for r in load_rules([lessons])] == ["local.1"]


def test_note_with_no_drawings_has_no_drawings_key(tmp_path):
    from kei.signoff import note_shot
    root = waiting(tmp_path)
    note_shot(root, "x", "passes", tmp_path / "l.md")
    assert "drawings" not in load_state(root).history[-1]


def test_note_with_an_unknown_stage_is_refused_and_writes_nothing(tmp_path):
    from kei.signoff import SignOffError, note_shot
    root = waiting(tmp_path)
    with pytest.raises(SignOffError, match="bloking"):
        note_shot(root, "x", "bloking", tmp_path / "l.md")
    assert not (tmp_path / "l.md").exists()
    assert load_state(root).status == "needs_approval"


def test_reject_keeps_the_reason_and_adds_no_lesson_by_default(tmp_path):
    from kei.signoff import reject_shot
    root = waiting(tmp_path)
    lessons = tmp_path / "l.md"
    s = reject_shot(root, "wrong brief: she should run", False, lessons)
    assert s.status == "rejected"
    h = load_state(root).history[-1]
    assert h["result"] == "rejected" and h["reason"] == "wrong brief: she should run" and "lesson" not in h
    assert not lessons.exists()


def test_reject_adds_a_lesson_only_when_asked(tmp_path):
    from kei.signoff import reject_shot
    root = waiting(tmp_path)
    lessons = tmp_path / "l.md"
    reject_shot(root, "the weight never reads", True, lessons)
    assert load_state(root).history[-1]["lesson"] == "local.1"
    assert "the weight never reads" in load_rules([lessons])[0].text


def test_reject_with_no_reason_is_refused(tmp_path):
    from kei.signoff import SignOffError, reject_shot
    root = waiting(tmp_path)
    with pytest.raises(SignOffError):
        reject_shot(root, "  ", False, tmp_path / "l.md")
    assert load_state(root).status == "needs_approval"


def test_a_note_reopens_a_rejected_shot(tmp_path):
    from kei.signoff import note_shot, reject_shot
    root = waiting(tmp_path)
    reject_shot(root, "wrong brief", False, tmp_path / "l.md")
    s, _ = note_shot(root, "make it a run", "brief", tmp_path / "l.md")
    assert (s.stage, s.status) == ("brief", "running")
    assert load_state(root).history[-1]["reopened"] is True


def test_rejected_is_a_known_status(tmp_path):
    root = waiting(tmp_path, "rejected")
    assert load_state(root).status == "rejected"


def test_kei_run_on_a_rejected_shot_exits_1_with_the_reason(tmp_path, capsys):
    from kei.signoff import reject_shot
    root = waiting(tmp_path)
    reject_shot(root, "wrong brief: she should run", False, tmp_path / "l.md")
    c = cfg(tmp_path, '[animator]\ncmd = ["x"]\n')
    assert main(["run", str(root), "--config", c]) == 1
    out = capsys.readouterr().out
    assert "wrong brief: she should run" in out and "kei note" in out and "Traceback" not in out
    assert load_state(root).status == "rejected"


def test_kei_status_of_a_rejected_shot_shows_the_reason(tmp_path, capsys):
    from kei.signoff import reject_shot
    root = waiting(tmp_path)
    reject_shot(root, "wrong brief", False, tmp_path / "l.md")
    assert main(["status", str(root)]) == 0
    out = capsys.readouterr().out
    assert "rejected" in out and "wrong brief" in out
