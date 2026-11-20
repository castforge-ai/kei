"""kei check: the checks stage's own tool. It writes out_<pass>/body_check/body_check.json from Kei's own data."""
import json
import os
import shutil
from pathlib import Path

from kei.body_check import check_pass, knee_snaps
from kei.cli import main
from kei.gates.stage_gate import stage_misses
from kei.stages import stage_by_id
from shotkit import full

ROOT = Path(__file__).resolve().parent.parent
WALK = ROOT / "examples" / "stepped_walk" / "out_blocking" / "shot.json"
STAND = {"root": [0, 0.915, 0], "footL": [-0.12, 0.09, 0, 0, 0], "footR": [0.12, 0.09, 0, 0, 0]}


def pass_dir(tmp_path, shot, name="p1"):
    out = tmp_path / f"out_{name}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "shot.json").write_text(json.dumps(shot), encoding="utf-8")
    return tmp_path


def held(pose, frames=12):
    return {"rig": "v4", "fps": 24, "frames": frames, "keys": [{"f": 0, **pose}, {"f": frames, **pose}]}


def flags(report, check):
    return [f for f in report["flags"] if f["check"] == check]


def test_writes_every_measure_the_checks_row_promises(tmp_path):
    shutil.copy(WALK, pass_dir(tmp_path, {}, "p1") / "out_p1" / "shot.json")
    path = check_pass(tmp_path, "p1", character="kei")
    assert path == tmp_path / "out_p1" / "body_check" / "body_check.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    for key in ("contacts", "foot_slide", "balance", "joint_ranges", "arcs", "flags", "thresholds"):
        assert key in report, key
    assert report["character"] == "kei" and report["mode"] == "spline"
    assert all("source" in t for t in report["thresholds"].values())
    assert report["contacts"]["l"], "the walk plants the left foot"


def test_a_standing_pose_raises_no_flag(tmp_path):
    report = json.loads(check_pass(pass_dir(tmp_path, held(STAND)), "p1", character="kei").read_text())
    assert report["flags"] == []
    assert report["balance"]["frames_outside_support"] == []


def test_a_planted_foot_that_slides_is_flagged_with_its_frames(tmp_path):
    shot = {"rig": "v4", "fps": 24, "frames": 10, "keys": [
        {"f": 0, **STAND}, {"f": 10, **STAND, "footL": [-0.12, 0.09, 0.15, 0, 0]}]}
    report = json.loads(check_pass(pass_dir(tmp_path, shot), "p1", character="kei", mode="linear").read_text())
    slide = flags(report, "foot_slide")
    assert slide and slide[0]["side"] == "l"
    assert slide[0]["frames"][0] == 0 and slide[0]["frames"][1] == 10
    assert report["foot_slide"]["max_m_per_frame"]["l"] > 0.01


def test_a_held_lean_past_the_feet_is_out_of_balance(tmp_path):
    report = json.loads(check_pass(pass_dir(tmp_path, held({**STAND, "root": [0, 0.9, 0.15], "spine": [1.3, 0, 0]})), "p1",
                                   character="kei").read_text())
    assert flags(report, "balance")
    assert len(report["balance"]["frames_outside_support"]) >= 10


def test_a_foot_target_out_of_reach_is_a_joint_range_flag(tmp_path):
    report = json.loads(check_pass(pass_dir(tmp_path, held({**STAND, "footL": [-0.12, 0.09, 1.2, 0, 0]})), "p1",
                                   character="kei").read_text())
    assert any("reach" in f["what"] for f in flags(report, "joint_ranges"))


def test_a_kink_in_a_path_is_an_arc_flag(tmp_path):
    shot = {"rig": "v4", "fps": 24, "frames": 12, "keys": [
        {"f": 0, **STAND, "ikR": [0.3, 1.0, 0.2, 1]}, {"f": 6, **STAND, "ikR": [0.3, 1.3, 0.2, 1]},
        {"f": 12, **STAND, "ikR": [0.3, 1.3, 0.5, 1]}]}
    report = json.loads(check_pass(pass_dir(tmp_path, shot), "p1", character="kei", mode="linear").read_text())
    kinks = [f for f in flags(report, "arcs") if f["part"] == "hand_r_tip"]
    assert kinks and kinks[0]["frames"][0] == 6


def test_kei_check_clears_the_p10_gate(tmp_path, capsys):
    root = tmp_path / "shots" / "box_fall"
    root.mkdir(parents=True)
    full(root, upto="passes")
    (root / "out_p1" / "shot.json").write_text(json.dumps(held(STAND)), encoding="utf-8")
    os.utime(root / "out_p1" / "shot.json")
    assert any(m.startswith("P10") for m in stage_misses(root, stage_by_id("checks")))
    assert main(["check", str(root), "p1", "--character", "kei"]) == 0
    assert "body_check.json" in capsys.readouterr().out
    assert not any(m.startswith("P10") for m in stage_misses(root, stage_by_id("checks")))


