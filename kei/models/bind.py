"""Bind an imported mesh to Kei's bones (the rest skeleton of kei.rig, at the fitted proportions).

A mesh built of separate pieces binds one piece to one bone, as Kei's own characters are built:
  - a small round piece (a joint ball or ring) centred on a joint goes to the bone that starts there (the child);
  - a piece goes to the bone nearest most of its vertices when RIGID_SHARE of them agree, or when it is small;
  - a piece that spans several bones (one piece for a whole arm, a continuous body) gets smooth weights.
The distance from a vertex to a bone is to the bone's segment, head to tail. The pelvis bone is the two segments from
the pelvis joint to the hip joints, so the hips go to it, and a small piece at or above a hip joint goes to the
pelvis too (on the thigh it would swing out sideways with every step). The clavicles are left out (the chest top belongs to the
chest; the shoulder ball goes to the upper arm). A finger bone takes a piece only within FINGER_REACH of it; the
rest of the hand goes to the hand.

Smooth weights: per vertex, w = 1 / (d + SOFT)^4 over its NEAREST nearest bones, normalised, then SMOOTHING rounds of
averaging with the vertex's neighbours along the mesh's edges; weights under 1 % are dropped, at most 4 kept.

map_bones(names) maps the bone names of a rigged model to Kei's (the Unreal mannequin names, the common Mixamo names,
and plain names with a side mark; a UE4 mannequin's three spine bones spread over Kei's five, its spine_03 the chest), and bind_rigged carries the model's own weights over: a weight on a bone that does
not map goes to its nearest mapped parent. A mesh with no skin of its own (a hat, the eyes, a weapon) goes rigidly to
the nearest mapped joint above it in the file; with no joint above it, it is bound by its shape as an unrigged mesh.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from kei.models.fit import shells
from kei.models.model import MeshData, Model
from kei.rig import ALL_BONES, FINGER_BONES

RIGID_SHARE = 0.9
SMALL = 0.04          # share of the height: a piece smaller than this is rigid on its most common bone
FINGER_REACH = 0.012  # metres at 1.71 m: a piece this close to a finger bone goes to it
SOFT, NEAREST, SMOOTHING = 0.01, 3, 2
TORSO_SKIP = ("root", "clavicle_l", "clavicle_r")


@dataclass
class BoundPart:
    bone: str               # the one bone of a rigid part; for a smooth part, the bone with the most weight
    material: str
    verts: list             # Kei's world at the rest pose
    tris: list
    skin: list | None = None   # smooth parts: per vertex [(bone, weight)], the weights summing to 1
    uvs: list | None = None    # a textured part: per triangle its corners' (u, v), v from the image's top
    texture: str | int | None = None   # its base colour image: the model's file when bound, its index at import


def _seg_dist(p, a, b) -> float:
    ab = [b[k] - a[k] for k in range(3)]
    ap = [p[k] - a[k] for k in range(3)]
    L2 = sum(c * c for c in ab)
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, sum(ap[k] * ab[k] for k in range(3)) / L2))
    return math.dist(p, [a[k] + ab[k] * t for k in range(3)])


def _segments(bones) -> list[tuple[str, tuple, tuple]]:
    out = []
    for n in ALL_BONES:
        if n in TORSO_SKIP or n == "pelvis":
            continue
        out.append((n, bones[n].head, bones[n].tail))
    for side in "lr":
        out.append(("pelvis", bones["pelvis"].head, bones[f"thigh_{side}"].head))
    return out


def _nearest(p, segs, k: float):
    """[(distance, bone)] nearest first, a finger bone only within its reach."""
    out = []
    for n, a, b in segs:
        d = _seg_dist(p, a, b)
        if n in FINGER_BONES and d > FINGER_REACH * k:
            continue
        out.append((d, n))
    out.sort()
    return out


def _round(pts, height):
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    ext = sorted(hi[k] - lo[k] for k in range(3))
    return ext[2] <= 0.08 * height and ext[2] <= 1.6 * ext[1], [(lo[k] + hi[k]) / 2 for k in range(3)], ext[2]


def _smooth(verts, tris, idx, segs, k):
    """Smooth weights for the vertices idx of a piece (see the module docstring)."""
    local = {v: i for i, v in enumerate(idx)}
    weights = []
    for v in idx:
        near = _nearest(verts[v], segs, k)[:NEAREST]
        w = {}
        for d, n in near:
            w[n] = w.get(n, 0.0) + 1.0 / (d + SOFT) ** 4
        t = sum(w.values())
        weights.append({n: x / t for n, x in w.items()})
    nbr = [set() for _ in idx]
    for a, b, c in tris:
        if a in local and b in local and c in local:
            for p, q in ((a, b), (b, c), (c, a)):
                nbr[local[p]].add(local[q])
                nbr[local[q]].add(local[p])
    for _ in range(SMOOTHING):
        new = []
        for i, w in enumerate(weights):
            acc = dict(w)
            for j in nbr[i]:
                for n, x in weights[j].items():
                    acc[n] = acc.get(n, 0.0) + x
            t = sum(acc.values())
            new.append({n: x / t for n, x in acc.items()})
        weights = new
    out = []
    for w in weights:
        top = sorted(((x, n) for n, x in w.items() if x >= 0.01), reverse=True)[:4]
        t = sum(x for x, _ in top)
        out.append([(n, x / t) for x, n in top])
    return out


def bind_mesh(mesh: MeshData, bones, height: float, material: str = "body") -> list[BoundPart]:
    """The mesh's pieces bound to Kei's bones (the rest skeleton `bones`, kei.rig.skeleton output)."""
    k = height / 1.71
    segs = _segments(bones)
    heads = [(n, bones[n].head) for n in ALL_BONES if n not in FINGER_BONES and n not in TORSO_SKIP]
    rigid, smooth = {}, []
    for piece in shells(mesh):
        pts = [mesh.verts[i] for i in piece]
        is_round, centre, size = _round(pts, height)
        bone = None
        if is_round:
            n, h = min(heads, key=lambda nh: math.dist(nh[1], centre))
            if math.dist(h, centre) < 0.6 * size:
                bone = n
        if bone is None and size < 0.08 * height:   # a small piece at or above a hip joint belongs to the pelvis
            for side in "lr":
                h = bones[f"thigh_{side}"].head
                if centre[1] >= h[1] - 0.01 * k and math.dist(centre, h) < 0.06 * height:
                    bone = "pelvis"
        if bone is None:
            votes = {}
            for p in pts:
                near = _nearest(p, segs, k)
                votes[near[0][1]] = votes.get(near[0][1], 0) + 1
            top = max(votes, key=votes.get)
            if votes[top] >= RIGID_SHARE * len(pts) or size < SMALL * height:
                bone = top
        if bone is not None:
            rigid.setdefault(bone, []).append(piece)
        else:
            smooth.append(piece)
    parts = []
    for bone in sorted(rigid, key=ALL_BONES.index):
        parts.append(_sub(mesh, [i for piece in rigid[bone] for i in piece], bone, material, None))
    for piece in smooth:
        skin = _smooth(mesh.verts, mesh.tris, piece, segs, k)
        total = {}
        for w in skin:
            for n, x in w:
                total[n] = total.get(n, 0.0) + x
        parts.append(_sub(mesh, piece, max(total, key=total.get), material, skin))
    return parts


def _sub(mesh: MeshData, idx: list[int], bone: str, material: str, skin) -> BoundPart:
    """The vertices idx of a mesh and the triangles among them, renumbered."""
    remap = {v: i for i, v in enumerate(idx)}
    keep = [k for k, (a, b, c) in enumerate(mesh.tris) if a in remap and b in remap and c in remap]
    tris = [tuple(remap[i] for i in mesh.tris[k]) for k in keep]
    uvs = [mesh.tri_uvs[k] for k in keep] if mesh.tri_uvs else None
    return BoundPart(bone, material, [mesh.verts[i] for i in idx], tris, skin, uvs, mesh.texture if uvs else None)


# ---------------- a rigged model's bone names ----------------
_SIDE = re.compile(r"(?:^|[^a-z])(left|right|l|r)(?:$|[^a-z])")
_TABLE = [  # (words that name the bone, Kei's bone without its side, needs a side)
    (("hips", "pelvis", "root_hips"), "pelvis", False),
    (("upperchest", "chest", "spine2", "spine_03", "spine03"), "spine_05", False),
    (("spine1", "spine_02", "spine02"), "spine_03", False),
    (("spine", "spine_01", "spine01"), "spine_01", False),
    (("neck",), "neck_01", False),
    (("head",), "head", False),
    (("clavicle", "collar"), "clavicle", True),
    (("shoulder", "shldr"), "clavicle", True),     # an upper arm when the rig also has a collar (map_bones)
    (("forearm", "lowerarm", "elbow"), "lowerarm", True),
    (("upperarm", "arm"), "upperarm", True),
    (("hand", "wrist"), "hand", True),
    (("upleg", "upperleg", "thigh", "hip"), "thigh", True),
    (("toebase", "toe", "ball"), "ball", True),
    (("foot", "ankle"), "foot", True),
    (("calf", "shin", "lowerleg", "knee", "leg"), "calf", True),
]
FINGERS = ("thumb", "index", "middle", "ring", "pinky")


def _clean(name: str) -> str:
    n = name.split(":")[-1].split("|")[-1]
    n = re.sub(r"^(def|org|mch)[-_.]", "", n, flags=re.I)
    n = re.sub(r"^bip\d*[ _]", "", n, flags=re.I)
    n = re.sub(r"([a-z])([A-Z])", r"\1_\2", n)
    return n.lower().replace(".", "_").replace(" ", "_").replace("-", "_")


def _side(clean: str) -> str | None:
    for m in _SIDE.finditer(clean):
        return "l" if m.group(1) in ("left", "l") else "r"
    return None


UE4_SPINE = ("spine_01", "spine_02", "spine_03")


def _three_spine(names) -> bool:
    """A UE4 mannequin's spine: spine_01..03 and no spine_04 or spine_05, so its spine_03 is the chest."""
    clean = {_clean(n) for n in names}
    return "spine_03" in clean and not clean & {"spine_04", "spine_05"}


