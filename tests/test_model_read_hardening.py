"""Model files are untrusted: a bad or hostile file is refused with a ModelError, never followed outside its folder,
never left looping, never answered with a traceback."""
import base64
import json
import pathlib
import random
import struct

import pytest

from kei.characters import load_character, rest_pose
from kei.characters.mesh import pose_mesh
from kei.export_fbx import export_fbx
from kei.export_gltf import export_glb
from kei.fbx import Node, P, fbx_file
from kei.models.fit import normalise
from kei.models.model import ModelError, read_model
from test_model_read import _quad_fbx

TRI = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)


def _gltf(tmp_path, uri=None, extra=None, name="t.gltf"):
    buf = {"byteLength": 36}
    if uri is not None:
        buf["uri"] = uri
    doc = {"asset": {"version": "2.0"}, "nodes": [{"mesh": 0}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
           "bufferViews": [{"buffer": 0, "byteLength": 36}], "buffers": [buf]}
    for k, v in (extra or {}).items():
        doc[k] = v
    p = tmp_path / name
    p.write_text(json.dumps(doc))
    return p


@pytest.mark.parametrize("uri", ["//host/share/x.bin", "\\\\host\\share\\x.bin", "C:/x.bin", "c:x.bin",
                                 "file:///x.bin", "http://host/x.bin", "..%2Fx.bin", "/x.bin", "\\x.bin",
                                 "sub/../../x.bin", "sub/%2E%2E/%2E%2E/x.bin"])
def test_a_buffer_outside_the_model_s_folder_is_refused_before_any_path_is_touched(tmp_path, monkeypatch, uri):
    touched = []
    real = pathlib.Path.resolve
    monkeypatch.setattr(pathlib.Path, "resolve", lambda self, *a, **k: touched.append(str(self)) or real(self, *a, **k))
    with pytest.raises(ModelError, match="buffer"):
        read_model(_gltf(tmp_path, uri))
    assert not [t for t in touched if "x.bin" in t]


def test_a_buffer_beside_the_model_still_reads(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "x.bin").write_bytes(TRI)
    assert len(read_model(_gltf(tmp_path, "bin/x.bin")).meshes[0].verts) == 3


def test_a_data_uri_with_no_comma_is_refused(tmp_path):
    with pytest.raises(ModelError):
        read_model(_gltf(tmp_path, "data:application/octet-stream;base64"))


def test_a_gltf_joint_cycle_is_refused(tmp_path):
    uri = "data:application/octet-stream;base64," + base64.b64encode(TRI).decode()
    p = _gltf(tmp_path, uri, {"nodes": [{"mesh": 0, "skin": 0}, {"children": [2]}, {"children": [1]}],
                              "skins": [{"joints": [1, 2]}]})
    with pytest.raises(ModelError, match="cycle"):
        read_model(p)


def test_an_accessor_larger_than_its_buffer_is_refused(tmp_path):
    uri = "data:application/octet-stream;base64," + base64.b64encode(TRI).decode()
    p = _gltf(tmp_path, uri, {"accessors": [{"componentType": 5126, "count": 10 ** 9, "type": "VEC3"}]})
    with pytest.raises(ModelError):
        read_model(p)


def test_a_triangle_index_past_the_vertices_is_refused(tmp_path):
    data = TRI + struct.pack("<3I", 0, 1, 7)
    uri = "data:application/octet-stream;base64," + base64.b64encode(data).decode()
    p = _gltf(tmp_path, uri, {
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
                      {"bufferView": 1, "componentType": 5125, "count": 3, "type": "SCALAR"}],
        "bufferViews": [{"buffer": 0, "byteLength": 36}, {"buffer": 0, "byteOffset": 36, "byteLength": 12}],
        "buffers": [{"byteLength": 48, "uri": uri}]})
    with pytest.raises(ModelError, match="index"):
        read_model(p)


