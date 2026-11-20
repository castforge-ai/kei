"""The conductor's failure paths: the history since a stage began, a seat error that floods its output, a timeout
past the allowance, and the send-back limit across several automatic retries."""
from dataclasses import replace

from kei.conductor import MAX_TIMEOUTS, SEAT_ERROR_CHARS, capped, since_stage_began
from kei.seats import FakeSeat, SeatResult
from kei.state import ShotState
from test_conductor import CFG, Recorder, run_shot, shot
from test_conductor_critic import SEND_BACK, PASS, critic


def test_since_stage_began_stops_at_another_stage_and_at_the_stages_own_pass():
    st = ShotState(stage="plan", history=[
        {"stage": "plan", "result": "fail", "n": 1}, {"stage": "plan", "result": "pass", "n": 2},
        {"stage": "blocking", "result": "pass", "n": 3}, {"stage": "plan", "result": "note", "n": 4},
        {"stage": "plan", "result": "send_back", "n": 5}, {"stage": "plan", "result": "fail", "n": 6}])
    assert [h["n"] for h in since_stage_began(st)] == [6, 5, 4]
    assert [h["n"] for h in since_stage_began(st, "blocking")] == []
    assert since_stage_began(ShotState(stage="brief")) == []


def test_capped_keeps_the_end_of_a_long_output_and_says_what_it_cut():
    assert capped("  short  ") == "short"
    long = "x" * 10000 + "THE ERROR"
    got = capped(long)
    assert got.endswith("THE ERROR") and len(got) < SEAT_ERROR_CHARS + 100
    assert got.startswith("(the first 8009 characters")


def test_a_seat_that_floods_its_output_leaves_a_capped_miss_and_the_next_prompt_sees_the_end(tmp_path):
    root = shot(tmp_path)
    prompts = []

    def seat(prompt, workdir):
        prompts.append(prompt)
        if len(prompts) == 1:
            return SeatResult(1, "log line\n" * 20000 + "Error: the tool crashed")
        return Recorder()(prompt, workdir)
    st = run_shot(root, "a box falls", replace(CFG, max_attempts=2), animator=FakeSeat("fake", seat))
    err = next(h for h in st.history if h["result"] == "seat_error")
    assert len(err["misses"][0]) < SEAT_ERROR_CHARS + 100 and err["misses"][0].endswith("Error: the tool crashed")
    assert "Error: the tool crashed" in prompts[1] and len(prompts[1]) < len(prompts[0]) + SEAT_ERROR_CHARS + 2000


def test_a_timeout_past_the_allowance_counts_as_a_try(tmp_path):
    root = shot(tmp_path)
    st = run_shot(root, "a box falls", replace(CFG, max_attempts=1),
                  animator=FakeSeat("fake", lambda p, w: SeatResult(124, "timed out")))
    results = [h["result"] for h in st.history if h["stage"] == "brief"]
    assert results == ["timeout"] * MAX_TIMEOUTS + ["seat_error"]
    assert st.status == "needs_human"


def test_the_send_back_limit_holds_across_two_automatic_retries_then_stops(tmp_path):
    root = shot(tmp_path)
    c = critic("c1", lambda t, p: SEND_BACK if t == "Plan" else PASS)
    cfg = replace(CFG, on_send_back_limit="retry", auto_retries=2, retry_note="go on")
    from kei.conductor import run_shot as with_critics
    st = with_critics(root, "a box falls", cfg, animator=FakeSeat("fake", Recorder()), critics=[c])
    results = [h["result"] for h in st.history if h["stage"] == "plan"]
    assert results == (["send_back"] * 3 + ["auto_retry"]) * 2 + ["send_back"] * 3
    assert (st.status, st.stage) == ("needs_human", "plan")
