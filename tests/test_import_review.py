"""Review fixes on kei import (2026-11-03): each test reproduces one defect the review found."""
import pytest

from kei.models.bind import map_bones


def test_a_ue4_mannequin_s_chest_spine_03_maps_to_kei_s_chest_not_the_mid_back():
    """A UE4 mannequin has three spine bones (spine_01..03, no spine_04/05): its spine_03 is the chest."""
    names = ["root", "pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head", "clavicle_l", "upperarm_l"]
    mapping, _ = map_bones(names)
    assert mapping["spine_03"] == "spine_05"
    assert mapping["spine_02"] == "spine_03"
    assert mapping["spine_01"] == "spine_01"
    assert mapping["neck_01"] == "neck_01" and mapping["clavicle_l"] == "clavicle_l"


def test_a_five_spine_skeleton_keeps_its_own_spine_names():
    names = ["pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "head"]
    mapping, _ = map_bones(names)
    assert all(mapping[n] == n for n in names)


# ---------------- 3: the FBX reader takes the base colour texture only ----------------
def _p70(*ps):
    from kei.fbx import Node
    return Node("Properties70", [], [Node("P", list(x)) for x in ps])


def _two_texture_quad_fbx(folder, channels):
    """A textured square whose material has one texture per (channel, file name), connected in that order."""
    from kei.fbx import Node, P, fbx_file
    gs = Node("GlobalSettings", [], [_p70(("UnitScaleFactor", "double", "Number", "", 1.0))])
    verts = [-10.0, 0.0, 0.0, 10.0, 0.0, 0.0, 10.0, 20.0, 0.0, -10.0, 20.0, 0.0]
    uv = [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]
    geo = Node("Geometry", [P("L", 10), "q\x00\x01Geometry", "Mesh"], [
        Node("Vertices", [P("d", verts)]), Node("PolygonVertexIndex", [P("i", [0, 1, 2, -4])]),
        Node("LayerElementUV", [0], [Node("MappingInformationType", ["ByPolygonVertex"]),
                                     Node("ReferenceInformationType", ["IndexToDirect"]),
                                     Node("UV", [P("d", uv)]), Node("UVIndex", [P("i", [0, 1, 2, 3])])])])
    model = Node("Model", [P("L", 11), "q\x00\x01Model", "Mesh"], [])
    mat = Node("Material", [P("L", 12), "m\x00\x01Material", ""], [])
    objs, conn = [geo, model, mat], [Node("C", ["OO", P("L", 11), P("L", 0)]), Node("C", ["OO", P("L", 10), P("L", 11)]),
                                     Node("C", ["OO", P("L", 12), P("L", 11)])]
    for i, (channel, fname) in enumerate(channels):
        objs.append(Node("Texture", [P("L", 20 + i), f"t{i}\x00\x01Texture", ""], [Node("RelativeFilename", [fname])]))
        conn.append(Node("C", ["OP", P("L", 20 + i), P("L", 12), channel]))
        (folder / fname).write_bytes(b"image")
    p = folder / "quad.fbx"
    p.write_bytes(fbx_file([gs, Node("Objects", [], objs), Node("Connections", [], conn)]))
    return p


@pytest.mark.parametrize("channel", ["DiffuseColor", "Maya|baseColor", "Maya|TEX_color_map"])
def test_a_normal_map_connected_first_is_ignored_and_the_base_colour_is_kept(tmp_path, channel):
    from kei.models.model import read_model
    p = _two_texture_quad_fbx(tmp_path, [("NormalMap", "normal.png"), (channel, "base.png")])
    assert read_model(p).meshes[0].texture == str((tmp_path / "base.png").resolve())


def test_a_material_with_only_a_normal_map_is_untextured(tmp_path):
    from kei.models.model import read_model
    mesh = read_model(_two_texture_quad_fbx(tmp_path, [("NormalMap", "normal.png")])).meshes[0]
    assert mesh.texture is None


# ---------------- 1: an unskinned mesh under a joint follows that joint ----------------
def _gltf_with_hat(folder):
    """A skinned body node and a hat mesh with no skin, the hat a child of the Head joint node."""
    import base64
    import json
    import struct
    pos = struct.pack("<9f", 0, 0, 0, 0.1, 0, 0, 0, 0.1, 0)
    doc = {"asset": {"version": "2.0"},
           "nodes": [{"name": "Hips", "children": [1], "translation": [0, 1, 0]},
                     {"name": "Head", "children": [2], "translation": [0, 0.6, 0]},
                     {"name": "hat", "mesh": 0},
                     {"name": "body", "mesh": 0, "skin": 0}],
           "skins": [{"joints": [0, 1]}],
           "meshes": [{"name": "tri", "primitives": [{"attributes": {"POSITION": 0}}]}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
           "bufferViews": [{"buffer": 0, "byteLength": 36}],
           "buffers": [{"byteLength": 36, "uri": "data:application/octet-stream;base64," +
                        base64.b64encode(pos).decode()}]}
    p = folder / "hat.gltf"
    p.write_text(json.dumps(doc))
    return p


def test_the_gltf_reader_records_the_joint_an_unskinned_mesh_hangs_from(tmp_path):
    from kei.models.model import read_model
    m = read_model(_gltf_with_hat(tmp_path))
    hat = m.meshes[0]
    assert hat.skin is None and hat.parent_joint == "Head"
    assert min(v[1] for v in hat.verts) == pytest.approx(1.6)      # placed by the head joint


def test_the_fbx_reader_records_the_joint_an_unskinned_mesh_hangs_from(tmp_path):
    from kei.fbx import Node, P, fbx_file
    from kei.models.model import read_model
    verts = [0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0, 0.0]
    geo = Node("Geometry", [P("L", 10), "hat\x00\x01Geometry", "Mesh"], [
        Node("Vertices", [P("d", verts)]), Node("PolygonVertexIndex", [P("i", [0, 1, -3])])])
    hat = Node("Model", [P("L", 11), "hat\x00\x01Model", "Mesh"], [])
    head = Node("Model", [P("L", 30), "Head\x00\x01Model", "LimbNode"], [_p70(
        ("Lcl Translation", "Lcl Translation", "", "A", 0.0, 160.0, 0.0))])
    conn = [Node("C", ["OO", P("L", 30), P("L", 0)]), Node("C", ["OO", P("L", 11), P("L", 30)]),
            Node("C", ["OO", P("L", 10), P("L", 11)])]
    p = tmp_path / "hat.fbx"
    p.write_bytes(fbx_file([Node("Objects", [], [geo, hat, head]), Node("Connections", [], conn)]))
    m = read_model(p)
    assert m.meshes[0].parent_joint == "Head"


def test_a_hat_under_the_head_joint_binds_rigidly_to_kei_s_head_not_the_pelvis():
    from kei.characters import load_character, rest_skeleton
    from kei.models.bind import bind_rigged
    from kei.models.model import Joint, MeshData, Model
    joints = [Joint("Hips", None, (0, 0.9, 0)), Joint("Spine", "Hips", (0, 1.1, 0)), Joint("Neck", "Spine", (0, 1.45, 0)),
              Joint("Head", "Neck", (0, 1.55, 0)), Joint("HeadTop_End", "Head", (0, 1.7, 0))]
    body = MeshData("body", [(0, 0.9, 0), (0.1, 1.0, 0), (0, 1.1, 0.05)], [(0, 1, 2)],
                    skin=[[("Hips", 1.0)], [("Spine", 1.0)], [("Spine", 1.0)]])
    hat = MeshData("hat", [(0, 1.7, 0), (0.1, 1.7, 0), (0, 1.75, 0.05)], [(0, 1, 2)], parent_joint="HeadTop_End")
    model = Model([body, hat], joints, "hat")
    mapping, _ = map_bones([j.name for j in joints])
    kei = load_character("kei")
    parts = bind_rigged(model, mapping, bones=rest_skeleton(kei), height=kei.height)
    hat_part = parts[1]
    assert hat_part.bone == "head" and hat_part.skin is None


def test_an_unskinned_mesh_with_no_joint_above_it_is_bound_by_its_shape():
    """A forearm guard that hangs from no joint is bound as an unrigged piece is (bind_mesh), not to the pelvis."""
    from kei.characters import load_character, rest_skeleton
    from kei.models.bind import bind_rigged
    from kei.models.model import Joint, MeshData, Model
    from test_model_bind import _mid, _tube
    kei = load_character("kei")
    B = rest_skeleton(kei)
    b = B["lowerarm_r"]
    guard = _tube(_mid(b.head, b.tail, 0.2), _mid(b.head, b.tail, 0.8), 0.03)
    body = MeshData("body", [(0, 0.9, 0), (0.1, 1.0, 0), (0, 1.1, 0.05)], [(0, 1, 2)], skin=[[("Hips", 1.0)]] * 3)
    model = Model([body, guard], [Joint("Hips", None, (0, 0.9, 0))], "guard")
    parts = bind_rigged(model, {"Hips": "pelvis"}, bones=B, height=kei.height)
    assert [(p.bone, p.skin) for p in parts[1:]] == [("lowerarm_r", None)]


def test_normalising_a_model_keeps_the_joint_a_mesh_hangs_from():
    from kei.models.fit import normalise
    from kei.models.model import Joint, MeshData, Model
    legs = MeshData("body", [(0, 0, 0), (0.1, 1.7, 0), (0, 1.0, 0.1)], [(0, 1, 2)], skin=[[("Hips", 1.0)]] * 3)
    hat = MeshData("hat", [(0, 1.7, 0), (0.1, 1.7, 0), (0, 1.75, 0.05)], [(0, 1, 2)], parent_joint="Head")
    m = normalise(Model([legs, hat], [Joint("Hips", None, (0, 0.9, 0)), Joint("Head", "Hips", (0, 1.6, 0))], "x"), 1.71)
    assert m.meshes[1].parent_joint == "Head"


# ---------------- 2: each part keeps its own texture ----------------
def _split_head(mesh):
    """The mesh as two meshes: the triangles above 1.5 m (the head) and the rest, each with its own vertices."""
    from kei.models.model import MeshData
    out = []
    for keep in (lambda y: y > 1.5, lambda y: y <= 1.5):
        tris = [t for t in mesh.tris if keep(sum(mesh.verts[i][1] for i in t) / 3)]
        used = sorted({i for t in tris for i in t})
        remap = {v: k for k, v in enumerate(used)}
        out.append(MeshData(mesh.name, [mesh.verts[i] for i in used], [tuple(remap[i] for i in t) for t in tris]))
    return out


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="ffmpeg is not installed")
def test_a_model_with_separate_head_and_body_textures_draws_each_part_with_its_own(tmp_path, monkeypatch):
    import json
    import subprocess
    from kei.characters import load_character, rest_pose
    from kei.cli import main
    from kei.models import importer
    from kei.render import draw_character_views
    from test_import_cli import unrigged_fbx
    from test_sheet import decode
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    src = unrigged_fbx(tmp_path / "scan.fbx")
    for colour in ("red", "blue"):
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=16x16", "-frames:v", "1",
                        str(tmp_path / f"{colour}.png")], check=True)
    real = importer.read_model

    def two_textures(path):
        m = real(path)
        head, body = _split_head(m.meshes[0])
        for mesh, colour in ((head, "blue"), (body, "red")):
            mesh.texture = str(tmp_path / f"{colour}.png")
            mesh.tri_uvs = [((0.5, 0.5),) * 3 for _ in mesh.tris]
        m.meshes = [body, head]
        return m
    monkeypatch.setattr(importer, "read_model", two_textures)
    main(["import", str(src), "--name", "two_tex", "--height", "1.71"])
    ch = load_character("two_tex")
    w, h, px = decode(draw_character_views(ch, rest_pose(ch), size=200, views=("front",)))
    reds = [y for y in range(h) for x in range(w) if px(x, y)[0] > 120 and px(x, y)[2] < 60]
    blues = [y for y in range(h) for x in range(w) if px(x, y)[2] > 120 and px(x, y)[0] < 60]
    assert reds and blues, "the head is drawn with its own (blue) texture, the body with its (red) one"
    assert max(blues) < min(reds) + 5                      # the blue is the head, above the red body
    data = json.loads((tmp_path / "chars" / "two_tex" / "character.json").read_text())
    assert [t["file"] for t in data["texture"]] == ["texture.rgb", "texture_1.rgb"]


