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


def test_a_failing_critic_fails_closed(tmp_path):
    full(tmp_path, upto="blocking")
    out = panel_review(stage_by_id("blocking"), tmp_path, "a box falls",
                       [critic("codex", SeatResult(127, "command not found: codex"))])
    assert out == ["critic codex: command not found: codex"]


def test_plan_change_brings_a_late_stage_to_review(tmp_path):
    full(tmp_path, upto="checks")
    approved = approve_plan(tmp_path)
    write(tmp_path, "plan/plan_sheet.png", "redrawn")
    calls = []
    changed = plan_changes(tmp_path, approved)
    assert panel_review(stage_by_id("checks"), tmp_path, "a box falls", [critic("a", PASS, calls)], changed) == []
    assert len(calls) == 1
    assert "The plan changed since it was approved" in calls[0][1]
