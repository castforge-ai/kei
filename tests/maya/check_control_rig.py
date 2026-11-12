"""In mayapy: build the control rig on Kei and Keira and report what the tests in test_maya_control_rig.py check."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maya_poses import POSE, ROLLS  # noqa: E402
from run_job import script_main  # noqa: E402


def joints(cmds, ns):
    import kei_tools
    from kei.rig import ALL_BONES
    return kei_tools.call("read_samples", {"joints": [f"{ns}:{b}" for b in ALL_BONES], "start": 0, "end": 0})


def apply(cmds, values):
    for plug, v in values.items():
        cmds.setAttr(plug, v)


def main(args, cmds):
    import kei_tools
    from kei.apps.maya_controls import control_rig_job, pose_to_controls, shot_keys
    from kei.apps.maya_scene import character_job
    from kei.characters import load_character, rest_pose
    out = {}
    walk = json.load(open(os.path.join(args["repo"], "examples", "stepped_walk", "out_blocking", "shot.json")))
    for name in ("kei", "keira"):
        cmds.file(new=True, force=True)
        kei_tools.call("load_character", {"job": character_job(name)})
        rig = kei_tools.call("build_control_rig", {"job": control_rig_job(name)})
        r = {"map": rig}
        ns = name
        undriven = []
        for j in cmds.ls(ns + ":*", type="joint"):
            if j.endswith(("_ik",)):
                continue
            if not (cmds.listConnections(j + ".rotateX", source=True, destination=False)
                    and cmds.listConnections(j + ".translateX", source=True, destination=False)):
                undriven.append(j)
        r["undriven"] = undriven
        r["rest"] = joints(cmds, ns)
        shapes = {}
        for c in rig["controls"]:
            shp = cmds.listRelatives(c["name"], shapes=True) or []
            shapes[c["name"]] = list(cmds.getAttr(shp[0] + ".overrideColorRGB")[0]) if shp else None
        r["colours"] = shapes
        r["locked"] = {c["name"]: [a for a in ("translateX", "scaleX", "visibility")
                                   if cmds.getAttr(f"{c['name']}.{a}", lock=True)] for c in rig["controls"]}
        # a posed character: the values Kei keys, set by hand
        vals = pose_to_controls(POSE, rig)
        apply(cmds, vals)
        r["posed_ik"] = joints(cmds, ns)
        for s in "lr":
            cmds.setAttr(f"{ns}:{s}_leg_settings_ctl.ikFk", 0)
            cmds.setAttr(f"{ns}:{s}_arm_settings_ctl.ikFk", 1)
        r["posed_switched"] = joints(cmds, ns)
        for s in "lr":
            cmds.setAttr(f"{ns}:{s}_leg_settings_ctl.ikFk", 1)
            cmds.setAttr(f"{ns}:{s}_arm_settings_ctl.ikFk", 0)
        rest = rest_pose(load_character(name))
        r["rolls"] = {}
        for key, extra in ROLLS.items():
            apply(cmds, pose_to_controls({**rest, **extra}, rig))
            r["rolls"][key] = joints(cmds, ns)
        apply(cmds, pose_to_controls(rest, rig))
        # the round trip: Kei's stepped walk as spline keys on the controls, read back on every frame
        keys = shot_keys(walk, rig, "spline")
        r["set_keys"] = kei_tools.call("set_keys", {"keys": keys})
        from kei.rig import ALL_BONES
        r["walk"] = kei_tools.call("read_samples", {"joints": [f"{ns}:{b}" for b in ALL_BONES], "start": 0,
                                                    "end": walk["frames"]})
        out[name] = r
    return out


if __name__ == "__main__":
    script_main(main)