# ---------------- 4: the fit sheet shows what a shot will play ----------------
def test_the_fit_sheet_has_a_neutral_stance_panel_that_shows_the_stacked_head(tmp_path, monkeypatch):
    from kei.characters import load_character
    from kei.characters.imported import write_character
    from kei.characters.mesh import pose_mesh
    from kei.characters import rest_pose
    from kei.models.bind import BoundPart
    from kei.render import draw_fit_sheet
    from test_sheet import decode
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    kei = load_character("kei")
    rest = {**kei.rest, "spine": [-0.15, 0, 0], "neck": [0.5, 0, 0]}   # a sculpt leaning back, its head forward
    parts = [BoundPart(p.bone, "body", p.verts, p.tris) for p in pose_mesh(kei, {**rest_pose(kei), **rest})]
    write_character(tmp_path / "chars", "leaner", "Leaner", kei.height, kei.proportions, rest, parts, {"file": "t"}, {})
    size = 120
    w, h, px = decode(draw_fit_sheet(load_character("leaner"), size=size))
    assert w == 4 * size, "front, side, three quarter at rest, and the side at a shot's neutral stance"
    side = [px(size + x, y) for y in range(h) for x in range(size)]
    neutral = [px(3 * size + x, y) for y in range(h) for x in range(size)]
    assert side != neutral, "the neutral stance stands the trunk up and moves the head, so it reads differently"


