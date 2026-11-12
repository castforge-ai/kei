"""An imported character: a folder outside the repository that Kei loads, renders, poses and exports like its own."""
import math

import pytest

from kei.characters import CharacterError, known_characters, load_character, rest_pose
from kei.characters.imported import write_character
from kei.characters.mesh import pose_mesh
from kei.config import load_config
from kei.export_fbx import export_fbx
from kei.export_gltf import export_glb
from kei.models.bind import BoundPart, bind_mesh
from kei.models.fit import fit_rig, landmarks, normalise, stack_head
from kei.models.model import MeshData, Model, read_model
from kei.render import draw_character_views
from kei.rig import skeleton


@pytest.fixture
def chars(tmp_path, monkeypatch):
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "characters"))
    return tmp_path / "characters"


def _copy_of_kei(chars, name="kei_copy", extra=()):
    kei = load_character("kei")
    parts = pose_mesh(kei, rest_pose(kei))
    model = normalise(Model([MeshData(str(i), p.verts, p.tris) for i, p in enumerate(parts)], [], "kei"), 1.71)
    P, rest, report = fit_rig(landmarks(model), 1.71)
    bones = skeleton(rest, P)
    bound = [b for m in model.meshes for b in bind_mesh(m, bones, 1.71)] + list(extra)
    return write_character(chars, name, "Kei copy", 1.71, P, rest, bound, {"file": "test"}, report), bones


def _arm_piece(bones):
    """Three vertices on the right arm, weighted half and half between the upper arm and the forearm."""
    e = bones["lowerarm_r"].head
    verts = [(e[0] + 0.03, e[1], e[2]), (e[0], e[1] + 0.03, e[2]), (e[0], e[1], e[2] + 0.03)]
    skin = [[("upperarm_r", 0.5), ("lowerarm_r", 0.5)]] * 3
    return BoundPart("upperarm_r", "body", verts, [(0, 1, 2)], skin)


def test_an_imported_character_is_known_and_loads_by_name(chars):
    _copy_of_kei(chars)
    assert "kei_copy" in known_characters()
    ch = load_character("kei_copy")
    assert ch.height == 1.71 and not ch.confirmed
    png = draw_character_views(ch, rest_pose(ch), size=120)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_folder_may_not_take_a_built_in_character_s_name(chars):
    with pytest.raises(CharacterError, match="built-in"):
        _copy_of_kei(chars, name="keira")


def test_a_smooth_vertex_follows_the_weighted_blend_of_its_bones(chars):
    _, bones = _copy_of_kei(chars)
    _copy_of_kei(chars, "kei_arm", extra=[_arm_piece(bones)])
    ch = load_character("kei_arm")
    pose = {**ch.rest, "elbowR": [1.57, 0]}
    B = skeleton(pose, ch.proportions)
    smooth = [p for p in pose_mesh(ch, pose, B) if p.skin is not None]
    rest_B = skeleton(ch.rest, ch.proportions)

    def rigid(v, bone):
        b0, b1 = rest_B[bone], B[bone]
        d = [v[k] - b0.head[k] for k in range(3)]
        loc = [sum(d[k] * b0.frame[a][k] for k in range(3)) for a in range(3)]
        return tuple(b1.head[k] + sum(b1.frame[a][k] * loc[a] for a in range(3)) for k in range(3))
    v0 = _arm_piece(bones).verts[0]
    want = tuple((rigid(v0, "upperarm_r")[k] + rigid(v0, "lowerarm_r")[k]) / 2 for k in range(3))
    got = [v for p in smooth for v in p.verts]
    assert min(math.dist(v, want) for v in got) < 1e-5     # the files keep 6 decimals


@pytest.mark.parametrize("fmt", ["glb", "fbx"])
def test_an_imported_character_exports_with_its_weights(chars, tmp_path, fmt):
    _, bones = _copy_of_kei(chars)
    _copy_of_kei(chars, "kei_arm", extra=[_arm_piece(bones)])
    path = tmp_path / f"arm.{fmt}"
    (export_glb if fmt == "glb" else export_fbx)(load_character("kei_arm"), path, 1.0, None, "spline")
    m = read_model(path)
    arm = {"upperarm_r", "lowerarm_r"}
    halves = [w for mesh in m.meshes for w in mesh.skin if {n for n, _ in w} == arm
              and sorted(x for _, x in w) == pytest.approx([0.5, 0.5], abs=1e-5)]
    assert len(halves) >= 3                       # the three vertices of the arm piece, half and half
    for mesh in m.meshes:
        for w in mesh.skin:
            assert 1 <= len(w) <= 4 and abs(sum(x for _, x in w) - 1) < 1e-5


