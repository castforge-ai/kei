import json

import pytest

from kei.conductor import NoCriticError, run_shot
from kei.config import Config, SeatSpec
from kei.seats import FakeSeat, SeatResult
from kei.state import load_state, state_path
from shotkit import write
from test_conductor import Recorder, shot, stage_of

MOVED = json.dumps({"keys": [{"f": 0, "function": "slip", "kind": "key", "drawing": {"lines": [[0, 0, 3, 1]]}}]})

PASS = '{"verdict": "pass", "notes": []}'
CFG = Config(animator=SeatSpec(name="fake", cmd=["unused"]), max_attempts=3, max_send_backs=3)


def critic(name, decide):
    """decide(stage title, prompt) -> the critic's answer."""
    prompts = []

    def act(prompt, root):
        prompts.append(prompt)
        title = next(l for l in prompt.splitlines() if l.startswith("Stage under review: "))[20:]
        return SeatResult(0, decide(title, prompt))
    seat = FakeSeat(name, act)
    seat.prompts = prompts
    return seat


def always_pass(title, prompt):
    return PASS


def test_no_critic_is_refused_before_any_stage(tmp_path):
    root = shot(tmp_path)
    rec = Recorder()
    with pytest.raises(NoCriticError):
        run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec))
    assert rec.prompts == []


def test_send_backs_stop_for_a_human(tmp_path):
    root = shot(tmp_path)
    c = critic("c1", lambda t, p: '{"verdict": "send_back", "notes": ["key 2 is off its frame"]}' if t == "Plan" else PASS)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[c])
    assert (state.status, state.stage, state.attempts, state.send_backs) == ("needs_human", "plan", 0, 3)
    assert [h["result"] for h in state.history if h["stage"] == "plan"] == ["send_back"] * 3


def test_send_back_notes_reach_the_next_prompt(tmp_path):
    root = shot(tmp_path)
    answers = iter(['{"verdict": "send_back", "notes": ["key 2 is off its frame"]}'])
    c = critic("c1", lambda t, p: next(answers, PASS) if t == "Plan" else PASS)
    rec = Recorder()
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec), critics=[c])
    plans = [p for p in rec.prompts if stage_of(p) == "Plan"]
    assert "critic c1: key 2 is off its frame" in plans[1]
    assert state.status == "needs_approval"


def test_plan_is_approved_when_the_plan_stage_passes(tmp_path):
    root = shot(tmp_path)
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(lambda sid, n, r: sid == "blocking")),
             critics=[critic("c1", always_pass)])
    assert (root / ".kei" / "approved_plan" / "plan" / "plan.json").exists()


def test_an_unapproved_plan_change_is_reviewed(tmp_path):
    root = shot(tmp_path)

    def fault(sid, n, r):
        if sid == "blocking" and n == 1:
            write(r, "plan/plan.json", MOVED)
        return False

    c = critic("c1", always_pass)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(fault)), critics=[c])
    assert state.status == "needs_approval"
    assert any("The plan changed since it was approved" in p for p in c.prompts)
    approved = root / ".kei" / "approved_plan" / "plan" / "plan.json"
    assert approved.read_text(encoding="utf-8") == MOVED


def test_old_state_file_loads_without_send_backs(tmp_path):
    p = state_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"stage": "rig", "attempts": 1, "status": "running", "request": "x", "history": []}),
                 encoding="utf-8")
    assert load_state(tmp_path).send_backs == 0


def test_deleting_the_approved_copy_does_not_hide_a_plan_change(tmp_path):
    import shutil
    root = shot(tmp_path)

    def fault(sid, n, r):
        if sid == "blocking" and n == 1:
            write(r, "plan/plan.json", MOVED)
            shutil.rmtree(r / ".kei" / "approved_plan")
        return False

    c = critic("c1", always_pass)
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(fault)), critics=[c])
    blocking = [p for p in c.prompts if "Stage under review: Blocking" in p]
    assert "The plan changed since it was approved: plan/plan.json" in blocking[0]


def test_a_critic_edit_during_review_is_not_approved(tmp_path):
    root = shot(tmp_path)

    def decide(title, prompt):
        if title == "Plan":
            write(root, "plan/plan.json", MOVED.replace("slip", "edited by the critic"))
        return PASS

    c = critic("c1", decide)
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(lambda sid, n, r: sid == "passes")),
             critics=[c])
    blocking = [p for p in c.prompts if "Stage under review: Blocking" in p]
    assert "The plan changed since it was approved: plan/plan.json" in blocking[0]


