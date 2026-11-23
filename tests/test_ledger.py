"""The note ledger: notes judged fixed are kept for the shot, shown to later critics, and checked for regressions."""
import json

from kei.ledger import close, ledger_block, note_frames, regressions, reopen
from kei.state import ShotState


def test_note_frames_reads_the_first_range_or_frame():
    assert note_frames("critic codex: 149-152: In out_p6, the left elbow opens") == (149, 152)
    assert note_frames("critic c: f7-9: after B1 lifted the left foot") == (7, 9)
    assert note_frames("a wrist jump at f58 of 19 cm") == (58, 58)
    assert note_frames("the closing look is too short") is None


def _state():
    return ShotState(stage="passes", history=[{"stage": "blocking", "result": "send_back",
                                               "misses": ["critic c: f7-9: the mass sits behind the heel"]}])


def test_a_note_judged_fixed_joins_the_ledger_with_its_full_text_and_frames():
    st = _state()
    close(st, "blocking", [{"from": "c", "note": "f7-9: the mass sits", "status": "fixed"}], "t")
    assert st.ledger == [{"stage": "blocking", "note": "critic c: f7-9: the mass sits behind the heel",
                          "frames": (7, 9), "fixed_by": "c", "at": "t"}]
    close(st, "blocking", [{"from": "c", "note": "f7-9: the mass sits", "status": "fixed"}], "t2")
    assert len(st.ledger) == 1, "once"
    reopen(st, "blocking", [{"from": "c", "note": "f7-9: the mass sits", "status": "not fixed"}])
    assert st.ledger == []


def test_a_hard_flag_inside_a_fixed_note_is_a_likely_regression(tmp_path):
    st = _state()
    close(st, "blocking", [{"from": "c", "note": "f7-9: the mass sits", "status": "fixed"}], "t")
    bc = tmp_path / "out_p4" / "body_check"
    bc.mkdir(parents=True)
    bc.joinpath("body_check.json").write_text(json.dumps({"flags": [
        {"check": "foot_slide", "frames": [8, 10], "rule": "hard", "what": "the planted l foot slides"},
        {"check": "balance", "frames": [8, 9], "rule": "soft", "note": True, "what": "pushed"},
        {"check": "contacts", "frames": [40, 41], "rule": "hard", "what": "far away"}]}), encoding="utf-8")
    reg = regressions(tmp_path, st, "p4")
    assert len(reg) == 1 and reg[0].startswith("f8-10 foot_slide")
    block = ledger_block(st, tmp_path, "p4")
    assert block[0].startswith("Notes fixed earlier") and any("likely regressions" in b for b in block)


def test_a_flag_declared_in_gates_is_not_a_regression(tmp_path):
    st = ShotState(ledger=[{"stage": "blocking", "note": "critic c: f0-33: the lfoot version", "frames": [0, 33]}])
    p = tmp_path / "out_blocking" / "body_check"
    p.mkdir(parents=True)
    (p / "body_check.json").write_text(json.dumps({"flags": [
        {"check": "contacts", "frames": [0, 13], "rule": "hard", "what": "toe marker under the floor"},
        {"check": "foot_slide", "frames": [5, 6], "rule": "hard", "what": "peel slides"}]}), encoding="utf-8")
    (tmp_path / "GATES.md").write_text("# Gates\n\n## Declared\n- contacts.body.f0: the toe marker, answer B\n",
                                       encoding="utf-8")
    reg = regressions(tmp_path, st, "blocking")
    assert len(reg) == 1 and reg[0].startswith("f5-6 foot_slide"), reg


def test_an_old_state_file_has_an_empty_ledger(tmp_path):
    from kei.state import load_state, save_state, state_path
    save_state(tmp_path, ShotState())
    data = json.loads(state_path(tmp_path).read_text())
    del data["ledger"]
    state_path(tmp_path).write_text(json.dumps(data))
    assert load_state(tmp_path).ledger == []


def test_a_regression_fails_the_try_before_the_critics(tmp_path):
    from kei.conductor import run_shot
    from kei.seats import FakeSeat
    from kei.state import load_state, save_state
    from test_conductor import CFG, Recorder, shot
    from test_questions import no_review
    root = shot(tmp_path)
    st = load_state(root)
    st.ledger = [{"stage": "blocking", "note": "critic c: f8-10: the heel slides", "frames": [8, 10]}]
    save_state(root, st)
    calls = []

    def fault(sid, n, r):
        if sid == "blocking":
            bc = r / "out_blocking" / "body_check"
            bc.mkdir(parents=True, exist_ok=True)
            bc.joinpath("body_check.json").write_text(json.dumps({"flags": [
                {"check": "foot_slide", "frames": [9, 9], "rule": "hard", "what": "the l foot slides"}]}))
        return False

    def review(stage, d, changed):
        calls.append(stage.id)
        return []
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(fault)), review=review)
    blk = [h for h in state.history if h["stage"] == "blocking"]
    assert blk and all(h["result"] == "fail" for h in blk)
    assert any("regression of a fixed note: f9-9 foot_slide" in m for m in blk[0]["misses"])
    assert "blocking" not in calls
