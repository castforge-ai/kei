"""The export scene: a character as plain data that any file writer serialises (glTF now, FBX next).

build_scene(ch, emission=1.0, shot=None, mode="spline") -> ExportScene, all in Kei's world axes (x the character's
right, y up, z forward, metres); each writer converts to its own format's axes.

ExportScene
  name, title         the character's file name and display name
  axes, units         "Kei world: x right, y up, z forward", "metres"
  bones               [SceneBone], parents before children (kei.rig.ALL_BONES order)
    name, parent      Unreal mannequin names; parent None for root
    head, frame       the rest pose in the world: the joint position and the bone frame (X, Y, Z; Y along the bone)
    translation       the rest local translation: the head in the parent's frame (the world for root)
    rotation          the rest local rotation, a unit quaternion (x, y, z, w) of parent frame to bone frame
  meshes              [SceneMesh], one per shape (an imported character: one per part), at the rest pose
    name, bone        the shape's note (or kind) and the one bone it is bound to (weight 1)
    weights           None, or for a smooth imported part per vertex [(bone, weight)] (then bone is unused)
    material          body, joint or emission
    vertices, normals [(x, y, z)] in the world at rest
    triangles         [(i, j, k)] counter-clockwise seen from outside
  materials           [SceneMaterial]: name, colour '#rrggbb' (sRGB), emission '#rrggbb', emission_strength 0..1
  animation           SceneAnimation or None
    fps               frames per second; frame k is at k / fps seconds
    rotations         [frame][bone index] local rotation quaternions (x, y, z, w), the short way between frames
    translations      [frame][bone index] local translations (the root's carry the travel; any bone's change with
                      a length scale)
    root_translations [frame] the root bone's translation
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from kei.characters import Character, on_character, rest_pose
from kei.characters.mesh import pose_mesh
from kei.rig import ALL_BONES, PARENTS, skeleton
from kei.sample import bake

Vec = tuple[float, float, float]
Quat = tuple[float, float, float, float]
AXES = "Kei world: x the character's right, y up, z forward"


@dataclass
class SceneBone:
    name: str
    parent: str | None
    head: Vec
    frame: tuple[Vec, Vec, Vec]
    translation: Vec
    rotation: Quat


@dataclass
class SceneMesh:
    name: str
    bone: str
    material: str
    vertices: list
    normals: list
    triangles: list
    weights: list | None = None


@dataclass
class SceneMaterial:
    name: str
    colour: str
    emission: str
    emission_strength: float


@dataclass
class SceneAnimation:
    fps: float
    rotations: list
    translations: list

    @property
    def root_translations(self) -> list:
        return [t[0] for t in self.translations]


@dataclass
class ExportScene:
    name: str
    title: str
    axes: str
    units: str
    bones: list
    meshes: list
    materials: list
    animation: SceneAnimation | None


def mat_quat(m) -> Quat:
    """A unit quaternion (x, y, z, w) of a proper rotation matrix (rows)."""
    tr = m[0][0] + m[1][1] + m[2][2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = ((m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, 0.25 * s)
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2
        q = (0.25 * s, (m[0][1] + m[1][0]) / s, (m[0][2] + m[2][0]) / s, (m[2][1] - m[1][2]) / s)
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2
        q = ((m[0][1] + m[1][0]) / s, 0.25 * s, (m[1][2] + m[2][1]) / s, (m[0][2] - m[2][0]) / s)
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2
        q = ((m[0][2] + m[2][0]) / s, (m[1][2] + m[2][1]) / s, 0.25 * s, (m[1][0] - m[0][1]) / s)
    n = math.sqrt(sum(c * c for c in q))
    return tuple(c / n for c in q)


def quat_matrix(q) -> list[list[float]]:
    """The rotation matrix (rows) of a unit quaternion (x, y, z, w)."""
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def _columns(frame):
    """The frame (X, Y, Z) as a matrix with those columns: bone axes to world."""
    return [[frame[c][r] for c in range(3)] for r in range(3)]


def local_transforms(bones) -> list[tuple[Vec, Quat]]:
    """Per bone of ALL_BONES: (local translation, local rotation) from kei.rig.skeleton output."""
    out = []
    for name in ALL_BONES:
        b, parent = bones[name], PARENTS[name]
        R = _columns(b.frame)
        if parent is None:
            out.append((tuple(b.head), mat_quat(R)))
            continue
        P = bones[parent]
        Pt = [[P.frame[r][c] for c in range(3)] for r in range(3)]     # rows X, Y, Z: world to parent axes
        d = [b.head[i] - P.head[i] for i in range(3)]
        t = tuple(sum(Pt[r][k] * d[k] for k in range(3)) for r in range(3))
        L = [[sum(Pt[r][k] * R[k][c] for k in range(3)) for c in range(3)] for r in range(3)]
        out.append((t, mat_quat(L)))
    return out


def build_scene(ch: Character, emission: float = 1.0, shot: dict | None = None, mode: str = "spline") -> ExportScene:
    """A character at rest (the bind pose), its shapes as rigidly bound meshes, and optionally a shot baked on it."""
    emission = max(0.0, min(1.0, float(emission)))
    pose = rest_pose(ch)
    B = skeleton(pose, ch.proportions)
    bones = [SceneBone(n, PARENTS[n], B[n].head, B[n].frame, t, q)
             for n, (t, q) in zip(ALL_BONES, local_transforms(B))]
    meshes = [SceneMesh((ch.shapes[p.shape].note or ch.shapes[p.shape].kind) if p.shape >= 0 else f"{p.bone}_{i}",
                        p.bone, p.material, p.verts, p.normals, p.tris,
                        [[(n, w) for n, w, *_ in vw] for vw in p.skin] if p.skin else None)
              for i, p in enumerate(pose_mesh(ch, pose, B))]
    body = ch.materials["body"]
    materials = [SceneMaterial("body", body, ch.materials["emission"], 0.0),
                 SceneMaterial("joint", ch.materials["joint"], ch.materials["emission"], 0.0),
                 SceneMaterial("emission", body, ch.materials["emission"], emission)]
    animation = None
    if shot is not None:
        frames = bake(on_character(shot, ch), mode)
        rots, trans = [], []
        for fr in frames:
            loc = local_transforms(skeleton(fr["pose"], ch.proportions))
            row = []
            for i, (_, q) in enumerate(loc):
                if rots and sum(a * b for a, b in zip(rots[-1][i], q)) < 0:     # the short way round
                    q = tuple(-c for c in q)
                row.append(q)
            rots.append(row)
            trans.append([t for t, _ in loc])
        animation = SceneAnimation(float(shot.get("fps") or 24), rots, trans)
    return ExportScene(ch.name, ch.title, AXES, "metres", bones, meshes, materials, animation)
