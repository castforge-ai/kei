"""Reading outside models: glTF/GLB and binary FBX into Kei's world (x the character's right, y up, z forward, m)."""
import base64
import json
import struct

import pytest

from kei.characters import load_character, rest_skeleton
from kei.export_fbx import export_fbx
from kei.export_gltf import export_glb
from kei.fbx import Node, P, fbx_file
from kei.models.model import ModelError, read_model


def _height(model):
    ys = [v[1] for v in model.all_verts()]
    return max(ys) - min(ys)


@pytest.mark.parametrize("fmt", ["glb", "fbx"])
def test_kei_s_own_export_reads_back_with_its_skeleton_where_it_was(tmp_path, fmt):
    kei = load_character("kei")
    path = tmp_path / f"kei.{fmt}"
    (export_glb if fmt == "glb" else export_fbx)(kei, path, 1.0, None, "spline")
    m = read_model(path)
    assert m.rigged
    assert abs(_height(m) - 1.71) < 0.03
    rest = rest_skeleton(kei)
    joints = {j.name: j for j in m.joints}
    for name in ("hand_l", "hand_r", "foot_l", "head", "pelvis"):
        assert max(abs(a - b) for a, b in zip(joints[name].head, rest[name].head)) < 1e-3, name
    assert joints["hand_l"].head[0] < -0.1          # the left hand on the character's left (Kei's -x)
    assert joints["hand_l"].parent == "lowerarm_l"
    for mesh in m.meshes:
        for w in mesh.skin:
            assert abs(sum(x for _, x in w) - 1) < 1e-6


def _quad_fbx(path, up=1, front=2, front_sign=1, unit=1.0, translate=(0.0, 50.0, 0.0), coord_sign=1,
              rotation_order=None):
    """One square, 20 x 20 file units, facing +z, on a model moved by `translate` (file units). UnitScaleFactor is
    centimetres per file unit: 1 is a centimetre file."""
    def p70(*ps):
        return Node("Properties70", [], [Node("P", list(x)) for x in ps])
    gs = Node("GlobalSettings", [], [Node("Version", [1000]), p70(
        ("UpAxis", "int", "Integer", "", up), ("UpAxisSign", "int", "Integer", "", 1),
        ("FrontAxis", "int", "Integer", "", front), ("FrontAxisSign", "int", "Integer", "", front_sign),
        ("CoordAxis", "int", "Integer", "", 0), ("CoordAxisSign", "int", "Integer", "", coord_sign),
        ("UnitScaleFactor", "double", "Number", "", unit))])
    verts = [-10.0, 0.0, 0.0, 10.0, 0.0, 0.0, 10.0, 20.0, 0.0, -10.0, 20.0, 0.0]
    geo = Node("Geometry", [P("L", 10), "quad\x00\x01Geometry", "Mesh"], [
        Node("Vertices", [P("d", verts)]), Node("PolygonVertexIndex", [P("i", [0, 1, 2, -4])])])
    extra = [("RotationOrder", "enum", "", "", rotation_order)] if rotation_order is not None else []
    model = Node("Model", [P("L", 11), "quad\x00\x01Model", "Mesh"], [p70(
        ("Lcl Translation", "Lcl Translation", "", "A", *translate), *extra)])
    mat = Node("Material", [P("L", 12), "red\x00\x01Material", ""], [p70(
        ("DiffuseColor", "Color", "", "A", 1.0, 0.0, 0.0))])
    conn = Node("Connections", [], [Node("C", ["OO", P("L", 11), P("L", 0)]), Node("C", ["OO", P("L", 10), P("L", 11)]),
                                    Node("C", ["OO", P("L", 12), P("L", 11)])])
    path.write_bytes(fbx_file([gs, Node("Objects", [], [geo, model, mat]), conn]))
    return path


def test_an_fbx_in_centimetres_reads_in_metres_with_its_model_transform(tmp_path):
    m = read_model(_quad_fbx(tmp_path / "q.fbx"))
    assert len(m.meshes) == 1 and len(m.meshes[0].tris) == 2
    ys = sorted({round(v[1], 6) for v in m.meshes[0].verts})
    assert ys == [0.5, 0.7]
    assert m.meshes[0].colour == "#FF0000"
    assert not m.rigged


def test_triangles_still_face_out_after_the_mirror(tmp_path):
    """The quad faces +z in the file (counter-clockwise from +z); in Kei's world it still faces +z."""
    mesh = read_model(_quad_fbx(tmp_path / "q.fbx")).meshes[0]
    for a, b, c in mesh.tris:
        v0, v1, v2 = mesh.verts[a], mesh.verts[b], mesh.verts[c]
        e1 = [v1[i] - v0[i] for i in range(3)]
        e2 = [v2[i] - v0[i] for i in range(3)]
        assert e1[0] * e2[1] - e1[1] * e2[0] > 0      # the normal's z


def test_a_z_up_fbx_stands_up(tmp_path):
    """Up is the file's z, the front its -y: the square, drawn in the file's x-y plane, lies on the ground."""
    m = read_model(_quad_fbx(tmp_path / "z.fbx", up=2, front=1, front_sign=-1, translate=(0.0, 0.0, 0.0)))
    ys = {round(v[1], 6) for v in m.meshes[0].verts}
    assert ys == {0.0}
    zs = sorted({round(v[2], 6) for v in m.meshes[0].verts})
    assert zs == [-0.2, 0.0]                           # the file's +y is the back


def test_a_gltf_with_an_embedded_buffer_reads(tmp_path):
    pos = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"mesh": 0, "translation": [0, 2, 0]}],
           "meshes": [{"name": "tri", "primitives": [{"attributes": {"POSITION": 0}}]}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
           "bufferViews": [{"buffer": 0, "byteLength": 36}],
           "buffers": [{"byteLength": 36, "uri": "data:application/octet-stream;base64," +
                        base64.b64encode(pos).decode()}]}
    path = tmp_path / "t.gltf"
    path.write_text(json.dumps(doc))
    m = read_model(path)
    assert sorted(v[1] for v in m.meshes[0].verts) == [2.0, 2.0, 3.0]
    assert sorted(v[0] for v in m.meshes[0].verts) == [-1.0, 0.0, 0.0]   # glTF's +x is the character's left


def test_a_file_that_is_no_model_is_refused_by_name(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hello")
    with pytest.raises(ModelError, match="notes.txt"):
        read_model(p)
