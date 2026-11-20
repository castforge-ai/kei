"""Rotation maths for the Maya adapter, shared by Kei's side and Maya's side. Standard library only, so it runs in any
Python, Maya's included.

Matrices are 3 x 3 lists of rows that act on column vectors: a frame's columns are its X, Y and Z axes in the parent.
Maya's rotate order "xyz" turns about x first, then y, then z, each about the parent's axes: R = Rz Ry Rx. The
six orders keep Maya's names and numbers (ORDERS[i] is rotateOrder i).

Kei's world has x on the character's right, y up and z forward; that is a left-handed world. Maya's world is right-
handed with y up, so the character's right is -x there. The adapter mirrors x, the same as the glTF and FBX exports:
a point p becomes D p and a rotation R becomes D R D, with D = diag(-1, 1, 1).
"""
from __future__ import annotations

import math

ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")
_AXIS = {"x": 0, "y": 1, "z": 2}


def identity() -> list[list[float]]:
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def mul(a, b) -> list[list[float]]:
    return [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def transpose(a) -> list[list[float]]:
    return [[a[c][r] for c in range(3)] for r in range(3)]


def apply(a, v) -> tuple[float, float, float]:
    return tuple(sum(a[r][k] * v[k] for k in range(3)) for r in range(3))


def det(a) -> float:
    return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
            + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))


def axis_matrix(axis: str, angle: float) -> list[list[float]]:
    """A turn of angle (radians) about the x, y or z axis, right-handed."""
    c, s = math.cos(angle), math.sin(angle)
    if axis == "x":
        return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]
    if axis == "y":
        return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def euler_matrix(angles, order: str = "xyz") -> list[list[float]]:
    """The rotation of Euler angles (x, y, z in radians) applied in Maya's rotate order."""
    R = identity()
    for ax in order:
        R = mul(axis_matrix(ax, angles[_AXIS[ax]]), R)
    return R


def _wrap(a: float, near: float) -> float:
    return a + 2 * math.pi * round((near - a) / (2 * math.pi))


def matrix_euler(R, order: str = "xyz", near=None) -> list[float]:
    """Euler angles (x, y, z in radians) for rotation R in the rotate order. With near, each angle is the one of its
    360 degree family closest to near's, and of the two Euler solutions the closer one is kept."""
    i, j, k = (_AXIS[a] for a in order)
    s = 1.0 if (i, j, k) in ((0, 1, 2), (1, 2, 0), (2, 0, 1)) else -1.0
    sb = max(-1.0, min(1.0, -s * R[k][i]))
    b = math.asin(sb)
    if math.cos(b) > 1e-9:
        a = math.atan2(s * R[k][j], R[k][k])
        c = math.atan2(s * R[j][i], R[i][i])
    else:                                   # gimbal lock: put the whole turn on the first axis
        c = 0.0
        a = math.atan2(-s * R[j][k], R[j][j])
    out = [0.0, 0.0, 0.0]
    out[i], out[j], out[k] = a, b, c
    if near is None:
        return out
    other = [0.0, 0.0, 0.0]
    other[i], other[j], other[k] = a + math.pi, math.pi - b, c + math.pi
    best = None
    for cand in (out, other):
        w = [_wrap(cand[n], near[n]) for n in range(3)]
        d = sum((w[n] - near[n]) ** 2 for n in range(3))
        if best is None or d < best[0] - 1e-12:
            best = (d, w)
    return best[1]


def mirror_point(p) -> tuple[float, float, float]:
    """A Kei world point in the right-handed world (x mirrored)."""
    return (-p[0], p[1], p[2])


def mirror_matrix(R) -> list[list[float]]:
    """D R D: a Kei world rotation in the right-handed world."""
    sgn = (-1.0, 1.0, 1.0)
    return [[R[r][c] * sgn[r] * sgn[c] for c in range(3)] for r in range(3)]


def frame_columns(frame) -> list[list[float]]:
    """A Kei bone frame (X, Y, Z) as the matrix with those columns."""
    return [[frame[c][r] for c in range(3)] for r in range(3)]


def mirror_frame(frame) -> list[list[float]]:
    """A Kei bone frame (X, Y, Z) as a rotation matrix in the right-handed world."""
    return mirror_matrix(frame_columns(frame))


def local(parent_rot, parent_pos, child_rot, child_pos):
    """The child's translation and rotation in its parent's space."""
    Pt = transpose(parent_rot)
    d = tuple(child_pos[n] - parent_pos[n] for n in range(3))
    return apply(Pt, d), mul(Pt, child_rot)


def clamped_slopes(fs, vs):
    """Kei's clamped spline slopes (value per frame) for one curve's keys, as kei.sample does channel by channel: the
    neighbour slope, flat at a peak, a dip or the edge of a hold, and held within 3x either neighbouring secant, so the
    curve never passes beyond a key (Fritsch-Carlson)."""
    out = []
    n = len(fs)
    for i in range(n):
        fa, va = (fs[i - 1], vs[i - 1]) if i > 0 else (fs[i], vs[i])
        fb, vb = (fs[i + 1], vs[i + 1]) if i + 1 < n else (fs[i], vs[i])
        m = (vb - va) / (fb - fa) if fb > fa else 0.0
        dl = (vs[i] - va) / (fs[i] - fa) if fs[i] > fa else None
        dr = (vb - vs[i]) / (fb - fs[i]) if fb > fs[i] else None
        if dl is not None and dr is not None:
            if dl * dr <= 0:
                out.append(0.0)
                continue
            lim = 3 * min(abs(dl), abs(dr))
        else:
            one = dl if dl is not None else dr
            if not one or m * one <= 0:
                out.append(0.0)
                continue
            lim = 3 * abs(one)
        out.append(math.copysign(min(abs(m), lim), m))
    return out
