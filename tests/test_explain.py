"""kei check --explain, and the chest axis of a rig whose clavicles share one point."""
import json

from kei.explain import body_id, explain
from kei.principles import Motion


def reports(tmp_path):
    out = tmp_path / "out_p3"
    (out / "body_check").mkdir(parents=True)
    (out / "principles").mkdir()
    (out / "body_check" / "body_check.json").write_text(json.dumps({
        "flags": [{"check": "balance", "frames": [0, 3], "measure": "balance_outside_m", "value": 0.168,
                   "what": "the centre of mass stays outside the support", "rule": "soft", "note": True}],
        "thresholds": {"balance_tol_m": {"value": 0.03, "source": "BALANCE_TOL 0.03 m"},
                       "hover_m": {"value": 0.01, "source": "HOVER"}}}), encoding="utf-8")
    twin = {"id": "solid_drawing.twin_pose.hands.f95", "principle": "solid_drawing", "frames": [95, 95],
            "part": "hands", "what": "the hands mirror each other", "rule": "PSE"}
    (out / "principles" / "principles.json").write_text(json.dumps({
        "flags": [twin], "principles": {"solid_drawing": {"measured": {}, "flags": [twin]}},
        "thresholds": {"TWIN": 0.02, "CLAVICLE_MIN": 0.01, "UNISON": 0.97}, "scale": 1.0}), encoding="utf-8")
    return out


def test_a_principle_flag_is_explained_with_its_limits(tmp_path):
    lines = explain(reports(tmp_path), "solid_drawing.twin_pose.hands.f95")
    text = "\n".join(lines)
    assert "frames 95-95, rule PSE" in text and "limit TWIN = 0.02" in text and "UNISON" not in text
    assert "- solid_drawing.twin_pose.hands.f95: <reason>" in text


def test_a_copied_id_whose_frame_moved_still_finds_its_flag(tmp_path):
    assert explain(reports(tmp_path), "solid_drawing.twin_pose.hands.f97")


def test_a_body_check_is_named_by_check_part_and_frame(tmp_path):
    out = reports(tmp_path)
    assert body_id({"check": "balance", "frames": [0, 3]}) == "balance.body.f0"
    text = "\n".join(explain(out, "balance"))
    assert "measured balance_outside_m = 0.168" in text and "limit balance_tol_m = 0.03" in text
    assert "hover_m" not in text and "the register is pushed" in text


def test_nothing_matches_an_unknown_name(tmp_path):
    assert explain(reports(tmp_path), "arcs.kink") == []


def frame(clav_gap):
    return {"f": 0, "joints": {"clavicle_l": (-clav_gap / 2, 1.4, 0), "clavicle_r": (clav_gap / 2, 1.4, 0),
                               "upperarm_l": (-0.2, 1.4, 0), "upperarm_r": (0.2, 1.4, 0),
                               "spine_03": (0, 1.3, 0), "neck_01": (0, 1.5, 0)}}


def test_clavicles_at_one_point_take_the_chest_axis_from_the_upper_arms():
    right, up, forward = Motion([frame(0.0)]).chest_axes(0)
    assert right == (1.0, 0.0, 0.0) and up == (0.0, 1.0, 0.0) and abs(forward[2]) == 1.0
    assert Motion([frame(0.3)]).chest_axes(0)[0] == (1.0, 0.0, 0.0)
