"""The format-free export scene that every exporter (glTF now, FBX later) serialises."""
import math

from kei import hands
from kei.characters import load_character, rest_pose
from kei.characters.mesh import pose_mesh
from kei.export_scene import build_scene, quat_matrix
from kei.rig import ALL_BONES, PARENTS, skeleton
from kei.sample import bake

SHOT = {"rig": "v4", "fps": 30, "frames": 4,
        "keys": [{"f": 0, "root": [0, 0.915, 0]},
                 {"f": 4, "root": [0.1, 0.9, 0.3], "armL": [1.2, 0.2, 0.3], "fingersL": hands.preset("fist"),
                  "sq": 1.1}]}


def mat_vec(m, v):
    return tuple(sum(m[r][c] * v[c] for c in range(3)) for r in range(3))


def compose(scene, frame=None):
    """World heads from the local transforms, parent first (Kei axes)."""
    rot, pos = {}, {}
    for i, b in enumerate(scene.bones):
        q = b.rotation if frame is None else scene.animation.rotations[frame][i]
        t = b.translation if frame is None else scene.animation.translations[frame][i]
        m = quat_matrix(q)
        if b.parent is None:
            rot[b.name], pos[b.name] = m, t
        else:
            pm = rot[b.parent]
            rot[b.name] = [[sum(pm[r][k] * m[k][c] for k in range(3)) for c in range(3)] for r in range(3)]
            off = mat_vec(pm, t)
            pos[b.name] = tuple(pos[b.parent][k] + off[k] for k in range(3))
    return pos


def test_the_skeleton_names_parents_and_rest():
    ch = load_character("kei")
    s = build_scene(ch)
    assert [b.name for b in s.bones] == list(ALL_BONES)
    assert all(b.parent == PARENTS[b.name] for b in s.bones)
    B = skeleton(rest_pose(ch), ch.proportions)
    for b in s.bones:
        assert math.dist(b.head, B[b.name].head) < 1e-12
        assert b.frame == B[b.name].frame
    pos = compose(s)
    assert max(math.dist(pos[n], B[n].head) for n in pos) < 1e-9
    assert s.axes.startswith("Kei world") and s.units == "metres"


def test_meshes_materials_and_binding():
    ch = load_character("keira")
    s = build_scene(ch, emission=0.3)
    parts = pose_mesh(ch, rest_pose(ch))
    assert len(s.meshes) == len(parts)
    for m, p in zip(s.meshes, parts):
        assert m.bone == p.bone and m.material == p.material and m.vertices == p.verts and m.triangles == p.tris
    mats = {m.name: m for m in s.materials}
    assert set(mats) == {"body", "joint", "emission"}
    assert mats["emission"].emission_strength == 0.3 and mats["body"].emission_strength == 0.0
    assert mats["body"].colour == ch.materials["body"]


def test_the_animation_reproduces_the_rig():
    ch = load_character("kei")
    s = build_scene(ch, shot=SHOT, mode="linear")
    a = s.animation
    assert a.fps == 30 and len(a.rotations) == len(a.translations) == 5
    frames = bake({**SHOT, "props": {"proportions": ch.proportions}}, "linear")
    for f in range(5):
        pos = compose(s, f)
        B = skeleton(frames[f]["pose"], ch.proportions)
        assert max(math.dist(pos[n], B[n].head) for n in pos) < 1e-9
    assert a.root_translations == [t[0] for t in a.translations]


def test_no_shot_no_animation():
    assert build_scene(load_character("kei")).animation is None
