"""Fit Kei's skeleton to an unrigged humanoid model: stand it up, find its body landmarks, and set Kei's rig
proportions and rest pose so the rig's joints sit on them.

normalise(model, height) turns the model (its mesh and its joints) to face +z (the toes are the longer side of each foot from the ankle; a
model deeper than it is wide is turned a quarter first), scales it to the height, puts its soles on y 0 and centres it
on x and z. humanoid_or_raise refuses what is not an upright two-legged figure.

landmarks(model) reads the figure in horizontal slices (all heights as shares of the height H):
  crotch    the lowest slice above 0.2 H with mesh at the centre line, the legs being apart below it
  legs      the centre of each leg's run just under the crotch, the ankle slice, the toe tip and the heel
  armpits   the highest slice under 0.82 H where the arms are apart from the torso (three runs or more)
  arms      the outer runs below the armpits: their centres make each arm's line, down to its lowest point
  neck      the narrowest centre run between 0.80 H and 0.95 H
The joints come from these features with offsets measured on Kei's and Keira's own meshes (OFFSETS), then a joint
snap moves each joint to the centre of a small round piece (a joint ball or ring) when one lies within SNAP of it.

fit_rig(marks, height) turns the joints into kei.rig proportions and a rest pose: lengths are distances between
joints, the arm and clavicle angles are found by a small search on kei.rig.solve, and the result keeps the fit's
largest joint error so the fit sheet can show it.
"""
from __future__ import annotations

import dataclasses
import math

from kei.models.model import Joint, MeshData, Model, ModelError
from kei.rig import PROPORTIONS, solve

# Offsets from the slice features to the joints, as shares of the height, measured on Kei's and Keira's own meshes.
OFFSETS = {
    "hip_above_crotch": 0.033,     # the hip joints above the crotch
    "ankle": 0.0526,               # the ankle joint's height (Kei: 0.09 m of 1.71 m)
    "shoulder_above_armpit": 0.072,  # the shoulder joint above the armpit
    "neck_base_below_neck": 0.028,  # the base of the neck below its narrowest slice
    "head_joint_above_neck": 0.026,  # the head joint above the narrowest slice
    "knee_forward": 0.0,           # the knee joint in front of the knee slice's centre
}
KNEE_SHARE = 0.5125                # the knee's share of the ankle-to-hip length, up from the ankle (Kei 0.41 / 0.80)
ELBOW_SHARE, WRIST_SHARE = 0.413, 0.757  # along the shoulder to arm-end line (Kei's rest arm)
SPINE_SHARE = (0.10, 0.06, 0.06, 0.15, 0.155)   # Kei's spine segments, the share each takes of the spine
# The spine pitch that puts the neck's base on its mark, found on Kei's and Keira's own meshes standing as they stand
# (-0.042 and -0.0225 rad, the mean): the marks sit a little off Kei's joints, so a sculpt is bound with its own pitch
# less this one.
SPINE_MARK = -0.032
# The middle of the head ahead of the shoulder joints on Kei's and Keira's own meshes at rest (1.85 and 2.47 cm, the
# mean, on 1.71 m): a sculpt's neck is bound so its head stacks there at a shot's neutral stance.
HEAD_AHEAD = 0.0216
SNAP = 0.02                        # share of the height: a round piece this close to a joint takes the joint
SLICE = 0.01                       # share of the height: the thickness of one slice
GAP = 0.008                        # share of the height: a gap this wide splits two runs
A_POSE = ("stand the model in an A-pose (arms hanging 15 to 45 degrees from the body) and import it again; Kei "
          "does not read T-poses yet")
GENERAL_RIG = ("Kei animates humanoids for now: two legs, two arms, upright. Creatures (four legs, wings, many "
               "legs) need Kei's general rig, which is planned (plan 3e) and not built yet.")


def _bbox(verts):
    return [(min(v[k] for v in verts), max(v[k] for v in verts)) for k in range(3)]


def _transform(model: Model, f) -> Model:
    """The model with f applied to every vertex and every joint."""
    return dataclasses.replace(model, meshes=[dataclasses.replace(m, verts=[f(v) for v in m.verts])
                                              for m in model.meshes],
                               joints=[Joint(j.name, j.parent, f(j.head)) for j in model.joints])


