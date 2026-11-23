"""The conductor's stage attempt: what each result of a try spends, and that every result a run writes is one the
conductor names."""
from kei.conductor import RESULTS, Attempt, _record
from kei.config import Config, SeatSpec
from kei.stages import STAGES, stage_by_id
from kei.state import ShotState


def cfg(**kw):
    return Config(animator=SeatSpec(name="fake", cmd=["unused"]), **kw)


def record(result, state=None, stage="plan", misses=(), config=None, size_stop=False, tmp=None):
    state = state or ShotState(stage=stage)
    _record(tmp, state, config or cfg(), stage_by_id(stage), Attempt({"stage": stage, "result": result},
                                                                     list(misses), size_stop))
    return state


def test_a_pass_goes_to_the_next_stage_and_clears_the_budgets(tmp_path):
    s = ShotState(stage="plan", attempts=2, send_backs=1)
    record("pass", s, tmp=tmp_path)
    order = [x.id for x in STAGES]
    assert s.stage == order[order.index("plan") + 1] and (s.attempts, s.send_backs) == (0, 0)
    assert s.history[-1]["result"] == "pass" and s.history[-1]["misses"] == []


def test_the_last_stage_waits_for_a_person_to_sign_off(tmp_path):
    s = record("pass", stage=STAGES[-1].id, tmp=tmp_path)
    assert s.status == "needs_approval"


def test_a_failure_spends_a_try_and_the_last_try_goes_to_a_person(tmp_path):
    c = cfg(max_attempts=2)
    s = record("fail", misses=["a"], config=c, tmp=tmp_path)
    assert (s.attempts, s.status, s.stage) == (1, "running", "plan")
    record("seat_error", s, misses=["b"], config=c, tmp=tmp_path)
    assert s.status == "needs_human"


def test_rule_text_past_the_limit_goes_to_a_person_at_once(tmp_path):
    s = record("fail", misses=["too much"], size_stop=True, tmp=tmp_path)
    assert s.attempts == 1 and s.status == "needs_human"


def test_a_send_back_spends_a_send_back_not_a_try(tmp_path):
    s = record("send_back", misses=["note"], tmp=tmp_path)
    assert (s.send_backs, s.attempts, s.status) == (1, 0, "running")


def test_a_records_round_spends_nothing(tmp_path):
    s = record("records", tmp=tmp_path)
    assert (s.send_backs, s.attempts, s.stage, s.status) == (0, 0, "plan", "running")


def test_the_attempt_names_its_result():
    assert Attempt({"result": "send_back"}).result == "send_back" and Attempt({}).result == ""
    assert set(RESULTS) >= {"pass", "escalated", "fail", "seat_error", "send_back", "records", "timeout", "reused"}


def test_every_result_a_run_writes_is_a_named_one(tmp_path):
    """A whole run with a fake seat: each history entry's result is one of RESULTS, or the run's own marks
    (resume, a pause, a question)."""
    from kei.conductor import run_shot
    from kei.seats import FakeSeat
    from test_conductor import Recorder, shot
    root = shot(tmp_path)
    state = run_shot(root, "a box falls", cfg(), animator=FakeSeat("fake", Recorder()), review=lambda s, d, c: [])
    own = {"resume", "asked", "paused_usage", "paused_machine"}
    assert state.history and all(h["result"] in set(RESULTS) | own for h in state.history), \
        sorted({h["result"] for h in state.history})
