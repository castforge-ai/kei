"""In mayapy: Kei's pass on its layer kei_p1, then an animator's additive layer feedback and override layer
feedback_over on top, keyed the way an animator keys them (setKeyframe's value is the value seen, so the additive
layer holds the difference), read back by read_feedback_layers, and the layers as they were after the read. It also
records what getAttr's time flag gives under an additive layer, which the tool does not use. Two plain transforms
stand in for rig controls, so the scene is cheap to make."""
from run_job import script_main


def main(args, cmds):
    import kei_tools
    cmds.file(new=True, force=True)
    cmds.currentUnit(linear="cm")
    cmds.namespace(add="kei")
    ctl = cmds.createNode("transform", name="kei:pole_ctl")
    head = cmds.createNode("transform", name="kei:head_ctl")
    kei_tools.call("set_time", {"start": 0, "end": 12})
    # Kei's pass, keyed the way kei maya key keys it in the open Maya: an override layer per pass
    kei_tools.call("set_keys", {"layer": "kei_p1", "keys": [
        {"f": 0, "tangent": "linear", "channels": {f"{ctl}.translateX": 10.0, f"{head}.rotateZ": 0.0}},
        {"f": 12, "tangent": "linear", "channels": {f"{ctl}.translateX": 10.0, f"{head}.rotateZ": 6.0}}]})
    # the animator: an additive layer with one key (an offset on every frame), an override layer with one key
    cmds.animLayer("feedback")
    cmds.select(ctl, replace=True)
    cmds.animLayer("feedback", edit=True, addSelectedObjects=True)
    cmds.setKeyframe(ctl, attribute="translateX", time=6, value=15.0, animLayer="feedback")   # 5 cm more
    cmds.animLayer("feedback_over", override=True)
    cmds.select(head, replace=True)
    cmds.animLayer("feedback_over", edit=True, addSelectedObjects=True)
    cmds.setKeyframe(head, attribute="rotateZ", time=6, value=9.0, animLayer="feedback_over")
    cmds.animLayer("feedback_over", edit=True, mute=True)       # the animator left this one muted
    cmds.select(clear=True)

    def layers():
        return {n: bool(cmds.animLayer(n, q=True, mute=True)) for n in cmds.ls(type="animLayer")}
    before = layers()

    def at(plug, f):
        cmds.currentTime(f, update=True)
        return cmds.getAttr(plug)
    seen = {"pole_f6_all_on": at(f"{ctl}.translateX", 6),
            "pole_f6_time_flag": cmds.getAttr(f"{ctl}.translateX", time=6),
            "layer_key": cmds.keyframe(cmds.animLayer("feedback", q=True, findCurveForPlug=f"{ctl}.translateX")[0],
                                       q=True, valueChange=True)}
    cmds.currentTime(0, update=True)
    read = kei_tools.call("read_feedback_layers", {"rig": "kei", "start": 0, "end": 12})
    after = layers()
    time_after_read = cmds.currentTime(q=True)
    muted = kei_tools.call("set_feedback_mute", {"mute": True})
    seen["pole_f6_muted"] = at(f"{ctl}.translateX", 6)
    seen["head_f6_muted"] = at(f"{head}.rotateZ", 6)
    seen["time_after_read"] = time_after_read
    return {"read": read, "before": before, "after": after, "muted": muted, "seen": seen}


if __name__ == "__main__":
    script_main(main)