def test_a_critic_that_is_not_installed_is_refused_before_any_stage(tmp_path):
    root = shot(tmp_path)
    cfg = Config(animator=SeatSpec(name="fake", cmd=["unused"]),
                 critics=[SeatSpec(name="ghost", cmd=["no-such-critic-cli-xyz"])])
    rec = Recorder()
    with pytest.raises(NoCriticError, match="ghost"):
        run_shot(root, "a box falls", cfg, animator=FakeSeat("fake", rec))
    assert rec.prompts == []


SEND_BACK = '{"verdict": "send_back", "notes": ["f9: the hips sink too late"]}'


def _stopped_after_send_backs(tmp_path):
    root = shot(tmp_path)
    c = critic("c1", lambda t, p: SEND_BACK if t == "Plan" else PASS)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[c])
    assert (state.status, state.stage) == ("needs_human", "plan")
    return root


def test_retry_keeps_the_critics_last_notes(tmp_path):
    from kei.cli import main
    root = _stopped_after_send_backs(tmp_path)
    assert main(["retry", str(root)]) == 0
    rec = Recorder()
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec), critics=[critic("c2", always_pass)])
    assert "critic c1: f9: the hips sink too late" in rec.prompts[0]


def test_retry_note_reaches_the_next_prompt(tmp_path):
    from kei.cli import main
    root = _stopped_after_send_backs(tmp_path)
    assert main(["retry", str(root), "--note", "keep the contacts, lift the passings"]) == 0
    rec = Recorder()
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec), critics=[critic("c2", always_pass)])
    assert "keep the contacts, lift the passings" in rec.prompts[0]
    assert "critic c1: f9: the hips sink too late" in rec.prompts[0]


def test_a_seat_error_after_a_send_back_keeps_the_notes(tmp_path):
    root = shot(tmp_path)
    c = critic("c1", lambda t, p: SEND_BACK if t == "Plan" and len(c.prompts) <= 7 else PASS)
    rec = Recorder()
    calls = {"plan": 0}

    def animator(prompt, r):
        if stage_of(prompt) == "Plan":
            calls["plan"] += 1
            if calls["plan"] == 2:
                rec.prompts.append(prompt)
                return SeatResult(1, "the seat crashed")
        return rec(prompt, r)

    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", animator), critics=[c])
    plans = [p for p in rec.prompts if stage_of(p) == "Plan"]
    assert len(plans) >= 3
    assert "critic c1: f9: the hips sink too late" in plans[2]


def test_a_gate_miss_after_a_send_back_keeps_the_critics_notes(tmp_path):
    root = shot(tmp_path)
    answers = iter([SEND_BACK])
    c = critic("c1", lambda t, p: next(answers, PASS) if t == "Plan" else PASS)

    def fault(sid, n, r):
        if sid == "plan" and n == 2:
            write(r, "plan/plan.json", '{"keys": [{"f": 0}]}')
            return True
        return False

    rec = Recorder(fault)
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec), critics=[c])
    plans = [p for p in rec.prompts if stage_of(p) == "Plan"]
    assert "P7" in plans[2] and "critic c1: f9: the hips sink too late" in plans[2]


def test_critics_see_the_stage_earlier_send_backs_and_may_not_reverse_one_silently(tmp_path):
    root = shot(tmp_path)
    answers = iter(['{"verdict": "send_back", "notes": ["f9: raise the passing by 1 cm"]}',
                    '{"verdict": "send_back", "notes": ["f3: the up is late"]}'])
    c = critic("c1", lambda t, p: next(answers, PASS) if t == "Plan" else PASS)
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[c])
    plans = [p for p in c.prompts if "Stage under review: Plan" in p]
    assert "Earlier send-backs" not in plans[0]
    assert "critic c1: f9: raise the passing by 1 cm" in plans[1]
    assert "critic c1: f9: raise the passing by 1 cm" in plans[2] and "critic c1: f3: the up is late" in plans[2]
    assert "without saying so" in plans[2]


def test_earlier_send_backs_are_capped_to_the_latest(tmp_path):
    from kei.critic import EARLIER_MAX, critic_prompt
    from kei.stages import stage_by_id
    earlier = [[f"note {i}"] for i in range(EARLIER_MAX + 3)]
    p = critic_prompt(stage_by_id("plan"), tmp_path, "x", [], earlier=earlier)
    assert f"note {EARLIER_MAX + 2}" in p and "note 0\n" not in p and "3 older" in p


