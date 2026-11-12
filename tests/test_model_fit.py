"""Fitting Kei's skeleton to an unrigged humanoid: Kei's and Keira's own meshes, with their joints known, are the
fixtures."""
import math

import pytest

from kei.characters import load_character, rest_pose
from kei.characters.mesh import pose_mesh
from kei.models.fit import fit_rig, humanoid_or_raise, landmarks, normalise, shells
from kei.models.model import MeshData, Model, ModelError
from kei.rig import solve

JOINTS = ("thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r", "upperarm_l", "upperarm_r", "lowerarm_l",
          "lowerarm_r", "hand_l", "hand_r", "neck_01", "head")


def _own(name, f=None):
    ch = load_character(name)
    parts = pose_mesh(ch, rest_pose(ch))
    meshes = [MeshData(str(i), [f(v) if f else v for v in p.verts], p.tris) for i, p in enumerate(parts)]
    return ch, Model(meshes, [], name)


def _box(c, r):
    vs = [(c[0] + sx * r[0], c[1] + sy * r[1], c[2] + sz * r[2]) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    tris = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6), (0, 2, 6),
            (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    return MeshData("box", vs, tris)


@pytest.mark.parametrize("name", ["kei", "keira"])
def test_the_fitted_rig_puts_its_joints_on_the_character_s_own(name):
    ch, model = _own(name)
    n = normalise(model, ch.height)
    P, rest, report = fit_rig(landmarks(n), ch.height)
    got, true = solve(rest, P), solve(rest_pose(ch), ch.proportions)
    shift = [got["foot_l"][k] - true["foot_l"][k] for k in range(3)]    # the model's placement is free; compare shapes
    for j in JOINTS:
        moved = tuple(got[j][k] - shift[k] for k in range(3))
        assert math.dist(moved, true[j]) < 0.03, (j, moved, true[j])
    assert report["largest"] < 0.025      # the trunk stays neutral at rest, so the neck and shoulders fit to ~2 cm


def test_a_model_facing_back_is_turned_to_face_forward():
    ch, model = _own("kei", lambda v: (-v[0], v[1], -v[2]))
    n = normalise(model, 1.71)
    marks = landmarks(n)
    assert marks["toe_l"][2] - marks["foot_l"][2] > 0.1           # the toes point to +z
    assert marks["hand_l"][0] < 0 < marks["hand_r"][0]            # the left hand on the character's left


def test_a_one_metre_model_off_the_ground_is_scaled_and_stood_on_it():
    ch, model = _own("kei", lambda v: (v[0] / 1.71, v[1] / 1.71 + 5.0, v[2] / 1.71))
    n = normalise(model, 1.71)
    ys = [v[1] for v in n.all_verts()]
    assert abs(min(ys)) < 1e-9 and abs(max(ys) - 1.71) < 1e-9


def test_a_side_on_model_is_turned_a_quarter():
    ch, model = _own("kei", lambda v: (v[2], v[1], -v[0]))
    n = normalise(model, 1.71)
    xs = [v[0] for v in n.all_verts()]
    zs = [v[2] for v in n.all_verts()]
    assert max(xs) - min(xs) > max(zs) - min(zs)
    humanoid_or_raise(n)


def test_a_figure_on_four_legs_is_refused_naming_the_general_rig():
    legs = [_box((x, 0.4, z), (0.05, 0.4, 0.05)) for x in (-0.3, 0.3) for z in (-0.3, 0.3)]
    table = Model(legs + [_box((0, 0.9, 0), (0.35, 0.1, 0.35))], [], "table")
    with pytest.raises(ModelError, match="plan 3e"):
        humanoid_or_raise(normalise(table, 1.0))


def test_a_body_longer_than_it_is_tall_is_refused_naming_the_general_rig():
    dog = Model([_box((0, 0.5, 0), (0.2, 0.25, 0.8))], [], "dog")
    with pytest.raises(ModelError, match="plan 3e"):
        humanoid_or_raise(normalise(dog, 1.0))


def test_pieces_split_at_a_texture_seam_stay_one_piece():
    a = _box((0, 0, 0), (1, 1, 1))
    # the same box with its last face's vertices duplicated, as a texture seam stores them
    verts = a.verts + [a.verts[1], a.verts[7], a.verts[3]]
    tris = a.tris[:-1] + [(8, 9, 10)]
    assert len(shells(MeshData("seam", verts, tris))) == 1
    two = MeshData("two", a.verts + [(v[0] + 5, v[1], v[2]) for v in a.verts],
                   a.tris + [(i + 8, j + 8, k + 8) for i, j, k in a.tris])
    assert len(shells(two)) == 2


def test_a_knee_behind_the_hip_to_ankle_line_is_fitted_on_the_line():
    """Kei's rig bends its knees forward. A model standing with its knees pushed back gets a straight leg, so the
    rig's knee is off by the knee's distance from the line, not twice that on the wrong side."""
    ch, model = _own("kei")
    marks = landmarks(normalise(model, 1.71))
    for s in "lr":
        hip, ankle = marks[f"thigh_{s}"], marks[f"foot_{s}"]
        mid = tuple(hip[k] + (ankle[k] - hip[k]) * 0.5 for k in range(3))
        marks[f"calf_{s}"] = (mid[0], mid[1], mid[2] - 0.03)        # 3 cm behind the line
    P, rest, report = fit_rig(marks, 1.71)
    assert report["errors"]["calf_l"] < 0.045 and report["errors"]["calf_r"] < 0.045     # 0.06 when mirrored


def test_a_t_posed_model_is_asked_for_in_an_a_pose():
    """The fitter follows the arms down from the armpits, so it needs them hanging apart from the body."""
    kei = load_character("kei")
    pose = {**rest_pose(kei), "armL": [0, 1.5, 0], "armR": [0, 1.5, 0], "elbowL": [0, 0], "elbowR": [0, 0]}
    model = Model([MeshData(str(i), p.verts, p.tris) for i, p in enumerate(pose_mesh(kei, pose))], [], "t")
    with pytest.raises(ModelError) as e:
        landmarks(normalise(model, 1.71))
    assert "A-pose" in str(e.value) and "does not read T-poses" in str(e.value)


def test_a_head_carried_forward_of_the_chest_keeps_the_neck_on_the_neck():
    """The neck's base and the head's joint sit in the middle of the neck at their own heights, not on the line of
    the narrowest slice, so a forward head does not pull the top of the spine forward."""
    kei = load_character("keira")
    pose = {**rest_pose(kei), "neck": [0.5, 0, 0], "head": [-0.4, 0, 0]}
    parts = pose_mesh(kei, pose)
    model = Model([MeshData(str(i), p.verts, p.tris) for i, p in enumerate(parts)], [], "forward head")
    n = normalise(model, kei.height)
    marks = landmarks(n)
    true = solve(pose, kei.proportions)
    shift = [marks["foot_l"][k] - true["foot_l"][k] for k in range(3)]
    for j in ("neck_01", "head"):
        got = tuple(marks[j][k] - shift[k] for k in range(3))
        assert abs(got[2] - true[j][2]) < 0.02, (j, got, true[j])


def test_the_fitted_rest_keeps_the_trunk_neutral_so_animation_starts_from_the_sculpt():
    """Kei's shots set the spine, neck, head and clavicles as absolute angles, with 0 as the neutral stance. fit_rig
    leaves the neck, head and clavicles at 0 and stands an upright trunk at 0; the neck's rest pitch is the
    importer's (kei.models.fit.stack_head), from the mesh, since 2026-11-02."""
    kei = load_character("keira")
    pose = {**rest_pose(kei), "neck": [0.5, 0, 0], "head": [-0.4, 0, 0]}
    model = Model([MeshData(str(i), p.verts, p.tris) for i, p in enumerate(pose_mesh(kei, pose))], [], "forward head")
    P, rest, report = fit_rig(landmarks(normalise(model, kei.height)), kei.height)
    for c in ("neck", "head", "clavL", "clavR"):
        assert all(abs(x) < 1e-9 for x in rest.get(c, [0, 0, 0])), (c, rest.get(c))
    assert abs(rest["spine"][0]) < 0.05                   # the trunk itself stands upright



def test_a_sculpt_leaning_back_is_bound_with_its_lean_so_a_shot_stands_it_upright():
    """A model whose trunk leans back as it was made gets that lean as its rest spine pitch, so a shot's spine at 0
    (Kei's upright) stands it up instead of keeping it back."""
    kei = load_character("keira")
    pose = {**rest_pose(kei), "spine": [-0.15, 0, 0]}
    model = Model([MeshData(str(i), p.verts, p.tris) for i, p in enumerate(pose_mesh(kei, pose))], [], "leaning back")
    P, rest, report = fit_rig(landmarks(normalise(model, kei.height)), kei.height)
    own = fit_rig(landmarks(normalise(_own("keira")[1], kei.height)), kei.height)[1]["spine"][0]
    assert -0.15 <= rest["spine"][0] - own <= -0.05, (rest["spine"], own)    # its back line's own angle
