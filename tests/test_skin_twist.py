"""Smooth skin at a twist: dual quaternion skinning keeps a twisting forearm's volume where linear blending collapses
it to a candy wrap; at rest and on one bone the two agree."""
import math
from types import SimpleNamespace as B

from kei.characters.mesh import Part, _local, _local_dir, _skinned, bone_dq, dq_point

I = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def twist(a):
    """A frame turned by a about its Y axis (the bone's length): the forearm's pronation."""
    c, s = math.cos(a), math.sin(a)
    return ((c, 0.0, -s), (0.0, 1.0, 0.0), (s, 0.0, c))


def tube(rest):
    """A ring of a tube of radius 1 cm around the y axis at y = 0.1, half on the forearm, half on the hand."""
    verts = [(0.01 * math.cos(2 * math.pi * i / 16), 0.1, 0.01 * math.sin(2 * math.pi * i / 16)) for i in range(16)]
    normals = [(v[0] / 0.01, 0.0, v[2] / 0.01) for v in verts]
    skin = [[(n, 0.5, _local(rest[n], v), _local_dir(rest[n], nv)) for n in ("lowerarm", "hand")]
            for v, nv in zip(verts, normals)]
    return Part("lowerarm", "body", verts, normals, [], -1, skin)


def radius(part):
    return min(math.hypot(v[0], v[2]) for v in part.verts)


REST = {"lowerarm": B(head=(0.0, 0.0, 0.0), frame=I), "hand": B(head=(0.0, 0.2, 0.0), frame=I)}


def test_a_twisted_wrist_keeps_its_volume():
    p = tube(REST)
    pose = {"lowerarm": REST["lowerarm"], "hand": B(head=(0.0, 0.2, 0.0), frame=twist(math.radians(150)))}
    linear, dq = _skinned(p, pose), _skinned(p, pose, REST)
    assert radius(linear) < 0.004            # linear blending: the ring shrinks to cos(75 deg) of its radius
    assert abs(radius(dq) - 0.01) < 1e-6     # dual quaternions: the ring turns halfway and keeps its radius


def test_at_rest_and_on_one_bone_both_ways_agree():
    p = tube(REST)
    for a, b in zip(_skinned(p, REST, REST).verts, p.verts):
        assert math.dist(a, b) < 1e-12
    pose = {"lowerarm": B(head=(0.1, 0.0, 0.3), frame=twist(0.7)), "hand": B(head=(0.1, 0.2, 0.3), frame=twist(0.7))}
    for a, b in zip(_skinned(p, pose, REST).verts, _skinned(p, pose).verts):     # both bones move as one
        assert math.dist(a, b) < 1e-9


def test_a_bone_move_as_a_dual_quaternion_moves_a_point_as_the_bone_does():
    rest = B(head=(0.0, 1.0, 0.0), frame=I)
    pose = B(head=(0.3, 1.2, -0.1), frame=twist(1.1))
    x = (0.05, 1.3, 0.02)
    moved, _ = dq_point(bone_dq(rest, pose), x)
    F = pose.frame
    local = [x[i] - rest.head[i] for i in range(3)]
    want = tuple(pose.head[r] + sum(F[a][r] * local[a] for a in range(3)) for r in range(3))
    assert math.dist(moved, want) < 1e-12


def test_kei_renders_blend_linearly_unless_asked():
    """The default plays a skin as Maya, Unreal and the engines do; KEI_SKINNING picks dual quaternions."""
    import pytest
    from kei.characters import mesh
    assert mesh.skinning_from({}) == "linear"
    assert mesh.skinning_from({"KEI_SKINNING": "dual_quaternion"}) == "dual_quaternion"
    with pytest.raises(ValueError, match="KEI_SKINNING"):
        mesh.skinning_from({"KEI_SKINNING": "lbs"})


def test_the_fbx_declares_the_skinning(monkeypatch):
    from fbxread import read_fbx
    from kei.characters import load_character, mesh
    from kei.export_fbx import build_fbx

    def skin_type():
        _, top = read_fbx(build_fbx(load_character("kei")))
        objs = next(n for n in top if n.name == "Objects").children
        d = next(o for o in objs if o.name == "Deformer" and o.props[2] == "Skin")
        return d.find("SkinningType").props[0]
    assert skin_type() == "Linear"
    monkeypatch.setattr(mesh, "SKINNING", "dual_quaternion")
    assert skin_type() == "DualQuaternion"
