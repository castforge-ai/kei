"""Task 5 of plan 6: a pass keyed on the controls in Maya and read back for the checks. The Maya half runs real
mayapy jobs on a shot folder; it is skipped, with the reason, without Maya."""
import json
from pathlib import Path

import pytest

from kei.apps.maya import MayaError
from kei.apps.maya_shot import key_pass, keys_for, setup_shot
from kei.body_check import check_pass
from kei.characters import load_character
from kei.sample import ShotError, bake

import mayakit

REPO = Path(__file__).resolve().parents[1]
WALK = json.loads((REPO / "examples" / "stepped_walk" / "out_blocking" / "shot.json").read_text())


def test_a_maya_rig_shot_keys_its_own_controls(tmp_path):
    shot = {"rig": "maya", "frames": 10, "keys": [{"f": 0, "tangent": "linear", "ctl.translateY": 1.0},
                                                  {"f": 10, "ctl.translateY": 2.0}]}
    keys = keys_for(shot, tmp_path, "spline")
    assert keys == [{"f": 0, "tangent": "linear", "channels": {"ctl.translateY": 1.0}},
                    {"f": 10, "tangent": "spline", "channels": {"ctl.translateY": 2.0}}]
    assert {k["tangent"] for k in keys_for(shot, tmp_path, "step")} == {"step"}


def test_a_kei_rig_shot_without_a_control_map_is_refused(tmp_path):
    with pytest.raises(ShotError, match="maya_controls.json"):
        keys_for(WALK, tmp_path, "step")


def test_an_unknown_tangent_is_refused_with_the_key(tmp_path):
    with pytest.raises(ShotError, match="f 3"):
        keys_for({"rig": "maya", "keys": [{"f": 3, "tangent": "bouncy", "a.tx": 1}]}, tmp_path, "spline")


# ---------------- in Maya ----------------
@pytest.fixture(scope="module")
def shot(tmp_path_factory):
    py = mayakit.mayapy()
    d = tmp_path_factory.mktemp("maya_shot")
    setup_shot(d, character="kei", mayapy=py)
    (d / "out_blocking").mkdir()
    (d / "out_blocking" / "shot.json").write_text(json.dumps(WALK))
    report = key_pass(d, "blocking", mayapy=py)
    return d, report, py


@pytest.mark.maya
def test_setup_writes_the_scene_the_control_map_and_the_rig(shot):
    d, _, _ = shot
    assert (d / "maya" / "scene.ma").is_file()
    rig = json.loads((d / "rig" / "maya_controls.json").read_text())
    assert rig["character"] == "kei" and rig["units"] == "cm"
    assert json.loads((d / "rig" / "maya_rig.json").read_text())["controls"]


@pytest.mark.maya
def test_a_stepped_walk_keyed_on_the_controls_reads_back_as_kei_s_own(shot):
    d, report, _ = shot
    data = json.loads((d / "out_blocking" / "joints.json").read_text())
    assert data["source"] == "maya" and data["mode"] == "step" and report["clipped"] == []
    ch = load_character("kei")
    kei = bake({**WALK, "props": {"proportions": ch.proportions}}, "step")
    worst = max(max(abs(a - b) for a, b in zip(fr["joints"][n], k["joints"][n]))
                for fr, k in zip(data["frames"], kei) for n in k["joints"])
    assert worst < 0.001, worst
    assert (d / "out_blocking" / "scene.ma").is_file()


@pytest.mark.maya
def test_kei_check_measures_the_joints_maya_gave_back(shot):
    d, _, _ = shot
    rep = json.loads(check_pass(d, "blocking", "kei").read_text())
    assert rep["joints_from"] == "maya" and rep["frames"] == WALK["frames"]


@pytest.mark.maya
def test_a_locked_channel_in_shot_json_is_refused_with_the_control_and_channel(shot):
    d, _, py = shot
    (d / "out_p1").mkdir(exist_ok=True)
    (d / "out_p1" / "shot.json").write_text(json.dumps(
        {"rig": "maya", "frames": 4, "keys": [{"f": 0, "kei:l_index_02_fk_ctl.translateX": 1.0}]}))
    with pytest.raises(MayaError, match=r"l_index_02_fk_ctl\.translateX is locked"):
        key_pass(d, "p1", mayapy=py)


@pytest.mark.maya
def test_render_writes_each_view_s_frames_and_records_the_renderer(shot):
    d, _, py = shot
    from kei.apps.maya_shot import render_pass
    r = render_pass(d, "blocking", views=["front", "side"], width=320, height=180, mayapy=py)
    assert r["renderer"] == "maya playblast"
    assert r["frames"] == {"front": WALK["frames"] + 1, "side": WALK["frames"] + 1}
    assert (d / "out_blocking" / "maya_views" / "side" / "f0000.png").read_bytes()[:4] == b"\x89PNG"
    rep = json.loads((d / "out_blocking" / "maya_report.json").read_text())
    assert rep["views"]["renderer"] == "maya playblast"


@pytest.mark.maya
def test_the_fbx_holds_the_mannequin_joints_baked_and_no_control_rig(shot):
    d, _, py = shot
    from fbxread import read_fbx
    from kei.apps.maya_shot import export_pass
    from kei.rig import ALL_BONES
    before = (d / "out_blocking" / "scene.ma").read_bytes()
    r = export_pass(d, "blocking", d / "walk.fbx", mayapy=py)
    _, top = read_fbx((d / "walk.fbx").read_bytes())
    objects = next(n for n in top if n.name == "Objects").children
    models = [o.props[1].split("\x00")[0] for o in objects if o.name == "Model"]
    limbs = {o.props[1].split("\x00")[0] for o in objects if o.name == "Model" and o.props[2] == "LimbNode"}
    assert set(ALL_BONES) <= limbs
    assert not [m for m in models if m.endswith("_ctl") or ":" in m]
    assert not [o for o in objects if "Constraint" in o.name]
    assert any(o.name == "AnimationCurve" for o in objects)
    assert r["joints"] == len(ALL_BONES)
    assert (d / "out_blocking" / "scene.ma").read_bytes() == before     # the pass's scene is never saved over


def test_kei_bake_refuses_a_maya_shot_so_maya_s_joints_are_kept(tmp_path, capsys):
    from kei.cli import main
    (tmp_path / "maya").mkdir()
    (tmp_path / "maya" / "scene.ma").write_text("//Maya ASCII")
    assert main(["bake", str(tmp_path), "p1"]) == 1
    assert "kei maya key" in capsys.readouterr().out


def test_kei_render_with_another_camera_on_a_maya_shot_says_why(tmp_path, capsys):
    from kei.cli import main
    (tmp_path / "maya").mkdir()
    (tmp_path / "maya" / "scene.ma").write_text("//Maya ASCII")
    assert main(["render", str(tmp_path), "p1", "--camera", "follow"]) == 1
    assert "Maya's cameras" in capsys.readouterr().out
