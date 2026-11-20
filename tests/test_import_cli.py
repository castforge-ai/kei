"""kei import: an outside model becomes a character; a shot on it waits until the person approves the fit."""
import json

import pytest

from kei.characters import load_character, rest_pose
from kei.characters.mesh import pose_mesh
from kei.cli import EXIT_DONE, EXIT_ERROR, EXIT_NEEDS_ANSWER, main
from kei.config import Config, SeatSpec
from kei.conductor import run_shot
from kei.export_gltf import export_glb
from kei.fbx import Node, P, fbx_file
from kei.seats import FakeSeat
from test_conductor import Recorder, shot


@pytest.fixture
def chars(tmp_path, monkeypatch):
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "characters"))
    return tmp_path / "characters"


def unrigged_fbx(path, name="kei"):
    """A character's rest mesh as a plain FBX: one mesh, no skeleton, in centimetres (glTF axes, as files are)."""
    ch = load_character(name)
    verts, poly = [], []
    for p in pose_mesh(ch, rest_pose(ch)):
        base = len(verts) // 3
        for v in p.verts:
            verts += [-v[0] * 100, v[1] * 100, v[2] * 100]
        for a, b, c in p.tris:
            poly += [base + a, base + c, -(base + b) - 1]
    gs = Node("GlobalSettings", [], [Node("Properties70", [], [
        Node("P", ["UnitScaleFactor", "double", "Number", "", 1.0])])])
    geo = Node("Geometry", [P("L", 10), "body\x00\x01Geometry", "Mesh"], [
        Node("Vertices", [P("d", verts)]), Node("PolygonVertexIndex", [P("i", poly)])])
    model = Node("Model", [P("L", 11), "body\x00\x01Model", "Mesh"], [])
    conn = Node("Connections", [], [Node("C", ["OO", P("L", 11), P("L", 0)]), Node("C", ["OO", P("L", 10), P("L", 11)])])
    path.write_bytes(fbx_file([gs, Node("Objects", [], [geo, model]), conn]))
    return path


def test_kei_import_writes_the_character_and_its_fit_sheet(chars, tmp_path, capsys):
    src = unrigged_fbx(tmp_path / "scan.fbx")
    assert main(["import", str(src), "--name", "kei_scan", "--height", "1.71"]) == EXIT_NEEDS_ANSWER
    out = capsys.readouterr().out
    folder = chars / "kei_scan"
    for f in ("character.json", "mesh.json", "fit.png"):
        assert (folder / f).is_file()
    assert str(folder / "fit.png") in out and "kei import --confirm --name kei_scan" in out
    ch = load_character("kei_scan")
    assert not ch.confirmed and ch.source["file"] == str(src)


def test_an_unrigged_model_with_no_height_asks_for_one(chars, tmp_path, capsys):
    assert main(["import", str(unrigged_fbx(tmp_path / "scan.fbx")), "--name", "kei_scan"]) == EXIT_ERROR
    assert "--height" in "".join(capsys.readouterr())


def test_a_rigged_model_imports_on_its_own_skeleton_at_its_own_height(chars, tmp_path):
    src = tmp_path / "keira.glb"
    export_glb(load_character("keira"), src, 1.0, None, "spline")
    assert main(["import", str(src), "--name", "keira_copy"]) == EXIT_NEEDS_ANSWER
    copy, keira = load_character("keira_copy"), load_character("keira")
    assert abs(copy.height - 1.71) < 0.02
    for k in ("thigh", "calf", "upperarm", "lowerarm"):
        assert abs(copy.proportions[k] - keira.proportions[k]) < 0.01, k
    assert json.loads((chars / "keira_copy" / "character.json").read_text())["source"]["skeleton"] == "the model's own"


def test_kei_import_confirm_marks_the_fit_approved(chars, tmp_path):
    main(["import", str(unrigged_fbx(tmp_path / "scan.fbx")), "--name", "kei_scan", "--height", "1.71"])
    assert main(["import", "--confirm", "--name", "kei_scan"]) == EXIT_DONE
    assert load_character("kei_scan").confirmed


