"""Hand presets: the finger channel values of six common hand shapes.

A value list is the rig's fingersL or fingersR channel: [thumb curl, thumb oppose, index curl, index spread, middle
curl, middle spread, ring curl, ring spread, pinky curl, pinky spread], in radians. A curl splits over the knuckle,
the middle joint and the tip in the ratio 1 : 2 : 1.5 (the measured relaxed hand: knuckle 15 to 21 deg, middle joint
33 to 40, tip 25 to 31).

  relaxed   the hand at rest: a soft cascade, the pinky curled most
  open      flat and fanned
  fist      every finger closed onto the palm, the thumb across it
  point     the index straight, the others in a fist
  ok        the index tip meets the thumb tip, the other three loose
  palm-up   the open, softly cupped fingers of an offering hand; turning the palm up is the forearm's job
            (elbowL or elbowR pron), not the fingers'
"""
from __future__ import annotations

from kei.rig import FINGER_POSE

PRESETS = {
    "relaxed": FINGER_POSE["fingersR"],
    "open": [0.0, 0.0, 0.0, 0.25, 0.0, 0.25, 0.0, 0.25, 0.0, 0.25],
    "fist": [1.0, 1.1, 4.2, 0.0, 4.2, 0.0, 4.2, 0.0, 4.2, 0.0],
    "point": [1.0, 1.1, 0.0, 0.0, 4.2, 0.0, 4.2, 0.0, 4.2, 0.0],
    "ok": [0.0, 0.8, 2.2, 0.2, 0.5, 0.1, 0.7, 0.1, 0.9, 0.1],
    "palm-up": [0.15, 0.1, 0.55, 0.1, 0.65, 0.1, 0.75, 0.1, 0.85, 0.1],
}


def preset(name: str) -> list[float]:
    """The ten finger values of a preset, as floats."""
    if name not in PRESETS:
        raise ValueError(f"no hand preset {name!r}: use one of {', '.join(PRESETS)}")
    return [float(v) for v in PRESETS[name]]


def hand_pose(name: str, side: str = "both") -> dict[str, list[float]]:
    """The channels that put one hand (side "L" or "R") or both in a preset."""
    sides = {"L": ("L",), "R": ("R",), "both": ("L", "R")}
    if side not in sides:
        raise ValueError(f"side is L, R or both, not {side!r}")
    return {f"fingers{s}": preset(name) for s in sides[side]}