def test_a_head_the_fit_cannot_stack_is_named_in_the_import_warnings(tmp_path, monkeypatch):
    from kei.models import importer
    from test_import_cli import unrigged_fbx
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    monkeypatch.setattr(importer, "stack_head", lambda *a, **k: 1.2)      # the search's upper bound
    _, report = importer.import_model(unrigged_fbx(tmp_path / "scan.fbx"), "clamped", 1.71)
    assert any("neck" in w and "fit.png" in w for w in report["warnings"]), report["warnings"]


def test_a_head_the_fit_stacks_brings_no_warning(tmp_path, monkeypatch):
    from kei.models import importer
    from test_import_cli import unrigged_fbx
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    _, report = importer.import_model(unrigged_fbx(tmp_path / "scan.fbx"), "stacked", 1.71)
    assert not any("neck" in w for w in report["warnings"]), report["warnings"]


# ---------------- minor: a texture file that is missing or the wrong size ----------------
@pytest.mark.parametrize("data", [None, bytes(5)])
def test_a_missing_or_wrong_size_texture_is_an_error_naming_the_file(tmp_path, monkeypatch, data):
    import json
    from kei.characters import CharacterError, load_character, rest_pose
    from kei.characters.imported import write_character
    from kei.models.bind import BoundPart
    from kei.render import draw_character_views
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    kei = load_character("kei")
    part = BoundPart("spine_04", "body", [(0, 1.2, 0.2), (0.1, 1.2, 0.2), (0, 1.3, 0.2)], [(0, 1, 2)], None,
                     [[(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]])
    folder = write_character(tmp_path / "chars", "no_tex", "N", kei.height, kei.proportions, kei.rest, [part],
                             {"file": "t"}, {}, texture={"file": "texture.rgb", "width": 2, "height": 1})
    if data is not None:
        (folder / "texture.rgb").write_bytes(data)
    ch = load_character("no_tex")
    with pytest.raises(CharacterError, match="texture.rgb"):
        draw_character_views(ch, rest_pose(ch), size=60, views=("front",))


# ---------------- minor: kei import <model> --confirm ----------------
def test_import_with_a_model_and_confirm_is_refused_and_approves_nothing(tmp_path, monkeypatch, capsys):
    from kei.characters import load_character
    from kei.cli import EXIT_ERROR, main
    from test_import_cli import unrigged_fbx
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    src = unrigged_fbx(tmp_path / "scan.fbx")
    main(["import", str(src), "--name", "scan", "--height", "1.71"])
    capsys.readouterr()
    assert main(["import", str(src), "--name", "scan", "--confirm"]) == EXIT_ERROR
    out = capsys.readouterr().out
    assert "--confirm" in out and "model" in out
    assert not load_character("scan").confirmed


# ---------------- minor: non-finite positions and UVs ----------------
def _gltf_tri(folder, pos, uv=None):
    import base64
    import json
    import struct
    data = struct.pack("<9f", *pos)
    attrs = {"POSITION": 0}
    accessors = [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}]
    views = [{"buffer": 0, "byteLength": 36}]
    doc = {"asset": {"version": "2.0"}, "nodes": [{"mesh": 0}]}
    if uv is not None:
        data += struct.pack("<6f", *uv)
        attrs["TEXCOORD_0"] = 1
        accessors.append({"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2"})
        views.append({"buffer": 0, "byteOffset": 36, "byteLength": 24})
        (folder / "base.png").write_bytes(b"png")
        doc.update({"materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
                    "textures": [{"source": 0}], "images": [{"uri": "base.png"}]})
    doc.update({"meshes": [{"primitives": [{"attributes": attrs, **({"material": 0} if uv else {})}]}],
                "accessors": accessors, "bufferViews": views,
                "buffers": [{"byteLength": len(data), "uri": "data:application/octet-stream;base64," +
                             base64.b64encode(data).decode()}]})
    p = folder / "t.gltf"
    p.write_text(json.dumps(doc))
    return p


