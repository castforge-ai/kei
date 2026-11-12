"""Textured models: UVs and the base colour texture are read, kept through binding, and drawn by the renderer."""
import base64
import json
import shutil
import struct

import pytest

from kei.fbx import Node, P, fbx_file
from kei.models.model import ModelError, read_model

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


def _p70(*ps):
    return Node("Properties70", [], [Node("P", list(x)) for x in ps])


def textured_quad_fbx(folder, rel="quad.fbm/base.jpg"):
    """A 20 x 20 cm square facing the front, in centimetres. u runs with the file's x (0 at x -10), v with height
    (FBX's v is up: 0 at the bottom). Its material's diffuse colour takes a texture at rel."""
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
    tex = Node("Texture", [P("L", 13), "t\x00\x01Texture", ""], [Node("RelativeFilename", [rel])])
    conn = [Node("C", ["OO", P("L", 11), P("L", 0)]), Node("C", ["OO", P("L", 10), P("L", 11)]),
            Node("C", ["OO", P("L", 12), P("L", 11)]), Node("C", ["OP", P("L", 13), P("L", 12), "DiffuseColor"])]
    p = folder / "quad.fbx"
    p.write_bytes(fbx_file([gs, Node("Objects", [], [geo, model, mat, tex]), Node("Connections", [], conn)]))
    (folder / "quad.fbm").mkdir(exist_ok=True)
    (folder / "quad.fbm" / "base.jpg").write_bytes(b"not decoded here")
    return p


def _expected_uv(v):
    """The UV of a Kei-world point of the square: file x = -kei x (in cm), u from the file's x, v from the top."""
    x_file = -v[0] * 100
    return ((x_file + 10) / 20, 1 - v[1] * 100 / 20)


def test_fbx_uvs_follow_each_triangle_corner_and_the_texture_is_found(tmp_path):
    m = read_model(textured_quad_fbx(tmp_path))
    mesh = m.meshes[0]
    assert mesh.texture == str((tmp_path / "quad.fbm" / "base.jpg").resolve())
    assert len(mesh.tri_uvs) == len(mesh.tris) == 2
    for tri, uvs in zip(mesh.tris, mesh.tri_uvs):
        for corner, uv in zip(tri, uvs):
            assert uv == pytest.approx(_expected_uv(mesh.verts[corner]))


def test_a_texture_outside_the_model_s_folder_is_not_read(tmp_path):
    m = read_model(textured_quad_fbx(tmp_path, rel="../../secret.jpg"))
    assert m.meshes[0].texture is None and any("texture" in w for w in m.warnings)


