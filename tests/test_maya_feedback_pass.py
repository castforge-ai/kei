"""Plan 6c, Task 4: the next pass matches the animator's pose. The note's pose reaches the animator (and the critics)
as targets, and a pass that misses one is sent back by the check, naming the control. No Maya needed: the check reads
the pass's keys."""
import json

from kei.apps import maya_feedback
from kei.conductor import carried_poses
from kei.seats import FakeSeat, SeatResult
from kei.state import ShotState, load_state, save_state
from test_conductor import CFG, run_shot, shot as new_shot

TARGETS = [{"control": "kei:l_leg_pv_ctl", "attr": "translateX", "frame": 6, "value": 15.0},
           {"control": "kei:c_head_fk_ctl", "attr": "rotateZ", "frame": 6, "value": -2.0}]


def _pass(root, name, pv_at_6, head_at_6=-2.0):
    (root / f"out_{name}").mkdir(parents=True, exist_ok=True)
    (root / f"out_{name}" / "shot.json").write_text(json.dumps({"rig": "maya", "frames": 12, "keys": [
        {"f": 0, "kei:l_leg_pv_ctl.translateX": 10.0, "kei:c_head_fk_ctl.rotateZ": 0.0},
        {"f": 4, "kei:l_leg_pv_ctl.translateX": 10.0, "kei:c_head_fk_ctl.rotateZ": head_at_6},
        {"f": 8, "kei:l_leg_pv_ctl.translateX": pv_at_6 * 2 - 10.0, "kei:c_head_fk_ctl.rotateZ": head_at_6},
        {"f": 12, "kei:l_leg_pv_ctl.translateX": 10.0, "kei:c_head_fk_ctl.rotateZ": 0.0}]}))


def _shot(tmp_path):
    root = new_shot(tmp_path)
    _pass(root, "p1", 10.0, 0.0)              # Kei's pass the animator corrected
    (root / "feedback" / "1").mkdir(parents=True)
    (root / "feedback" / "1" / "pose.json").write_text(json.dumps(
        {"pass": "p1", "rig": "kei", "unit_per_m": 100.0, "units": "cm", "targets": TARGETS}))
    note = {"stage": "passes", "attempt": 0, "result": "note", "misses": ["The knee reads heavier."],
            "pose": "feedback/1/pose.json", "scope": "this shot", "at": "x"}
    save_state(root, ShotState(stage="passes", status="running", request="a walk",
                               history=[{"stage": "deliver", "result": "approved", "misses": []}, note]))
    return root


def test_the_carried_note_includes_the_pose_targets(tmp_path):
    root = _shot(tmp_path)
    assert carried_poses(load_state(root)) == ["feedback/1/pose.json"]
    lines = maya_feedback.target_lines(root, ["feedback/1/pose.json"])
    assert len(lines) == 1
    assert "kei:l_leg_pv_ctl.translateX 15.000 at f6" in lines[0]
    assert "kei:c_head_fk_ctl.rotateZ -2.000 at f6" in lines[0]
    seen = []
    run_shot(root, "a walk", CFG, animator=FakeSeat("fake", lambda p, r: seen.append(p) or SeatResult(1, "x")))
    assert "The knee reads heavier." in seen[0] and "kei:l_leg_pv_ctl.translateX 15.000 at f6" in seen[0]


def test_a_pass_that_matches_the_pose_has_no_miss(tmp_path):
    root = _shot(tmp_path)
    _pass(root, "p2", 15.0)
    assert maya_feedback.target_misses(root, ["feedback/1/pose.json"]) == []


def test_a_pass_that_ignores_one_target_is_named(tmp_path):
    root = _shot(tmp_path)
    _pass(root, "p2", 10.0)
    misses = maya_feedback.target_misses(root, ["feedback/1/pose.json"])
    assert len(misses) == 1
    assert "kei:l_leg_pv_ctl.translateX" in misses[0] and "f6" in misses[0] and "p2" in misses[0]
    assert "15.000" in misses[0] and "10.000" in misses[0]


def test_no_new_pass_after_the_feedback_is_a_miss(tmp_path):
    root = _shot(tmp_path)
    misses = maya_feedback.target_misses(root, ["feedback/1/pose.json"])
    assert len(misses) == 1 and "new pass" in misses[0]


def test_a_pass_that_ignores_one_is_sent_back_by_the_check(tmp_path):
    root = _shot(tmp_path)

    def animator(prompt, shot_dir):
        _pass(root, "p2", 10.0)
        return SeatResult(0, "done")
    state = run_shot(root, "a walk", CFG, animator=FakeSeat("fake", animator))
    tries = [h for h in state.history if h.get("stage") == "passes" and h.get("result") == "fail"]
    assert tries and any("kei:l_leg_pv_ctl.translateX" in m for m in tries[0]["misses"])


def test_a_pass_that_matches_is_not_sent_back_by_the_check(tmp_path):
    root = _shot(tmp_path)

    def animator(prompt, shot_dir):
        _pass(root, "p2", 15.0)
        return SeatResult(0, "done")
    state = run_shot(root, "a walk", CFG, animator=FakeSeat("fake", animator))
    first = next(h for h in state.history if h.get("stage") == "passes" and h.get("result") in ("fail", "pass"))
    assert not any("feedback/1/pose.json" in m for m in first["misses"])


def test_the_passes_prompt_says_how_to_read_a_feedback_pose():
    from kei.prompts import HERE
    text = (HERE / "passes.md").read_text(encoding="utf-8")
    assert "feedback pose" in text and "pose.json" in text and "targets" in text


def test_the_critics_read_the_pose_targets_with_the_author_s_notes(tmp_path):
    from kei.conductor import _author_notes
    root = _shot(tmp_path)
    notes = _author_notes(load_state(root), root)
    assert notes[0] == "The knee reads heavier." and "kei:c_head_fk_ctl.rotateZ -2.000 at f6" in notes[1]
