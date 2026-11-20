"""Checks the heavy_lift agents wrote for themselves and marked owed to Kei: jolts and arm targets out of reach.

  jolt          the pelvis or the centre of mass accelerates harder than JOLT_G times gravity on a frame, away from
                a contact: a body does not jump like that (the critics found a pelvis jolt of 9.7 g). Soft: a style
                range can allow one, a pushed register cannot.
  arm reach     an arm's IK target (ikL, ikR at full weight) lies more than REACH beyond where the wrist gets: the
                arm stops short of it, and the hand misses what it reaches for. Hard, as the legs' reach is.

A one-frame jump of a hand at an IK to FK hand-off shows as a spacing pop (kei.arc_check).
"""
from __future__ import annotations

import math

G = 9.81
JOLT_G = 4.0
JOLT_PARTS = ("pelvis", "com")
REACH = 0.01          # m
FULL = 0.99           # an IK weight at or over this is a full hold of the target


def _runs(fs: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for f in fs:
        if out and f == out[-1][1] + 1:
            out[-1][1] = f
        else:
            out.append([f, f])
    return out


def motion_flags(frames: list[dict], fps: float, k: float = 1.0) -> list[dict]:
    flags = []
    for part in JOLT_PARTS:
        hits, top = [], {}
        for i in range(1, len(frames) - 1):
            a, b, c = (frames[n]["joints"].get(part) for n in (i - 1, i, i + 1))
            if a is None or b is None or c is None:
                continue
            acc = math.sqrt(sum((c[n] - 2 * b[n] + a[n]) ** 2 for n in range(3))) * fps * fps / k
            if acc > JOLT_G * G:
                hits.append(frames[i]["f"])
                top[frames[i]["f"]] = acc / G
        for lo, hi in _runs(hits):
            g = max(top[f] for f in range(lo, hi + 1))
            flags.append({"check": "jolt", "part": part, "frames": [lo, hi], "measure": "jolt_g", "value": round(g, 1),
                          "what": f"the {part} accelerates at up to {g:.1f} g over f{lo}-{hi}, over {JOLT_G:g} g: a "
                                  f"jolt no body makes. Ease the spacing into and out of it"})
    for side, ch in (("l", "ikL"), ("r", "ikR")):
        miss = {}
        for fr in frames:
            pose, j = fr.get("pose"), fr["joints"]
            t = pose.get(ch) if isinstance(pose, dict) else None
            if not (isinstance(t, (list, tuple)) and len(t) >= 4 and t[3] >= FULL and f"hand_{side}" in j):
                continue
            gap = math.dist(t[:3], j[f"hand_{side}"])
            if gap > REACH * k:
                miss[fr["f"]] = gap
        for lo, hi in _runs(sorted(miss)):
            gap = max(miss[f] for f in range(lo, hi + 1))
            flags.append({"check": "joint_ranges", "side": side, "frames": [lo, hi],
                          "what": f"the {'left' if side == 'l' else 'right'} wrist stops up to {gap * 100:.1f} cm short "
                                  f"of its {ch} target: the arm cannot reach it. Bring the target in, or move the "
                                  f"body toward it"})
    return flags
