"""Plan 6b: an imported character (kei import) in Maya, built from its own files: Kei's skeleton at its proportions and
rest pose, its mesh with the rigid parts on their bone and the smooth parts on their weights, its texture as a file
texture on its UVs, and the same control rig as Kei's own characters. The job half needs no Maya; the Maya half is
skipped, with the reason, where Maya is not installed."""
import json
import math
import struct
import zlib

import pytest

from kei.apps.maya_scene import character_job, mesh_groups
from kei.apps.maya_side import kei_math as km
from kei.characters import CharacterError, load_character, rest_skeleton
from kei.rig import ALL_BONES

import mayakit
from imported_kit import TEXTURE, make_imported, unconfirm
from test_maya_character import _world


@pytest.fixture
def chars(tmp_path, monkeypatch):
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "characters"))
    make_imported(tmp_path / "characters")
    return tmp_path / "characters"


def _png_pixels(path):
    """(width, height, rows of RGB bytes) of an 8-bit RGB PNG with no interlace."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w, h = 8, b"", None, None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, colour = struct.unpack(">IIBB", body[:10])
            assert (depth, colour) == (8, 2)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    rows = [raw[y * (w * 3 + 1):(y + 1) * (w * 3 + 1)] for y in range(h)]
    assert all(r[0] == 0 for r in rows)            # filter 0: the bytes are the pixels
    return w, h, b"".join(r[1:] for r in rows)


def test_an_unconfirmed_import_is_refused_with_how_to_approve_its_fit(chars, tmp_path):
    unconfirm(chars / "synth")
    with pytest.raises(CharacterError, match=r"approve.*kei import --confirm --name synth"):
        character_job("synth", texture_dir=tmp_path / "tex")


def test_the_bones_sit_at_the_imported_character_s_proportions_and_rest(chars, tmp_path):
    job = character_job("synth", texture_dir=tmp_path / "tex")
    assert [b["name"] for b in job["bones"]] == list(ALL_BONES)
    world, rest = _world(job), rest_skeleton(load_character("synth"))
    for n in ALL_BONES:
        R, p = world[n]
        assert all(abs(a - b) < 1e-9 for a, b in zip(p, km.mirror_point(rest[n].head))), n
        want = km.mirror_frame(rest[n].frame)
        assert all(abs(R[r][c] - want[r][c]) < 1e-9 for r in range(3) for c in range(3)), n


def test_every_part_is_in_the_job_once_with_its_own_weights(chars, tmp_path):
    ch = load_character("synth")
    job = character_job("synth", texture_dir=tmp_path / "tex")
    meshes = {m["name"]: m for m in job["meshes"]}
    seen = 0
    for name, _, parts in mesh_groups(ch):
        m = meshes[name]
        assert len(m["points"]) == len(m["weights"]) == len(m["normals"])
        at = 0
        for i in parts:
            p = ch.parts[i]
            for k, v in enumerate(p["verts"]):
                assert m["points"][at + k] == pytest.approx(list(km.mirror_point(v)), abs=1e-9)
                got = {ALL_BONES[b]: w for b, w in m["weights"][at + k]}
                want = dict(p["skin"][k]) if p.get("skin") else {p["bone"]: 1.0}
                assert got == pytest.approx(want, abs=1e-6), (name, i, k)
            at += len(p["verts"])
        seen += at
    assert seen == sum(len(p["verts"]) for p in ch.parts)
    blended = [w for m in job["meshes"] for w in m["weights"] if len(w) == 2]
    assert blended, "the smooth parts' vertices near the knee and the elbow carry two bones"


def test_the_textured_parts_carry_their_uvs_in_maya_s_convention_and_the_head_has_none(chars, tmp_path):
    ch = load_character("synth")
    job = character_job("synth", texture_dir=tmp_path / "tex")
    meshes = {m["name"]: m for m in job["meshes"]}
    groups = mesh_groups(ch)
    tex = [g for g in groups if meshes[g[0]].get("uvs")]
    plain = [g for g in groups if not meshes[g[0]].get("uvs")]
    assert tex and plain
    assert all(ch.parts[i]["bone"] == "head" for _, _, parts in plain for i in parts)
    name, _, parts = tex[0]
    m, p = meshes[name], ch.parts[parts[0]]
    # the mirror flips each triangle (a, b, c) to (a, c, b); its corners' uvs follow, v counted from the bottom
    a, b, c = p["tris"][0]
    assert m["triangles"][0] == [a, c, b]
    u = p["uvs"][0]
    assert m["uvs"][0] == pytest.approx([u[0], 1 - u[1], u[4], 1 - u[5], u[2], 1 - u[3]])
    assert len(m["uvs"]) == len(m["triangles"])


def test_the_texture_goes_to_maya_as_a_png_with_the_same_texels(chars, tmp_path):
    job = character_job("synth", texture_dir=tmp_path / "tex")
    textured = [m for m in job["materials"] if m.get("texture")]
    assert len(textured) == 1
    path = tmp_path / "tex" / "synth_texture.png"
    assert textured[0]["texture"] == str(path.resolve()).replace("\\", "/")
    assert _png_pixels(path) == (4, 2, TEXTURE)
    assert {m["material"] for m in job["meshes"] if m.get("uvs")} == {textured[0]["name"]}


def test_a_textured_import_needs_a_folder_for_its_texture(chars):
    with pytest.raises(CharacterError, match="texture"):
        character_job("synth")


def test_kei_maya_setup_builds_the_character_plan_md_names(chars, tmp_path, monkeypatch):
    from kei.apps import maya_shot
    sent = []
    monkeypatch.setattr(maya_shot, "run_job", lambda py, job, **kw: sent.append(job) or {
        "maya_version": "2027", "results": [{}, {}, {"controls": []}, {"joints": []}]})
    shot = tmp_path / "shot"
    shot.mkdir()
    (shot / "PLAN.md").write_text("# a walk\n\nCharacter: synth\n", encoding="utf-8")
    r = maya_shot.setup_shot(shot, mayapy=tmp_path / "mayapy.exe")
    assert r["character"] == "synth"
    job = sent[0]["calls"][1]["inputs"]["job"]
    assert job["character"] == "synth"
    assert (shot / "maya" / "textures" / "synth_texture.png").is_file()
    assert sent[0]["calls"][2]["inputs"]["job"]["character"] == "synth"


# ---------------- in Maya ----------------
@pytest.fixture(scope="module")
def maya_chars(tmp_path_factory):
    root = tmp_path_factory.mktemp("imported")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("KEI_CHARACTERS", str(root / "characters"))
        make_imported(root / "characters")
        yield root


@pytest.fixture(scope="module")
def built(maya_chars):
    return mayakit.run_script("check_imported.py", character="synth", texture_dir=str(maya_chars / "tex"))


@pytest.mark.maya
def test_in_maya_the_imported_skeleton_stands_at_its_rest_pose(built, maya_chars):
    rest = rest_skeleton(load_character("synth"))
    for n in ALL_BONES:
        got, want = built["joints_m"][n], km.mirror_point(rest[n].head)
        assert max(abs(a - b) for a, b in zip(got, want)) < 0.001, (n, got, want)


@pytest.mark.maya
def test_in_maya_every_vertex_carries_its_own_weights_at_its_rest_place(built, maya_chars):
    job = character_job("synth", texture_dir=maya_chars / "tex")
    assert sorted(built["meshes"]) == sorted(m["name"] for m in job["meshes"])
    for m in job["meshes"]:
        got = built["meshes"][m["name"]]
        assert got["vertices"] == len(m["points"]) and got["weight_mismatches"] == 0, m["name"]
        assert got["rest_far_m"] < 1e-6, m["name"]


@pytest.mark.maya
def test_in_maya_the_texture_is_a_file_texture_on_the_uvs(built, maya_chars):
    job = character_job("synth", texture_dir=maya_chars / "tex")
    tex = next(m for m in job["meshes"] if m.get("uvs"))
    got = built["meshes"][tex["name"]]
    assert got["file"] == str((maya_chars / "tex" / "synth_texture.png").resolve()).replace("\\", "/")
    assert got["colour_space"] == "sRGB"
    assert [c for uv in got["first_uvs"] for c in uv] == pytest.approx(tex["uvs"][0], abs=1e-6)
    plain = next(m for m in job["meshes"] if not m.get("uvs"))
    assert "file" not in built["meshes"][plain["name"]]
