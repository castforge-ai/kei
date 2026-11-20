"""kei poses and kei probe: the measured record of each key pose, and a frame-by-frame reader of a pass."""
import json
from pathlib import Path

import pytest

from kei.cli import main
from kei.pose_record import latest_pass, measure_pose, write_records
from kei.probe import ProbeError, parse_frames, probe
from test_sheet import decode

ROOT = Path(__file__).resolve().parent.parent
WALK = ROOT / "tests" / "fixtures" / "walks" / "kei_p10_approved.json"


def _shot(tmp_path, frames=8, **extra):
    shot = json.loads(WALK.read_text(encoding="utf-8"))
    src = tmp_path / "out_p1" / "shot.json"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(json.dumps({**shot, "frames": frames, "loop": False, **extra}), encoding="utf-8")
    return shot


def _joints(com, l_y=0.0, r_y=0.0):
    j = {"pelvis": (0.0, 0.95, 0.0), "head": (0.0, 1.6, 0.1), "com": com}
    for s, x, y in (("l", 0.15, l_y), ("r", -0.15, r_y)):
        j[f"heel_{s}"] = (x, y, -0.05)
        j[f"ball_{s}"] = (x, y, 0.12)
        j[f"ball_{s}_tip"] = (x, y, 0.18)
    return j


def test_the_weight_sits_over_the_foot_the_centre_of_mass_is_nearer():
    r = measure_pose(_joints((0.13, 0.9, 0.08)))
    assert r["support"] == "both" and r["weight_side"] == "left" and r["com"]["inside"]
    assert r["planted"] == {"left": True, "right": True}
    assert measure_pose(_joints((0.0, 0.9, 0.08)))["weight_side"] == "between"


def test_one_foot_down_carries_the_weight_and_a_com_off_it_is_out():
    r = measure_pose(_joints((-0.15, 0.9, 0.5), l_y=0.2))
    assert r["support"] == "right" and r["weight_side"] == "right"
    assert not r["com"]["inside"] and r["com"]["outside_m"] > 0.3


def test_airborne_has_no_support_and_no_com_verdict():
    r = measure_pose(_joints((0.0, 1.2, 0.0), l_y=0.3, r_y=0.3))
    assert (r["support"], r["weight_side"], r["com"]) == ("none", None, None)


def test_the_line_of_action_leans_forward_when_the_head_is_ahead():
    r = measure_pose(_joints((0.0, 0.9, 0.08)))
    assert r["line_of_action"]["side"] > 5 and abs(r["line_of_action"]["front"]) < 0.1


def test_kei_poses_writes_a_record_per_key_with_the_plan_half_and_a_sheet(tmp_path):
    shot = _shot(tmp_path)
    key_fs = sorted({int(k["f"]) for k in shot["keys"] if k["f"] <= 8})
    (tmp_path / "plan").mkdir()
    (tmp_path / "plan" / "plan.json").write_text(json.dumps({"keys": [
        {"f": key_fs[0], "function": "contact", "kind": "key", "intent": "a proud stride", "judged_in": "side",
         "note": "free text stays"}]}), encoding="utf-8")
    path = write_records(tmp_path, "p1", "kei")
    data = json.loads(path.read_text(encoding="utf-8"))
    first = data["keys"][0]
    assert first["function"] == "contact" and first["intent"] == "a proud stride" and first["in_plan"]
    assert first["support"] in ("both", "left", "right", "none") and "line_of_action" in first
    assert [r["f"] for r in data["keys"]] == [key_fs[0]], "the key poses are the plan's"
    w, h, _ = decode((path.parent / "pose_sheet.png").read_bytes())
    assert w == 4 * 200 and h % len(data["keys"]) == 0


def test_kei_poses_records_who_holds_an_object(tmp_path):
    _shot(tmp_path, objects=[{"name": "ball", "shape": "sphere", "size": [0.2], "rest": [0.5, 0.1, 0.0]}])
    shot = json.loads((tmp_path / "out_p1" / "shot.json").read_text(encoding="utf-8"))
    data = json.loads(write_records(tmp_path, "p1", "kei", sheet=False).read_text(encoding="utf-8"))
    assert all(r["objects"] == {"ball": None} for r in data["keys"])
    # no plan: the pass's own keys are the key poses
    assert [r["f"] for r in data["keys"]] == sorted({int(k["f"]) for k in shot["keys"] if k["f"] <= 8})
    assert not any(r["in_plan"] for r in data["keys"])


