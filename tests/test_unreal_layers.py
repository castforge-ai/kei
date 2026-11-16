"""A pass as a layer of the one before it: only what changed is written, as deltas, then merged down."""
import contextlib
import json

from kei.apps.unreal_keys import apply_keys, previous_pass
from kei.apps.unreal_layers import layer_plan, section_channel
from kei.apps.unreal_rig import read_rig
from unrealkit import MANNY, FakeEditor

TYPES = {"pelvis_ctrl": "euler_transform", "spine_blend": "float", "head_ctrl": "rotator", "ik": "bool"}


def dense(frames, pelvis=lambda f: 90.0, tangent="spline"):
    return [{"f": f, "tangent": tangent, "controls": {"pelvis_ctrl": {"location.z": pelvis(f), "rotation.z": 0.0},
                                                      "spine_blend": {"value": 0.5}}}
            for f in range(frames + 1)]


def test_section_channels_are_named_as_the_editor_lists_them():
    assert section_channel("body_ctrl", "location.x", "euler_transform") == "body_ctrl.Location.X"
    assert section_channel("body_ctrl", "rotation.z", "euler_transform") == "body_ctrl.Rotation.Z"
    assert section_channel("hand_l_ikorient_ctrl", "rotation.x", "rotator") == "hand_l_ikorient_ctrl.Rotation.Roll"
    assert section_channel("roll_blend_l_ctrl", "value", "float") == "roll_blend_l_ctrl"
    assert section_channel("arm_l_fk_ik_switch", "value", "bool") is None


def test_only_the_changed_channel_is_written_with_zero_keys_one_frame_either_side():
    new = dense(24, pelvis=lambda f: 90.0 + (2.0 if 10 <= f <= 14 else 0.0))
    plan = layer_plan(dense(24), new, TYPES, 24)
    assert list(plan["channels"]) == ["pelvis_ctrl.Location.Z"]
    keys = plan["channels"]["pelvis_ctrl.Location.Z"]
    assert keys[0] == [9, 0.0] and keys[-1] == [15, 0.0] and [10, 2.0] in keys
    assert plan["controls"] == {"pelvis_ctrl": [9, 15]} and plan["keys"] == 7


def test_a_sparse_pass_new_tangents_or_a_flipped_switch_are_keyed_whole():
    assert "full" in layer_plan(dense(24)[::2], dense(24), TYPES, 24)
    assert "full" in layer_plan(dense(24), dense(24, tangent="linear"), TYPES, 24)
    a, b = dense(4), dense(4)
    for k in a:
        k["controls"]["ik"] = {"value": True}
    for k in b:
        k["controls"]["ik"] = {"value": k["f"] < 2}
    assert layer_plan(a, b, TYPES, 4)["full"] == "the switch ik changed"


def _write(shot, name, keys, frames=24):
    out = shot / f"out_{name}"
    out.mkdir(parents=True, exist_ok=True)
    flat = [{"f": k["f"], "tangent": k["tangent"], **{f"{c}.{ch}": v for c, chans in k["controls"].items()
                                                       for ch, v in chans.items()}} for k in keys]
    (out / "shot.json").write_text(json.dumps({"rig": "unreal", "fps": 24, "frames": frames, "keys": flat}))


@contextlib.contextmanager
def two_passes(tmp_path, new):
    shot = tmp_path / "walk_01"
    shot.mkdir()
    ed = FakeEditor()
    with ed.server() as fake:
        read_rig(ed.client(), shot, MANNY)
        _write(shot, "p1", dense(24))
        apply_keys(ed.client(), shot, "p1")
        _write(shot, "p2", new)
        fake.scripts.clear()
        yield shot, ed, fake


def test_the_next_pass_is_a_copy_of_the_last_one_with_its_changes_layered_and_merged(tmp_path):
    with two_passes(tmp_path, dense(24, pelvis=lambda f: 90.0 + (3.0 if f == 12 else 0.0))) as (shot, ed, fake):
        assert previous_pass(shot, "p2") == "p1" and previous_pass(shot, "p1") is None
        r = apply_keys(ed.client(), shot, "p2")
        assert fake.scripts == ["make_sequence", "dirty", "layer_keys", "dirty", "save_asset"]       # no set_keys
    seq = ed.sequences[r["sequence"]]
    assert seq["copy_from"] == "/Game/Kei/walk_01/LS_walk_01_p1_1"
    assert seq["layer"] == {"pelvis_ctrl.Location.Z": [[11, 0.0], [12, 3.0], [13, 0.0]]}
    assert r["layer"] == {"from": "p1", "controls": {"pelvis_ctrl": [11, 13]}, "keys": 3, "channels": 1}
    assert "layered 1 changed channel" in r["said"]


def test_a_layer_the_editor_cannot_place_is_keyed_whole_on_the_copy(tmp_path):
    with two_passes(tmp_path, dense(24, pelvis=lambda f: 91.0)) as (shot, ed, fake):
        ed.missing_channels = {"pelvis_ctrl.Location.Z"}
        r = apply_keys(ed.client(), shot, "p2")
        assert "set_keys" in fake.scripts
    assert "full" in r["layer"] and "pelvis_ctrl.Location.Z" in r["layer"]["full"]


def test_a_seat_finds_kei_installed_for_one_user(tmp_path, monkeypatch):
    import os
    import sysconfig
    from kei import seats
    exe = "kei.exe" if os.name == "nt" else "kei"
    (tmp_path / exe).write_text("")
    real = sysconfig.get_path
    monkeypatch.setattr(seats.sysconfig, "get_path",
                        lambda name, scheme=None: str(tmp_path) if scheme and scheme.endswith("_user") else real(name))
    assert str(tmp_path) in seats.seat_env()["PATH"].split(os.pathsep)[:3]
