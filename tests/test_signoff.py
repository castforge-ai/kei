from dataclasses import replace

from kei.book import load_rules
from kei.cli import main
from kei.seats import FakeSeat
from kei.state import ShotState, load_state, save_state
from test_conductor import CFG, Recorder, run_shot, shot, stage_of
from test_cli import cfg


def waiting(tmp_path):
    root = shot(tmp_path)
    save_state(root, ShotState(stage="deliver", status="needs_approval", request="a box falls",
                               approved_plan={"plan/plan.json": "abc"}))
    return root


def note(tmp_path, root, text, *more):
    c = cfg(tmp_path, '[animator]\ncmd = ["x"]\n')
    return main(["note", str(root), "--text", text, "--config", c, *more])


def test_delivery_stops_for_approval(tmp_path):
    state = run_shot(shot(tmp_path), "a box falls", CFG, animator=FakeSeat("fake", Recorder()))
    assert (state.stage, state.status) == ("deliver", "needs_approval")


def test_run_says_how_to_sign_off(tmp_path, capsys):
    root = waiting(tmp_path)
    assert main(["status", str(root)]) == 0
    assert "kei approve" in capsys.readouterr().out


def test_approve_closes_the_shot(tmp_path):
    root = waiting(tmp_path)
    assert main(["approve", str(root)]) == 0
    s = load_state(root)
    assert s.status == "done" and s.history[-1]["result"] == "approved"


def test_approve_refused_unless_waiting(tmp_path, capsys):
    root = shot(tmp_path)
    assert main(["approve", str(root)]) == 1
    assert "Traceback" not in capsys.readouterr().out
    assert load_state(root).status == "running"


def test_note_adds_a_local_lesson_and_sends_the_shot_back(tmp_path, capsys):
    root = waiting(tmp_path)
    assert note(tmp_path, root, "the feet slide on contact") == 0
    assert "local.1" in capsys.readouterr().out
    rules = load_rules([tmp_path / "lessons.local.md"])
    assert [(r.id, r.stages) for r in rules] == [("local.1", ("passes",))]
    assert "the feet slide on contact" in rules[0].text and "provisional" in rules[0].title
    s = load_state(root)
    assert (s.stage, s.status, s.attempts, s.send_backs) == ("passes", "running", 0, 0)
    assert s.history[-1]["result"] == "note" and s.history[-1]["lesson"] == "local.1"
    assert s.approved_plan == {"plan/plan.json": "abc"}


def test_second_note_is_local_2(tmp_path):
    root = waiting(tmp_path)
    note(tmp_path, root, "one")
    s = load_state(root)
    s.status, s.stage = "needs_approval", "deliver"
    save_state(root, s)
    note(tmp_path, root, "two")
    assert [r.id for r in load_rules([tmp_path / "lessons.local.md"])] == ["local.1", "local.2"]


def test_note_before_plan_clears_the_approval(tmp_path):
    root = waiting(tmp_path)
    assert note(tmp_path, root, "the box is hollow", "--stage", "study") == 0
    s = load_state(root)
    assert s.stage == "study" and s.approved_plan is None


def test_note_with_a_heading_stays_one_lesson(tmp_path):
    root = waiting(tmp_path)
    assert note(tmp_path, root, "les pieds glissent\n### oops") == 0
    rules = load_rules([tmp_path / "lessons.local.md"])
    assert len(rules) == 1 and "oops" in rules[0].text and "glissent" in rules[0].title


def test_note_with_a_bad_stage_is_one_line_and_exit_1(tmp_path, capsys):
    root = waiting(tmp_path)
    assert note(tmp_path, root, "x", "--stage", "bloking") == 1
    out = capsys.readouterr().out
    assert "bloking" in out and "Traceback" not in out
    assert load_state(root).status == "needs_approval"
    assert not (tmp_path / "lessons.local.md").exists()


def test_next_prompt_lists_the_note(tmp_path):
    root = waiting(tmp_path)
    note(tmp_path, root, "the feet slide on contact")
    rec = Recorder()
    config = replace(CFG, lessons=tmp_path / "lessons.local.md")
    run_shot(root, "a box falls", config, animator=FakeSeat("fake", rec))
    first = rec.prompts[0]
    assert stage_of(first) == "Breakdowns, spline and polish"
    assert "- the feet slide on contact" in first and "### local.1." in first


def test_a_later_review_replaces_that_critics_earlier_checks_of_the_stage():
    from kei.conductor import _add_sign_off
    s = ShotState()
    _add_sign_off(s, "blocking", [{"from": "critic a", "check": "watch blocking_x10.mp4 for the seam"}])
    _add_sign_off(s, "passes", [{"from": "critic a", "check": "watch out_p3/playback_x10.mp4 for the seam"},
                                {"from": "critic b", "check": "check the heel drop in out_p3"}])
    _add_sign_off(s, "passes", [{"from": "critic a", "check": "watch out_p4/playback_x10.mp4 for the seam"}])
    assert [(i["stage"], i["from"], i["check"]) for i in s.sign_off] == [
        ("blocking", "critic a", "watch blocking_x10.mp4 for the seam"),
        ("passes", "critic b", "check the heel drop in out_p3"),
        ("passes", "critic a", "watch out_p4/playback_x10.mp4 for the seam")]


def test_the_same_check_twice_is_listed_once_whatever_its_case_or_spacing():
    from kei.conductor import _add_sign_off
    s = ShotState()
    _add_sign_off(s, "blocking", [{"from": "critic a", "check": "Watch the seam at 24 fps."}])
    _add_sign_off(s, "passes", [{"from": "critic b", "check": "watch the  seam at 24 fps"}])
    assert [i["check"] for i in s.sign_off] == ["Watch the seam at 24 fps."]


def test_approve_with_no_shot_approves_the_current_folder(tmp_path, monkeypatch):
    root = waiting(tmp_path)
    monkeypatch.chdir(root)
    assert main(["approve"]) == 0
    assert load_state(root).status == "done"


def test_a_note_on_an_approved_shot_withdraws_the_approval_and_sends_it_back(tmp_path, capsys):
    # The author withdrew a 10/10 after the sign-off (2026-11-02): the note must still reach the shot.
    root = waiting(tmp_path)
    s = load_state(root)
    s.status = "done"
    save_state(root, s)
    assert note(tmp_path, root, "she would fall behind for sure") == 0
    assert "approval withdrawn" in capsys.readouterr().out
    s = load_state(root)
    assert (s.stage, s.status) == ("passes", "running")
    assert s.history[-1]["result"] == "note" and s.history[-1]["withdrew_approval"] is True
