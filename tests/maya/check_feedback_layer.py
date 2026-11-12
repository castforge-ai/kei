"""In mayapy: Kei keys pass p23 and makes feedback_p23; the animator keys a correction on it with no layer named; the
animator adds a layer of their own on top; Kei keys p24 (its layer first, then again with the feedback layer, so the
new layer has to go between Kei's layer and the animator's); the animator's next key lands on feedback_p24; keying
p24 once more leaves feedback_p24 as it is; the read for p24 names feedback_p23 and does not read it. Two plain
transforms stand in for rig controls."""
from run_job import script_main


def main(args, cmds):
    import kei_tools
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")
    cmds.namespace(add="kei")
    pole = cmds.createNode("transform", name="kei:pole_ctl")
    head = cmds.createNode("transform", name="kei:head_ctl")
    kei_tools.call("set_time", {"start": 0, "end": 12})

    def keys(v):
        return [{"f": 0, "tangent": "linear", "channels": {f"{pole}.translateX": v, f"{head}.rotateZ": 0.0}},
                {"f": 12, "tangent": "linear", "channels": {f"{pole}.translateX": v, f"{head}.rotateZ": 0.0}}]

    def layers():
        return {n: {"mute": bool(cmds.animLayer(n, q=True, mute=True)),
                    "selected": bool(cmds.animLayer(n, q=True, selected=True)),
                    "preferred": bool(cmds.animLayer(n, q=True, preferred=True))} for n in cmds.ls(type="animLayer")}

    def layer_keys(layer, plug):
        c = cmds.animLayer(layer, q=True, findCurveForPlug=plug) or []
        return cmds.keyframe(c[0], q=True, timeChange=True, valueChange=True) if c else None

    out = {}
    out["p23"] = kei_tools.call("set_keys", {"keys": keys(1.0), "layer": "kei_p23", "feedback": "feedback_p23"})
    cmds.currentTime(6, update=True)
    cmds.setAttr(f"{pole}.translateX", 4.0)
    cmds.setKeyframe(pole, attribute="translateX", time=6)        # the animator, no layer named
    out["p23_key"] = layer_keys("feedback_p23", f"{pole}.translateX")
    kei_tools.call("set_keys", {"keys": keys(2.0), "layer": "kei_p24"})
    cmds.animLayer("fixes")                                        # the animator's own layer, on top
    out["p24"] = kei_tools.call("set_keys", {"keys": keys(2.0), "layer": "kei_p24", "feedback": "feedback_p24"})
    out["order"] = cmds.animLayer("BaseAnimation", q=True, children=True)
    out["override"] = bool(cmds.animLayer("feedback_p24", q=True, override=True))
    out["attributes"] = sorted(cmds.animLayer("feedback_p24", q=True, attribute=True) or [])
    out["flags"] = layers()
    out["empty_keys"] = layer_keys("feedback_p24", f"{pole}.translateX")
    cmds.currentTime(6, update=True)
    cmds.setAttr(f"{pole}.translateX", 7.0)
    cmds.setKeyframe(pole, attribute="translateX", time=6)        # the animator's next key
    out["p24_key"] = layer_keys("feedback_p24", f"{pole}.translateX")
    out["kei_p24_keys"] = layer_keys("kei_p24", f"{pole}.translateX")
    cmds.animLayer("feedback_p24", edit=True, mute=True)           # the animator mutes it to compare
    out["again"] = kei_tools.call("set_keys", {"keys": keys(2.0), "layer": "kei_p24", "feedback": "feedback_p24"})
    out["again_key"] = layer_keys("feedback_p24", f"{pole}.translateX")
    out["again_flags"] = layers()
    cmds.animLayer("feedback_p24", edit=True, mute=False)
    out["read"] = kei_tools.call("read_feedback_layers", {"rig": "kei", "start": 0, "end": 12, "pass_name": "p24"})
    return out


if __name__ == "__main__":
    script_main(main)
