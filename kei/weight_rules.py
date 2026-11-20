"""The book's heavy-lift rules, measured. Only an object with mass_kg at or over HEAVY_KG is judged; all are soft flags.

  hinge_deg        while a hand-held heavy load rises, the trunk pitches forward over HINGE_DEG with the knees
                   straighter than STRAIGHT_KNEE_DEG: a lift from the back on straight legs, never from the legs.
  hips_forward_m   while a held heavy load sits more than AHEAD_M in front of the feet, the pelvis is not behind the
                   middle of the support: nothing counterweighs the load (WGT22, the seesaw of mass about the support).
  low_point_frames at a heavy pick-up or set-down (an attach or let-go frame), the pelvis spends fewer than LOW_FRAMES
                   frames within LOW_BAND of its lowest point there: the heavy bottom is a frame, not a phase (WGT12).
  load_accel_g     the held load's acceleration over LOAD_ACCEL_G: a heavy mass that starts or stops at once (WGT18).
"""
from __future__ import annotations

import math

HEAVY_KG = 15.0
HINGE_DEG = 35.0
STRAIGHT_KNEE_DEG = 25.0
AHEAD_M = 0.25
LOW_FRAMES = 3
LOW_BAND = 0.01
LOAD_ACCEL_G = 1.5
LOW_LOOK = 6     # frames either side of a pick-up or set-down searched for the lowest pelvis


def _knee(j: dict, s: str) -> float:
    a, b, c = j[f"thigh_{s}"], j[f"calf_{s}"], j[f"foot_{s}"]
    u = [a[i] - b[i] for i in range(3)]
    w = [c[i] - b[i] for i in range(3)]
    d = sum(u[i] * w[i] for i in range(3)) / ((math.hypot(*u) * math.hypot(*w)) or 1.0)
    return 180.0 - math.degrees(math.acos(max(-1.0, min(1.0, d))))


def _pitch(j: dict) -> float:
    """The trunk's angle from vertical, pelvis to neck, in degrees."""
    v = [j["neck_01"][i] - j["pelvis"][i] for i in range(3)]
    return math.degrees(math.acos(max(-1.0, min(1.0, v[1] / (math.hypot(*v) or 1.0)))))


def _runs(fs):
    out = []
    for f in fs:
        if out and f == out[-1][1] + 1:
            out[-1][1] = f
        else:
            out.append([f, f])
    return out


def weight_flags(shot: dict, frames: list[dict], k: float = 1.0, contact_h: float = 0.02) -> list[dict]:
    from kei.body_check import SOLE
    from kei.objects import read_objects, track
    flags = []
    fps = float(shot.get("fps") or 24)
    for o in read_objects(shot):
        if not isinstance(o.get("mass_kg"), (int, float)) or o["mass_kg"] < HEAVY_KG:
            continue
        t = track(o, frames)
        held = [h is not None for _, h in t]
        ys = [c[1] for c, _ in t]
        hinge, forward, jerk = [], [], []
        for i, fr in enumerate(frames):
            if not held[i]:
                continue
            j = fr["joints"]
            if 0 < i and ys[i] > ys[i - 1] + 0.002 * k:
                if _pitch(j) > HINGE_DEG and max(_knee(j, "l"), _knee(j, "r")) < STRAIGHT_KNEE_DEG:
                    hinge.append(fr["f"])
            feet = [j[p.format(s=s)] for s in "lr" for p in SOLE if j[p.format(s=s)][1] <= contact_h]
            if feet:
                mid = (sum(p[2] for p in feet) / len(feet))
                front = max(p[2] for p in feet)
                if t[i][0][2] - front > AHEAD_M * k and j["pelvis"][2] >= mid:
                    forward.append(fr["f"])
            if 0 < i < len(frames) - 1 and held[i - 1] and held[i + 1]:
                a = [(t[i + 1][0][n] - 2 * t[i][0][n] + t[i - 1][0][n]) * fps * fps for n in range(3)]
                if math.sqrt(sum(x * x for x in a)) / 9.81 > LOAD_ACCEL_G:
                    jerk.append(fr["f"])
        name = o["name"]
        for a, b in _runs(hinge):
            flags.append({"check": "weight", "part": name, "frames": [a, b], "measure": "hinge_deg",
                          "value": HINGE_DEG, "what": f"the {name} rises while the trunk hinges forward on straight "
                          f"legs: lift a heavy load with the legs, knees bent, back long"})
        for a, b in _runs(forward):
            flags.append({"check": "weight", "part": name, "frames": [a, b], "measure": "hips_forward_m",
                          "value": AHEAD_M, "what": f"the {name} is held well in front of the feet and the hips do "
                          f"not go back to counterweigh it"})
        for a, b in _runs(jerk):
            flags.append({"check": "weight", "part": name, "frames": [a, b], "measure": "load_accel_g",
                          "value": LOAD_ACCEL_G, "what": f"the {name} ({o['mass_kg']:g} kg) speeds up or stops "
                          f"over {LOAD_ACCEL_G} g: a heavy mass eases in and out of every move"})
        for e in o["attach"]:
            idx = next((i for i, fr in enumerate(frames) if fr["f"] == e["f"]), None)
            if idx is None:
                continue
            lo, hi = max(0, idx - LOW_LOOK), min(len(frames), idx + LOW_LOOK + 1)
            ph = [frames[i]["joints"]["pelvis"][1] for i in range(lo, hi)]
            bottom = min(ph)
            near = sum(1 for y in ph if y <= bottom + LOW_BAND * k)
            if near < LOW_FRAMES:
                kind = "set-down" if e["to"] == "floor" else "pick-up"
                flags.append({"check": "weight", "part": name, "frames": [e["f"], e["f"]],
                              "measure": "low_point_frames", "value": near,
                              "what": f"at the {name}'s {kind} (f{e['f']}) the hips touch their lowest for "
                                      f"{near} frame(s): a heavy low point settles, holds and pushes off over "
                                      f"{LOW_FRAMES} or more"})
    return flags
