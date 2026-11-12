"""Shapes to triangles: each shape of a character becomes a closed mesh in its bone's frame, and a pose places it.

shape_mesh(shape) gives (vertices, normals, triangles) in the bone's frame; the triangles wind counter-clockwise seen
from outside. character_mesh(ch) is every shape's mesh, one Part each; pose_mesh(ch, pose) moves each part rigidly
with its bone. widths(ch) measures the shoulders and the hips at rest.

An imported character (kei import) has bound parts instead of shapes: a rigid part moves with its one bone as a shape
does; a smooth part has a skin, and each of its vertices moves to the weighted sum of where each of its bones would
carry it (linear blend skinning), its normal likewise, then normalised. Imported parts carry shape -1.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from kei.characters import Character, Shape, rest_pose
from kei.rig import skeleton

Vec = tuple[float, float, float]


@dataclass
class Part:
    bone: str
    material: str
    verts: list
    normals: list
    tris: list
    shape: int          # the index of the shape in the character (-1: an imported part)
    skin: list | None = None   # a smooth part: per vertex [(bone, weight, vertex in the bone's frame, normal in it)]
    uvs: list | None = None    # a textured part: per triangle (u0, v0, u1, v1, u2, v2), v from the image's top
    texture: int = 0           # which of the character's textures the uvs read


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    n = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / n, a[1] / n, a[2] / n)


def _segments(r: float) -> int:
    """Segments around a shape of radius r (m): small parts stay light, large ones stay round."""
    return max(8, min(24, int(8 + r * 90)))


def _revolve(profile, centre: Vec, axis: Vec, u: Vec, w: Vec, n: int):
    """A closed surface of revolution. profile: [(along, radius, normal along, normal out)] from pole to pole."""
    verts, normals, tris = [], [], []
    rows = []
    for along, rad, na, nr in profile:
        row = []
        for k in range(n if rad > 1e-12 else 1):
            a = 2 * math.pi * k / n
            out = _add(_mul(u, math.cos(a)), _mul(w, math.sin(a)))
            row.append(len(verts))
            verts.append(_add(centre, _add(_mul(axis, along), _mul(out, rad))))
            normals.append(_norm(_add(_mul(axis, na), _mul(out, nr))))
        rows.append(row)
    for r0, r1 in zip(rows, rows[1:]):
        for k in range(n):
            a, b = r0[k % len(r0)], r0[(k + 1) % len(r0)]
            c, d = r1[k % len(r1)], r1[(k + 1) % len(r1)]
            if len(r0) == 1:
                tris.append((a, d, c))
            elif len(r1) == 1:
                tris.append((a, b, c))
            else:
                tris.append((a, b, d))
                tris.append((a, d, c))
    return _orient(verts, normals, tris)


def _orient(verts, normals, tris):
    """Turn each triangle so it winds counter-clockwise seen from outside (its normals' side)."""
    out = []
    for t in tris:
        a, b, c = (verts[i] for i in t)
        face = _cross(_sub(b, a), _sub(c, a))
        avg = _add(_add(normals[t[0]], normals[t[1]]), normals[t[2]])
        out.append(t if _dot(face, avg) >= 0 else (t[0], t[2], t[1]))
    return verts, normals, out


def _sphere_profile(rings: int):
    return [(-math.cos(math.pi * i / rings), math.sin(math.pi * i / rings), -math.cos(math.pi * i / rings),
             math.sin(math.pi * i / rings)) for i in range(rings + 1)]


def _ellipsoid(c: Vec, r, axes):
    n = _segments(max(r))
    unit = _revolve(_sphere_profile(max(4, n // 2)), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0),
                    (0.0, 0.0, 1.0), n)
    X, Y, Z = axes
    verts = [_add(c, _add(_add(_mul(X, p[0] * r[0]), _mul(Y, p[1] * r[1])), _mul(Z, p[2] * r[2]))) for p in unit[0]]
    normals = [_norm(_add(_add(_mul(X, q[0] / r[0]), _mul(Y, q[1] / r[1])), _mul(Z, q[2] / r[2]))) for q in unit[1]]
    return _orient(verts, normals, unit[2])


def _block(c: Vec, r, axes, power: float, taper):
    """A rounded box: the unit sphere pushed out radially onto |x|^p + |y|^p + |z|^p = 1, scaled by r and tapered.
    The push and the scale keep the sphere's outward winding; the normals are the faces' normals averaged."""
    n = 48                      # flat sides need even rows: a coarse block bends its flat front
    unit_v, _, tris = _revolve(_sphere_profile(n // 2), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0),
                               (0.0, 0.0, 1.0), n)
    X, Y, Z = axes
    verts = []
    for p in unit_v:
        k = (abs(p[0]) ** power + abs(p[1]) ** power + abs(p[2]) ** power) ** (1.0 / power)
        q = (p[0] / k, p[1] / k, p[2] / k)
        lx, ly, lz = q[0] * r[0] * (1 + taper[0] * q[1]), q[1] * r[1], q[2] * r[2] * (1 + taper[1] * q[1])
        verts.append(_add(c, _add(_add(_mul(X, lx), _mul(Y, ly)), _mul(Z, lz))))
    if _dot(X, _cross(Y, Z)) < 0:          # mirrored axes (a left-side copy) turn the winding inside out
        tris = [(t[0], t[2], t[1]) for t in tris]
    acc = [(0.0, 0.0, 0.0)] * len(verts)
    for t in tris:
        a, b, d = (verts[i] for i in t)
        f = _cross(_sub(b, a), _sub(d, a))
        for i in t:
            acc[i] = _add(acc[i], f)
    return verts, [_norm(v) for v in acc], tris


def _capsule(a: Vec, b: Vec, ra: float, rb: float):
    """A tapered capsule: two spheres joined by the cone tangent to both."""
    d = _sub(b, a)
    L = math.sqrt(_dot(d, d))
    axis = _norm(d) if L > 1e-12 else (0.0, 1.0, 0.0)
    h = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _norm(_cross(axis, h))
    w = _cross(axis, u)
    s = max(-0.99, min(0.99, (ra - rb) / L)) if L > 1e-12 else 0.0
    t = math.acos(s)                          # the polar angle (from -axis) where the cone touches both spheres
    n = _segments(max(ra, rb))
    ka = max(3, n // 4)
    kb = max(3, n // 4)
    prof = []
    for i in range(ka + 1):                   # sphere a, from its far pole to the tangent circle
        th = t * i / ka
        prof.append((-ra * math.cos(th), ra * math.sin(th), -math.cos(th), math.sin(th)))
    for i in range(kb + 1):                   # sphere b, from the tangent circle to its far pole
        th = t + (math.pi - t) * i / kb
        prof.append((L - rb * math.cos(th), rb * math.sin(th), -math.cos(th), math.sin(th)))
    return _revolve(prof, a, axis, u, w, n)


def _ring(c: Vec, axes, major: float, minor: float):
    u, axis, w = axes
    n, m = _segments(major), max(6, _segments(minor) // 2 + 4)
    verts, normals, tris = [], [], []
    for i in range(n):
        a = 2 * math.pi * i / n
        out = _add(_mul(u, math.cos(a)), _mul(w, math.sin(a)))
        for j in range(m):
            b = 2 * math.pi * j / m
            nrm = _add(_mul(out, math.cos(b)), _mul(axis, math.sin(b)))
            verts.append(_add(c, _add(_mul(out, major), _mul(nrm, minor))))
            normals.append(nrm)
    for i in range(n):
        for j in range(m):
            p, q = i * m + j, ((i + 1) % n) * m + j
            p2, q2 = i * m + (j + 1) % m, ((i + 1) % n) * m + (j + 1) % m
            tris += [(p, q, q2), (p, q2, p2)]
    return _orient(verts, normals, tris)


# The angular C in front-view units (u to the viewer's right, v up), in a square of side 1 centred on 0: the back
# with its two cut corners, the top bar and the bottom bar with its slanted end, as one outline, counter-clockwise.
STROKE, CUT = 0.27, 0.16
C_OUTLINE = ((-0.5 + CUT, 0.5), (-0.5, 0.5 - CUT), (-0.5, -0.5 + CUT), (-0.5 + CUT, -0.5), (0.5 - STROKE * 0.6, -0.5),
             (0.5, -0.5 + STROKE), (-0.5 + STROKE, -0.5 + STROKE), (-0.5 + STROKE, 0.5 - STROKE),
             (0.5, 0.5 - STROKE), (0.5, 0.5))


def _ears(poly) -> list[tuple[int, int, int]]:
    """Ear clipping of a simple counter-clockwise polygon into triangles of its corner indices."""
    def cross2(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    left, out = list(range(len(poly))), []
    while len(left) > 3:
        for k in range(len(left)):
            i, j, m = left[k - 1], left[k], left[(k + 1) % len(left)]
            a, b, c = poly[i], poly[j], poly[m]
            if cross2(a, b, c) <= 0:
                continue
            if any(cross2(a, b, poly[q]) >= 0 and cross2(b, c, poly[q]) >= 0 and cross2(c, a, poly[q]) >= 0
                   for q in left if q not in (i, j, m)):
                continue
            out.append((i, j, m))
            left.pop(k)
            break
        else:
            raise ValueError("the outline is not a simple counter-clockwise polygon")
    out.append(tuple(left))
    return out


def _mark(c: Vec, axes, size: float, depth: float):
    """The C: a prism of the outline, its front face toward the bone's +Z, the opening toward the bone's -X."""
    X, Y, Z = axes
    verts, normals, tris = [], [], []

    def at(uv, z):
        return _add(c, _add(_add(_mul(X, -uv[0] * size), _mul(Y, uv[1] * size)), _mul(Z, z)))

    ears = _ears(C_OUTLINE)
    for poly in (C_OUTLINE,):
        k = len(poly)
        for z, nrm in ((depth / 2, Z), (-depth / 2, _mul(Z, -1))):     # front and back faces
            base = len(verts)
            for p in poly:
                verts.append(at(p, z))
                normals.append(nrm)
            tris += [(base + i, base + j, base + m) for i, j, m in ears]
        for i in range(k):                                             # the sides, flat
            p, q = poly[i], poly[(i + 1) % k]
            # the outward side of an edge of a counter-clockwise outline is on its right: (dv, -du) in u, v
            du, dv = q[0] - p[0], q[1] - p[1]
            side = _norm(_add(_mul(X, -dv), _mul(Y, -du)))
            base = len(verts)
            for pt in (at(p, depth / 2), at(q, depth / 2), at(q, -depth / 2), at(p, -depth / 2)):
                verts.append(pt)
                normals.append(side)
            tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    return _orient(verts, normals, tris)


def _weld(verts, normals, tris):
    """One vertex per distinct position and normal; the flat sides of the C keep their own corners."""
    index, v2, n2, remap = {}, [], [], []
    for p, q in zip(verts, normals):
        key = tuple(round(x, 9) for x in p) + tuple(round(x, 6) for x in q)
        if key not in index:
            index[key] = len(v2)
            v2.append(p)
            n2.append(q)
        remap.append(index[key])
    return v2, n2, [tuple(remap[i] for i in t) for t in tris if len({remap[i] for i in t}) == 3]


def shape_mesh(s: Shape):
    """(vertices, normals, triangles) of one shape in its bone's frame."""
    if s.kind in ("sphere", "ellipsoid"):
        r = (s.r[0],) * 3 if s.kind == "sphere" else s.r
        m = _ellipsoid(s.c, r, s.axes)
    elif s.kind == "block":
        m = _block(s.c, s.r, s.axes, s.power, s.taper)
    elif s.kind == "capsule":
        m = _capsule(s.a, s.b, s.r[0], s.r[1])
    elif s.kind == "ring":
        m = _ring(s.c, s.axes, s.r[0], s.r[1])
    else:
        m = _mark(s.c, s.axes, s.size, s.depth)
    return _weld(*m)


def _vertex_normals(verts, tris):
    acc = [[0.0, 0.0, 0.0] for _ in verts]
    for a, b, c in tris:
        n = _cross(_sub(verts[b], verts[a]), _sub(verts[c], verts[a]))     # its length weights it by area
        for i in (a, b, c):
            acc[i] = [acc[i][k] + n[k] for k in range(3)]
    out = []
    for n in acc:
        length = math.sqrt(sum(c * c for c in n))
        out.append((n[0] / length, n[1] / length, n[2] / length) if length > 1e-15 else (0.0, 1.0, 0.0))
    return out


def _local(b, v):
    d = _sub(v, b.head)
    return tuple(_dot(d, e) for e in b.frame)


def _local_dir(b, v):
    return tuple(_dot(v, e) for e in b.frame)


def _imported_parts(ch: Character) -> list[Part]:
    B = skeleton(rest_pose(ch), ch.proportions)
    out = []
    for d in ch.parts:
        verts = [tuple(v) for v in d["verts"]]
        tris = [tuple(t) for t in d["tris"]]
        normals = _vertex_normals(verts, tris)
        if d.get("skin"):
            skin = [[(n, w, _local(B[n], v), _local_dir(B[n], nv)) for n, w in vw]
                    for v, nv, vw in zip(verts, normals, d["skin"])]
            out.append(Part(d["bone"], d.get("material", "body"), verts, normals, tris, -1, skin, d.get("uvs"),
                            d.get("texture", 0)))
        else:
            b = B[d["bone"]]
            out.append(Part(d["bone"], d.get("material", "body"), [_local(b, v) for v in verts],
                            [_local_dir(b, n) for n in normals], tris, -1, None, d.get("uvs"), d.get("texture", 0)))
    return out


def character_mesh(ch: Character) -> list[Part]:
    """Every shape's mesh in its bone's frame, one Part each, in the order of the character's shapes; an imported
    character's parts (a rigid part in its bone's frame, a smooth part with its skin)."""
    if getattr(ch, "_mesh", None) is None:
        if ch.parts is not None:
            ch._mesh = _imported_parts(ch)
        else:
            ch._mesh = [Part(s.bone, s.material, *shape_mesh(s), i) for i, s in enumerate(ch.shapes)]
    return ch._mesh


def _skinned(p: Part, B) -> Part:
    verts, normals = [], []
    for vw in p.skin:
        v, n = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        for bone, w, lv, ln in vw:
            b = B[bone]
            (X, Y, Z), h = b.frame, b.head
            for k in range(3):
                v[k] += w * (h[k] + X[k] * lv[0] + Y[k] * lv[1] + Z[k] * lv[2])
                n[k] += w * (X[k] * ln[0] + Y[k] * ln[1] + Z[k] * ln[2])
        length = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) or 1.0
        verts.append(tuple(v))
        normals.append((n[0] / length, n[1] / length, n[2] / length))
    return Part(p.bone, p.material, verts, normals, p.tris, p.shape, p.skin, p.uvs, p.texture)


def pose_mesh(ch: Character, pose: dict, bones=None) -> list[Part]:
    """The parts placed by a pose: every vertex moved rigidly with its bone (normals turned with it)."""
    B = bones or skeleton(pose, ch.proportions)
    out = []
    for p in character_mesh(ch):
        if p.skin is not None:
            out.append(_skinned(p, B))
            continue
        b = B[p.bone]
        (X, Y, Z), h = b.frame, b.head
        verts = [(h[0] + X[0] * v[0] + Y[0] * v[1] + Z[0] * v[2], h[1] + X[1] * v[0] + Y[1] * v[1] + Z[1] * v[2],
                  h[2] + X[2] * v[0] + Y[2] * v[1] + Z[2] * v[2]) for v in p.verts]
        normals = [(X[0] * v[0] + Y[0] * v[1] + Z[0] * v[2], X[1] * v[0] + Y[1] * v[1] + Z[1] * v[2],
                    X[2] * v[0] + Y[2] * v[1] + Z[2] * v[2]) for v in p.normals]
        out.append(Part(p.bone, p.material, verts, normals, p.tris, p.shape, None, p.uvs, p.texture))
    return out


HIP_BONES = ("pelvis", "thigh_l", "thigh_r")
BAND = 0.015          # metres above and below the hip joints


def widths(ch: Character) -> dict:
    """At rest: the shoulder width (between the shoulder joint centres), the hip width (the outer width of the pelvis
    and thighs within BAND of the hip joints' height) and their ratio."""
    pose = rest_pose(ch)
    B = skeleton(pose, ch.proportions)
    shoulder = math.dist(B["upperarm_l"].head, B["upperarm_r"].head)
    y = (B["thigh_l"].head[1] + B["thigh_r"].head[1]) / 2
    xs = [v[0] for p in pose_mesh(ch, pose, B) if p.bone in HIP_BONES for v in p.verts if abs(v[1] - y) <= BAND]
    hip = max(xs) - min(xs)
    return {"shoulder": shoulder, "hip": hip, "ratio": shoulder / hip}
