"""Engine-ready export: the shot's objects come along, several clips go in one file, an imported character keeps its
own bone names, and a file can hold the skeleton and the animation only."""
import json
import math

import pytest

from fbxread import read_fbx
from kei.characters import load_character
from kei.cli import EXIT_DONE, EXIT_ERROR, EXIT_NEEDS_ANSWER, main
from kei.export_fbx import fbx_from_scene
from kei.export_gltf import gltf_from_scene, pack_glb, read_glb, to_gltf
from kei.export_scene import ExportError, build_scene, source_names
from kei.objects import track
from kei.sample import bake
from kei.characters import on_character
from test_export_gltf import data

STILL = {"rig": "v4", "fps": 24, "frames": 6,
         "keys": [{"f": 0, "root": [0, 0.915, 0]}, {"f": 6, "root": [0, 0.9, 0.1]}]}
CRATE = {"rig": "v4", "fps": 24, "frames": 12,
         "keys": [{"f": 0, "root": [0, 0.915, 0]}, {"f": 12, "root": [0, 0.915, 0.4]}],
         "objects": [{"name": "crate", "shape": "box", "size": [0.4, 0.4, 0.4], "rest": [0.0, 0.2, 0.6],
                      "colour": "#9a7448",
                      "path": [{"f": 0, "pos": [0.0, 0.2, 0.6], "yaw_deg": 0},
                               {"f": 12, "pos": [0.3, 0.2, 1.0], "yaw_deg": 90}],
                      "attach": []}]}


def _fbx(scene):
    _, top = read_fbx(fbx_from_scene(scene))
    top = {n.name: n for n in top}
    objs = top["Objects"].children
    return top, objs


def _named(objs, kind, sub=None):
    return [o.props[1].split("\x00\x01")[0] for o in objs if o.name == kind and (sub is None or o.props[2] == sub)]


# ---- objects --------------------------------------------------------------------------------------------------------

def test_a_shot_object_is_its_own_unskinned_mesh_with_a_track():
    ch = load_character("kei")
    scene = build_scene(ch, shot=CRATE)
    assert [o.name for o in scene.objects] == ["crate"]
    doc, binary = gltf_from_scene(scene)
    node = next(i for i, n in enumerate(doc["nodes"]) if n["name"] == "crate")
    assert "skin" not in doc["nodes"][node] and node in doc["scenes"][0]["nodes"]
    mesh = doc["meshes"][doc["nodes"][node]["mesh"]]
    assert set(mesh["primitives"][0]["attributes"]) == {"POSITION", "NORMAL"}
    assert any(m["name"] == "object:crate" for m in doc["materials"])
    anim = doc["animations"][0]
    moves = {ch_["target"]["path"]: data(doc, binary, anim["samplers"][ch_["sampler"]]["output"])
             for ch_ in anim["channels"] if ch_["target"]["node"] == node}
    frames = bake(on_character(CRATE, ch))
    want = [c for c, _ in track(CRATE["objects"][0], frames)]
    assert len(moves["translation"]) == len(want)
    for got, w in zip(moves["translation"], want):
        assert math.dist(got, to_gltf(w)) < 1e-5
    q = moves["rotation"][-1]                       # a quarter turn about the vertical by the last frame
    assert abs(abs(q[3]) - math.cos(math.pi / 4)) < 1e-5 and abs(q[0]) < 1e-6 and abs(q[2]) < 1e-6


def test_the_fbx_object_is_a_mesh_model_with_its_curves():
    top, objs = _fbx(build_scene(load_character("kei"), shot=CRATE))
    assert "crate" in _named(objs, "Model", "Mesh")
    assert "crate" in _named(objs, "Material")
    geos = _named(objs, "Geometry")
    assert "crate" in geos and len(geos) == 2            # the character and the crate
    assert len([o for o in objs if o.name == "Deformer" and o.props[2] == "Skin"]) == 1   # only the character


# ---- several clips --------------------------------------------------------------------------------------------------

def test_several_clips_in_one_file():
    ch = load_character("keira")
    scene = build_scene(ch, clips=[("walk", STILL, "spline"), ("carry", CRATE, "spline")])
    assert [c.name for c in scene.clips()] == ["walk", "carry"]
    doc, _ = gltf_from_scene(scene)
    assert [a["name"] for a in doc["animations"]] == ["walk", "carry"]
    crate = next(i for i, n in enumerate(doc["nodes"]) if n["name"] == "crate")
    assert not any(c["target"]["node"] == crate for c in doc["animations"][0]["channels"])
    assert any(c["target"]["node"] == crate for c in doc["animations"][1]["channels"])
    top, objs = _fbx(scene)
    assert _named(objs, "AnimationStack") == ["walk", "carry"]
    assert [t.props[0] for t in top["Takes"].children if t.name == "Take"] == ["walk", "carry"]


def test_two_clips_with_one_name_are_refused():
    with pytest.raises(ExportError):
        build_scene(load_character("kei"), clips=[("a", STILL, "spline"), ("a", STILL, "spline")])


# ---- skeleton only --------------------------------------------------------------------------------------------------

def test_skeleton_only_has_no_mesh_but_keeps_the_animation():
    scene = build_scene(load_character("kei"), shot=CRATE, mesh=False)
    doc, _ = gltf_from_scene(scene)
    assert "meshes" not in doc and doc["skins"] and len(doc["animations"]) == 1
    crate = next(n for n in doc["nodes"] if n["name"] == "crate")
    assert "mesh" not in crate
    _, objs = _fbx(scene)
    assert not _named(objs, "Geometry") and not [o for o in objs if o.name == "Deformer"]
    assert "crate" in _named(objs, "Model", "Null") and _named(objs, "AnimationStack")


