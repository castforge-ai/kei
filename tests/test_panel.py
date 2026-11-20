from kei.critic import panel_review
from kei.plan_lock import approve_plan, plan_changes
from kei.seats import FakeSeat, SeatResult
from kei.stages import stage_by_id
from shotkit import full, write

PASS = '{"verdict": "pass", "notes": []}'


def critic(name, answer, calls=None):
    def act(prompt, root):
        if calls is not None:
            calls.append((name, prompt))
        return answer if isinstance(answer, SeatResult) else SeatResult(0, answer)
    return FakeSeat(name, act)


def test_unreviewed_stage_skips_the_panel(tmp_path):
    full(tmp_path, upto="references")
    calls = []
    c = critic("a", '{"verdict": "send_back", "notes": ["no"]}', calls)
    assert panel_review(stage_by_id("references"), tmp_path, "a box falls", [c]) == []
    assert calls == []


def test_all_pass(tmp_path):
    full(tmp_path, upto="blocking")
    calls = []
    out = panel_review(stage_by_id("blocking"), tmp_path, "a box falls",
                       [critic("a", PASS, calls), critic("b", PASS, calls)])
    assert out == []
    assert [n for n, _ in calls] == ["a", "b"]


def test_any_send_back_wins(tmp_path):
    full(tmp_path, upto="blocking")
    out = panel_review(stage_by_id("blocking"), tmp_path, "a box falls",
                       [critic("a", PASS), critic("b", '{"verdict": "send_back", "notes": ["arm pops f22"]}')])
    assert out == ["critic b: arm pops f22"]


def test_a_critic_that_cannot_answer_pauses_the_stage_and_costs_no_send_back(tmp_path):
    import pytest
    from kei.seats import SeatPaused
    full(tmp_path, upto="blocking")
    calls = []
    with pytest.raises(SeatPaused) as e:
        panel_review(stage_by_id("blocking"), tmp_path, "a box falls",
                     [critic("codex", SeatResult(1, "Traceback: boom"), calls)])
    assert e.value.kind == "machine" and "could not give a verdict" in e.value.output
    assert len(calls) == 2, "asked once more before pausing"


def test_a_critic_with_no_verdict_is_asked_for_the_verdict_line_alone(tmp_path):
    full(tmp_path, upto="blocking")
    answers = iter(["All good, I think.", PASS])
    calls = []
    out = panel_review(stage_by_id("blocking"), tmp_path, "a box falls",
                       [FakeSeat("codex", lambda prompt, root: (calls.append(prompt), SeatResult(0, next(answers)))[1])])
    assert out == [] and "only the one JSON verdict line" in calls[1]


def test_a_timeout_then_an_answer_is_judged_as_the_answer(tmp_path):
    full(tmp_path, upto="blocking")
    answers = iter([SeatResult(124, "timeout after 1800 s"), SeatResult(0, PASS)])
    out = panel_review(stage_by_id("blocking"), tmp_path, "a box falls",
                       [FakeSeat("codex", lambda prompt, root: next(answers))])
    assert out == []


def test_plan_change_brings_a_late_stage_to_review(tmp_path):
    full(tmp_path, upto="checks")
    approved = approve_plan(tmp_path)
    write(tmp_path, "plan/plan_sheet.png", "redrawn")
    calls = []
    changed = plan_changes(tmp_path, approved)
    assert panel_review(stage_by_id("checks"), tmp_path, "a box falls", [critic("a", PASS, calls)], changed) == []
    assert len(calls) == 1
    assert "The plan changed since it was approved" in calls[0][1]
