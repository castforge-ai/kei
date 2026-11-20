# kei_script: match_switch
# Read only on the sequence: it keys nothing, and every control it moves is put back. A matched IK/FK switch of one
# limb at one frame: the rig is posed as Kei's sequence plays that frame (every animatable transform control and every
# limb switch), the limb's bones are read, then each control of the mode switched to is placed where its bone is (at
# the control's own rest offset from that bone; the pole out past the elbow or knee), the switch is flipped, the rig
# is solved again and the bones are read again. Output: values {control: {channel: value}} for the new mode's
# controls and the switch, in the units of the keys (cm, degrees), types, gap_cm (the largest bone move the switch
# makes), before {bone: [x, y, z]}, after.
# Input: sequence, frame, limb (arm_l, arm_r, leg_l, leg_r), to (ik or fk), performer ("").
LIMBS = {
    "arm": {"bones": ["upperarm", "lowerarm", "hand"], "fk": ["upperarm", "lowerarm", "hand"],
            "ik": [("hand_{s}_ik_ctrl", "hand")], "pole": "arm_{s}_pv_ik_ctrl", "mid": "lowerarm"},
    "leg": {"bones": ["thigh", "calf", "foot", "ball"], "fk": ["thigh", "calf", "foot", "ball"],
            "ik": [("foot_{s}_ik_ctrl", "foot"), ("ball_{s}_ik_ctrl", "ball")], "pole": "leg_{s}_pv_ik_ctrl",
            "mid": "calf"},
}


def _key_of(el):
    return el.get_key() if hasattr(el, "get_key") else el


def _euler(h, key):
    e = h.get_euler_transform_from_control_value(h.get_control_value(key, unreal.RigControlValueType.CURRENT))
    return {"location.x": e.location.x, "location.y": e.location.y, "location.z": e.location.z,
            "rotation.x": e.rotation.roll, "rotation.y": e.rotation.pitch, "rotation.z": e.rotation.yaw,
            "scale.x": e.scale.x, "scale.y": e.scale.y, "scale.z": e.scale.z}


