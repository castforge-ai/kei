"""Task 3 of plan 6, Kei's side: Kei's poses as values on the Maya control rig (no Maya needed)."""
import math

import pytest

from kei.apps.maya_controls import (FK_BONES, ROTATE_ORDERS, ControlError, control_rig_job, extra_offsets, fk_name,
                                    pose_to_controls, shot_keys)
from kei.characters import load_character, rest_pose
from kei.rig import _skeleton


def _rig(name="kei", unit=100.0, extra=()):
    ctls = ["c_world_ctl", "c_root_ctl", "c_body_ctl"] + [fk_name(b) for b in FK_BONES]
    roles = {"c_world_ctl": "world", "c_root_ctl": "root", "c_body_ctl": "body"}
    for s in "lr":
        for c, r in (("foot_ik", "foot_ik"), ("leg_pv", "leg_pv"), ("arm_ik", "arm_ik"), ("arm_pv", "arm_pv"),
                     ("leg_settings", "leg_settings"), ("arm_settings", "arm_settings")):
            ctls.append(f"{s}_{c}_ctl")
            roles[f"{s}_{c}_ctl"] = r
    controls = [{"name": f"{name}:{c}", "role": roles.get(c, "fk")} for c in ctls] + list(extra)
    return {"character": name, "namespace": name, "unit_per_m": unit, "controls": controls}


DEFAULTS = {"ikFk": None, "stretch": 1.0, "squash": 1.0, "neckStretch": 1.0, "roll": 0.0, "bank": 0.0,
            "toeTap": 0.0, "heelPivot": 0.0, "toePivot": 0.0}


@pytest.mark.parametrize("name", ["kei", "keira"])
def test_the_rest_pose_gives_zero_on_every_control_and_defaults_on_the_attributes(name):
    ch = load_character(name)
    vals = pose_to_controls(rest_pose(ch), _rig(name))
    for k, v in vals.items():
        attr = k.rsplit(".", 1)[1]
        if attr.startswith(("translate", "rotate")):
            assert abs(v) < 1e-6, (k, v)
        elif attr == "ballAngle":
            assert abs(v - math.degrees(0.6)) < 1e-9
        elif attr == "ikFk":
            assert v == (1.0 if "_leg_" in k else 0.0)
        else:
            assert v == DEFAULTS[attr], k


def test_a_pose_missing_channels_takes_the_stand():
    a = pose_to_controls({}, _rig())
    b = pose_to_controls({"spine": [0.05, 0, 0]}, _rig())
    assert a == b


def test_translates_are_in_the_scene_unit():
    cm = pose_to_controls({"root": [0.0, 0.9, 0.1]}, _rig(unit=100.0))
    m = pose_to_controls({"root": [0.0, 0.9, 0.1]}, _rig(unit=1.0))
    assert abs(cm["kei:c_root_ctl.translateZ"] - 100 * m["kei:c_root_ctl.translateZ"]) < 1e-9
    assert abs(m["kei:c_root_ctl.translateZ"] - 0.1) < 1e-12


def test_kei_right_is_maya_minus_x():
    vals = pose_to_controls({"root": [0.2, 0.98, 0.0]}, _rig(unit=1.0))
    assert abs(vals["kei:c_root_ctl.translateX"] + 0.2) < 1e-12


def test_an_unknown_control_in_the_map_is_refused_with_its_name():
    bad = _rig(extra=[{"name": "kei:l_tail_fk_ctl", "role": "tail"}])
    with pytest.raises(ControlError, match="l_tail_fk_ctl"):
        pose_to_controls({}, bad)


def test_a_control_missing_from_the_map_is_refused_with_its_name():
    rig = _rig()
    rig["controls"] = [c for c in rig["controls"] if not c["name"].endswith("l_foot_ik_ctl")]
    with pytest.raises(ControlError, match="l_foot_ik_ctl"):
        pose_to_controls({}, rig)


def test_every_rotate_order_has_a_reason():
    assert all(len(reason) > 20 and order in ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")
               for order, reason in ROTATE_ORDERS.values())


def test_keys_keep_euler_angles_near_the_key_before():
    """A head that turns past 180 degrees in three keys keeps a smooth curve, with no 360 jump."""
    shot = {"rig": "v4", "frames": 20, "keys": [{"f": 0, "head": [0, 0, 2.5]}, {"f": 10, "head": [0, 0, 3.0]},
                                                 {"f": 20, "head": [0, 0, 3.4]}]}
    keys = shot_keys(shot, _rig(), "spline")
    ys = [k["channels"]["kei:c_head_fk_ctl.rotateY"] for k in keys]
    assert all(abs(b - a) < 60 for a, b in zip(ys, ys[1:])), ys


def test_blocking_keys_are_stepped():
    shot = {"rig": "v4", "frames": 10, "keys": [{"f": 0}, {"f": 10, "tangent": "flat"}]}
    assert {k["tangent"] for k in shot_keys(shot, _rig(), "step")} == {"step"}
    assert [k["tangent"] for k in shot_keys(shot, _rig(), "spline")] == ["spline", "flat"]


def test_the_job_names_every_fk_control_and_the_limb_pivots():
    job = control_rig_job("keira")
    assert [c["name"] for c in job["fk"]] == [fk_name(b) for b in FK_BONES]
    assert job["legs"]["l"]["sg"] == -1 and job["legs"]["r"]["sg"] == 1
    assert job["scales"]["spine_02"]["sq"][1] > 0          # a longer spine moves the next segment up its parent's Y


def test_extra_points_ride_on_their_bones():
    ch = load_character("kei")
    B, extra, _ = _skeleton(rest_pose(ch), ch.proportions)
    offs = extra_offsets("kei")
    bone, o = offs["heel_l"]
    head, _, F, _ = B[bone]
    p = [head[i] + sum(o[a] * F[a][i] for a in range(3)) for i in range(3)]
    assert max(abs(a - b) for a, b in zip(p, extra["heel_l"])) < 1e-12
