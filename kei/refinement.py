"""Refinement depth: how much each pass changes the motion, and whether it is animated or sampled.

In the heavy_lift benchmark, later passes barely changed the motion (GPT p3-p7 moved joints 0.1-1.1 mm on average,
and p8 was identical to p7), and one seat keyed every frame with auto tangents from p2 on, which its own review called
animating by sampling (WFL26). Kei measures each pass against the one before (blocking for p1) on its baked joints
and writes out_<pass>/refinement.json. Two things are gate misses at the passes stage:

  a pass that changes nothing   no joint moves more than SAME_MM on any frame from the pass before: it is a copy.
  a sampled pass                keys on more than SAMPLED of its frames (on a shot of MIN_FRAMES or more): the motion
                                is sampled, not animated. Keep the keys on poses and breakdowns; shape the rest with
                                tangents.

Every pass's numbers (keys, keyed share, mean and largest joint change, frames that changed) go to the critics too.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from kei.sample import ShotError, bake, check_shot, normalize_keys, read_json

SAME_MM = 1.0        # mm: a pass whose joints all stay this close to the pass before is the same motion
CHANGED_MM = 2.0     # mm: a frame where any joint moves this much changed
SAMPLED = 0.9        # share of the frames keyed: over it, the pass is sampled
MIN_FRAMES = 60       # a short cycle may key most frames: the approved kei walk (29 frames) keys 25


def _passes(shot_dir: Path) -> list[str]:
    ns = sorted(int(m.group(1)) for p in Path(shot_dir).glob("out_p*")
                if (m := re.fullmatch(r"out_p(\d+)", p.name)) and (p / "shot.json").is_file())
    return [f"p{n}" for n in ns]


def _joints(shot_dir: Path, name: str) -> tuple[dict, list[dict]] | None:
    try:
        shot = read_json(Path(shot_dir) / f"out_{name}" / "shot.json", "shot")
        check_shot(shot)
        return shot, bake(shot, "step" if name == "blocking" else "spline")
    except (ShotError, OSError, ValueError):
        return None


def _delta(a: list[dict], b: list[dict]) -> dict:
    n = min(len(a), len(b))
    total, count, top, changed = 0.0, 0, 0.0, 0
    for i in range(n):
        ja, jb = a[i]["joints"], b[i]["joints"]
        worst = 0.0
        for k, p in jb.items():
            q = ja.get(k)
            if q is None:
                continue
            d = math.dist(p, q) * 1000
            total += d
            count += 1
            worst = max(worst, d)
        top = max(top, worst)
        changed += worst >= CHANGED_MM
    return {"mean_mm": round(total / count, 2) if count else 0.0, "max_mm": round(top, 2), "frames_changed": changed}


def measure(shot_dir: Path) -> list[dict]:
    """One row per pass, oldest first: keys, keyed share and the change from the pass before."""
    rows, prev = [], _joints(shot_dir, "blocking")
    prev_name = "blocking" if prev else None
    for name in _passes(shot_dir):
        cur = _joints(shot_dir, name)
        if cur is None:
            continue
        shot, frames = cur
        keyed = {int(k["f"]) for k in normalize_keys(shot) if float(k["f"]).is_integer()}
        row = {"pass": name, "keys": len(keyed), "frames": len(frames),
               "keyed_share": round(len(keyed) / max(1, len(frames)), 2)}
        if prev is not None:
            row["from"] = prev_name
            row.update(_delta(prev[1], frames))
        rows.append(row)
        prev, prev_name = cur, name
    return rows


def refinement_misses(shot_dir: Path) -> list[str]:
    """The gate misses of the newest pass, and out_<pass>/refinement.json written for the critics."""
    rows = measure(shot_dir)
    if not rows:
        return []
    last = rows[-1]
    out = Path(shot_dir) / f"out_{last['pass']}" / "refinement.json"
    out.write_text(json.dumps({"tool": "kei refinement", "passes": rows}, indent=1), encoding="utf-8")
    misses = []
    if last.get("from", "blocking") != "blocking" and last.get("max_mm", SAME_MM + 1) < SAME_MM:
        misses.append(f"P9 out_{last['pass']} is the same motion as out_{last['from']} (no joint moves more than "
                      f"{SAME_MM:g} mm): a pass that changes nothing is not a pass. Refine it, or stop making passes")
    if last["frames"] >= MIN_FRAMES and last["keyed_share"] > SAMPLED:
        misses.append(f"P9 out_{last['pass']} keys {last['keys']} of its {last['frames']} frames: the motion is "
                      f"sampled, not animated (WFL26). Keep keys on the poses and breakdowns and shape the rest with "
                      f"tangents")
    return misses
