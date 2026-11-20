"""Jolts and arm targets out of reach: the checks the heavy_lift agents wrote for themselves."""
from kei.motion_check import motion_flags


def _frames(ys, ik=None):
    out = []
    for f, y in enumerate(ys):
        j = {"pelvis": (0.0, y, 0.0), "com": (0.0, y, 0.0), "hand_l": (0.3, 1.0, 0.3), "hand_r": (-0.3, 1.0, 0.3)}
        pose = {"ikL": ik} if ik else {}
        out.append({"f": f, "joints": j, "pose": pose})
    return out


def test_a_pelvis_that_jumps_is_a_jolt_and_smooth_motion_is_not():
    smooth = [0.95 - 0.001 * f for f in range(10)]
    assert motion_flags(_frames(smooth), 24) == []
    jolt = smooth[:5] + [smooth[5] - 0.05] + smooth[6:]
    fl = [f for f in motion_flags(_frames(jolt), 24) if f["check"] == "jolt"]
    assert fl and fl[0]["measure"] == "jolt_g" and fl[0]["value"] > 4


def test_an_ik_target_beyond_the_wrist_is_a_hard_reach_flag():
    fl = motion_flags(_frames([0.95] * 4, ik=[0.3, 1.0, 0.36, 1.0]), 24)
    reach = [f for f in fl if f["check"] == "joint_ranges"]
    assert reach and "6.0 cm short" in reach[0]["what"] and "measure" not in reach[0]
    assert motion_flags(_frames([0.95] * 4, ik=[0.3, 1.0, 0.36, 0.5]), 24) == [], "a partial weight is not a hold"
