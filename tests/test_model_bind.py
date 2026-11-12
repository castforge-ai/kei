"""Binding an imported mesh to Kei's bones: rigid by piece where a piece belongs to one bone, smooth weights where it
spans several, and a rigged model's own weights carried over by bone name."""
import math

import pytest

from kei.characters import load_character, rest_skeleton
from kei.models.bind import bind_mesh, bind_rigged, map_bones
from kei.models.model import Joint, MeshData, Model

KEI = rest_skeleton(load_character("kei"))


def _tube(a, b, r, rings=10, sides=6, name="tube"):
    """A closed tube from a to b of radius r: rings of vertices, so a weight can change along it."""
    ax = [b[k] - a[k] for k in range(3)]
    n = math.sqrt(sum(c * c for c in ax))
    ax = [c / n for c in ax]
    h = (1.0, 0.0, 0.0) if abs(ax[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = [ax[1] * h[2] - ax[2] * h[1], ax[2] * h[0] - ax[0] * h[2], ax[0] * h[1] - ax[1] * h[0]]
    un = math.sqrt(sum(c * c for c in u))
    u = [c / un for c in u]
    w = [ax[1] * u[2] - ax[2] * u[1], ax[2] * u[0] - ax[0] * u[2], ax[0] * u[1] - ax[1] * u[0]]
    verts, tris = [], []
    for i in range(rings):
        t = i / (rings - 1)
        c = [a[k] + (b[k] - a[k]) * t for k in range(3)]
        for j in range(sides):
            ang = 2 * math.pi * j / sides
            verts.append(tuple(c[k] + r * (math.cos(ang) * u[k] + math.sin(ang) * w[k]) for k in range(3)))
    for i in range(rings - 1):
        for j in range(sides):
            p, q = i * sides + j, i * sides + (j + 1) % sides
            tris += [(p, q, q + sides), (p, q + sides, p + sides)]
    return MeshData(name, verts, tris)


def _ball(c, r):
    return _tube((c[0], c[1] - r, c[2]), (c[0], c[1] + r, c[2]), r, rings=4, sides=8, name="ball")


def _mid(a, b, t=0.5):
    return tuple(a[k] + (b[k] - a[k]) * t for k in range(3))


def test_a_piece_around_the_forearm_binds_rigidly_to_the_forearm():
    b = KEI["lowerarm_r"]
    parts = bind_mesh(_tube(_mid(b.head, b.tail, 0.2), _mid(b.head, b.tail, 0.8), 0.03), KEI, 1.71)
    assert [(p.bone, p.skin) for p in parts] == [("lowerarm_r", None)]


def test_a_ball_on_the_elbow_goes_to_the_child_bone():
    parts = bind_mesh(_ball(KEI["lowerarm_r"].head, 0.03), KEI, 1.71)
    assert [p.bone for p in parts] == ["lowerarm_r"]


def test_a_piece_around_the_hips_goes_to_the_pelvis():
    root, hip_l, hip_r = KEI["pelvis"].head, KEI["thigh_l"].head, KEI["thigh_r"].head
    parts = bind_mesh(_tube((hip_l[0] - 0.04, root[1] - 0.03, 0), (hip_r[0] + 0.04, root[1] - 0.03, 0), 0.06), KEI, 1.71)
    assert [p.bone for p in parts] == ["pelvis"]


def test_one_piece_for_the_whole_arm_gets_smooth_weights_along_it():
    sh, wr = KEI["upperarm_r"].head, KEI["hand_r"].head
    parts = bind_mesh(_tube(sh, wr, 0.035, rings=12), KEI, 1.71)
    assert len(parts) == 1 and parts[0].skin is not None
    skin = parts[0].skin
    for w in skin:
        assert abs(sum(x for _, x in w) - 1) < 1e-9 and len(w) <= 4
    top, bottom = dict(skin[0]), dict(skin[-1])
    assert max(top, key=top.get) == "upperarm_r"
    assert max(bottom, key=bottom.get) == "lowerarm_r"


@pytest.mark.parametrize("name, kei", [
    ("upperarm_l", "upperarm_l"), ("mixamorig:LeftForeArm", "lowerarm_l"), ("mixamorig:RightUpLeg", "thigh_r"),
    ("mixamorig:Hips", "pelvis"), ("mixamorig:LeftHandIndex2", "index_02_l"), ("L_Elbow", "lowerarm_l"),
    ("forearm.L", "lowerarm_l"), ("Bip01 R Thigh", "thigh_r"), ("DEF-shin.R", "calf_r"), ("Head", "head"),
    ("RightToeBase", "ball_r"), ("thumb_03_r", "thumb_03_r"),
])
def test_bone_names_from_the_common_families_map_to_kei_s(name, kei):
    mapping, unmapped = map_bones([name])
    assert mapping == {name: kei} and unmapped == []


def test_a_bone_kei_has_no_place_for_is_listed_unmapped():
    mapping, unmapped = map_bones(["mixamorig:LeftUpLeg", "LeftUpLegTwist_01", "tail_03"])
    assert mapping == {"mixamorig:LeftUpLeg": "thigh_l"} and unmapped == ["LeftUpLegTwist_01", "tail_03"]


def test_a_rigged_model_s_weights_on_an_unmapped_bone_go_to_its_mapped_parent():
    joints = [Joint("Hips", None, (0, 0.9, 0)), Joint("LeftUpLeg", "Hips", (-0.1, 0.88, 0)),
              Joint("LeftUpLegTwist_01", "LeftUpLeg", (-0.11, 0.7, 0))]
    mesh = MeshData("leg", [(-0.1, 0.7, 0), (-0.1, 0.6, 0), (-0.12, 0.65, 0.02)], [(0, 1, 2)],
                    skin=[[("LeftUpLegTwist_01", 1.0)], [("LeftUpLegTwist_01", 0.5), ("LeftUpLeg", 0.5)],
                          [("Hips", 1.0)]])
    model = Model([mesh], joints, "rigged")
    mapping, _ = map_bones([j.name for j in joints])
    parts = bind_rigged(model, mapping)
    assert len(parts) == 1
    assert [dict(w) for w in parts[0].skin] == [{"thigh_l": 1.0}, {"thigh_l": 1.0}, {"pelvis": 1.0}]


@pytest.mark.parametrize("names, want", [
    (["L_Hip", "R_Hip"], {"L_Hip": "thigh_l", "R_Hip": "thigh_r"}),
    (["lCollar", "lShldr"], {"lCollar": "clavicle_l", "lShldr": "upperarm_l"}),
    (["mixamorig:LeftShoulder", "mixamorig:LeftArm"],
     {"mixamorig:LeftShoulder": "clavicle_l", "mixamorig:LeftArm": "upperarm_l"}),
])
def test_hips_and_a_collar_beside_a_shoulder_map_apart(names, want):
    mapping, _ = map_bones(names)
    assert mapping == want


def test_a_piece_on_the_front_of_the_hip_stays_with_the_pelvis():
    """A plate at the height of the hip joint, in front of it, is part of the pelvis: on the thigh it would swing out
    sideways with every step."""
    hip = KEI["thigh_r"].head
    c = (hip[0] + 0.03, hip[1] + 0.005, hip[2] + 0.06)
    parts = bind_mesh(_ball(c, 0.035), KEI, 1.71)
    assert [(p.bone, p.skin) for p in parts] == [("pelvis", None)]
