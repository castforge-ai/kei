"""Guards the audit asked for: curves stay between their keys, a smooth arc raises no flag, a held object stays in
the hands, and a short render stays fast."""
import json
import math
import random
import time

from kei.body_check import check_pass
from kei.objects import GRAB, palm, read_objects, surface_gap, track, yaws
from kei.sample import bake, sampler
from test_body_check import STAND, flags, pass_dir


def test_a_clamped_curve_never_leaves_the_range_of_the_two_keys_around_it():
    rng = random.Random(7)
    for _ in range(25):
        fs = sorted(rng.sample(range(1, 40), 5))
        keys = [{"f": 0, "yaw": 0.0}] + [{"f": f, "yaw": round(rng.uniform(-1, 1), 3), "spine": [round(rng.uniform(
            -0.4, 0.4), 3), 0, 0]} for f in fs]
        at = sampler({"rig": "v4", "fps": 24, "frames": fs[-1], "keys": keys}, "spline")
        for a, b in zip(keys, keys[1:]):
            for ch, idx in (("yaw", None), ("spine", 0)):
                va, vb = at(a["f"])[ch], at(b["f"])[ch]
                lo, hi = (min(va, vb), max(va, vb)) if idx is None else (min(va[0], vb[0]), max(va[0], vb[0]))
                for k in range(a["f"], b["f"] + 1):
                    v = at(k)[ch] if idx is None else at(k)[ch][0]
                    assert lo - 1e-9 <= v <= hi + 1e-9, (ch, a["f"], b["f"], k, v)


def test_a_smooth_arc_of_the_hand_raises_no_arc_flag(tmp_path):
    keys = []
    for i, f in enumerate(range(0, 25, 4)):
        t = math.pi * i / 6
        keys.append({"f": f, **STAND, "ikR": [round(0.3 + 0.15 * math.sin(t), 4), round(1.1 + 0.15 * math.cos(t), 4),
                                              0.25, 1]})
    shot = {"rig": "v4", "fps": 24, "frames": 24, "keys": keys}
    report = json.loads(check_pass(pass_dir(tmp_path, shot), "p1", character="kei", mode="spline").read_text())
    assert [f for f in flags(report, "arcs") if f["part"] == "hand_r_tip"] == []


def test_a_held_object_stays_in_both_hands_for_the_whole_hold_even_as_it_turns():
    shot = {"rig": "v4", "fps": 24, "frames": 24, "keys": [
        {"f": 0, **STAND, "ikL": [-0.2, 1.0, 0.35, 1], "ikR": [0.2, 1.0, 0.35, 1]},
        {"f": 12, **STAND, "ikL": [-0.15, 1.1, 0.45, 1], "ikR": [0.25, 1.1, 0.3, 1]},
        {"f": 24, **STAND, "ikL": [-0.2, 1.0, 0.35, 1], "ikR": [0.2, 1.0, 0.35, 1]}],
        "objects": [{"name": "box", "shape": "box", "size": [0.36, 0.3, 0.3], "rest": [0.0, 1.0, 0.35],
                     "turn": "hands", "attach": [{"f": 0, "to": "hands"}]}]}
    frames = bake(shot)
    o = read_objects(shot)[0]
    start = [surface_gap(o, track(o, frames)[0][0], palm(frames[0]["joints"], s)) for s in "lr"]
    for fr, (c, holder), y in zip(frames, track(o, frames), yaws(o, frames)):
        assert holder == "hands"
        for s, g0 in zip("lr", start):
            assert surface_gap(o, c, palm(fr["joints"], s), y) <= g0 + GRAB, (fr["f"], s)


def test_a_short_stick_render_stays_fast(tmp_path):
    from kei.render import render_shot
    shot = {"rig": "v4", "fps": 24, "frames": 12, "keys": [{"f": 0, **STAND}, {"f": 12, **STAND, "yaw": 0.4}]}
    src = tmp_path / "shot.json"
    src.write_text(json.dumps(shot), encoding="utf-8")
    t0 = time.perf_counter()
    render_shot(src, tmp_path / "out", "spline", size=120, workers=1)
    assert time.perf_counter() - t0 < 20     # about 1 s on the dev machine: a ten-times slowdown fails here