def _slice(verts, y0, y1):
    return [v for v in verts if y0 <= v[1] < y1]


def _runs(vals, gap):
    """Sorted values split where two neighbours are more than gap apart: [(lo, hi)]."""
    vals = sorted(vals)
    if not vals:
        return []
    out, lo, prev = [], vals[0], vals[0]
    for x in vals[1:]:
        if x - prev > gap:
            out.append((lo, prev))
            lo = x
        prev = x
    out.append((lo, prev))
    return out


class Sections:
    """Horizontal cross-sections of a mesh: each triangle cut by the plane at height y gives a segment, and the
    segments' x intervals, merged where they touch or overlap within a gap, are the runs of the figure at y."""

    def __init__(self, model: Model, bucket: float = 0.01):
        self.tris, self.bucket, self.index = [], bucket, {}
        for m in model.meshes:
            for a, b, c in m.tris:
                t = (m.verts[a], m.verts[b], m.verts[c])
                lo, hi = min(p[1] for p in t), max(p[1] for p in t)
                k = len(self.tris)
                self.tris.append((t, lo, hi))
                for i in range(int(lo // bucket), int(hi // bucket) + 1):
                    self.index.setdefault(i, []).append(k)

    def segments(self, y: float):
        out = []
        for k in self.index.get(int(y // self.bucket), []):
            t, lo, hi = self.tris[k]
            if not (lo <= y <= hi) or hi - lo < 1e-12:
                continue
            pts = []
            for p, q in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                if (p[1] - y) * (q[1] - y) <= 0 and p[1] != q[1]:
                    u = (y - p[1]) / (q[1] - p[1])
                    pts.append((p[0] + (q[0] - p[0]) * u, p[2] + (q[2] - p[2]) * u))
            if len(pts) >= 2:
                out.append((pts[0], pts[1]))
        return out

    def runs(self, y: float, gap: float, side: int = 0):
        """[(x lo, x hi, z lo, z hi)] at height y, left to right; side -1 or +1 keeps the runs on that side of x 0
        (cut at x 0)."""
        iv = []
        for (x0, z0), (x1, z1) in self.segments(y):
            lo, hi = min(x0, x1), max(x0, x1)
            if side < 0:
                if lo >= 0:
                    continue
                hi = min(hi, 0.0)
            elif side > 0:
                if hi <= 0:
                    continue
                lo = max(lo, 0.0)
            iv.append((lo, hi, min(z0, z1), max(z0, z1)))
        iv.sort()
        out = []
        for lo, hi, zl, zh in iv:
            if out and lo - out[-1][1] <= gap:
                a = out[-1]
                out[-1] = (a[0], max(a[1], hi), min(a[2], zl), max(a[3], zh))
            else:
                out.append((lo, hi, zl, zh))
        return out


def _facing_sign(verts, H) -> int:
    """+1 when the toes point to +z, -1 when they point to -z: per foot, the toe side is the longer side of the
    foot's sole from the shin above it."""
    votes = 0
    for side in (-1, 1):
        sole = [v for v in verts if v[1] < 0.03 * H and v[0] * side > 0]
        shin = [v for v in verts if 0.07 * H <= v[1] < 0.11 * H and v[0] * side > 0]
        if not sole or not shin:
            continue
        zs = [v[2] for v in shin]
        mid = (min(zs) + max(zs)) / 2
        front = max(v[2] for v in sole) - mid
        back = mid - min(v[2] for v in sole)
        votes += 1 if front > back else -1
    return -1 if votes < 0 else 1


def normalise(model: Model, height: float) -> Model:
    """The model on the ground, centred, facing +z (Kei's forward) and scaled to height (metres)."""
    verts = model.all_verts()
    if not verts:
        raise ModelError(f"{model.source}: the model has no vertices")
    (x0, x1), (y0, y1), (z0, z1) = _bbox(verts)
    if y1 - y0 < 1e-6:
        raise ModelError(f"{model.source}: the model is flat")
    if (z1 - z0) > 1.25 * (x1 - x0):                   # side on: turn a quarter so the width is on x
        model = _transform(model, lambda v: (v[2], v[1], -v[0]))
        verts = model.all_verts()
    (x0, x1), (y0, y1), (z0, z1) = _bbox(verts)
    s = height / (y1 - y0)
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    model = _transform(model, lambda v: ((v[0] - cx) * s, (v[1] - y0) * s, (v[2] - cz) * s))
    if _facing_sign(model.all_verts(), height) < 0:     # facing back: half a turn about y
        model = _transform(model, lambda v: (-v[0], v[1], -v[2]))
    # centre on the shins' depth just above the ankles, so the rig's feet (at z 0) stand where the model's are
    ank = [v for v in model.all_verts() if 0.08 * height <= v[1] < 0.12 * height]
    if ank:
        mz = (min(v[2] for v in ank) + max(v[2] for v in ank)) / 2
        model = _transform(model, lambda v: (v[0], v[1], v[2] - mz))
    return model


def humanoid_or_raise(model: Model, S: "Sections | None" = None) -> None:
    """Refuse a model that is not an upright two-legged figure, naming why (the model is normalised)."""
    verts = model.all_verts()
    (x0, x1), (y0, y1), (z0, z1) = _bbox(verts)
    H = y1 - y0
    if max(x1 - x0, z1 - z0) > 1.1 * H:
        raise ModelError(f"{model.source}: the model is longer than it is tall. {GENERAL_RIG}")
    S = S or Sections(model)
    for share in (0.12, 0.2):
        legs = S.runs(share * H, GAP * H)
        if len(legs) != 2 or legs[0][1] > 0 or legs[1][0] < 0:
            raise ModelError(f"{model.source}: the model does not stand on two legs ({len(legs)} found across "
                             f"the body at {round(share * 100)} % of its height). {GENERAL_RIG}")
        for leg in legs:          # one foot per side: two feet one behind the other on a side is four legs
            zs = sorted((min(p[1], q[1]), max(p[1], q[1])) for p, q in S.segments(share * H)
                        if leg[0] <= min(p[0], q[0]) and max(p[0], q[0]) <= leg[1])
            feet, end = 0, -math.inf
            for lo, hi in zs:
                if lo - end > GAP * H:
                    feet += 1
                end = max(end, hi)
            if feet > 1:
                raise ModelError(f"{model.source}: the model stands on more than two legs. {GENERAL_RIG}")


def shells(mesh: MeshData) -> list[list[int]]:
    """The mesh's connected pieces as lists of vertex indices. Vertices at the same position (to 1e-6 m) join, so a
    seam split for the texture does not cut a piece in two."""
    parent = list(range(len(mesh.verts)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a
    first = {}
    for i, v in enumerate(mesh.verts):
        k = (round(v[0], 6), round(v[1], 6), round(v[2], 6))
        if k in first:
            union(first[k], i)
        else:
            first[k] = i
    for a, b, c in mesh.tris:
        union(a, b)
        union(a, c)
    groups = {}
    for i in range(len(mesh.verts)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _round_pieces(model: Model, H: float):
    """Centres of the small round pieces (joint balls and rings): the two largest extents within 1.6 of each other,
    the largest between 0.012 H and 0.08 H."""
    out = []
    for m in model.meshes:
        for sh in shells(m):
            pts = [m.verts[i] for i in sh]
            bb = _bbox(pts)
            ext = sorted(hi - lo for lo, hi in bb)
            if 0.012 * H <= ext[2] <= 0.08 * H and ext[2] <= 1.6 * ext[1]:
                out.append(tuple((lo + hi) / 2 for lo, hi in bb))
    return out


def _mid(vals):
    return (min(vals) + max(vals)) / 2


def trunk_lean(S: "Sections", y0: float, y1: float, H: float, x: float = 0.0) -> float | None:
    """The trunk's lean (radians, + forward): the line along the back of the trunk (the spine side) from y0 (the
    waist) to y1 (just under the neck), fitted to nine cross-sections. The back follows the spine; the middle of
    the depth also follows the shape of the chest and belly."""
    line = []
    for i in range(9):
        y = y0 + (y1 - y0) * i / 8
        centre = [r for r in S.runs(y, GAP * H) if r[0] <= x <= r[1]]
        if centre:
            line.append((y, centre[0][2]))
    if len(line) < 4:
        return None
    my, mz = sum(p[0] for p in line) / len(line), sum(p[1] for p in line) / len(line)
    syy = sum((p[0] - my) ** 2 for p in line) or 1e-9
    return math.atan(sum((p[0] - my) * (p[1] - mz) for p in line) / syy)


def _centre(run):
    return ((run[0] + run[1]) / 2, (run[2] + run[3]) / 2)


def features(model: Model, S: "Sections | None" = None) -> dict:
    """The slice features of a normalised humanoid model (heights in metres): crotch, armpit, neck and, per side
    ('l' on -x, 'r' on +x), the leg run under the crotch, each arm's line and its lowest point."""
    S = S or Sections(model)
    H = max(v[1] for v in model.all_verts())
    gap, step = GAP * H, 0.0025 * H
    f = {"H": H}
    y = 0.2 * H
    while y < 0.65 * H and not any(r[0] <= 0 <= r[1] for r in S.runs(y, gap)):
        y += step
    f["crotch"] = y if y < 0.65 * H else 0.5 * H
    for side, s in (("l", -1), ("r", 1)):
        runs = S.runs(f["crotch"] - 0.02 * H, gap, s)
        f["leg_" + side] = min(runs, key=lambda r: abs(r[0] + r[1])) if runs else None
    # the armpit: the highest height under 0.82 H from which three runs or more hold for 3 % of the height down
    y, armpit = 0.82 * H, None
    while y > f["crotch"]:
        if all(len(S.runs(y - k * 0.01 * H, gap)) >= 3 for k in range(4)):
            armpit = y
            break
        y -= step
    if armpit is None:
        raise ModelError(f"{model.source}: the arms are not apart from the body below the armpits: {A_POSE}")
    f["armpit"] = armpit
    for side, s in (("l", -1), ("r", 1)):
        pts, y = [], armpit
        while y > 0.2 * H:
            runs = S.runs(y, gap, s)
            if len(runs) < 2:
                break
            outer = max(runs, key=lambda r: abs(r[0] + r[1]))
            x, z = _centre(outer)
            if pts and abs(x - pts[-1][0]) > 0.04 * H:      # jumped to another part: the arm has ended
                break
            pts.append((x, y, z))
            y -= step
        if len(pts) < 5:
            raise ModelError(f"{model.source}: cannot follow the {'left' if s < 0 else 'right'} arm down from the "
                             f"armpit: {A_POSE}")
        n = len(pts)
        mx, my, mz = (sum(p[k] for p in pts) / n for k in range(3))
        syy = sum((p[1] - my) ** 2 for p in pts) or 1e-9
        ax = sum((p[1] - my) * (p[0] - mx) for p in pts) / syy
        az = sum((p[1] - my) * (p[2] - mz) for p in pts) / syy
        f["arm_" + side] = (mx, my, mz, ax, az)
        f["arm_end_" + side] = pts[-1][1]
        top = pts[:max(3, n // 5)]
        f["arm_top_z_" + side] = sum(p[2] for p in top) / len(top)
    best, y = None, 0.80 * H
    while y < 0.95 * H:
        centre = [r for r in S.runs(y, gap) if r[0] <= 0 <= r[1]]
        if centre and (best is None or centre[0][1] - centre[0][0] < best[0]):
            best = (centre[0][1] - centre[0][0], y, _centre(centre[0]))
        y += step
    f["neck"], (f["neck_x"], f["neck_z"]) = (best[1], best[2]) if best else (0.875 * H, (0.0, 0.0))
    return f


def landmarks(model: Model) -> dict:
    """The joints of a normalised humanoid model, by Kei's bone names (see the module docstring)."""
    S = Sections(model)
    f = features(model, S)
    H = f["H"]
    gap = GAP * H
    marks = {"head_top": (f["neck_x"], H, f["neck_z"])}
    for side, s in (("l", -1), ("r", 1)):
        leg = f["leg_" + side]
        hx, hz = _centre(leg) if leg else (s * 0.06 * H, 0.0)
        hip = (hx, f["crotch"] + OFFSETS["hip_above_crotch"] * H, hz)
        ay = OFFSETS["ankle"] * H
        shin = S.runs(ay, gap, s)
        shin = min(shin, key=lambda r: abs(r[0] + r[1])) if shin else None
        ax_, az_ = _centre(shin) if shin else (hx, 0.0)
        ankle = (ax_, ay, az_)
        sole = S.runs(0.01 * H, gap, s)
        toe_z = max((r[3] for r in sole), default=az_ + 0.12 * H)
        heel_z = min((r[2] for r in sole), default=az_ - 0.035 * H)
        ky = ay + (hip[1] - ay) * KNEE_SHARE
        kr = S.runs(ky, gap, s)
        kr = min(kr, key=lambda r: abs(r[0] + r[1])) if kr else None
        kx, kz = _centre(kr) if kr else ((hx + ax_) / 2, (hz + az_) / 2)
        marks.update({f"thigh_{side}": hip, f"calf_{side}": (kx, ky, kz + OFFSETS["knee_forward"] * H),
                      f"foot_{side}": ankle, f"toe_{side}": (ax_, 0.0, toe_z), f"heel_{side}": (ax_, 0.0, heel_z)})
        mx, my, mz, ax, az = f["arm_" + side]

        def at(yy):
            return (mx + ax * (yy - my), yy, mz + az * (yy - my))
        sx_, sy_, _ = at(f["armpit"] + OFFSETS["shoulder_above_armpit"] * H)
        shoulder = (sx_, sy_, f["arm_top_z_" + side])
        end = at(f["arm_end_" + side])
        marks[f"upperarm_{side}"] = shoulder
        marks[f"lowerarm_{side}"] = tuple(shoulder[k] + (end[k] - shoulder[k]) * ELBOW_SHARE for k in range(3))
        marks[f"hand_{side}"] = tuple(shoulder[k] + (end[k] - shoulder[k]) * WRIST_SHARE for k in range(3))
        marks[f"hand_{side}_end"] = end
    def mid_depth(y):      # the middle of the centre run at this height: a forward head moves the neck with it
        centre = [r for r in S.runs(y, gap) if r[0] <= 0 <= r[1]]
        return _centre(centre[0])[1] if centre else f["neck_z"]
    yb, yn = f["neck"] - OFFSETS["neck_base_below_neck"] * H, f["neck"]
    yh = f["neck"] + OFFSETS["head_joint_above_neck"] * H
    zb, zn = mid_depth(yb), mid_depth(yn)
    marks["neck_01"] = (f["neck_x"], yb, zb)
    # the head joint: the back of the neck at its height plus the neck's half depth (the head's own mid depth is not
    # the joint: a face or a chin moves it forward, while the back of the neck follows the neck)
    def run_at(y):
        centre = [r for r in S.runs(y, gap) if r[0] <= 0 <= r[1]]
        return centre[0] if centre else None
    rn, rh = run_at(yn), run_at(yh)
    zh = rh[2] + (rn[3] - rn[2]) / 2 if rn and rh else zn
    marks["head"] = (f["neck_x"], yh, zh)
    pieces = _round_pieces(model, H)
    snapped = []
    for name in ("upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "thigh_l", "thigh_r",
                 "calf_l", "calf_r", "foot_l", "foot_r"):
        j = marks[name]
        near = min(pieces, key=lambda c: math.dist(c, j), default=None)
        if near is not None and math.dist(near, j) < SNAP * H:
            marks[name] = near
            snapped.append(name)
    for side in "lr":       # a knee found on its joint ball sets the hip's depth: the standing leg is straight
        if f"calf_{side}" in snapped and f"thigh_{side}" not in snapped:
            hip, knee, ankle = marks[f"thigh_{side}"], marks[f"calf_{side}"], marks[f"foot_{side}"]
            if knee[1] - ankle[1] > 1e-6:
                z = knee[2] + (knee[2] - ankle[2]) * (hip[1] - knee[1]) / (knee[1] - ankle[1])
                marks[f"thigh_{side}"] = (hip[0], hip[1], z)
    lean = trunk_lean(S, f["crotch"] + 0.18 * H, marks["neck_01"][1] - 0.02 * H, H)
    if lean is not None:
        marks["_trunk_lean"] = lean
    marks["_trunk_span"] = (f["crotch"] + 0.18 * H, marks["neck_01"][1] - 0.02 * H)
    marks["_snapped"] = snapped
    marks["_height"] = H
    return marks


# ---------------- marks to Kei's rig ----------------
def _search(f, x, steps, rounds=60):
    """Minimise f(x) by coordinate steps that halve when no step helps."""
    x, best = list(x), f(x)
    steps = list(steps)
    for _ in range(rounds):
        moved = False
        for i in range(len(x)):
            for d in (steps[i], -steps[i]):
                y = list(x)
                y[i] += d
                v = f(y)
                if v < best:
                    x, best, moved = y, v, True
                    break
        if not moved:
            steps = [s / 2 for s in steps]
            if max(steps) < 1e-5:
                break
    return x, best


def fit_rig(marks: dict, height: float) -> tuple[dict, dict, dict]:
    """(proportions, rest pose, report) that put kei.rig's joints on the marks. The report holds each joint's error
    in metres and the largest."""
    def d(a, b):
        return math.dist(marks[a], marks[b])

    def avg(a, b):
        return (a + b) / 2
    P = {k: (list(v) if isinstance(v, list) else v) for k, v in PROPORTIONS.items()}
    k = height / 1.71
    hip_l, hip_r = marks["thigh_l"], marks["thigh_r"]
    hip_drop = 0.03 * k
    given, marks = marks, dict(marks)
    for s in "lr":      # the rig bends its knees forward: a knee pushed back is fitted on the hip to ankle line
        H_, K, A = marks[f"thigh_{s}"], marks[f"calf_{s}"], marks[f"foot_{s}"]
        u = [A[k] - H_[k] for k in range(3)]
        n = math.sqrt(sum(c * c for c in u)) or 1.0
        u = [c / n for c in u]
        t = sum((K[k] - H_[k]) * u[k] for k in range(3))
        on = tuple(H_[k] + u[k] * t for k in range(3))
        if K[2] < on[2]:
            marks[f"calf_{s}"] = on
    root = (avg(hip_l[0], hip_r[0]), avg(hip_l[1], hip_r[1]) + hip_drop, avg(hip_l[2], hip_r[2]))
    P["hipWidth"], P["hipDrop"] = abs(hip_r[0] - hip_l[0]) / 2, hip_drop
    P["thigh"] = avg(d("thigh_l", "calf_l"), d("thigh_r", "calf_r"))
    P["calf"] = avg(d("calf_l", "foot_l"), d("calf_r", "foot_r"))
    P["ankleH"] = avg(marks["foot_l"][1], marks["foot_r"][1])
    toe = avg(marks["toe_l"][2] - marks["foot_l"][2], marks["toe_r"][2] - marks["foot_r"][2])
    P["toeFwd"], P["ballFwd"] = max(0.02, toe), max(0.015, toe * 0.71)
    P["heelBack"] = max(0.01, avg(marks["foot_l"][2] - marks["heel_l"][2], marks["foot_r"][2] - marks["heel_r"][2]))
    neck_base, head_joint = marks["neck_01"], marks["head"]
    spine_len = max(0.1, neck_base[1] - root[1])
    share = [x / sum(SPINE_SHARE) for x in SPINE_SHARE]
    P["spine"] = [round(spine_len * s, 5) for s in share]
    P["neck"] = [max(0.01, head_joint[1] - neck_base[1]) / 2] * 2
    P["head"] = max(0.05, height - head_joint[1])
    P["upperarm"] = avg(d("upperarm_l", "lowerarm_l"), d("upperarm_r", "lowerarm_r"))
    P["lowerarm"] = avg(d("lowerarm_l", "hand_l"), d("lowerarm_r", "hand_r"))
    P["hand"] = max(0.03, 0.5 * avg(d("hand_l", "hand_l_end"), d("hand_r", "hand_r_end")))
    sh_y = avg(marks["upperarm_l"][1], marks["upperarm_r"][1])
    P["sternumDrop"] = max(0.0, neck_base[1] - sh_y)
    P["clavicle"] = avg(abs(marks["upperarm_l"][0]), abs(marks["upperarm_r"][0]))
    # Kei's shots set the spine, neck and head as absolute angles, 0 being Kei's own stance: trunk upright, head
    # stacked over the shoulders. A sculpt made leaning back is bound with that pitch as its rest spine, so a shot's 0
    # stands it as Kei stands and a walk's own trunk angles play unchanged on it: the spine's rest pitch puts the
    # neck's base on its mark, less the pitch the same search finds on Kei's and Keira's own meshes (SPINE_MARK).
    # The neck's rest pitch is set by the importer (stack_head), from the mesh.
    P["spine"] = [round(max(0.1, math.dist(root, neck_base)) * s, 5) for s in share]
    base = {"root": list(root), "spine": [0.0, 0, 0], "neck": [0, 0, 0], "head": [0, 0, 0]}
    s_ = _search(lambda x: math.dist(solve({**base, "spine": [x[0], 0, 0]}, P)["neck_01"], neck_base),
                 [0.0], [0.1])[0][0] - SPINE_MARK
    rest = {"root": [round(c, 5) for c in root], "spine": [round(s_, 4), 0, 0],
            "neck": [0, 0, 0], "head": [0, 0, 0],
            "footL": [marks["foot_l"][0], marks["foot_l"][1], marks["foot_l"][2], 0, 0],
            "footR": [marks["foot_r"][0], marks["foot_r"][1], marks["foot_r"][2], 0, 0]}
    targets = {n: marks[n] for n in ("upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r")}
    for side in ("L", "R"):
        lo = side.lower()

        def err(x, side=side, lo=lo):
            pose = {**rest, "arm" + side: [x[0], x[1], 0], "elbow" + side: [x[2], 0]}
            j = solve(pose, P)
            return sum(math.dist(j[n], targets[n]) ** 2 for n in (f"lowerarm_{lo}", f"hand_{lo}"))
        x, _ = _search(err, [0.0, 0.3, 0.1], [0.2, 0.2, 0.2])
        rest["arm" + side], rest["elbow" + side] = [x[0], x[1], 0], [x[2], 0]
    rest = {c: ([round(v, 5) for v in val] if isinstance(val, list) else val) for c, val in rest.items()}
    P = {c: ([round(v, 5) for v in val] if isinstance(val, list) else round(val, 5)) for c, val in P.items()
         if c in ("spine", "neck", "head", "sternumDrop", "clavicle", "upperarm", "lowerarm", "hand", "hipWidth",
                  "hipDrop", "thigh", "calf", "ankleH", "heelBack", "ballFwd", "toeFwd")}
    j = solve(rest, P)
    errors = {n: round(math.dist(j[n], given[n]), 4) for n in
              ("thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r", "upperarm_l", "upperarm_r",
               "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "neck_01", "head")}
    return P, rest, {"errors": errors, "largest": max(errors.values()), "snapped": given.get("_snapped", [])}


def _pitch(p, c, a):
    """The point p turned forward by a radians about c (pitch, in the y up, z forward plane)."""
    dy, dz = p[1] - c[1], p[2] - c[2]
    return (p[0], c[1] + dy * math.cos(a) - dz * math.sin(a), c[2] + dy * math.sin(a) + dz * math.cos(a))


STACK_RANGE = (-0.3, 1.2)       # radians: the neck rest pitch stack_head searches; a bound means it could not stack


def stack_head(model: Model, P: dict, rest: dict, height: float) -> float:
    """The neck's rest pitch that, at a shot's neutral stance (spine and neck at 0), stacks the sculpt's head over its
    shoulders as Kei's and Keira's stack (HEAD_AHEAD): the head is the mesh above the base of the skull, turned with
    the trunk about the root and with the neck about its base."""
    j = solve(rest, P)
    s = rest["spine"][0]
    root, neck = j["root"], j["neck_01"]
    above = j["neck_02"][1] + 0.03 * height / 1.71
    head = [v for v in model.all_verts() if v[1] > above and abs(v[0] - j["head"][0]) < 0.13 * height / 1.71]
    if not head:
        return 0.0
    shoulders = [_pitch(j[n], root, -s) for n in ("upperarm_l", "upperarm_r")]
    sh_z = (shoulders[0][2] + shoulders[1][2]) / 2
    pivot = _pitch(neck, root, -s)
    want = HEAD_AHEAD * height / 1.71

    def ahead(n):
        zs = [_pitch(_pitch(v, root, -s), pivot, -n)[2] for v in head]
        return (min(zs) + max(zs)) / 2 - sh_z
    lo, hi = STACK_RANGE                 # the head goes back as the bound neck pitch grows
    if ahead(lo) <= want:
        return lo
    if ahead(hi) >= want:
        return hi
    for _ in range(30):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ahead(mid) > want else (lo, mid)
    return round((lo + hi) / 2, 4)