def test_a_sparse_accessor_is_read_with_a_warning(tmp_path):
    uri = "data:application/octet-stream;base64," + base64.b64encode(TRI).decode()
    p = _gltf(tmp_path, uri, {"accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                                             "sparse": {"count": 1}}]})
    assert any("sparse" in w for w in read_model(p).warnings)


def test_a_draco_compressed_gltf_is_refused_by_name(tmp_path):
    p = _gltf(tmp_path, None, {"extensionsRequired": ["KHR_draco_mesh_compression"]})
    with pytest.raises(ModelError, match="Draco"):
        read_model(p)


# ---------------- FBX ----------------
HEADER = b"Kaydara FBX Binary  \x00\x1a\x00" + struct.pack("<I", 7400)


def test_an_fbx_record_that_does_not_advance_is_refused(tmp_path):
    p = tmp_path / "loop.fbx"
    p.write_bytes(HEADER + struct.pack("<IIIB", 27, 0, 0, 1) + b"A" + b"\x00" * 200)
    with pytest.raises(ModelError):
        read_model(p)


def test_an_fbx_array_claiming_too_much_is_refused(tmp_path):
    prop = b"d" + struct.pack("<III", 10 ** 9, 0, 8) + b"\x00" * 8
    rec_len = 13 + 1 + len(prop)
    p = tmp_path / "big.fbx"
    p.write_bytes(HEADER + struct.pack("<IIIB", 27 + rec_len, 1, len(prop), 1) + b"V" + prop + b"\x00" * 200)
    with pytest.raises(ModelError):
        read_model(p)


def test_an_fbx_array_that_inflates_past_its_count_is_refused(tmp_path):
    import zlib
    bomb = zlib.compress(b"\x00" * 50_000_000)
    prop = b"d" + struct.pack("<III", 3, 1, len(bomb)) + bomb
    rec_len = 13 + 1 + len(prop)
    p = tmp_path / "bomb.fbx"
    p.write_bytes(HEADER + struct.pack("<IIIB", 27 + rec_len, 1, len(prop), 1) + b"V" + prop + b"\x00" * 200)
    with pytest.raises(ModelError):
        read_model(p)


def _fbx(objects, connections, gs=None):
    gs = gs or [("UnitScaleFactor", "double", "Number", "", 1.0)]
    return fbx_file([Node("GlobalSettings", [], [Node("Properties70", [], [Node("P", list(x)) for x in gs])]),
                     Node("Objects", [], objects), Node("Connections", [], connections)])


def test_an_fbx_joint_cycle_is_refused(tmp_path):
    joints = [Node("Model", [P("L", i), f"j{i}\x00\x01Model", "LimbNode"], []) for i in (1, 2)]
    geo = Node("Geometry", [P("L", 10), "g\x00\x01Geometry", "Mesh"], [
        Node("Vertices", [P("d", [0.0, 0, 0, 1, 0, 0, 0, 1, 0])]), Node("PolygonVertexIndex", [P("i", [0, 1, -3])])])
    mesh = Node("Model", [P("L", 11), "m\x00\x01Model", "Mesh"], [])
    conn = [Node("C", ["OO", P("L", 1), P("L", 2)]), Node("C", ["OO", P("L", 2), P("L", 1)]),
            Node("C", ["OO", P("L", 11), P("L", 0)]), Node("C", ["OO", P("L", 10), P("L", 11)])]
    p = tmp_path / "cycle.fbx"
    p.write_bytes(_fbx(joints + [geo, mesh], conn))
    with pytest.raises(ModelError, match="cycle"):
        read_model(p)


@pytest.mark.parametrize("verts, poly", [([0.0, 0, 0, 1, 0, 0, 0, 1, 0], [0, 1, -10]),
                                         ([0.0, 0, 0, 1, 0, 0, 0, 1], [0, 1, -3])])
def test_bad_fbx_geometry_is_refused(tmp_path, verts, poly):
    geo = Node("Geometry", [P("L", 10), "g\x00\x01Geometry", "Mesh"], [
        Node("Vertices", [P("d", verts)]), Node("PolygonVertexIndex", [P("i", poly)])])
    mesh = Node("Model", [P("L", 11), "m\x00\x01Model", "Mesh"], [])
    p = tmp_path / "bad.fbx"
    p.write_bytes(_fbx([geo, mesh], [Node("C", ["OO", P("L", 11), P("L", 0)]), Node("C", ["OO", P("L", 10), P("L", 11)])]))
    with pytest.raises(ModelError):
        read_model(p)


def test_a_metre_fbx_reads_in_metres_and_a_bad_unit_falls_back_with_a_warning(tmp_path):
    m = read_model(_quad_fbx(tmp_path / "m.fbx", unit=100.0, translate=(0.0, 0.0, 0.0)))
    ys = [v[1] for v in m.meshes[0].verts]
    assert max(ys) - min(ys) == pytest.approx(20.0)
    bad = read_model(_quad_fbx(tmp_path / "bad.fbx", unit=-3.0, translate=(0.0, 0.0, 0.0)))
    ys = [v[1] for v in bad.meshes[0].verts]
    assert max(ys) - min(ys) == pytest.approx(0.2) and any("UnitScaleFactor" in w for w in bad.warnings)


def test_a_left_handed_fbx_keeps_its_triangles_facing_out(tmp_path):
    """The square is drawn counter-clockwise seen from the file's front. With the right axis on the file's -x the
    file is left-handed, and the square must still face the front (Kei's +z), as it does in a right-handed file."""
    mesh = read_model(_quad_fbx(tmp_path / "lh.fbx", translate=(0.0, 0.0, 0.0), coord_sign=-1)).meshes[0]
    for a, b, c in mesh.tris:
        v0, v1, v2 = mesh.verts[a], mesh.verts[b], mesh.verts[c]
        e1 = [v1[i] - v0[i] for i in range(3)]
        e2 = [v2[i] - v0[i] for i in range(3)]
        assert e1[0] * e2[1] - e1[1] * e2[0] > 0      # the normal's z


def test_a_non_default_rotation_order_warns(tmp_path):
    p = _quad_fbx(tmp_path / "ro.fbx", rotation_order=3)
    assert any("RotationOrder" in w for w in read_model(p).warnings)


@pytest.mark.parametrize("fmt", ["glb", "fbx"])
def test_damaged_files_give_a_model_error_and_nothing_else(tmp_path, fmt):
    good = tmp_path / f"k.{fmt}"
    (export_glb if fmt == "glb" else export_fbx)(load_character("kei"), good, 1.0, None, "spline")
    blob = good.read_bytes()
    rnd = random.Random(7)
    for k in range(30):
        bad = bytearray(blob[:rnd.randrange(30, len(blob))] if k % 2 else blob)
        for _ in range(rnd.randrange(1, 40)):
            bad[rnd.randrange(30, len(bad))] = rnd.randrange(256)
        p = tmp_path / f"bad{k}.{fmt}"
        p.write_bytes(bytes(bad))
        try:
            read_model(p)
        except ModelError:
            pass


# ---------------- left stays left (Review Focus 1) ----------------
def _kei_with_left_block():
    """Kei's rest mesh plus a block on the left hand (Kei's world: the left is -x)."""
    kei = load_character("kei")
    parts = pose_mesh(kei, rest_pose(kei))
    hand = next(p for p in parts if p.bone == "hand_l")
    c = [sum(v[k] for v in hand.verts) / len(hand.verts) for k in range(3)]
    block = [(c[0] + sx * 0.05, c[1] + sy * 0.05, c[2] + sz * 0.05) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    tris = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6), (0, 2, 6),
            (0, 6, 4), (1, 5, 7), (1, 7, 3)]
    return [(p.verts, p.tris) for p in parts] + [(block, tris)], c


def test_a_block_on_the_left_hand_lands_on_the_left_from_fbx_and_gltf(tmp_path):
    pieces, c = _kei_with_left_block()
    # FBX, in centimetres, glTF axes (the character's left on +x)
    verts, poly = [], []
    for vs, ts in pieces:
        base = len(verts) // 3
        for v in vs:
            verts += [-v[0] * 100, v[1] * 100, v[2] * 100]
        for a, b, cc in ts:
            poly += [base + a, base + cc, -(base + b) - 1]
    geo = Node("Geometry", [P("L", 10), "b\x00\x01Geometry", "Mesh"], [
        Node("Vertices", [P("d", verts)]), Node("PolygonVertexIndex", [P("i", poly)])])
    fbx = tmp_path / "left.fbx"
    fbx.write_bytes(_fbx([geo, Node("Model", [P("L", 11), "b\x00\x01Model", "Mesh"], [])],
                         [Node("C", ["OO", P("L", 11), P("L", 0)]), Node("C", ["OO", P("L", 10), P("L", 11)])]))
    # glTF, in metres
    flat = [x for vs, _ in pieces for v in vs for x in (-v[0], v[1], v[2])]
    idx, base = [], 0
    for vs, ts in pieces:
        idx += [base + i for a, b, cc in ts for i in (a, cc, b)]
        base += len(vs)
    data = struct.pack(f"<{len(flat)}f", *flat) + struct.pack(f"<{len(idx)}I", *idx)
    n = len(flat) // 3
    doc = {"asset": {"version": "2.0"}, "nodes": [{"mesh": 0}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": n, "type": "VEC3"},
                         {"bufferView": 1, "componentType": 5125, "count": len(idx), "type": "SCALAR"}],
           "bufferViews": [{"buffer": 0, "byteLength": n * 12},
                           {"buffer": 0, "byteOffset": n * 12, "byteLength": len(idx) * 4}],
           "buffers": [{"byteLength": len(data), "uri": "data:application/octet-stream;base64,"
                        + base64.b64encode(data).decode()}]}
    gl = tmp_path / "left.gltf"
    gl.write_text(json.dumps(doc))
    for p in (fbx, gl):
        m = normalise(read_model(p), 1.71)
        ys = [v[1] for v in m.all_verts()]
        low = [v for v in m.all_verts() if abs(v[1] - (c[1] - min(ys))) < 0.06]
        far = max(low, key=lambda v: abs(v[0]))
        assert far[0] < 0, p                     # the block (the widest point at hand height) is on the left


def test_a_rigged_model_whose_left_bones_sit_on_the_right_is_refused():
    from kei.models.importer import _rigged_marks
    from kei.models.fit import Sections
    from kei.models.model import Joint, MeshData, Model
    names = ["pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r", "upperarm_l", "upperarm_r",
             "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "head"]
    side = {"l": 0.2, "r": -0.2}                 # mirrored: _l on +x
    joints = [Joint(n, None, (side.get(n[-1], 0.0) if n[-2] == "_" else 0.0, 1.0, 0.0)) for n in names]
    model = Model([MeshData("m", [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)])], joints, "mirrored")
    with pytest.raises(ModelError, match="left"):
        _rigged_marks(model, {n: n for n in names}, Sections(model), 1.71)
