"""In mayapy: the controls display layer. A scene whose controls sit in no display layer gets kei_controls with all of
them (a child control stays its own member, its parent is not swept in with it); keying again leaves it as it is; a
scene where the animator already has a layer with every control uses that layer; a control in the animator's own
layer stays there while the others go to kei_controls. Plain transforms stand in for rig controls."""
from run_job import script_main


def main(args, cmds):
    import kei_tools

    def scene():
        cmds.file(new=True, force=True)
        cmds.namespace(add="kei")
        body = cmds.createNode("transform", name="kei:body_ctl")
        hand = cmds.createNode("transform", name="kei:hand_ctl", parent=body)
        geo = cmds.polyCube(name="kei:mesh")[0]
        return [cmds.ls(body)[0], cmds.ls(hand)[0]], geo

    def members(layer):
        return sorted(cmds.ls(cmds.editDisplayLayerMembers(layer, q=True, fullNames=True) or []))

    def key(ctls, **extra):
        k = [{"f": 0, "tangent": "linear", "channels": {f"{ctls[0]}.translateX": 1.0}}]
        return kei_tools.call("set_keys", {"keys": k, "layer": "kei_p1", "controls_layer": ctls, **extra})

    out = {}
    ctls, geo = scene()
    out["made"] = key(ctls)["controls_layer"]
    out["made_members"] = members("kei_controls")
    out["again"] = key(ctls)["controls_layer"]
    out["undo"] = cmds.undoInfo(q=True, undoName=True)

    ctls, geo = scene()
    mine = cmds.createDisplayLayer(name="anim_ctrls", empty=True, noRecurse=True)
    cmds.editDisplayLayerMembers(mine, *ctls, noRecurse=True)
    out["theirs"] = key(ctls)["controls_layer"]
    out["no_kei_layer"] = "kei_controls" not in (cmds.ls(type="displayLayer") or [])

    ctls, geo = scene()
    mine = cmds.createDisplayLayer(name="hands", empty=True, noRecurse=True)
    cmds.editDisplayLayerMembers(mine, ctls[1], noRecurse=True)
    out["split"] = key(ctls)["controls_layer"]
    out["split_members"] = {"kei_controls": members("kei_controls"), "hands": members("hands")}
    return out


if __name__ == "__main__":
    script_main(main)