def _fbx_tri(folder, verts, uv=None):
    from kei.fbx import Node, P, fbx_file
    kids = [Node("Vertices", [P("d", verts)]), Node("PolygonVertexIndex", [P("i", [0, 1, -3])])]
    if uv is not None:
        kids.append(Node("LayerElementUV", [0], [Node("MappingInformationType", ["ByPolygonVertex"]),
                                                 Node("ReferenceInformationType", ["Direct"]),
                                                 Node("UV", [P("d", uv)])]))
    geo = Node("Geometry", [P("L", 10), "t\x00\x01Geometry", "Mesh"], kids)
    model = Node("Model", [P("L", 11), "t\x00\x01Model", "Mesh"], [])
    conn = [Node("C", ["OO", P("L", 11), P("L", 0)]), Node("C", ["OO", P("L", 10), P("L", 11)])]
    p = folder / "t.fbx"
    p.write_bytes(fbx_file([Node("Objects", [], [geo, model]), Node("Connections", [], conn)]))
    return p


NAN, INF = float("nan"), float("inf")


@pytest.mark.parametrize("make", [
    lambda d: _gltf_tri(d, [0, 0, 0, NAN, 0, 0, 0, 1, 0]),
    lambda d: _gltf_tri(d, [0, 0, 0, 1, 0, 0, 0, 1, 0], [0, 0, INF, 0, 0, 1]),
    lambda d: _fbx_tri(d, [0.0, 0.0, 0.0, INF, 0.0, 0.0, 0.0, 1.0, 0.0]),
    lambda d: _fbx_tri(d, [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0], [0.0, 0.0, NAN, 0.0, 0.0, 1.0]),
], ids=["gltf position", "gltf uv", "fbx position", "fbx uv"])
def test_a_non_finite_position_or_uv_is_an_import_error_naming_the_file(tmp_path, make):
    from kei.models.model import ModelError, read_model
    with pytest.raises(ModelError, match=r"t\.(gltf|fbx).*not a finite number"):
        read_model(make(tmp_path))