def test_a_shot_on_an_unconfirmed_character_asks_about_the_fit_first(chars, tmp_path):
    main(["import", str(unrigged_fbx(tmp_path / "scan.fbx")), "--name", "kei_scan", "--height", "1.71"])
    cfg = Config(animator=SeatSpec(name="fake", cmd=["unused"]), character="kei_scan")
    rec = Recorder()
    root = shot(tmp_path)
    state = run_shot(root, "a box falls", cfg, animator=FakeSeat("fake", rec), review=lambda s, d, c: [])
    assert state.status == "needs_answer" and rec.prompts == []          # nothing ran before the answer
    q = state.questions[0]
    assert q["from"] == "kei" and q["look_at"] == [str(chars / "kei_scan" / "fit.png")]
    assert main(["answer", str(root), "--text", "Yes."]) == EXIT_DONE
    state = run_shot(root, "a box falls", cfg, animator=FakeSeat("fake", rec), review=lambda s, d, c: [])
    assert state.status == "needs_approval"
    assert load_character("kei_scan").confirmed


def test_a_fit_answered_no_stops_for_a_new_import(chars, tmp_path):
    main(["import", str(unrigged_fbx(tmp_path / "scan.fbx")), "--name", "kei_scan", "--height", "1.71"])
    cfg = Config(animator=SeatSpec(name="fake", cmd=["unused"]), character="kei_scan")
    root = shot(tmp_path)
    run_shot(root, "a box falls", cfg, animator=FakeSeat("fake", Recorder()), review=lambda s, d, c: [])
    main(["answer", str(root), "--text", "no, the elbows are too low"])
    state = run_shot(root, "a box falls", cfg, animator=FakeSeat("fake", Recorder()), review=lambda s, d, c: [])
    assert state.status == "needs_human"
    assert "the elbows are too low" in state.history[-1]["misses"][0]
    assert not load_character("kei_scan").confirmed


def _gated(chars, tmp_path, answer):
    main(["import", str(unrigged_fbx(tmp_path / "scan.fbx")), "--name", "kei_scan", "--height", "1.71"])
    cfg = Config(animator=SeatSpec(name="fake", cmd=["unused"]), character="kei_scan")
    root = shot(tmp_path)
    run_shot(root, "a box falls", cfg, animator=FakeSeat("fake", Recorder()), review=lambda s, d, c: [])
    main(["answer", str(root), "--text", answer])
    return root, cfg


def test_ok_but_something_is_not_a_yes(chars, tmp_path):
    root, cfg = _gated(chars, tmp_path, "ok but the elbows are low")
    state = run_shot(root, "a box falls", cfg, animator=FakeSeat("fake", Recorder()), review=lambda s, d, c: [])
    assert state.status == "needs_human" and not load_character("kei_scan").confirmed


def test_a_yes_given_before_a_new_import_does_not_approve_the_new_fit(chars, tmp_path):
    root, cfg = _gated(chars, tmp_path, "yes")
    main(["import", str(unrigged_fbx(tmp_path / "scan2.fbx")), "--name", "kei_scan", "--height", "1.71"])
    state = run_shot(root, "a box falls", cfg, animator=FakeSeat("fake", Recorder()), review=lambda s, d, c: [])
    assert state.status == "needs_answer" and not load_character("kei_scan").confirmed


def test_a_character_named_only_in_a_pass_is_gated_too(chars, tmp_path):
    main(["import", str(unrigged_fbx(tmp_path / "scan.fbx")), "--name", "kei_scan", "--height", "1.71"])
    root = shot(tmp_path)
    (root / "out_p1").mkdir()
    (root / "out_p1" / "shot.json").write_text(json.dumps({"character": "kei_scan"}))
    cfg = Config(animator=SeatSpec(name="fake", cmd=["unused"]))
    rec = Recorder()
    state = run_shot(root, "a box falls", cfg, animator=FakeSeat("fake", rec), review=lambda s, d, c: [])
    assert state.status == "needs_answer" and rec.prompts == []
    assert "kei_scan" in state.questions[0]["text"]


def test_kei_characters_lists_the_imported_ones_and_whether_their_fit_is_approved(chars, tmp_path, capsys):
    main(["import", str(unrigged_fbx(tmp_path / "scan.fbx")), "--name", "kei_scan", "--height", "1.71"])
    capsys.readouterr()
    assert main(["characters"]) == EXIT_DONE
    out = capsys.readouterr().out
    assert "kei_scan" in out and "fit not approved" in out and "keira" in out
