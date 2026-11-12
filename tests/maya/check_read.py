"""In mayapy: read rigs back (Kei's control rig, a bare skeleton with a lock and a limit), namespaces, duplicate short
names, and a centimetre Z up scene."""
from run_job import script_main


def main(args, cmds):
    import kei_tools
    from kei.apps.maya_controls import control_rig_job
    from kei.apps.maya_scene import character_job
    from kei.rig import ALL_BONES
    out = {}
    job = character_job("kei")
    cmds.file(new=True, force=True)
    kei_tools.call("load_character", {"job": job})
    kei_tools.call("build_control_rig", {"job": control_rig_job("kei")})
    out["kei_rig"] = kei_tools.call("read_rig", {"namespace": "kei"})
    # a twin under another namespace: keys go to the node the plug names
    kei_tools.call("load_character", {"job": job, "namespace": "kei2"})
    kei_tools.call("build_control_rig", {"job": control_rig_job("kei"), "namespace": "kei2"})
    kei_tools.call("set_keys", {"keys": [{"f": 1, "tangent": "step",
                                          "channels": {"kei2:l_foot_ik_ctl.translateY": 12.0}}]})
    cmds.currentTime(1)
    out["twins"] = {"kei2_foot_ty": cmds.getAttr("kei2:l_foot_ik_ctl.translateY"),
                    "kei_foot_ty": cmds.getAttr("kei:l_foot_ik_ctl.translateY")}
    # duplicate short names
    a = cmds.createNode("transform", name="a")
    b = cmds.createNode("transform", name="b")
    cmds.createNode("transform", name="dup", parent=a)
    cmds.createNode("transform", name="dup", parent=b)
    try:
        kei_tools.call("set_keys", {"keys": [{"f": 1, "channels": {"dup.translateX": 1.0}}]})
        err = ""
    except kei_tools.ToolError as e:
        err = str(e)
    r = kei_tools.call("set_keys", {"keys": [{"f": 1, "channels": {"|a|dup.translateX": 1.0}}]})
    out["duplicates"] = {"short_error": err, "full_path_keys": r["keys"]}
    # a bare skeleton (no controls): a locked channel and a limit
    cmds.file(new=True, force=True)
    kei_tools.call("load_character", {"job": job, "namespace": "kt", "variant": "test"})
    out["test_rig"] = kei_tools.call("read_rig", {"namespace": "kt"})
    try:
        kei_tools.call("set_keys", {"keys": [{"f": 1, "channels": {"kt:hand_r.rotateX": 10.0}}]})
        out["locked_error"] = ""
    except kei_tools.ToolError as e:
        out["locked_error"] = str(e)
    r = kei_tools.call("set_keys", {"keys": [{"f": 1, "channels": {"kt:head.rotateX": 45.0}}]})
    out["clipped"] = r["clipped"]
    # centimetres, Z up
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")
    cmds.upAxis(axis="z", rotateView=False)
    kei_tools.call("load_character", {"job": job})
    out["z_up"] = kei_tools.call("read_samples", {"joints": [f"kei:{b}" for b in ALL_BONES], "start": 0, "end": 0})
    return out


if __name__ == "__main__":
    script_main(main)