# ---------------- minor: a mirrored instance keeps its triangles facing out ----------------
def _normal_z(mesh):
    out = []
    for a, b, c in mesh.tris:
        v0, v1, v2 = mesh.verts[a], mesh.verts[b], mesh.verts[c]
        e1 = [v1[i] - v0[i] for i in range(3)]
        e2 = [v2[i] - v0[i] for i in range(3)]
        out.append(e1[0] * e2[1] - e1[1] * e2[0])
    return out


def test_a_gltf_node_with_a_negative_scale_keeps_its_triangle_facing_out(tmp_path):
    """A triangle facing +z (counter-clockwise from +z), placed by a node mirrored in x: it still faces +z."""
    import json
    from kei.models.model import read_model
    p = _gltf_tri(tmp_path, [0, 0, 0, 1, 0, 0, 0, 1, 0])
    doc = json.loads(p.read_text())
    doc["nodes"][0]["scale"] = [-1, 1, 1]
    p.write_text(json.dumps(doc))
    assert all(z > 0 for z in _normal_z(read_model(p).meshes[0]))


def test_an_fbx_model_with_a_negative_scale_keeps_its_triangles_facing_out(tmp_path):
    from kei.fbx import Node, P, fbx_file
    from kei.models.model import read_model
    verts = [-10.0, 0.0, 0.0, 10.0, 0.0, 0.0, 10.0, 20.0, 0.0, -10.0, 20.0, 0.0]
    geo = Node("Geometry", [P("L", 10), "q\x00\x01Geometry", "Mesh"], [
        Node("Vertices", [P("d", verts)]), Node("PolygonVertexIndex", [P("i", [0, 1, 2, -4])])])
    model = Node("Model", [P("L", 11), "q\x00\x01Model", "Mesh"], [_p70(
        ("Lcl Scaling", "Lcl Scaling", "", "A", -1.0, 1.0, 1.0))])
    conn = [Node("C", ["OO", P("L", 11), P("L", 0)]), Node("C", ["OO", P("L", 10), P("L", 11)])]
    p = tmp_path / "m.fbx"
    p.write_bytes(fbx_file([Node("Objects", [], [geo, model]), Node("Connections", [], conn)]))
    assert all(z > 0 for z in _normal_z(read_model(p).meshes[0]))