def test_gltf_uvs_and_its_image_are_read(tmp_path):
    pos = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    uv = struct.pack("<6f", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0)
    data = pos + uv
    (tmp_path / "base.png").write_bytes(b"png")
    doc = {"asset": {"version": "2.0"}, "nodes": [{"mesh": 0}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "material": 0}]}],
           "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
           "textures": [{"source": 0}], "images": [{"uri": "base.png"}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
                         {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC2"}],
           "bufferViews": [{"buffer": 0, "byteLength": 36}, {"buffer": 0, "byteOffset": 36, "byteLength": 24}],
           "buffers": [{"byteLength": 60, "uri": "data:application/octet-stream;base64," +
                        base64.b64encode(data).decode()}]}
    p = tmp_path / "t.gltf"
    p.write_text(json.dumps(doc))
    mesh = read_model(p).meshes[0]
    assert mesh.texture == str((tmp_path / "base.png").resolve())
    # glTF's v already runs from the top; the triangle is flipped for the mirror, its UVs with it
    a, b, c = mesh.tris[0]
    got = dict(zip((a, b, c), mesh.tri_uvs[0]))
    assert got == {0: (0.0, 0.0), 1: (1.0, 0.0), 2: (0.0, 1.0)}


def test_the_sampler_blends_between_texels():
    from kei.characters.texture import sample
    tex = (2, 1, bytes([0, 0, 0, 200, 100, 0]))          # a black texel and an orange one
    assert sample(tex, 0.25, 0.5) == (0, 0, 0)
    assert sample(tex, 0.75, 0.5) == (200, 100, 0)
    mid = sample(tex, 0.5, 0.5)
    assert mid == pytest.approx((100, 50, 0), abs=1)


def test_a_textured_part_draws_its_texture_and_an_untextured_one_stays_ivory(tmp_path, monkeypatch):
    from kei.characters import load_character, rest_pose
    from kei.characters.imported import write_character
    from kei.models.bind import BoundPart
    from kei.render import draw_character_views
    from kei.rig import skeleton
    from test_sheet import decode
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    kei = load_character("kei")
    B = skeleton(rest_pose(kei), kei.proportions)
    c = B["spine_04"].head
    sq = [(c[0] - 0.2, c[1] - 0.2, c[2] + 0.3), (c[0] + 0.2, c[1] - 0.2, c[2] + 0.3),
          (c[0] + 0.2, c[1] + 0.2, c[2] + 0.3), (c[0] - 0.2, c[1] + 0.2, c[2] + 0.3)]
    tris = [(0, 1, 2), (0, 2, 3)]                         # facing +z (the front)
    # u along Kei's x: 0 on the character's left (-x), 1 on its right
    uvs = [[(0.0, 1.0), (1.0, 1.0), (1.0, 0.0)], [(0.0, 1.0), (1.0, 0.0), (0.0, 0.0)]]
    part = BoundPart("spine_04", "body", sq, tris, None, uvs)
    folder = write_character(tmp_path / "chars", "tex_test", "Tex", kei.height, kei.proportions, kei.rest, [part],
                             {"file": "t"}, {})
    (folder / "texture.rgb").write_bytes(bytes([255, 0, 0, 0, 0, 255]))   # red on the left half, blue on the right
    data = json.loads((folder / "character.json").read_text())
    data["texture"] = {"file": "texture.rgb", "width": 2, "height": 1}
    (folder / "character.json").write_text(json.dumps(data))
    ch = load_character("tex_test")
    w, h, px = decode(draw_character_views(ch, rest_pose(ch), size=200, views=("front",)))
    reds = [(x, y) for y in range(h) for x in range(w) if px(x, y)[0] > 150 and px(x, y)[2] < 80]
    blues = [(x, y) for y in range(h) for x in range(w) if px(x, y)[2] > 150 and px(x, y)[0] < 80]
    assert reds and blues
    # the front view shows the character's left on the viewer's right
    assert min(x for x, _ in reds) > max(x for x, _ in blues) - 5


@needs_ffmpeg
def test_kei_import_converts_the_texture_once_into_the_character_folder(tmp_path, monkeypatch):
    import subprocess
    from kei.cli import main
    from test_import_cli import unrigged_fbx
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    src = unrigged_fbx(tmp_path / "scan.fbx")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x32", "-frames:v", "1",
                    str(tmp_path / "base.png")], check=True)
    from kei.models import importer
    real = importer.read_model

    def with_texture(path):
        m = real(path)
        for mesh in m.meshes:
            mesh.texture = str(tmp_path / "base.png")
            mesh.tri_uvs = [((0.5, 0.5),) * 3 for _ in mesh.tris]
        return m
    monkeypatch.setattr(importer, "read_model", with_texture)
    main(["import", str(src), "--name", "scan", "--height", "1.71"])
    data = json.loads((tmp_path / "chars" / "scan" / "character.json").read_text())
    assert data["texture"]["width"] == 64 and data["texture"]["height"] == 32
    raw = (tmp_path / "chars" / "scan" / data["texture"]["file"]).read_bytes()
    assert len(raw) == 64 * 32 * 3 and raw[0] > 200 and raw[1] < 40


def test_a_texture_without_ffmpeg_is_refused_cleanly(tmp_path, monkeypatch):
    from kei.models import importer
    monkeypatch.setattr(importer.shutil, "which", lambda name: None)
    with pytest.raises(ModelError, match="ffmpeg"):
        importer.convert_texture(tmp_path / "base.jpg", tmp_path / "out")
