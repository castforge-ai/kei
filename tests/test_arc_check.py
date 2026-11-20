"""Spacing pops and wobble: arc faults the one-frame kink rule misses."""
import json
import math
from pathlib import Path

from kei.arc_check import arc_flags
from kei.characters import load_character, on_character
from kei.sample import bake

ROOT = Path(__file__).resolve().parent.parent


def _frames(path):
    return [{"f": f, "joints": {"hand_l_tip": p, "spine_05": (0.0, 1.4, 0.0)}} for f, p in enumerate(path)]


def test_a_one_frame_jump_is_a_spacing_pop():
    path = [(0.0, 1.0, 0.01 * f) for f in range(10)]
    path = path[:5] + [(0.0, 1.0, p[2] + 0.05) for p in path[5:]]
    flags = [f for f in arc_flags(_frames(path)) if f["measure"] == "spacing_pop_ratio" and f["part"] == "hand_l_tip"]
    assert [f["frames"] for f in flags] == [[5, 5]] and flags[0]["value"] >= 2.5


def test_a_zigzag_is_a_wobble_and_a_smooth_arc_is_not():
    zig = [(0.02 * (f % 2), 1.0, 0.01 * f) for f in range(12)]
    assert any(f["measure"] == "arc_wobble_deg" for f in arc_flags(_frames(zig)))
    arc = [(0.3 * math.sin(f / 10), 1.0 + 0.3 * math.cos(f / 10), 0.0) for f in range(12)]
    assert arc_flags(_frames(arc)) == []


def test_the_approved_walk_has_no_arc_fault():
    walk = json.loads((ROOT / "tests" / "fixtures" / "walks" / "kei_p10_approved.json").read_text(encoding="utf-8"))
    frames = bake(on_character(walk, load_character("kei")), "spline")
    assert arc_flags(frames) == []