def _main(inp):
    seq = load_sequence(inp["sequence"])
    current = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
    if current is None or current.get_path_name() != seq.get_path_name():
        raise RuntimeError("the sequence " + inp["sequence"] + " is not the one open in Sequencer: open it first")
    part, s = inp["limb"].split("_")
    spec, to = LIMBS[part], inp["to"]
    lib = unreal.ControlRigSequencerLibrary
    rig = control_rig_of(seq, inp.get("performer", ""))
    h = rig.get_hierarchy()
    unit = unreal.MovieSceneTimeUnit.DISPLAY_RATE
    frame = unreal.FrameNumber(int(inp["frame"]))
    controls = {str(_key_of(el).name): _key_of(el) for el in h.get_controls()}
    bones = {str(b.name): b for b in h.get_bones()}
    switch = inp["limb"] + "_fk_ik_switch"
    if switch not in controls:
        raise RuntimeError("the rig has no switch " + switch)
    transforms, bools = [], []
    for name, key in controls.items():
        st = h.get_control_settings(key)
        kind = str(st.control_type).upper()
        if "ANIMATION_CONTROL" in str(st.animation_type).upper() and "EULER" in kind:
            transforms.append(name)
        elif name.endswith("_fk_ik_switch"):
            bools.append(name)
    originals = {n: h.get_control_value(controls[n], unreal.RigControlValueType.CURRENT) for n in bools}
    local_was = {n: h.get_local_transform(controls[n]) for n in transforms}
    want = [b + "_" + s for b in spec["bones"]]

    def solve():
        rig.execute(unreal.Name("Forwards Solve"))
        return {b: h.get_global_transform(bones[b]) for b in want}

    def pos(t):
        return [round(t.translation.x, 3), round(t.translation.y, 3), round(t.translation.z, 3)]

    try:
        for n in transforms:      # posed as eval_rig.py poses them, so the solve plays this frame, not the playhead
            e = lib.get_local_control_rig_euler_transform(seq, rig, n, frame, unit)
            h.set_local_transform(controls[n], unreal.Transform(
                location=[e.location.x, e.location.y, e.location.z], rotation=e.rotation,
                scale=[e.scale.x, e.scale.y, e.scale.z]))
        for n in bools:
            v = lib.get_local_control_rig_bool(seq, rig, n, frame, unit)
            h.set_control_value(controls[n], h.make_control_value_from_bool(bool(v)), unreal.RigControlValueType.CURRENT)
        was_ik = bool(lib.get_local_control_rig_bool(seq, rig, switch, frame, unit))
        before = solve()
        mm = unreal.MathLibrary
        if to == "ik":
            pairs = [(c.format(s=s), b + "_" + s) for c, b in spec["ik"]]
        else:
            pairs = [(b + "_" + s + "_fk_ctrl", b + "_" + s) for b in spec["fk"]]
        for ctrl, bone in pairs:
            if ctrl not in controls:
                raise RuntimeError("the rig has no control " + ctrl)
            rel = mm.compose_transforms(h.get_global_transform(controls[ctrl], True),
                                        mm.invert_transform(h.get_global_transform(bones[bone], True)))
            h.set_global_transform(controls[ctrl], mm.compose_transforms(rel, before[bone]), False, True)
            rig.execute(unreal.Name("Forwards Solve"))
        out = [pair[0] for pair in pairs]
        if to == "ik":
            pole = spec["pole"].format(s=s)
            root, mid, end = (before[b + "_" + s].translation for b in (spec["bones"][0], spec["mid"], spec["bones"][2]))
            c = unreal.Vector((root.x + end.x) / 2, (root.y + end.y) / 2, (root.z + end.z) / 2)
            d = unreal.Vector(mid.x - c.x, mid.y - c.y, mid.z - c.z)
            n = max((d.x * d.x + d.y * d.y + d.z * d.z) ** 0.5, 1e-6)
            length = ((root.x - end.x) ** 2 + (root.y - end.y) ** 2 + (root.z - end.z) ** 2) ** 0.5
            t = h.get_global_transform(controls[pole])
            t.translation = unreal.Vector(mid.x + d.x / n * length, mid.y + d.y / n * length, mid.z + d.z / n * length)
            h.set_global_transform(controls[pole], t, False, True)
            out.append(pole)
        h.set_control_value(controls[switch], h.make_control_value_from_bool(to == "ik"),
                            unreal.RigControlValueType.CURRENT)
        after = solve()
        gap = max(((before[b].translation.x - after[b].translation.x) ** 2 + (before[b].translation.y
                   - after[b].translation.y) ** 2 + (before[b].translation.z - after[b].translation.z) ** 2) ** 0.5
                  for b in want)
        # the old mode's controls as the sequence plays them on the frame and the frame before: Kei keys them too, so
        # new keys around the switch cannot change how their curves pass through those frames
        if to == "ik":
            old = [b + "_" + s + "_fk_ctrl" for b in spec["fk"]]
        else:
            old = [c.format(s=s) for c, _ in spec["ik"]] + [spec["pole"].format(s=s)]
        hold = {}
        for fr in (int(inp["frame"]) - 1, int(inp["frame"])):
            if fr < 0:
                continue
            hold[str(fr)] = {}
            for c in old:
                if c in controls:
                    e = lib.get_local_control_rig_euler_transform(seq, rig, c, unreal.FrameNumber(fr), unit)
                    hold[str(fr)][c] = {"location.x": e.location.x, "location.y": e.location.y,
                                        "location.z": e.location.z, "rotation.x": e.rotation.roll,
                                        "rotation.y": e.rotation.pitch, "rotation.z": e.rotation.yaw}
        values = {c: _euler(h, controls[c]) for c in out}
        values[switch] = {"value": to == "ik"}
        types = {c: "euler_transform" for c in out}
        types[switch] = "bool"
    finally:
        for n, v in originals.items():
            h.set_control_value(controls[n], v, unreal.RigControlValueType.CURRENT)
        for n, t in local_was.items():
            h.set_local_transform(controls[n], t)
        rig.execute(unreal.Name("Forwards Solve"))
    return {"values": values, "types": types, "gap_cm": round(gap, 4), "was_ik": was_ik, "hold": hold,
            "before": {b: pos(t) for b, t in before.items()}, "after": {b: pos(t) for b, t in after.items()}}


kei_run(_main)