def map_bone(name: str, three_spine: bool = False) -> str | None:
    """Kei's name for a bone name of a rigged model, or None. three_spine: the skeleton is a UE4 mannequin's
    (_three_spine), so its spine names go through the table, not straight to Kei's same names."""
    if name in ALL_BONES and not (three_spine and name in UE4_SPINE):
        return name
    c = _clean(name)
    side = _side(c)
    words = [w for w in c.split("_") if w and w not in ("left", "right", "l", "r", "mixamorig")]
    joined = "".join(words)
    if any(w in ("twist", "roll", "end", "nub", "ik", "pole", "target", "tail", "jaw", "eye") for w in words) or \
            re.search(r"twist|roll|nub|end$", joined):
        return None
    for f in FINGERS:
        if joined.startswith("hand" + f) or joined.startswith(f):
            if side is None:
                return None
            digits = re.findall(r"\d+", joined)
            num = int(digits[-1]) if digits else 1
            if f == "thumb":
                return f"thumb_0{min(max(num, 1), 3)}_{side}" if num <= 3 else None
            if num == 0 or "metacarpal" in joined:
                return f"{f}_metacarpal_{side}"
            return f"{f}_0{num}_{side}" if 1 <= num <= 3 else None
    for keys, bone, sided in _TABLE:
        if joined in keys or (sided and any(joined == k for k in keys)):
            if sided:
                return f"{bone}_{side}" if side else None
            return bone
    return None