WALKS = ROOT / "tests" / "fixtures" / "walks"


def _walk_report(tmp_path, fixture, character):
    shutil.copy(WALKS / fixture, pass_dir(tmp_path, {}, "p8") / "out_p8" / "shot.json")
    return json.loads(check_pass(tmp_path, "p8", character=character).read_text(encoding="utf-8"))


def test_a_walk_whose_mass_is_behind_the_front_heel_at_toe_off_falls_back_even_for_two_frames(tmp_path):
    # Keira's out_p8 (author's note, 2026-11-02: she would fall behind): the rear toe leaves the ground at frame 10
    # while the centre of mass is 0.11 m behind the front heel. A fall backward is never caught by the next step.
    report = _walk_report(tmp_path, "keira_p8_falls_back.json", "keira")
    back = [f for f in flags(report, "balance") if "behind" in f["what"]]
    assert back, report["flags"]
    assert back[0]["frames"][0] <= 10 <= back[0]["frames"][1]
    assert report["balance"]["max_behind_m"] > 0.1


def test_a_walk_whose_trunk_leans_back_against_the_travel_is_flagged_at_the_passing(tmp_path):
    report = _walk_report(tmp_path, "keira_p8_falls_back.json", "keira")
    lean = flags(report, "trunk_lean")
    assert lean and any(a <= 13 <= b for a, b in (f["frames"] for f in lean)), report["flags"]
    assert report["balance"]["trunk_lean_deg"]["min"] < -1.5


def test_the_approved_kei_walk_has_no_backward_fall_and_no_back_lean(tmp_path):
    report = _walk_report(tmp_path, "kei_p10_approved.json", "kei")
    assert not [f for f in flags(report, "balance") if "behind" in f["what"]]
    assert not flags(report, "trunk_lean")
    assert report["balance"]["trunk_lean_deg"]["min"] > 5


def test_a_shot_that_does_not_travel_has_no_trunk_lean_judgement(tmp_path):
    report = json.loads(check_pass(pass_dir(tmp_path, held(STAND)), "p1", character="kei").read_text())
    assert report["balance"]["trunk_lean_deg"] is None and not flags(report, "trunk_lean")


def _raised(shot: dict, dy: float) -> dict:
    """The shot with the root and both foot targets dy higher on every key: the same knees, the feet off the ground
    (keira_model re-imported on 2026-11-03 with a shorter ankle: her approved walk then hovered about 2.5 cm)."""
    keys = []
    for k in shot["keys"]:
        k = dict(k)
        for c in ("root", "footL", "footR"):
            if c in k:
                k[c] = [k[c][0], k[c][1] + dy, *k[c][2:]]
        keys.append(k)
    return {**shot, "keys": keys}


def test_a_planted_foot_that_hovers_above_the_ground_is_flagged_with_its_foot_frames_and_height(tmp_path):
    shot = _raised(json.loads((WALKS / "kei_p10_approved.json").read_text(encoding="utf-8")), 0.025)
    report = json.loads(check_pass(pass_dir(tmp_path, shot, "p8"), "p8", character="kei").read_text())
    hover = flags(report, "hover")
    assert {f["side"] for f in hover} == {"l", "r"}, report["flags"]
    for f in hover:
        assert f["frames"][1] - f["frames"][0] >= 3, f      # a planted span, not one frame of a swing
        assert f"the planted {f['side']} foot" in f["what"] and "0.02" in f["what"], f
    assert report["thresholds"]["hover_m"]["value"] == 0.01


def test_a_grounded_walk_and_a_standing_pose_do_not_hover(tmp_path):
    assert not flags(_walk_report(tmp_path / "walk", "kei_p10_approved.json", "kei"), "hover")
    report = json.loads(check_pass(pass_dir(tmp_path / "stand", held(STAND)), "p1", character="kei").read_text())
    assert not flags(report, "hover")


def test_kei_check_prints_a_hovering_foot(tmp_path, capsys):
    shot = _raised(json.loads((WALKS / "kei_p10_approved.json").read_text(encoding="utf-8")), 0.025)
    pass_dir(tmp_path, shot, "p8")
    assert main(["check", str(tmp_path), "p8", "--character", "kei"]) == 0
    out = capsys.readouterr().out
    assert "- hover f" in out and "the planted l foot" in out and "the planted r foot" in out, out


# The left knee bend of out_p22 (kei_model, kei retarget keeping the standing height, 2026-11-03), baked, f4..f7: the
# contact key snaps nearly straight for one frame. The same frames of p21 on the old model bend smoothly.
P22_KNEE_L = [24.0, 15.1, 1.8, 19.0]
P21_OLD_KNEE_L = [24.5, 16.7, 14.3, 21.2]