def test_the_latest_pass_is_the_highest_number(tmp_path):
    for n in ("p2", "p10", "blocking"):
        (tmp_path / f"out_{n}").mkdir()
        (tmp_path / f"out_{n}" / "shot.json").write_text("{}")
    assert latest_pass(tmp_path, "passes") == "p10"
    assert latest_pass(tmp_path, "blocking") == "blocking"
    assert latest_pass(tmp_path, "plan") is None


def test_probe_reads_bends_and_moves_frame_by_frame(tmp_path):
    _shot(tmp_path)
    t = probe(tmp_path, "p1", "2-4", ["knee_l", "hand_l"], "kei")
    assert [r["f"] for r in t["rows"]] == [2, 3, 4]
    assert 0 <= t["rows"][0]["knee_l"]["bend_deg"] < 160 and t["rows"][0]["knee_l"]["change_deg"] is not None
    assert len(t["rows"][1]["hand_l"]["pos_m"]) == 3 and t["rows"][1]["hand_l"]["moved_m"] >= 0
    assert set(t["rows"][0]["contact"]) == {"l", "r"}
    assert probe(tmp_path, "p1", "0", ["pelvis"], "kei")["rows"][0]["pelvis"]["moved_m"] is None


def test_probe_refuses_an_unknown_name_and_a_frame_outside_the_pass(tmp_path):
    _shot(tmp_path)
    with pytest.raises(ProbeError, match="no joint"):
        probe(tmp_path, "p1", "0-2", ["elbow"], "kei")
    with pytest.raises(ProbeError, match="outside"):
        parse_frames("5-99", 8)
    assert parse_frames("1,3-4,3", 8) == [1, 3, 4]


def test_the_commands_run_from_the_cli(tmp_path, capsys):
    _shot(tmp_path)
    assert main(["poses", str(tmp_path), "p1", "--character", "kei"]) == 0
    assert "pose_sheet.png" in capsys.readouterr().out
    out = tmp_path / "probe.json"
    assert main(["probe", str(tmp_path), "p1", "--character", "kei", "--frames", "0-2", "--joints", "elbow_r,com",
                 "--json", str(out)]) == 0
    text = capsys.readouterr().out
    assert "elbow_r" in text and "feet" in text and json.loads(out.read_text())["rows"][2]["f"] == 2
    assert main(["probe", str(tmp_path), "p1", "--character", "kei", "--frames", "0-2", "--joints", "wing"]) != 0


def test_before_a_review_kei_writes_the_records_of_the_latest_pass_and_never_stops_the_stage(tmp_path):
    from kei.pose_record import records_for_review
    _shot(tmp_path)
    (tmp_path / "out_p2").mkdir()
    (tmp_path / "out_p2" / "shot.json").write_text("{not json")   # a broken pass is the stage gates' to report
    records_for_review(tmp_path, "passes", "kei")
    assert not (tmp_path / "out_p2" / "poses").exists()
    (tmp_path / "out_p2" / "shot.json").unlink()
    records_for_review(tmp_path, "passes", "kei")
    assert (tmp_path / "out_p1" / "poses" / "poses.json").is_file()


def test_a_pose_record_carries_the_acting_reads(tmp_path):
    from kei.pose_record import acting_reads
    from kei.sample import bake
    shot = json.loads(WALK.read_text(encoding="utf-8"))
    r = acting_reads(bake(shot)[0]["joints"])
    assert set(r) == {"chest_facing_deg", "head_tilt_deg", "hands_clear"}
    assert abs(r["chest_facing_deg"]) < 45 and set(r["hands_clear"]) == {"left", "right"}
    turned = bake({**shot, "keys": [{**shot["keys"][0], "f": 0, "yaw": 1.0}], "frames": 2, "loop": False})
    assert abs(acting_reads(turned[0]["joints"])["chest_facing_deg"] - r["chest_facing_deg"]) > 30
