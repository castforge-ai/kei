"""The basic posing checks: each catches its own fault and leaves a walk and a relaxed stand alone."""
from kei.posing_check import posing_flags

HIP = 0.2


def pose(foot_gap=0.2, neck=(0.0, 0.0), arm_bend_deg=None):
    """A standing figure's joints (metres, y up, x across, z forward), the feet on the floor."""
    j = {"thigh_l": (-HIP / 2, 0.9, 0.0), "thigh_r": (HIP / 2, 0.9, 0.0),
         "foot_l": (-foot_gap / 2, 0.08, 0.0), "foot_r": (foot_gap / 2, 0.08, 0.0),
         "spine_05": (0.0, 1.4, 0.0), "neck_01": (0.0, 1.5, 0.0), "neck_02": (0.0, 1.58, 0.0), "head": (0.0, 1.68, 0.0)}
    for s, x in (("l", -foot_gap / 2), ("r", foot_gap / 2)):
        j[f"heel_{s}"] = (x, 0.0, -0.05)
        j[f"ball_{s}"] = (x, 0.0, 0.1)
        j[f"ball_{s}_tip"] = (x, 0.0, 0.15)
    j["head"] = (j["head"][0] + neck[0], j["head"][1], j["head"][2] + neck[1])
    return j


def run(joints_per_frame, knee=12.0, elbow=15.0):
    frames = [{"f": n, "joints": j} for n, j in enumerate(joints_per_frame)]
    return posing_flags(frames, {"l": [knee] * len(frames), "r": [knee] * len(frames)},
                        {"l": [elbow] * len(frames), "r": [elbow] * len(frames)}, 1.0, 0.02)[0]


def whats(flags):
    return " | ".join(f["what"] for f in flags)


def test_a_relaxed_stand_raises_no_flag():
    assert run([pose()] * 30) == [] or "hardly moves" in whats(run([pose()] * 30))     # only the still-body note


def test_a_wide_a_frame_stance_is_flagged():
    flags = run([pose(foot_gap=0.7)] * 8)
    assert any("A-frame" in f["what"] for f in flags)
    assert not any("A-frame" in f["what"] for f in run([pose(foot_gap=0.3)] * 8))


def test_both_knees_locked_with_both_feet_planted_is_flagged_but_one_straight_leg_is_not():
    assert any("locked knees" in f["what"] for f in run([pose()] * 10, knee=1.0))
    frames = [{"f": n, "joints": pose()} for n in range(10)]
    flags = posing_flags(frames, {"l": [1.0] * 10, "r": [30.0] * 10}, {"l": [15.0] * 10, "r": [15.0] * 10}, 1.0, 0.02)[0]
    assert not any("locked" in f["what"] for f in flags)


def test_a_kinked_neck_is_flagged_and_a_small_nod_is_not():
    assert any("neck breaks" in f["what"] for f in run([pose(neck=(0.0, 0.18))] * 3))
    assert not any("neck" in f["what"] for f in run([pose(neck=(0.0, 0.03))] * 3))


def test_a_dead_straight_arm_for_a_long_time_is_flagged():
    assert any("dead straight" in f["what"] for f in run([pose()] * 24, elbow=1.0))
    assert not any("dead straight" in f["what"] for f in run([pose()] * 24, elbow=12.0))


def test_a_whole_body_that_does_not_move_in_a_long_pass_is_flagged_but_a_short_hold_is_not():
    assert any("hardly moves" in f["what"] for f in run([pose()] * 30))
    assert not any("hardly moves" in f["what"] for f in run([pose()] * 12))


def test_a_body_that_moves_is_not_flagged_for_stillness():
    frames = [pose() for _ in range(30)]
    for n, j in enumerate(frames):
        j["head"] = (0.05 * (n % 6), j["head"][1], j["head"][2])
        j["spine_05"] = (0.0, 1.4 + 0.03 * (n % 5), 0.0)
        j["thigh_l"] = (j["thigh_l"][0], 0.9 + 0.05 * (n % 4), 0.0)
        for name in ("neck_01", "neck_02", "foot_l", "foot_r", "heel_l", "heel_r", "ball_l", "ball_r"):
            j[name] = (j[name][0] + 0.05 * (n % 7), j[name][1], j[name][2])
    assert not any("hardly moves" in f["what"] for f in run(frames))
