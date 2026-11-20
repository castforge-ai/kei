"""A character's style range, from their own shipped animation, and the register the author sets for a shot.

Kei's body checks are realism rules. A stylized character breaks some of them on purpose in every clip they ship, and
a critic that reads those flags as faults pushes the pose back toward generic realistic mechanics. So:

  hard rules   stay faults whatever the style: contacts, hover, foot slide, a knee bending backward, reach, a knee
               snap, locked knees, a body that does not move. A flag of a hard rule has no "measure".
  soft rules   balance, trunk lean, knee and elbow range, arc kinks, a wide stance, a neck bend, a straight arm. Each
               soft flag carries a "measure" and a "value" (kei.body_check, kei.posing_check).

rig/style.json (kei unreal style) holds, for each soft measure, the furthest the character's own clips go, the clip
that shows it, and the largest move of each part (the exaggeration check reads that). A soft flag at or under that
value (plus MARGIN) is marked "inside_style": a note with the clip that shows it, not a fault.

PLAN.md may carry a line "Register: realistic", "Register: stylized" or "Register: pushed", set by the author, never
guessed. Realistic (and no line) judges soft flags as faults unless they are inside the style range. Stylized does
the same, and says so. Pushed turns soft flags into notes, even outside the range. The Register line may name the
pushed beats as frame ranges ("Register: pushed f61-120, f150-167"): then only a flag that overlaps one of them is a
note, and the rest of the shot (a walk-in, a closing hold) is judged as realistic. With no ranges, pushed covers the
whole shot, as before. Spacing pops, wobble and jolts are never demoted by pushed; only the style range can allow one.
Arc kinks stay soft as before: the author's approved walk turns its hand tips sharply within single frames.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REGISTERS = ("realistic", "stylized", "pushed")
SOFT = ("balance_outside_m", "balance_behind_m", "trunk_lean_back_deg", "knee_max_deg", "elbow_max_deg",
        "arc_kink_deg", "stance_hip_widths", "neck_bend_deg", "straight_arm_frames", "spacing_pop_ratio",
        "arc_wobble_deg", "jolt_g", "lift_share", "land_share",
        "hinge_deg", "hips_forward_m", "low_point_frames", "load_accel_g", "mesh_depth_m")
MARGIN = 0.05       # a soft value up to 5% past the furthest her clips go is still hers: the same pose, read again
_REGISTER = re.compile(r"^[ \t>*+-]*\**register\**[ \t]*:[ \t]*\**[ \t]*([a-z]+)([^\n]*)", re.I | re.M)
_RANGE = re.compile(r"\bf?(\d+)\s*(?:-|to)\s*f?(\d+)\b", re.I)
PUSH_EXEMPT = ("spacing_pop_ratio", "arc_wobble_deg", "jolt_g")   # never demoted by pushed. Not arc_kink_deg: the
# approved walk turns its hand tips 66-110 deg in a frame at 2-5 cm a frame (tests/test_calibration.py)


def style_path(shot_dir: Path) -> Path:
    return Path(shot_dir) / "rig" / "style.json"


def load_style(shot_dir: Path) -> dict | None:
    p = style_path(shot_dir)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def register(shot_dir: Path) -> str | None:
    """The register the author set on PLAN.md's Register line, or None when there is no such line."""
    plan = Path(shot_dir) / "PLAN.md"
    if not plan.is_file():
        return None
    m = _REGISTER.search(plan.read_text(encoding="utf-8"))
    if not m:
        return None
    word = m.group(1).lower()
    return word if word in REGISTERS else None


def pushed_ranges(shot_dir: Path) -> list[tuple[int, int]] | None:
    """The frame ranges the Register line names for a pushed register, or None for the whole shot."""
    plan = Path(shot_dir) / "PLAN.md"
    if not plan.is_file():
        return None
    m = _REGISTER.search(plan.read_text(encoding="utf-8"))
    if not m or m.group(1).lower() != "pushed":
        return None
    found = [(int(a), int(b)) for a, b in _RANGE.findall(m.group(2) or "")]
    return [(min(a, b), max(a, b)) for a, b in found] or None


def range_from_clips(clips: list[dict]) -> dict:
    """clips: [{"name", "flags" (body_check flags of the clip), "move_cm" ({part: cm})}]. For each soft measure the
    largest value any clip shows, with that clip and its frames; for each part the largest move in any clip."""
    rng: dict[str, dict] = {}
    moves: dict[str, float] = {}
    for c in clips:
        for fl in c.get("flags") or []:
            m, v = fl.get("measure"), fl.get("value")
            if m in SOFT and v is not None and v > rng.get(m, {}).get("max", float("-inf")):
                rng[m] = {"max": v, "clip": c["name"], "frames": fl.get("frames")}
        for part, cm in (c.get("move_cm") or {}).items():
            moves[part] = max(moves.get(part, 0.0), cm)
    return {"range": rng, "move_cm": moves, "clips": [c["name"] for c in clips]}


def _in_ranges(frames, ranges) -> bool:
    if ranges is None:
        return True
    a, b = (frames or [None, None])[:2]
    if a is None:
        return False
    return any(a <= hi and b >= lo for lo, hi in ranges)


def apply(flags: list[dict], style: dict | None, reg: str | None, ranges: list | None = None) -> dict:
    """Mark the soft flags the style range or the register makes notes. Changes flags in place; returns a summary.
    ranges: the pushed beats (pushed_ranges); None means the whole shot."""
    rng = (style or {}).get("range") or {}
    notes = faults = 0
    for fl in flags:
        m = fl.get("measure")
        if m not in SOFT:
            fl["rule"] = "hard"
            faults += 1
            continue
        fl["rule"] = "soft"
        r = rng.get(m)
        if r is not None and fl.get("value") is not None and fl["value"] <= r["max"] * (1 + MARGIN):
            fl["inside_style"] = True
            fl["style_clip"] = r["clip"]
            fl["note"] = True
        elif reg == "pushed" and m not in PUSH_EXEMPT and _in_ranges(fl.get("frames"), ranges):
            fl["note"] = True
        if fl.get("note"):
            notes += 1
        else:
            faults += 1
    return {"register": (reg or "realistic (no Register line in PLAN.md)")
            + (f" in f{', f'.join(f'{a}-{b}' for a, b in ranges)}" if reg == "pushed" and ranges else ""),
            "style_range": bool(rng), "notes": notes, "faults": faults}