# ---- the model's own bone names -------------------------------------------------------------------------------------

def test_source_names_rename_bones_and_skin():
    ch = load_character("kei")
    ch.source = {"skeleton": "the model's own", "bones": {"pelvis": "Hips", "head": "Head", "hand_l": "LeftHand"}}
    scene = build_scene(ch, shot=STILL, names="source")
    names = [b.name for b in scene.bones]
    assert {"Hips", "Head", "LeftHand"} <= set(names) and "pelvis" not in names
    assert next(b for b in scene.bones if b.name == "spine_01").parent == "Hips"
    used = {m.bone for m in scene.meshes} | {n for m in scene.meshes if m.weights for vw in m.weights for n, _ in vw}
    assert used <= set(names)
    doc, _ = gltf_from_scene(scene)               # every vertex still finds its joint
    assert {"Hips", "Head"} <= {n["name"] for n in doc["nodes"]}


def test_a_built_in_character_keeps_kei_names():
    assert source_names(load_character("kei")) == {}


def test_an_old_rigged_import_with_its_file_gone_says_what_to_do(tmp_path):
    ch = load_character("kei")
    ch.source = {"skeleton": "the model's own", "file": str(tmp_path / "gone.fbx")}
    with pytest.raises(ExportError, match="import it again"):
        source_names(ch)


@pytest.fixture
def chars(tmp_path, monkeypatch):
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "characters"))
    return tmp_path / "characters"


def test_a_rigged_import_records_its_names_and_exports_them(chars, tmp_path, capsys):
    ours = {"pelvis": "Hips", "spine_01": "Spine", "head": "Head", "thigh_l": "LeftUpLeg", "calf_l": "LeftLeg",
            "upperarm_r": "RightArm", "hand_r": "RightHand"}
    scene = build_scene(load_character("keira"))
    for b in scene.bones:
        b.name, b.parent = ours.get(b.name, b.name), (ours.get(b.parent, b.parent) if b.parent else None)
    for m in scene.meshes:
        m.bone = ours.get(m.bone, m.bone)
    src = tmp_path / "theirs.glb"
    src.write_bytes(pack_glb(*gltf_from_scene(scene)))
    assert main(["import", str(src), "--name", "theirs"]) == EXIT_NEEDS_ANSWER
    recorded = json.loads((chars / "theirs" / "character.json").read_text())["source"]["bones"]
    for kei, theirs in ours.items():
        assert recorded.get(kei) == theirs, kei
    main(["import", "--confirm", "--name", "theirs"])
    shot = tmp_path / "s"
    (shot / "out_p1").mkdir(parents=True)
    (shot / "out_p1" / "shot.json").write_text(json.dumps({**STILL, "character": "theirs"}), encoding="utf-8")
    out = tmp_path / "back.glb"
    capsys.readouterr()
    assert main(["export", str(shot), "--pass", "p1", "--out", str(out)]) == EXIT_DONE
    assert "the model's own bone names" in capsys.readouterr().out
    names = {n["name"] for n in read_glb(out.read_bytes())[0]["nodes"]}
    assert set(ours.values()) <= names
    assert main(["export", str(shot), "--pass", "p1", "--out", str(out), "--names", "kei"]) == EXIT_DONE
    names = {n["name"] for n in read_glb(out.read_bytes())[0]["nodes"]}
    assert "pelvis" in names and "Hips" not in names


# ---- the command ----------------------------------------------------------------------------------------------------

def _shot(root, name, shot, character="kei"):
    d = root / name
    (d / "out_p1").mkdir(parents=True)
    (d / "out_p1" / "shot.json").write_text(json.dumps({**shot, "character": character}), encoding="utf-8")
    return d


def test_kei_export_clip_adds_clips_and_skeleton_only_drops_the_mesh(tmp_path, capsys):
    a, b = _shot(tmp_path, "walk", STILL), _shot(tmp_path, "carry", CRATE)
    out = tmp_path / "set.glb"
    assert main(["export", str(a), "--clip", f"{b}@p1", "--out", str(out), "--skeleton-only"]) == EXIT_DONE
    said = capsys.readouterr().out
    assert "2 clips: walk_p1, carry_p1" in said and "skeleton and animation only" in said
    doc, _ = read_glb(out.read_bytes())
    assert [x["name"] for x in doc["animations"]] == ["walk_p1", "carry_p1"] and "meshes" not in doc
    fbx = tmp_path / "set.fbx"
    assert main(["export", str(a), "--clip", str(b), "--out", str(fbx)]) == EXIT_DONE
    _, top = read_fbx(fbx.read_bytes())
    takes = next(n for n in top if n.name == "Takes")
    assert [t.props[0] for t in takes.children if t.name == "Take"] == ["walk_p1", "carry_p1"]


def test_a_clip_on_another_character_is_refused(tmp_path, capsys):
    a, b = _shot(tmp_path, "walk", STILL), _shot(tmp_path, "other", STILL, "keira")
    assert main(["export", str(a), "--clip", str(b), "--out", str(tmp_path / "x.glb")]) == EXIT_ERROR
    assert "one file holds one character" in "".join(capsys.readouterr())
