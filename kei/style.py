"""A character's style range, from their own shipped animation, and the register the author sets for a shot.

Kei's body checks are realism rules. A stylized character breaks some of them on purpose in every clip they ship, and
a critic that reads those flags as faults pushes the pose back toward textbook mechanics. So:

  hard rules   stay faults whatever the style: contacts, hover, foot slide, a knee bending backward, reach, a knee
               snap, locked knees, a body that does not move. A flag of a hard rule has no "measure".
  soft rules   balance, trunk lean, knee and elbow range, arc kinks, a wide stance, a neck bend, a straight arm. Each
               soft flag carries a "measure" and a "value" (kei.body_check, kei.posing_check).

rig/style.json (kei unreal style) holds, for each soft measure, the furthest the character's own clips go, the clip
that shows it, and the largest move of each part (the exaggeration check reads that). A soft flag at or under that
value (plus MARGIN) is marked "inside_style": a note with the clip that shows it, not a fault.

PLAN.md may carry a line "Register: realistic", "Register: stylized" or "Register: pushed", set by the author, never
guessed. Realistic (and no line) judges soft flags as faults unless they are inside the style range. Stylized does
the same, and says so. Pushed turns every soft flag into a note, even outside the range.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REGISTERS = ("realistic", "stylized", "pushed")
SOFT = ("balance_outside_m", "balance_behind_m", "trunk_lean_back_deg", "knee_max_deg", "elbow_max_deg",
        "arc_kink_deg", "stance_hip_widths", "neck_bend_deg", "straight_arm_frames")
MARGIN = 0.05       # a soft value up to 5% past the furthest her clips go is still hers: the same pose, read again
_REGISTER = re.compile(r"^[ \t>*+-]*\**register\**[ \t]*:[ \t]*\**[ \t]*([a-z]+)", re.I | re.M)


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


def apply(flags: list[dict], style: dict | None, reg: str | None) -> dict:
    """Mark the soft flags the style range or the register makes notes. Changes flags in place; returns a summary."""
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
        elif reg == "pushed":
            fl["note"] = True
        if fl.get("note"):
            notes += 1
        else:
            faults += 1
    return {"register": reg or "realistic (no Register line in PLAN.md)",
            "style_range": bool(rng), "notes": notes, "faults": faults}
