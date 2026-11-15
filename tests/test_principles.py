import json
import math
from pathlib import Path

from kei.book import BUNDLED_BOOK, load_topics
from kei.gates.pipeline import _declared, check
from kei.principles import measure, undeclared
from kei.topics import stage_block

REST = {"pelvis": (0, 1.0, 0), "spine_03": (0, 1.3, 0), "neck_01": (0, 1.5, 0), "head": (0, 1.6, 0),
        "clavicle_l": (-0.05, 1.45, 0), "clavicle_r": (0.05, 1.45, 0), "lowerarm_l": (-0.2, 1.15, 0),
        "lowerarm_r": (0.2, 1.15, 0), "hand_l": (-0.22, 0.9, 0.05), "hand_r": (0.22, 0.9, 0.05),
        "ball_l": (-0.1, 0.0, 0.1), "ball_r": (0.1, 0.0, 0.1)}


def ease(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def frames(n, offset_of):
    """n frames; offset_of(part, f) -> (dx, dy, dz) added to the rest position."""
    return [{"f": f, "joints": {p: tuple(a + b for a, b in zip(v, offset_of(p, f))) for p, v in REST.items()}}
            for f in range(n)]


def ids(report):
    return {f["id"].rsplit(".f", 1)[0] for f in report["flags"]}


def test_a_body_moving_as_one_block_and_stopping_on_one_frame_is_flagged():
    # every part slides 30 cm to the right from f10 to f20 together, then everything stops dead
    fr = frames(40, lambda p, f: (0.3 * ease((f - 10) / 10), 0, 0))
    r = measure(fr, 30, 1.71)
    assert "overlap.same_stop.body" in ids(r)
    assert "overlap.dead_stop.spine_03" in ids(r)
    assert {"overlap.rigid_arm.hand_l", "overlap.rigid_arm.hand_r"} <= ids(r)
    assert "solid_drawing.unison.hand" not in ids(r)         # nothing moves against the chest: no twin to measure
    assert r["principles"]["exaggeration"]["status"] == "unchecked"
    assert r["principles"]["appeal"]["status"] == "unchecked"


def test_the_same_move_with_a_dragging_arm_and_a_settle_clears_the_overlap_flags():
    def off(p, f):
        lag = {"hand_l": 3, "hand_r": 4, "lowerarm_l": 2, "lowerarm_r": 3, "head": 2}.get(p, 0)
        x = 0.3 * ease((f - 10 - lag) / 10)
        if p in ("hand_l", "hand_r", "head") and f > 20 + lag:      # overshoot, then settle back
            x += 0.012 * math.sin((f - 20 - lag) / 3.0) * math.exp(-(f - 20 - lag) / 6.0)
        return (x, 0, 0)
    r = measure(frames(50, off), 30, 1.71)
    assert not {"overlap.same_stop.body", "overlap.rigid_arm.hand_l", "overlap.rigid_arm.hand_r",
                "overlap.dead_stop.spine_03"} & ids(r)


def test_extremes_that_all_sit_on_the_blocking_keys_are_pose_to_pose_and_offset_ones_are_not():
    keys = list(range(0, 121, 10))

    def sway(shift):
        def off(p, f):
            s = shift.get(p, 0)
            return (0.05 * math.sin(math.pi * (f - s) / 10 + math.pi / 2), 0, 0)
        return off
    on_keys = measure(frames(121, sway({})), 30, 1.71, blocking_keys=keys)
    assert "pose_to_pose.only_keys.body" in ids(on_keys)
    offset = measure(frames(121, sway({"head": 3, "hand_l": 4, "hand_r": 5, "lowerarm_l": 3, "lowerarm_r": 4,
                                       "spine_03": 2})), 30, 1.71, blocking_keys=keys)
    assert "pose_to_pose.only_keys.body" not in ids(offset)
    assert offset["principles"]["pose_to_pose"]["measured"]["share"] < 0.6


def test_a_body_that_does_not_move_for_a_second_is_a_dead_hold():
    r = measure(frames(40, lambda p, f: (0, 0, 0)), 30, 1.71, blocking_keys=[0, 39])
    assert "timing.dead_hold.body" in ids(r)
    assert "timing.dead_hold.body" not in ids(measure(frames(40, lambda p, f: (0, 0, 0)), 30, 1.71,
                                                      blocking_keys=[0, 39], is_blocking=True))


def test_a_flag_is_open_until_gates_md_declares_it_with_a_reason():
    report = {"flags": [{"id": "overlap.same_stop.body.f20"}, {"id": "timing.dead_hold.body.f0"}]}
    gates = "## Declared\n- overlap.same_stop.body.f20: the catch lands hard, on purpose\n- timing.dead_hold.body.f0\n"
    assert _declared(gates) == {"overlap.same_stop.body.f20"}          # a declaration needs its reason
    assert [f["id"] for f in undeclared(report, gates)] == ["timing.dead_hold.body.f0"]


def test_the_passes_gate_needs_the_principles_checked_and_every_flag_fixed_or_declared(tmp_path):
    shot = tmp_path / "s"
    (shot / "out_p1" / "principles").mkdir(parents=True)
    (shot / "out_p1" / "shot.json").write_text("{}", encoding="utf-8")
    (shot / "PLAN.md").write_text("The brief.\nIdea sentence: a box falls.\n", encoding="utf-8")
    miss, _ = check(str(shot))
    assert any("twelve principles have not been checked on out_p1" in m for m in miss)
    import os
    import time
    pj = shot / "out_p1" / "principles" / "principles.json"
    pj.write_text(json.dumps({"flags": [{"id": "overlap.same_stop.body.f20", "principle": "overlap",
                                         "frames": [20, 20], "what": "everything stops on f20"}]}), encoding="utf-8")
    later = time.time() + 5
    os.utime(pj, (later, later))
    miss, _ = check(str(shot))
    assert any(m.startswith("P9 overlap.same_stop.body.f20") for m in miss)
    (shot / "GATES.md").write_text("## Declared\n- overlap.same_stop.body.f20: a hard landing, on purpose\n",
                                   encoding="utf-8")
    miss, _ = check(str(shot))
    assert not any("overlap.same_stop" in m for m in miss)
    assert any("the overlap gate is missing" in m for m in miss)
    assert any("the follow-through gate is missing" in m for m in miss)


def test_the_passes_stage_gets_its_core_topics_in_full_and_the_rest_as_an_index():
    topics = load_topics(BUNDLED_BOOK)
    text = stage_block("passes", topics, [], None)
    assert "### OVL18. Never stop every part on the same frame" in text
    assert "More rules for this stage" in text
    loco = next(t for t in topics if t.name == "locomotion")
    r = next(r for r in loco.rules if "passes" in r.stages)
    assert f"- {r.id}. {r.title} (locomotion)" in text and f"### {r.id}." not in text
    named = stage_block("passes", topics, [], ["locomotion"])
    assert f"### {r.id}." in named                                    # a subject the shot named comes in full
    assert len(text) < len(stage_block("brief", topics, [], None)) * 8
