"""A second performer of the same character in the shot (a ghost, a double): its own binding, keys, look and joints."""
import json

import pytest

from kei.apps.unreal_keys import apply_keys, parse_keys, performers_of
from kei.apps.unreal_readback import _placed, read_back
from kei.apps.unreal_rig import read_rig
from kei.render import draw_figure
from kei.sample import ShotError
from unrealkit import MANNY, FakeEditor

LOOK = [{"name": "GB_StatusEnshrouded_Enable", "value": 1, "association": "blend",
         "layer": "/Game/Art_Lib/MLB/MLB_CHA_GameplayBlend"}]
GHOST = {"ghost": {"offset_cm": [120, 60, 0], "yaw_deg": 0, "look": LOOK}}


def _shot(frames=4, ghost=True, performers=None, step=lambda f: 90.0):
    keys = []
    for f in range(frames + 1):
        k = {"f": f, "tangent": "spline", "pelvis_ctrl.location.z": step(f)}
        if ghost:
            k["ghost/pelvis_ctrl.location.z"] = 80.0 + f
        keys.append(k)
    return {"rig": "unreal", "fps": 24, "frames": frames, "keys": keys,
            **({"performers": performers if performers is not None else GHOST} if ghost else {})}


def _write(shot_dir, name, shot):
    out = shot_dir / f"out_{name}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "shot.json").write_text(json.dumps(shot))


def test_the_character_s_keys_and_a_performer_s_keys_are_read_apart():
    ed = FakeEditor()
    shot = _shot()
    mine = parse_keys(shot, ed.rig, "spline")
    ghost = parse_keys(shot, ed.rig, "spline", "ghost")
    assert mine[2]["controls"] == {"pelvis_ctrl": {"location.z": 90.0}}
    assert ghost[2]["controls"] == {"pelvis_ctrl": {"location.z": 82.0}}
    assert performers_of(shot)["ghost"]["look"][0]["association"] == "blend"


def test_a_prefix_that_names_no_performer_or_a_bad_look_is_refused_in_words():
    ed = FakeEditor()
    with pytest.raises(ShotError, match="names no performer"):
        parse_keys(_shot(performers={}), ed.rig, "spline")
    bad = {"ghost": {"offset_cm": [0, 0, 0], "look": [{"name": "X", "value": 1, "association": "blend"}]}}
    with pytest.raises(ShotError, match="names its layer function"):
        performers_of({"performers": bad})
    with pytest.raises(ShotError, match="lower case"):
        performers_of({"performers": {"Ghost Ren": {}}})


def test_a_performer_gets_its_own_binding_look_and_keys_and_is_read_back_where_it_stands(tmp_path):
    shot = tmp_path / "breaker"
    shot.mkdir()
    ed = FakeEditor(bones=lambda f: {"pelvis": [0.0, 0.0, 90.0]})
    ed.performer_bones["ghost"] = lambda f: {"pelvis": [0.0, 0.0, 80.0 + f]}
    with ed.server() as fake:
        read_rig(ed.client(), shot, MANNY)
        _write(shot, "blocking", _shot())
        fake.scripts.clear()
        r = apply_keys(ed.client(), shot, "blocking")
        assert fake.scripts[:2] == ["make_look", "make_sequence"]
        seq = ed.sequences[r["sequence"]]
        assert seq["performers"]["ghost"]["offset_cm"] == [120.0, 60.0, 0.0]
        assert seq["performers"]["ghost"]["materials"][0].startswith("/Game/Kei/breaker/looks/ghost/")
        assert ed.looks[0]["scalars"][0]["layer"] == "/Game/Art_Lib/MLB/MLB_CHA_GameplayBlend"
        assert {k["performer"] for k in ed.keys} == {"", "ghost"}
        assert r["performers"]["ghost"]["keys"] == 5 and "ghost (5 frames)" in r["said"]
        with pytest.raises(ShotError):      # the fake editor's bones lack most of the body: the read-back says so
            read_back(ed.client(), shot, "blocking", "kei")


def test_a_performer_stands_at_its_offset_turned_by_its_yaw():
    assert _placed((10.0, 0.0, 5.0), [100.0, 50.0, 0.0], 90.0) == pytest.approx((100.0, 60.0, 5.0))


def test_a_layered_pass_layers_each_performer_and_a_new_one_keys_the_whole_pass_fresh(tmp_path):
    shot = tmp_path / "breaker"
    shot.mkdir()
    ed = FakeEditor()
    with ed.server() as fake:
        read_rig(ed.client(), shot, MANNY)
        _write(shot, "p1", _shot())
        apply_keys(ed.client(), shot, "p1")
        moved = _shot()
        moved["keys"][2]["ghost/pelvis_ctrl.location.z"] = 95.0
        _write(shot, "p2", moved)
        fake.scripts.clear()
        r = apply_keys(ed.client(), shot, "p2")
        assert "set_keys" not in fake.scripts and r["layer"]["from"] == "p1"
        seq = ed.sequences[r["sequence"]]
        assert seq["copy_from"] and seq["layer/ghost"] == {"pelvis_ctrl.Location.Z": [[1, 0.0], [2, 13.0], [3, 0.0]]}
        _write(shot, "p3", _shot(performers={"ghost": {"offset_cm": [0, 200, 0], "look": LOOK}}))
        r = apply_keys(ed.client(), shot, "p3")
        assert not ed.sequences[r["sequence"]]["copy_from"] and "full" in r["layer"]


def test_the_renders_draw_a_performer_behind_the_character():
    class Canvas:
        def __init__(self):
            self.lines = []

        def line(self, x0, y0, x1, y1, c, *a):
            self.lines.append(c)

        def disk(self, *a):
            pass
    cv = Canvas()
    joints = {"spine_01": (0, 1, 0), "spine_02": (0, 1.1, 0), "ghost/spine_01": (1, 1, 0), "ghost/spine_02": (1, 1.1, 0)}
    draw_figure(cv, lambda p: (p[0], p[1]), joints)
    from kei.render import PERFORMER, RIGHT
    assert cv.lines[0] == PERFORMER and RIGHT in cv.lines[1:]
