"""Basic posing checks on the joints of a pass: what a person sees at a glance and a line drawing hides.

posing_flags(frames, knee_bend, elbow_bend, k, contact_h) -> (flags, thresholds)
  frames: [{"f", "joints": {name: (x, y, z)}}] in metres, y up, x across the body, z forward.
  stance        both feet planted and the feet farther apart across the body than STANCE_MAX hip widths: an A-frame,
                not a stance.
  locked_knees  both feet planted and both knees straighter than LOCKED_KNEE_DEG for LOCKED_RUN frames or more: a
                character standing on stilts (a walk's one straight leg at contact is never both).
  neck_kink     the neck bends between its segments (spine to neck, neck to head) by more than NECK_BEND: a break at
                the neck, not a nod.
  straight_arm  an elbow straighter than ARM_STRAIGHT_DEG for ARM_RUN frames or more.
  no_change     the whole body hardly moves in a pass of STILL_FRAMES frames or more (the mean distance of each joint from its own mean position
                stays under STILL x height): two keys that look the same.
These are the signs of a bad pose, found at once, before a person has to look. A flag is fixed at a key, or declared
with a reason, like every other flag. They are numbers: they never replace looking at the character.
"""
from __future__ import annotations

import math

STANCE_MAX = 2.2        # feet apart across the body, in hip widths, with both feet planted
STANCE_RUN = 6          # frames
LOCKED_KNEE_DEG = 4.0   # a knee bend below this is a locked knee
LOCKED_RUN = 8          # frames with both knees locked and both feet planted
NECK_BEND = 30.0        # degrees between the neck's segments
ARM_STRAIGHT_DEG = 4.0  # an elbow bend below this is a dead straight arm
ARM_RUN = 20            # frames
STILL_FRAMES = 24      # a pass shorter than this (a held test pose) is not judged for movement
STILL = 0.02            # of the character's height: mean excursion of a joint below this is a body that does not move
SOLE = ("heel_{s}", "ball_{s}", "ball_{s}_tip")


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _len(a) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _angle(a, b) -> float:
    n = _len(a) * _len(b)
    if n < 1e-12:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) / n))))


def _runs(frames: list[int]) -> list[tuple[int, int]]:
    out, start, prev = [], None, None
    for f in frames:
        if start is None:
            start = prev = f
        elif f == prev + 1:
            prev = f
        else:
            out.append((start, prev))
            start = prev = f
    if start is not None:
        out.append((start, prev))
    return out


def _planted(j: dict, s: str, contact_h: float) -> bool:
    return min(j[p.format(s=s)][1] for p in SOLE) <= contact_h


def posing_flags(frames: list[dict], knee_bend: dict, elbow_bend: dict, k: float, contact_h: float):
    thresholds = {
        "stance_max_hip_widths": {"value": STANCE_MAX, "source": f"STANCE_MAX for {STANCE_RUN}+ frames, both feet planted"},
        "locked_knee_deg": {"value": LOCKED_KNEE_DEG, "source": f"LOCKED_KNEE_DEG for {LOCKED_RUN}+ frames, both knees"},
        "neck_bend_deg": {"value": NECK_BEND, "source": "NECK_BEND between the neck's segments"},
        "straight_arm_deg": {"value": ARM_STRAIGHT_DEG, "source": f"ARM_STRAIGHT_DEG for {ARM_RUN}+ frames"},
        "still_m": {"value": round(STILL * 1.71 * k, 4), "source": f"STILL {STILL} of the height: the mean excursion"},
    }
    flags: list[dict] = []
    if not frames:
        return flags, thresholds
    fs = [fr["f"] for fr in frames]
    both = [_planted(fr["joints"], "l", contact_h) and _planted(fr["joints"], "r", contact_h) for fr in frames]

    wide = []
    for fr, on in zip(frames, both):
        j = fr["joints"]
        hips = abs(j["thigh_l"][0] - j["thigh_r"][0]) or 1e-9
        if on and abs(j["foot_l"][0] - j["foot_r"][0]) / hips > STANCE_MAX:
            wide.append(fr["f"])
    for a, b in _runs(wide):
        if b - a + 1 >= STANCE_RUN:
            flags.append({"check": "posing", "frames": [a, b], "what":
                          f"the feet are more than {STANCE_MAX:g} hip widths apart across the body with both planted: "
                          "an A-frame, not a stance"})

    locked = [f for f, on, bl, br in zip(fs, both, knee_bend["l"], knee_bend["r"])
              if on and bl < LOCKED_KNEE_DEG and br < LOCKED_KNEE_DEG]
    for a, b in _runs(locked):
        if b - a + 1 >= LOCKED_RUN:
            flags.append({"check": "posing", "frames": [a, b], "what":
                          f"both knees are straighter than {LOCKED_KNEE_DEG:g} deg with both feet planted: locked "
                          "knees, the character stands on stilts"})

    kinked = []
    worst = {}
    for fr in frames:
        j = fr["joints"]
        up = _angle(_sub(j["neck_01"], j["spine_05"]), _sub(j["neck_02"], j["neck_01"]))
        head = _angle(_sub(j["neck_02"], j["neck_01"]), _sub(j["head"], j["neck_02"]))
        bend = max(up, head)
        if bend > NECK_BEND:
            kinked.append(fr["f"])
            worst[fr["f"]] = bend
    for a, b in _runs(kinked):
        flags.append({"check": "posing", "frames": [a, b], "what":
                      f"the neck breaks by up to {max(worst[f] for f in range(a, b + 1) if f in worst):.0f} deg "
                      f"between its segments (past {NECK_BEND:g}): a kink, not a nod"})

    for s in "lr":
        straight = [f for f, e in zip(fs, elbow_bend[s]) if e < ARM_STRAIGHT_DEG]
        for a, b in _runs(straight):
            if b - a + 1 >= ARM_RUN:
                flags.append({"check": "posing", "side": s, "frames": [a, b], "what":
                              f"the {s} arm is dead straight (elbow under {ARM_STRAIGHT_DEG:g} deg) for "
                              f"{b - a + 1} frames: bend it a little"})

    if len(frames) >= STILL_FRAMES:
        names = sorted(frames[0]["joints"])
        total = 0.0
        for n in names:
            pts = [fr["joints"][n] for fr in frames]
            mean = tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))
            total += sum(_len(_sub(p, mean)) for p in pts) / len(pts)
        mean_excursion = total / max(1, len(names))
        if mean_excursion < STILL * 1.71 * k:
            flags.append({"check": "posing", "frames": [fs[0], fs[-1]], "what":
                          f"the body hardly moves in the whole pass (each joint stays within "
                          f"{mean_excursion * 100:.1f} cm of its mean position on average): the keys look the same"})
    return flags, thresholds
