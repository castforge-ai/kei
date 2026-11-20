"""The book's heavy-lift rules, measured on a held heavy load (hand-built frames: joints only)."""
import math

from kei.weight_rules import weight_flags


def body(f, pitch_deg, knee_deg, pelvis_y, pelvis_z, load_y, load_z):
    """A frame: legs bent knee_deg, trunk pitched forward pitch_deg, both palms at the load."""
    j = {}
    for s, x in (("l", -0.1), ("r", 0.1)):
        j[f"foot_{s}"] = (x, 0.09, 0.0)
        for p in ("heel_{s}", "ball_{s}", "ball_{s}_tip"):
            j[p.format(s=s)] = (x, 0.0, 0.05)
        a = math.radians(180 - knee_deg)                   # the knee's inner angle
        j[f"calf_{s}"] = (x, 0.5, 0.0)
        j[f"thigh_{s}"] = (x, 0.5 + 0.4 * math.sin(a - math.pi / 2 + math.pi / 2) * 0 + 0.4 * -math.cos(a),
                           0.4 * math.sin(a))
        j[f"hand_{s}"] = j[f"hand_{s}_tip"] = (x * 1.6, load_y, load_z)
    p = math.radians(pitch_deg)
    j["pelvis"] = (0.0, pelvis_y, pelvis_z)
    j["neck_01"] = (0.0, pelvis_y + 0.5 * math.cos(p), pelvis_z + 0.5 * math.sin(p))
    return {"f": f, "joints": j}


def shot(mass=35, attach=0):
    return {"fps": 24, "frames": 12, "objects": [{"name": "crate", "shape": "box", "size": [0.3, 0.3, 0.3],
                                                  "rest": [0.0, 0.3, 0.4], "mass_kg": mass,
                                                  "attach": [{"f": attach, "to": "hands"}]}]}


def kinds(flags):
    return sorted({f["measure"] for f in flags})


def lifting(pitch, knee, pelvis_z=-0.1, rise=0.03, n=13):
    return [body(f, pitch, knee, 0.8, pelvis_z, 0.3 + rise * f, 0.4) for f in range(n)]


def test_a_back_lift_on_straight_legs_is_flagged_and_a_leg_lift_is_not():
    assert "hinge_deg" in kinds(weight_flags(shot(), lifting(pitch=60, knee=5)))
    assert "hinge_deg" not in kinds(weight_flags(shot(), lifting(pitch=20, knee=70)))


def test_hips_that_do_not_counterweigh_a_load_far_ahead_are_flagged():
    frames = [body(f, 20, 60, 0.8, 0.12, 0.6, 0.6) for f in range(13)]       # load 0.35 m ahead, hips forward
    assert "hips_forward_m" in kinds(weight_flags(shot(), frames))
    frames = [body(f, 20, 60, 0.8, -0.15, 0.6, 0.6) for f in range(13)]      # hips back behind the feet
    assert "hips_forward_m" not in kinds(weight_flags(shot(), frames))


def test_a_light_load_is_not_judged():
    assert weight_flags(shot(mass=3), lifting(pitch=60, knee=5)) == []


def test_a_heavy_load_that_jumps_is_flagged():
    frames = lifting(20, 70)
    frames[6] = body(6, 20, 70, 0.8, -0.1, 0.9, 0.4)                       # one frame 0.42 m up and back down
    assert "load_accel_g" in kinds(weight_flags(shot(), frames))
    assert "load_accel_g" not in kinds(weight_flags(shot(), lifting(20, 70)))


def test_a_one_frame_low_point_at_the_pick_up_is_flagged_and_a_held_one_is_not():
    def dip(f, held):
        y = 0.8 - (0.2 if (f == 6 or (held and 5 <= f <= 7)) else 0.0)
        return body(f, 20, 70, y, -0.1, 0.3, 0.4)
    assert "low_point_frames" in kinds(weight_flags(shot(attach=6), [dip(f, False) for f in range(13)]))
    assert "low_point_frames" not in kinds(weight_flags(shot(attach=6), [dip(f, True) for f in range(13)]))
