"""In mayapy: the review findings that need Maya: a hostile FBX path, a copy over the open scene or a reference, a
scene in radians, and a frame rate change with keys in the scene."""
import os

from run_job import script_main


def _err(fn):
    import kei_tools
    try:
        fn()
        return ""
    except kei_tools.ToolError as e:
        return "ToolError: " + str(e)
    except Exception as e:      # anything else is not a clean refusal
        return "Other: " + repr(e)


def main(args, cmds):
    import kei_tools
    from kei.apps.maya_controls import control_rig_job
    from kei.apps.maya_scene import character_job
    d = args["dir"].replace("\\", "/")
    out = {}
    # I2: a path that would break out of a MEL string
    cmds.file(new=True, force=True)
    kei_tools.call("load_character", {"job": character_job("kei")})
    kei_tools.call("build_control_rig", {"job": control_rig_job("kei")})
    marker = d + "/INJECTED"
    hostile = d + '/a.fbx" -s; sysFile -md "' + marker + '"; print "x'
    out["hostile"] = _err(lambda: kei_tools.call("export_fbx", {"path": hostile, "start": 0, "end": 1}))
    out["injected"] = os.path.exists(marker)
    # a plain path with a semicolon still exports
    cmds.file(new=True, force=True)
    kei_tools.call("load_character", {"job": character_job("kei")})
    kei_tools.call("build_control_rig", {"job": control_rig_job("kei")})
    semi = d + "/semi;colon/walk.fbx"
    r = kei_tools.call("export_fbx", {"path": semi, "start": 0, "end": 1})
    out["semicolon_fbx"] = os.path.isfile(semi) and r["joints"]
    # I6: the temp copy may not overwrite the open scene's file or a referenced file, and must be .ma
    cmds.file(new=True, force=True)
    ref = d + "/ref.ma"
    cmds.polyCube(name="refcube")
    kei_tools.save_as(ref)
    cmds.file(new=True, force=True)
    cmds.file(ref, reference=True, namespace="r")
    user = d + "/user.ma"
    kei_tools.save_as(user)
    before = os.path.getmtime(user)
    out["over_scene"] = _err(lambda: kei_tools.call("save_temp_copy", {"path": user}))
    out["over_ref"] = _err(lambda: kei_tools.call("save_temp_copy", {"path": ref}))
    out["not_ma"] = _err(lambda: kei_tools.call("save_temp_copy", {"path": d + "/copy.mb"}))
    out["user_untouched"] = os.path.getmtime(user) == before
    # I7: a scene in radians keys and reads in degrees, and keeps radians
    cmds.file(new=True, force=True)
    cmds.currentUnit(angle="rad")
    n = cmds.createNode("transform", name="spin")
    kei_tools.call("set_keys", {"keys": [{"f": 1, "tangent": "step", "channels": {"spin.rotateX": 90.0}}]})
    cmds.currentTime(1)
    out["radians_value"] = cmds.getAttr(n + ".rotateX")          # in radians, as the scene shows it
    out["angle_unit_after"] = cmds.currentUnit(q=True, angle=True)
    cmds.transformLimits(n, rotationX=(-0.5235987756, 0.5235987756), enableRotationX=(True, True))   # 30 deg, in rad
    out["radians_limit"] = kei_tools.call("read_rig", {"namespace": None}) and kei_tools.limits_of(n).get("rotateX")
    # set_time with keys in the scene does not move them
    cmds.file(new=True, force=True)
    m = cmds.createNode("transform", name="ball")
    cmds.setKeyframe(m, attribute="translateY", time=12, value=5)
    kei_tools.call("set_time", {"start": 0, "end": 24, "fps": 30})
    out["key_times"] = cmds.keyframe(m, attribute="translateY", q=True, timeChange=True)
    # the host's scene and quit jobs are killed when it stops
    import kei_host
    os.environ["KEI_MAYA_SESSIONS"] = d + "/sessions"
    kei_host.start()
    jobs = list(kei_host.JOBS)
    kei_host.stop()
    out["jobs"] = len(jobs)
    out["jobs_left"] = [j for j in jobs if isinstance(j, int) and cmds.scriptJob(exists=j)]
    return out


if __name__ == "__main__":
    script_main(main)
