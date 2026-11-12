"""The hands and toes of an Unreal character, read back with the body so Kei can judge them itself.

DETAIL_BONES: the finger chains (metacarpal, 01, 02, 03; the thumb 01, 02, 03) and the toes (01, 02) of the Unreal
mannequin, both sides. A character without them simply has none: the readback asks, and the rig says which are missing.

measure(frames, rest) -> the report written to out_<pass>/hands_toes.json
  frames: [{"f", "bones": {name: (x, y, z)}}] in Kei's metres, Y up; rest: the same bones at the rig's rest pose
  (every control at its initial value, never the frame the editor happens to show).
  For every finger joint, its CURL in degrees on every frame: how far the joint bends, signed against the way the rest
  pose bends it. The mannequin's rest hand is a relaxed curl, so a positive curl closes the finger toward the palm and
  a negative curl bends it backward past straight-from-rest. For every toe, its LIFT in degrees: the toe's pitch
  against the foot (ball to toe against ankle to ball), minus the same angle at rest, positive when the toes rise.
  The summary gives each part's range over the pass and flags a finger bent backward more than BACKWARD_DEG, or a toe
  pressed down more than PRESSED_DEG: the signs a wrong control direction leaves.
"""
from __future__ import annotations

import math

FINGERS = ("index", "middle", "ring", "pinky")
TOES = ("bigtoe", "indextoe", "middletoe", "ringtoe", "littletoe")
BACKWARD_DEG = 5.0     # a finger joint bent this far backward from its rest curl is a wrong sign, not a pose
PRESSED_DEG = 10.0     # toes bent down this far below rest: a flick in the air, toes digging in on the floor
ON_FLOOR_M = 0.02      # a toe tip this close to the floor (Kei's y = 0) counts as on the floor


def _chain(side: str) -> dict[str, list[str]]:
    out = {f: [f"{f}_metacarpal_{side}", f"{f}_01_{side}", f"{f}_02_{side}", f"{f}_03_{side}"] for f in FINGERS}
    out["thumb"] = [f"thumb_01_{side}", f"thumb_02_{side}", f"thumb_03_{side}"]
    return out


DETAIL_BONES: tuple[str, ...] = tuple(
    [b for s in "lr" for chain in _chain(s).values() for b in chain]
    + [f"{t}_{n}_{s}" for s in "lr" for t in TOES for n in ("01", "02")])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _len(a):
    return math.sqrt(_dot(a, a))


def _angle(u, v) -> float:
    n = _len(u) * _len(v)
    if n < 1e-12:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, _dot(u, v) / n))))


def _bend(bones, a, b, c):
    """The bend at b (degrees) and its axis, or None when a bone is missing."""
    if a not in bones or b not in bones or c not in bones:
        return None
    u, v = _sub(bones[b], bones[a]), _sub(bones[c], bones[b])
    return _angle(u, v), _cross(u, v)


def _curl(bones, rest, a, b, c) -> float | None:
    now, ref = _bend(bones, a, b, c), _bend(rest, a, b, c)
    if now is None or ref is None:
        return None
    angle, axis = now
    _r, rest_axis = ref
    sign = -1.0 if _dot(axis, rest_axis) < 0 and angle > 0.5 else 1.0
    return round(sign * angle, 2)


def _pitch(v) -> float:
    return math.degrees(math.atan2(v[1], math.hypot(v[0], v[2])))


def _lift(bones, rest, side, toe) -> float | None:
    names = (f"foot_{side}", f"ball_{side}", f"{toe}_01_{side}", f"{toe}_02_{side}")
    if not all(n in bones and n in rest for n in names):
        return None
    foot, ball, t1, t2 = (bones[n] for n in names)
    rf, rb, r1, r2 = (rest[n] for n in names)
    now = _pitch(_sub(t2, t1)) - _pitch(_sub(ball, foot))
    then = _pitch(_sub(r2, r1)) - _pitch(_sub(rb, rf))
    return round(now - then, 2)


def joints_of(chain: list[str]) -> list[tuple[str, str, str, str]]:
    """(label, a, b, c) for each measurable joint of a chain: the joint at b, between a and c."""
    return [(chain[i].rsplit("_", 1)[0], chain[i - 1], chain[i], chain[i + 1]) for i in range(1, len(chain) - 1)]


def measure(frames: list[dict], rest: dict) -> dict:
    curls: dict[str, list] = {}
    lifts: dict[str, list] = {}
    for fr in frames:
        bones = fr["bones"]
        for s in "lr":
            for chain in _chain(s).values():
                for label, a, b, c in joints_of(chain):
                    v = _curl(bones, rest, a, b, c)
                    if v is not None:
                        curls.setdefault(f"{label}_{s}", []).append([fr["f"], v])
            for toe in TOES:
                v = _lift(bones, rest, s, toe)
                if v is not None:
                    tip = bones.get(f"{toe}_02_{s}")
                    lifts.setdefault(f"{toe}_{s}", []).append([fr["f"], v, bool(tip and tip[1] <= ON_FLOOR_M)])
    flags = []
    for name, rows in curls.items():
        bad = [f for f, v in rows if v < -BACKWARD_DEG]
        if bad:
            flags.append({"part": name, "frames": [bad[0], bad[-1]],
                          "what": f"bends backward up to {-min(v for _f, v in rows):.1f} deg past its rest curl: the "
                                  "control's sign may be the wrong way (a relaxed finger curls toward the palm)"})
    for name, rows in lifts.items():
        bad = [(f, on) for f, v, on in rows if v < -PRESSED_DEG]
        if bad:
            low = -min(r[1] for r in rows)
            where = ("on the floor: the toes dig in" if any(on for _f, on in bad)
                     else "with the foot in the air: a flick down before they lift")
            flags.append({"part": name, "frames": [bad[0][0], bad[-1][0]],
                          "what": f"bends down up to {low:.1f} deg below rest, {where}"})
    span = lambda rows: [min(r[1] for r in rows), max(r[1] for r in rows)]
    return {
        "units": "degrees; curl > 0 closes a finger toward the palm (the rest hand's own curl direction), < 0 bends "
                 "it backward; lift > 0 raises the toes against the foot, from the rest pose; each lift row is [frame, lift, toe tip on the floor]",
        "summary": {"curl_range": {k: span(v) for k, v in sorted(curls.items())},
                    "lift_range": {k: span(v) for k, v in sorted(lifts.items())}},
        "flags": flags,
        "curl": curls, "lift": lifts,
    }