def test_a_one_frame_knee_snap_is_found_with_its_frame_and_size():
    snaps = knee_snaps(P22_KNEE_L, [4, 5, 6, 7])
    assert [s[0] for s in snaps] == [6], snaps
    assert 13.0 < snaps[0][1] < 13.5          # the smaller of the two drops: 15.1 -> 1.8 and 1.8 -> 19.0


def test_a_smooth_knee_curve_has_no_snap():
    assert knee_snaps(P21_OLD_KNEE_L, [4, 5, 6, 7]) == []
    assert knee_snaps([10.0, 20.0, 30.0, 25.0, 12.0, 5.0, 9.0], list(range(7))) == []


def test_a_knee_spike_is_a_snap_too():
    assert [s[0] for s in knee_snaps([20.0, 21.0, 35.0, 22.0], [0, 1, 2, 3])] == [2]


def test_kei_check_flags_a_knee_snap_on_the_frame(tmp_path):
    # the stand, with the root dropped 8 cm on frame 6 only: the knees bend and straighten again in one frame
    keys = [{"f": f, **STAND, "tangent": "flat"} for f in (0, 5, 7, 12)]
    keys.insert(2, {"f": 6, **STAND, "root": [0, 0.835, 0], "tangent": "flat"})
    report = json.loads(check_pass(pass_dir(tmp_path, {"rig": "v4", "fps": 24, "frames": 12, "keys": keys}), "p1",
                                   character="kei", mode="linear").read_text())
    snaps = flags(report, "knee_snap")
    assert {f["side"] for f in snaps} == {"l", "r"} and all(f["frames"] == [6, 6] for f in snaps), report["flags"]
    assert "the l knee" in snaps[0]["what"] or "the r knee" in snaps[0]["what"]


def test_the_golden_walks_have_no_knee_snap(tmp_path):
    for fixture, name in (("kei_p10_approved.json", "kei"), ("keira_p8_falls_back.json", "keira")):
        assert not flags(_walk_report(tmp_path / name, fixture, name), "knee_snap"), fixture


def test_an_in_place_loop_is_measured_as_it_travels_so_its_treadmill_feet_are_planted(tmp_path):
    back = {**STAND, "footL": [-0.12, 0.09, -0.15, 0, 0], "footR": [0.12, 0.09, -0.15, 0, 0]}
    shot = {"rig": "v4", "fps": 24, "frames": 10, "keys": [{"f": 0, **STAND}, {"f": 10, **back}]}
    report = json.loads(check_pass(pass_dir(tmp_path, shot), "p1", character="kei", mode="linear").read_text())
    assert flags(report, "foot_slide")                     # without the speed, the feet skate back
    shot["in_place"] = {"speed_mps": 0.36}                 # 0.15 m in 10 frames at 24 fps
    report = json.loads(check_pass(pass_dir(tmp_path, shot), "p1", character="kei", mode="linear").read_text())
    assert flags(report, "foot_slide") == [] and report["in_place_speed_mps"] == 0.36


def test_contact_timing_flags_a_foot_that_lifts_with_the_weight_still_on_it():
    from kei.body_check import contact_timing

    def frame(f, l_y, r_y, com_x):
        j = {"com": (com_x, 0.9, 0.0)}
        for s, x, y in (("l", -0.1, l_y), ("r", 0.1, r_y)):
            for p in ("heel_{s}", "ball_{s}", "ball_{s}_tip"):
                j[p.format(s=s)] = (x, y, 0.0)
        return {"f": f, "joints": j}
    late = [frame(0, 0, 0, -0.08), frame(1, 0.1, 0, -0.08)]       # the left foot lifts with 90% on it
    early = [frame(0, 0, 0, 0.08), frame(1, 0.1, 0, 0.08)]        # the weight moved to the right foot first
    assert [(s, f) for s, f, _ in contact_timing(late, 0.02)["lifts"]] == [("l", 1)]
    assert contact_timing(early, 0.02)["lifts"] == []
    slam = [frame(0, 0.1, 0, 0.08), frame(1, 0, 0, -0.09)]        # the left foot lands and takes 95% at once
    assert [(s, f) for s, f, _ in contact_timing(slam, 0.02)["lands"]] == [("l", 1)]


def test_the_approved_walk_has_no_contact_timing_flag(tmp_path):
    report = json.loads(check_pass(pass_dir(tmp_path, json.loads(
        (ROOT / "tests" / "fixtures" / "walks" / "kei_p10_approved.json").read_text(encoding="utf-8"))), "p1",
        character="kei").read_text())
    assert flags(report, "contact_timing") == []