def map_bones(names) -> tuple[dict, list]:
    """({their name: Kei's name}, [their names with no Kei bone]). Two names that map to the same Kei bone keep the
    first; the later ones are unmapped."""
    mapping, unmapped, used = {}, [], set()
    names = list(names)
    ue4 = _three_spine(names)
    collars = {map_bone(n, ue4) for n in names if re.search(r"collar|clavicle", n, re.I)}
    for n in names:
        k = map_bone(n, ue4)
        if k in collars and k is not None and re.search(r"shoulder|shldr", n, re.I):
            k = k.replace("clavicle", "upperarm")      # a rig with a collar: its shoulder is the upper arm
        if k is None or k in used:
            unmapped.append(n)
        else:
            mapping[n] = k
            used.add(k)
    return mapping, unmapped


def bind_rigged(model: Model, mapping: dict, material: str = "body", bones=None,
                height: float | None = None) -> list[BoundPart]:
    """The model's meshes with their own weights on Kei's bone names. A weight on a bone that does not map goes to its
    nearest mapped parent; a vertex with no weight left goes to the pelvis. A mesh with no skin goes rigidly to the
    nearest mapped joint above it (its parent_joint, then that joint's parents); with none, and given Kei's rest
    `bones` and the height, it is bound by its shape (bind_mesh)."""
    parent = {j.name: j.parent for j in model.joints}

    def kei(n):
        seen = set()
        while n is not None and n not in mapping and n not in seen:
            seen.add(n)
            n = parent.get(n)
        return mapping.get(n)
    parts = []
    for m in model.meshes:
        if not m.skin:
            bone = kei(m.parent_joint) if m.parent_joint else None
            if bone is not None:
                parts.append(BoundPart(bone, material, list(m.verts), list(m.tris), None,
                                       list(m.tri_uvs) if m.tri_uvs else None, m.texture if m.tri_uvs else None))
                continue
            if bones is not None and height:
                parts.extend(bind_mesh(m, bones, height, material))
                continue
        skin = []
        for w in (m.skin or [[] for _ in m.verts]):
            acc = {}
            for n, x in w:
                k = kei(n)
                if k is not None:
                    acc[k] = acc.get(k, 0.0) + x
            t = sum(acc.values())
            skin.append([(n, x / t) for n, x in acc.items()] if t > 0 else [("pelvis", 1.0)])
        total = {}
        for w in skin:
            for n, x in w:
                total[n] = total.get(n, 0.0) + x
        parts.append(BoundPart(max(total, key=total.get), material, list(m.verts), list(m.tris), skin,
                               list(m.tri_uvs) if m.tri_uvs else None, m.texture if m.tri_uvs else None))
    return parts