def test_a_retry_note_is_for_the_animator_and_the_critics_do_not_judge_against_it(tmp_path):
    from kei.cli import main
    root = _stopped_after_send_backs(tmp_path)
    assert main(["retry", str(root), "--note", "keep the contacts, lift the passings"]) == 0
    c2 = critic("c2", always_pass)
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[c2])
    plan = next(p for p in c2.prompts if "Stage under review: Plan" in p)
    assert "keep the contacts, lift the passings" not in plan


def _cfg(**kw):
    from dataclasses import replace
    return replace(CFG, **kw)


def test_on_the_limit_retry_runs_the_stage_again_with_the_retry_note_then_stops(tmp_path):
    root = shot(tmp_path)
    c = critic("c1", lambda t, p: SEND_BACK if t == "Plan" else PASS)
    rec = Recorder()
    cfg = _cfg(on_send_back_limit="retry", auto_retries=1, retry_note="apply every note and go on")
    state = run_shot(root, "a box falls", cfg, animator=FakeSeat("fake", rec), critics=[c])
    results = [h["result"] for h in state.history if h["stage"] == "plan"]
    assert results == ["send_back"] * 3 + ["auto_retry"] + ["send_back"] * 3
    assert (state.status, state.stage) == ("needs_human", "plan")
    assert sum("apply every note and go on" in p for p in rec.prompts) == 3, "the three tries after the retry"
    assert all("apply every note and go on" not in p for p in c.prompts)


def test_on_the_limit_advance_moves_the_open_notes_to_the_sign_off_and_goes_on(tmp_path):
    root = shot(tmp_path)
    c = critic("c1", lambda t, p: SEND_BACK if t == "Plan" else PASS)
    state = run_shot(root, "a box falls", _cfg(on_send_back_limit="advance"), animator=FakeSeat("fake", Recorder()),
                     critics=[c])
    results = [h["result"] for h in state.history if h["stage"] == "plan"]
    assert results == ["send_back", "send_back", "escalated"]
    assert state.stage != "plan" and state.status != "needs_human"
    assert any("left open at plan" in s["check"] and "hips sink too late" in s["check"] for s in state.sign_off)


def test_a_bad_send_back_policy_is_refused(tmp_path):
    from kei.config import ConfigError, example_config, load_config
    cfg = tmp_path / "kei.toml"
    text = example_config().read_text(encoding="utf-8")
    assert "\n[limits]\n" in text
    cfg.write_text(text.replace("\n[limits]\n", '\n[limits]\non_send_back_limit = "ignore"\n'), encoding="utf-8")
    with pytest.raises(ConfigError, match="on_send_back_limit"):
        load_config(cfg)


RECORDS_ONLY = json.dumps({"verdict": "send_back", "notes": [], "records": [
    "F0-26: the blocking extent record is missing: reconstruct it from the saved blocking, label it retrospective"]})


def test_a_send_back_that_only_asks_for_records_is_a_note_and_spends_no_send_back(tmp_path):
    # 2026-11-02: a critic spent all three send-backs of a shot on records (an extent record, a trail comparison,
    # stale plan copies), none on the motion. A missing record is a note for the animator, not a send-back.
    root = shot(tmp_path)
    c = critic("c1", lambda t, p: RECORDS_ONLY if t == "Plan" else PASS)
    rec = Recorder()
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec), critics=[c])
    plan = [h for h in state.history if h["stage"] == "plan"]
    assert "send_back" not in [h["result"] for h in plan]
    assert state.status == "needs_approval"          # the records never stop the shot
    plans = [p for p in rec.prompts if stage_of(p) == "Plan"]
    assert len(plans) == 2 and "blocking extent record is missing" in plans[1]   # the animator reads it once


def test_a_send_back_with_a_fault_and_records_still_counts(tmp_path):
    root = shot(tmp_path)
    both = json.dumps({"verdict": "send_back", "notes": ["F3: the hand pops"], "records": ["the trail is stale"]})
    c = critic("c1", lambda t, p: both if t == "Plan" else PASS)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), critics=[c])
    assert (state.status, state.send_backs) == ("needs_human", 3)


def test_the_critic_prompt_keeps_send_backs_for_the_work(tmp_path):
    from kei.critic import critic_prompt
    from kei.stages import stage_by_id
    from shotkit import full
    full(tmp_path, upto="blocking")
    p = critic_prompt(stage_by_id("blocking"), tmp_path, "a walk", [])
    assert "visible fault in the motion" in p and '"records"' in p
