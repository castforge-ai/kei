"""A declared fault must fit its measurement, a control may not snap in one frame, and the critics must judge each
declared flag and author note on its frames."""
import json

from kei.critic import answers_block, parse_verdict
from kei.review_rigor import accept, control_snaps, declared_misses, evidence, required_misses
from kei.state import ShotState, load_state, save_state

TH = {"thresholds": {"slide_m_per_frame": {"value": 0.005}, "penetration_m": {"value": 0.01}}}


def _slide(size, start=14):
    return {"check": "foot_slide", "side": "l", "frames": [start, start + 4], "size": size, "unit": "m/frame",
            "rule": "hard", "what": "the planted l foot slides"}


def test_a_declared_slide_past_the_cap_is_a_fault(tmp_path):
    miss = declared_misses(tmp_path, [_slide(0.259)], TH)
    assert len(miss) == 1 and "foot_slide.body.f14" in miss[0] and "kei accept" in miss[0]
    assert declared_misses(tmp_path, [_slide(0.012, start=30)], TH) == []


def test_a_declared_flag_that_grows_counts_again(tmp_path):
    assert declared_misses(tmp_path, [_slide(0.010)], TH) == []          # first seen: recorded
    assert declared_misses(tmp_path, [_slide(0.011)], TH) == []          # about the same
    miss = declared_misses(tmp_path, [_slide(0.019)], TH)
    assert len(miss) == 1 and "grew" in miss[0]


def test_the_author_accepts_a_flag_at_its_size(tmp_path):
    save_state(tmp_path, ShotState(stage="passes"))
    p = tmp_path / "out_p3"
    (p / "body_check").mkdir(parents=True)
    (p / "body_check" / "body_check.json").write_text(json.dumps({"flags": [_slide(0.25)]}), encoding="utf-8")
    (p / "shot.json").write_text(json.dumps({"keys": []}), encoding="utf-8")
    e = accept(tmp_path, "foot_slide.body.f14", "a skid on purpose")
    assert e["size"] == 0.25 and load_state(tmp_path).accepted[0]["reason"] == "a skid on purpose"
    assert declared_misses(tmp_path, [_slide(0.25)], TH) == []
    assert declared_misses(tmp_path, [_slide(0.40)], TH) != []          # worse than accepted


def _keys(roll):
    return {"keys": [{"f": f, "foot_roll_ctrl.rotation.z": v, "switch.location.x": 1.0} for f, v in enumerate(roll)]}


def test_a_control_that_drops_to_rest_in_one_frame_snaps():
    snaps = control_snaps(_keys([0, -3, -14, -29, -40, -50, 0, 0, 0]))
    assert [s["id"] for s in snaps] == ["control_snap.foot_roll_ctrl.f6"] and snaps[0]["frames"] == [5, 6]
    assert control_snaps(_keys([0, -10, -20, -30, -40, -30, -20, -10, 0])) == []   # a steady roll is fine


def test_evidence_lists_the_frames_and_asks_for_a_judgment(tmp_path):
    p = tmp_path / "out_p2"
    (p / "body_check").mkdir(parents=True)
    (p / "mesh" / "feet").mkdir(parents=True)
    for f in range(12, 21):
        (p / "mesh" / "feet" / f"f{f:04d}.png").write_bytes(b"")
    (p / "body_check" / "body_check.json").write_text(json.dumps({"frames": 30, "flags": [_slide(0.259)]}),
                                                      encoding="utf-8")
    (tmp_path / "GATES.md").write_text("## Declared\n- foot_slide.body.f14: the peel at the toe\n", encoding="utf-8")
    ev = evidence(tmp_path, "p2", ["author: f14-19: the left foot resets at f19"])
    text = "\n".join(ev["lines"])
    assert ev["declared"] == ["foot_slide.body.f14"] and "out_p2/mesh/feet/f0012.png" in text
    assert "the peel at the toe" in text and ev["notes"]
    assert required_misses("c", {}, ev)                                   # nothing judged: sent back
    ok = {"declared": {"foot_slide.body.f14": "holds"}, "author_notes": {"f14-19: the left foot": "fixed"}}
    assert required_misses("c", ok, ev) == []
    bad = {"declared": {"foot_slide.body.f14": "does not hold"}, "author_notes": {"f14-19: the left foot": "fixed"}}
    assert len(required_misses("c", bad, ev)) == 1


def test_the_verdict_keeps_the_judgments():
    v = parse_verdict("c", '{"verdict": "pass", "notes": [], "declared": {"foot_slide.body.f14": "holds"}}')
    assert v.judged == {"declared": {"foot_slide.body.f14": "holds"}}


def test_an_answer_from_an_earlier_stage_accepts_nothing_later():
    lines = answers_block([{"stage": "blocking", "question": "accept the flags?", "answer": "A"}], "passes")
    assert "accepts nothing here" in lines[1]
    assert "accepts nothing here" not in answers_block([{"stage": "passes", "question": "q", "answer": "a"}],
                                                        "passes")[1]


def test_the_late_stages_judge_the_newest_pass(tmp_path):
    from kei.critic import review_evidence
    p = tmp_path / "out_p4"
    (p / "body_check").mkdir(parents=True)
    (p / "shot.json").write_text(json.dumps({"keys": [{"f": 0}]}), encoding="utf-8")
    (p / "body_check" / "body_check.json").write_text(json.dumps({"frames": 30, "flags": [_slide(0.01)]}),
                                                      encoding="utf-8")
    (tmp_path / "GATES.md").write_text("## Declared\n- foot_slide.body.f14: a pivot\n", encoding="utf-8")
    for stage in ("checks", "self_review", "deliver"):
        assert review_evidence(tmp_path, stage)["declared"] == ["foot_slide.body.f14"], stage
