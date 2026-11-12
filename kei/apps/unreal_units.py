"""The one pair of functions that converts between Unreal and Kei. Every value that crosses the adapter goes through them.

Unreal (rig space, as the Control Rig reports bones): centimetres, Z up, left-handed. Which way a character faces
depends on its mesh: the Third Person mannequin faces +Y with its left side on +X.
Kei: metres, Y up, X to the character's right, Z forward (left-handed), the world the checks measure in.

So the conversion takes a Frame, derived once per shot from the rest pose (frame_from_rest): L is the horizontal unit
vector from the character's right thigh to its left thigh, U is +Z, F = U x L is forward. Then
  Kei = (-(p . L), p . U, p . F) / 100.
The mannequin's frame (left +X, forward +Y) turns Unreal (10, 20, 30) cm into Kei (-0.1, 0.3, 0.2) m. A character that
faces +X (its left on -Y) turns the same point into (0.2, 0.3, 0.1) m. The map is a proper rotation of the axes plus a
scale, so a point never mirrors and a round trip is exact to float precision.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

CM_PER_M = 100.0

Vec = tuple[float, float, float]


@dataclass(frozen=True)
class Frame:
    left: Vec
    forward: Vec

    def as_dict(self) -> dict:
        return {"left": list(self.left), "forward": list(self.forward)}

    @staticmethod
    def from_dict(d: dict) -> "Frame":
        return Frame(tuple(d["left"]), tuple(d["forward"]))


MANNEQUIN = Frame((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))     # left +X, forward +Y, up +Z


def frame_from_rest(thigh_l: Vec, thigh_r: Vec) -> Frame:
    """The character's frame from its rest pose: left is horizontal(thigh_l - thigh_r), forward is up x left."""
    dx, dy = thigh_l[0] - thigh_r[0], thigh_l[1] - thigh_r[1]
    n = math.hypot(dx, dy)
    if n < 1e-6:
        raise ValueError("the two thighs are on one vertical line, so the character's facing cannot be found")
    left = (dx / n, dy / n, 0.0)
    return Frame(left, (-left[1], left[0], 0.0))      # U x L with U = +Z


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def ue_to_kei(p: Vec, frame: Frame) -> Vec:
    """A point in Unreal centimetres to Kei metres."""
    return (-_dot(p, frame.left) / CM_PER_M, p[2] / CM_PER_M, _dot(p, frame.forward) / CM_PER_M)


def kei_to_ue(p: Vec, frame: Frame) -> Vec:
    """A point in Kei metres to Unreal centimetres."""
    x, y, z = p[0] * CM_PER_M, p[1] * CM_PER_M, p[2] * CM_PER_M
    return tuple(-x * frame.left[i] + z * frame.forward[i] + (y if i == 2 else 0.0) for i in range(3))


def ue_dir_to_kei(d: Vec, frame: Frame) -> Vec:
    """A direction or an axis in Unreal to the same in Kei: the same rotation, no scale."""
    return (-_dot(d, frame.left), d[2], _dot(d, frame.forward))


def kei_dir_to_ue(d: Vec, frame: Frame) -> Vec:
    return tuple(-d[0] * frame.left[i] + d[2] * frame.forward[i] + (d[1] if i == 2 else 0.0) for i in range(3))