# ---------------- minor: an embedded image is written once and removed after the import ----------------
def test_an_embedded_image_used_by_two_primitives_is_written_once_and_listed_for_removal(tmp_path):
    import json
    import struct
    from kei.models.model import read_model
    pos = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    uv = struct.pack("<6f", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0)
    img = b"\x89PNG\r\n\x1a\n" + bytes(24)
    blob = pos + uv + img
    prim = {"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "material": 0}
    doc = {"asset": {"version": "2.0"}, "nodes": [{"mesh": 0}], "meshes": [{"primitives": [prim, prim]}],
           "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
           "textures": [{"source": 0}], "images": [{"bufferView": 2, "mimeType": "image/png"}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
                         {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2"}],
           "bufferViews": [{"buffer": 0, "byteLength": 36}, {"buffer": 0, "byteOffset": 36, "byteLength": 24},
                           {"buffer": 0, "byteOffset": 60, "byteLength": len(img)}],
           "buffers": [{"byteLength": len(blob)}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    body = blob + b"\x00" * (-len(blob) % 4)
    glb = (struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(body)) + struct.pack("<II", len(js), 0x4E4F534A)
           + js + struct.pack("<II", len(body), 0x004E4942) + body)
    p = tmp_path / "two.glb"
    p.write_bytes(glb)
    m = read_model(p)
    try:
        a, b = (mesh.texture for mesh in m.meshes)
        assert a == b and m.temp_files == [a]
    finally:
        for f in getattr(m, "temp_files", []) or {mesh.texture for mesh in m.meshes}:
            __import__("os").remove(f)


@pytest.mark.parametrize("height", [None, 1.71])
def test_the_import_removes_the_model_s_temporary_images_whether_it_succeeds_or_fails(tmp_path, monkeypatch, height):
    import shutil
    import subprocess
    from kei.models import importer
    from kei.models.model import ModelError
    from test_import_cli import unrigged_fbx
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is not installed")
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    temp = tmp_path / "kei_texture_1.png"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=8x8", "-frames:v", "1", str(temp)],
                   check=True)
    real = importer.read_model

    def with_temp(path):
        m = real(path)
        for mesh in m.meshes:
            mesh.texture, mesh.tri_uvs = str(temp), [((0.5, 0.5),) * 3 for _ in mesh.tris]
        m.temp_files = [str(temp)]
        return m
    monkeypatch.setattr(importer, "read_model", with_temp)
    src = unrigged_fbx(tmp_path / "scan.fbx")
    if height is None:
        with pytest.raises(ModelError, match="--height"):
            importer.import_model(src, "temp_tex")
    else:
        importer.import_model(src, "temp_tex", height)
    assert not temp.exists()


# ---------------- minor: ffmpeg reads a texture only as an image file ----------------
def test_ffprobe_and_ffmpeg_read_a_texture_as_a_local_image_of_its_type(tmp_path, monkeypatch):
    import json
    import types
    from kei.models import importer
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        if argv[0] == "ffprobe":
            return types.SimpleNamespace(stdout=json.dumps({"streams": [{"width": 2, "height": 2}]}), stderr="",
                                         returncode=0)
        __import__("pathlib").Path(argv[-1]).write_bytes(bytes(12))
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)
    monkeypatch.setattr(importer.subprocess, "run", run)
    monkeypatch.setattr(importer.shutil, "which", lambda name: name)
    importer.convert_texture(tmp_path / "base.JPG", tmp_path / "out")
    assert len(calls) == 2
    for argv in calls:
        i = argv.index("-i")
        before = argv[:i]
        assert before[before.index("-protocol_whitelist") + 1] == "file"
        assert before[before.index("-f") + 1] == "jpeg_pipe"


def test_a_texture_of_a_type_kei_does_not_read_is_refused_by_name(tmp_path, monkeypatch):
    from kei.models import importer
    from kei.models.model import ModelError
    monkeypatch.setattr(importer.shutil, "which", lambda name: name)
    with pytest.raises(ModelError, match=r"base\.m3u8: Kei reads textures of these types only"):
        importer.convert_texture(tmp_path / "base.m3u8", tmp_path / "out")


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="ffmpeg is not installed")
def test_a_texture_that_is_really_a_playlist_of_other_files_is_refused(tmp_path):
    import subprocess
    from kei.models import importer
    from kei.models.model import ModelError
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=8x8", "-frames:v", "1",
                    str(tmp_path / "other.png")], check=True)
    evil = tmp_path / "base.png"
    evil.write_text("ffconcat version 1.0\nfile other.png\n")
    with pytest.raises(ModelError, match="cannot read the texture"):    # read as a PNG, it is no image at all
        importer.convert_texture(evil, tmp_path / "out")


