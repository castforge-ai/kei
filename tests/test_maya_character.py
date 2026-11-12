"""Task 2 of plan 6: Kei's own characters in Maya. The job is plain JSON built from kei.export_scene (no Maya needed);
the Maya half loads it with mayapy and is skipped, with the reason, where Maya is not installed."""
import math

import pytest

from kei.apps.maya_scene import character_job
from kei.apps.maya_side import kei_math as km
from kei.characters import load_character, rest_skeleton
from kei.rig import ALL_BONES, PARENTS

import mayakit


def _world(job):
    """Each bone's world rotation and position, composed from the job's local translate and joint orient."""
    out = {}
    for b in job["bones"]:
        R = km.euler_matrix([math.radians(a) for a in b["orient"]], "xyz")
        if b["parent"] is None:
            out[b["name"]] = (R, tuple(b["translate"]))
        else:
            PR, Pp = out[b["parent"]]
            p = km.apply(PR, b["translate"])
            out[b["name"]] = (km.mul(PR, R), tuple(Pp[i] + p[i] for i in range(3)))
    return out


@pytest.mark.parametrize("name", ["kei", "keira"])
def test_the_job_holds_every_bone_in_the_mannequin_hierarchy(name):
    job = character_job(name)
    assert [b["name"] for b in job["bones"]] == list(ALL_BONES)
    assert all(b["parent"] == PARENTS[b["name"]] for b in job["bones"])
    assert job["units"] == "m" and job["character"] == name


@pytest.mark.parametrize("name", ["kei", "keira"])
def test_the_bones_compose_to_the_rest_skeleton_mirrored(name):
    job = character_job(name)
    world = _world(job)
    rest = rest_skeleton(load_character(name))
    for n in ALL_BONES:
        R, p = world[n]
        assert all(abs(a - b) < 1e-9 for a, b in zip(p, km.mirror_point(rest[n].head))), n
        want = km.mirror_frame(rest[n].frame)
        assert all(abs(R[r][c] - want[r][c]) < 1e-9 for r in range(3) for c in range(3)), n


def test_meshes_are_one_per_material_with_one_bone_per_vertex_and_outward_winding():
    job = character_job("kei")
    assert [m["material"] for m in job["meshes"]] == ["body", "joint", "emission"]
    names = [b["name"] for b in job["bones"]]
    for m in job["meshes"]:
        n = len(m["points"])
        assert len(m["normals"]) == n and len(m["bone"]) == n
        assert all(0 <= i < len(names) for i in m["bone"])
        assert all(0 <= i < n for tri in m["triangles"] for i in tri)
    # the mirror flips the winding, so the job reverses each triangle to keep the faces outward
    m = job["meshes"][0]
    a, b, c = (m["points"][i] for i in m["triangles"][0])
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    nrm = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    vn = m["normals"][m["triangles"][0][0]]
    assert sum(nrm[i] * vn[i] for i in range(3)) > 0


def test_emission_zero_turns_the_glow_off():
    on = {m["name"]: m for m in character_job("kei", emission=1.0)["materials"]}
    off = {m["name"]: m for m in character_job("kei", emission=0.0)["materials"]}
    assert on["emission"]["emission_strength"] == 1.0
    assert off["emission"]["emission_strength"] == 0.0


def test_an_unknown_character_is_refused_by_name():
    with pytest.raises(ValueError, match="nobody"):
        character_job("nobody")


# ---------------- in Maya ----------------
@pytest.fixture(scope="module")
def loaded():
    return mayakit.run_script("check_character.py")


@pytest.mark.maya
@pytest.mark.parametrize("name", ["kei", "keira"])
@pytest.mark.parametrize("unit", ["cm", "m"])
def test_in_maya_every_bone_is_a_joint_with_its_parent_at_the_rest_pose(loaded, name, unit):
    r = loaded[f"{name}_{unit}"]
    job = character_job(name)
    rest = rest_skeleton(load_character(name))
    assert r["joint_parents"] == {b["name"]: b["parent"] for b in job["bones"]}
    for n in ALL_BONES:
        got = r["joints_m"][n]
        want = km.mirror_point(rest[n].head)
        assert max(abs(a - b) for a, b in zip(got, want)) < 0.001, (unit, n, got, want)


@pytest.mark.maya
def test_in_maya_every_vertex_is_skinned_to_exactly_its_bone(loaded):
    r = loaded["kei_cm"]
    assert r["skin_mismatches"] == 0
    assert r["vertex_count"] == sum(len(m["points"]) for m in character_job("kei")["meshes"])


@pytest.mark.maya
def test_in_maya_the_materials_match_and_emission_zero_is_off(loaded):
    on, off = loaded["kei_cm"]["materials"], loaded["kei_off"]["materials"]
    assert sorted(on) == ["body", "emission", "joint"]
    assert on["emission"]["emission"] > 0.99 and off["emission"]["emission"] == 0.0
    job = {m["name"]: m for m in character_job("kei")["materials"]}
    for name, m in on.items():
        want = [int(job[name]["colour"][i:i + 2], 16) / 255 for i in (1, 3, 5)]
        assert max(abs(a - b) for a, b in zip(m["colour_srgb"], want)) < 0.01, name


@pytest.mark.maya
def test_in_maya_the_character_sits_in_its_namespace_with_the_top_node_tags(loaded):
    r = loaded["kei_cm"]
    assert r["top"] == "kei:kei_rig"
    assert r["tags"] == {"kei_character": "kei", "kei_units": "cm"}