def test_the_config_takes_an_imported_character(chars, tmp_path):
    _copy_of_kei(chars)
    cfg = tmp_path / "kei.toml"
    cfg.write_text('[animator]\ncmd = ["x"]\n[shot]\ncharacter = "kei_copy"\n')
    assert load_config(cfg).character == "kei_copy"


@pytest.mark.parametrize("name", ["con", "nul", "com1", "lpt9", "aux", "prn"])
def test_a_windows_reserved_name_is_refused(chars, name):
    with pytest.raises(CharacterError, match="reserved"):
        _copy_of_kei(chars, name=name)


def test_the_mesh_file_must_be_mesh_json(chars):
    import json as _json
    folder, _ = _copy_of_kei(chars)
    data = _json.loads((folder / "character.json").read_text())
    data["mesh"] = "../../elsewhere.json"
    (folder / "character.json").write_text(_json.dumps(data))
    with pytest.raises(CharacterError, match="mesh.json"):
        load_character("kei_copy")


def test_skin_bones_are_checked_and_weights_renormalised_on_load(chars):
    import json as _json
    _, bones = _copy_of_kei(chars)
    folder, _ = _copy_of_kei(chars, "kei_arm", extra=[_arm_piece(bones)])
    mesh = _json.loads((folder / "mesh.json").read_text())
    arm = next(p for p in mesh["parts"] if p.get("skin") and len(p["verts"]) == 3)
    arm["skin"] = [[["upperarm_r", 1.0], ["lowerarm_r", 1.0]]] * 3
    (folder / "mesh.json").write_text(_json.dumps(mesh))
    part = next(p for p in load_character("kei_arm").parts if p.get("skin") and len(p["verts"]) == 3)
    assert [w for _, w in part["skin"][0]] == [0.5, 0.5]
    arm["skin"] = [[["tail_03", 1.0]]] * 3
    (folder / "mesh.json").write_text(_json.dumps(mesh))
    with pytest.raises(CharacterError, match="tail_03"):
        load_character("kei_arm")


def _sculpt(chars, name, pose_over):
    """An imported copy of Kei's mesh, sculpted in the pose pose_over (a model made leaning, say)."""
    kei = load_character("kei")
    parts = pose_mesh(kei, {**rest_pose(kei), **pose_over})
    model = normalise(Model([MeshData(str(i), p.verts, p.tris) for i, p in enumerate(parts)], [], name), 1.71)
    P, rest, report = fit_rig(landmarks(model), 1.71)
    rest["neck"] = [stack_head(model, P, rest, 1.71), 0, 0]        # as kei.models.importer does
    bones = skeleton(rest, P)
    bound = [b for m in model.meshes for b in bind_mesh(m, bones, 1.71)]
    write_character(chars, name, name, 1.71, P, rest, bound, {"file": "test"}, report)
    return load_character(name)


def _posture(ch, shot):
    """Per key frame: the trunk pitch (pelvis to neck, degrees, + forward) and how far the head's middle is ahead of
    the shoulder joints (m), on the side view."""
    from kei.characters import on_character
    from kei.sample import bake
    out = []
    for fr in bake(on_character(shot, ch)):
        j = fr["joints"]
        pel, nk = j["pelvis"], j["neck_01"]
        verts = [v for p in pose_mesh(ch, fr["pose"]) for v in p.verts]
        hv = [v for v in verts if v[1] > j["neck_02"][1] + 0.03 and abs(v[0] - j["head"][0]) < 0.13]
        hz = (min(v[2] for v in hv) + max(v[2] for v in hv)) / 2
        out.append((math.degrees(math.atan2(nk[2] - pel[2], nk[1] - pel[1])),
                    hz - (j["upperarm_l"][2] + j["upperarm_r"][2]) / 2))
    return out


def test_a_sculpt_leaning_back_with_its_head_forward_plays_a_walk_with_the_walk_s_trunk_and_kei_s_head(chars):
    # 2026-11-02, Kei's approved walk on kei_model: "Kei is a bit too forward". The walk's trunk must play as
    # approved (7 to 8 deg forward) and the head must stack over the shoulders as Kei's does: the sculpt's forward
    # neck is bound in its rest, so a shot's neck at 0 stands it as Kei's stands.
    kei = load_character("kei")
    ch = _sculpt(chars, "swayback", {"spine": [-0.15, 0, 0], "neck": [0.45, 0, 0], "head": [-0.2, 0, 0]})
    lean = {"spine": [0.13, 0, 0]}
    shot = {"rig": "v4", "fps": 24, "frames": 2, "character": "kei",
            "keys": [{"f": 0, **rest_pose(kei), **lean}, {"f": 2, **rest_pose(kei), **lean}]}
    for (t0, a0), (t1, a1) in zip(_posture(kei, shot), _posture(ch, shot)):
        assert abs(t1 - t0) < 1.0, (t0, t1)
        assert abs(a1 - a0) < 0.02, (a0, a1)