# ---------------- minor: a re-import that fails leaves the old import whole ----------------
def _files(folder):
    return {p.name: p.read_bytes() for p in folder.iterdir()} if folder.is_dir() else {}


def test_a_re_import_that_fails_leaves_the_old_import_as_it_was(tmp_path, monkeypatch):
    import kei.render
    from kei.models import importer
    from test_import_cli import unrigged_fbx
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    src = unrigged_fbx(tmp_path / "scan.fbx")
    importer.import_model(src, "scan", 1.71)
    folder = tmp_path / "chars" / "scan"
    before = _files(folder)

    def broken(ch, size=480):
        raise RuntimeError("the fit sheet failed")
    monkeypatch.setattr(kei.render, "draw_fit_sheet", broken)
    with pytest.raises(RuntimeError):
        importer.import_model(src, "scan", 1.65)
    assert _files(folder) == before


def test_a_first_import_that_fails_leaves_no_character(tmp_path, monkeypatch):
    import kei.render
    from kei.characters import imported_characters
    from kei.models import importer
    from test_import_cli import unrigged_fbx
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    monkeypatch.setattr(kei.render, "draw_fit_sheet", lambda ch, size=480: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        importer.import_model(unrigged_fbx(tmp_path / "scan.fbx"), "scan", 1.71)
    assert "scan" not in imported_characters() and not (tmp_path / "chars" / "scan").exists()


def test_the_same_name_with_another_model_measures_again_instead_of_keeping_the_old_height(tmp_path, monkeypatch):
    from kei.characters import load_character
    from kei.models import importer
    from kei.models.model import ModelError
    from test_import_cli import unrigged_fbx
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    importer.import_model(unrigged_fbx(tmp_path / "scan.fbx"), "scan", 1.71)
    other = unrigged_fbx(tmp_path / "other.fbx", "keira")
    with pytest.raises(ModelError, match="--height"):          # an unrigged model: Kei cannot tell its size
        importer.import_model(other, "scan")
    importer.import_model(tmp_path / "scan.fbx", "scan")       # the same model again keeps its height
    assert load_character("scan").height == pytest.approx(1.71)


@pytest.mark.parametrize("bound, way", [(1.2, "forward"), (-0.3, "back")])
def test_the_clamp_warning_names_the_way_the_head_stays_off(tmp_path, monkeypatch, bound, way):
    """stack_head turns the head back as the neck pitch grows: stopped at the top it is still too far forward, at the
    bottom still too far back."""
    from kei.models import importer
    from test_import_cli import unrigged_fbx
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    monkeypatch.setattr(importer, "stack_head", lambda *a, **k: bound)
    _, report = importer.import_model(unrigged_fbx(tmp_path / "scan.fbx"), "clamped", 1.71)
    assert any(f"head too far {way}" in w for w in report["warnings"]), report["warnings"]
