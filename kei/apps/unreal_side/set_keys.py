# kei_script: set_keys
# Keys the Control Rig controls of Kei's own sequence at one frame, in one undo transaction. Kei calls it once per key
# frame, after the sequence has been open for an editor tick.
# Input: sequence, frame, tangent (step, linear, spline, flat), controls {control: {channel: value}}, types
# {control: euler_transform | float | bool | rotator}. Values are in the rig's own units (cm, degrees).
# A transform key writes all nine channels of the control, so the channels Kei does not name keep their value there.
# Output: keyed (channel count), clipped (asked versus reached, when a limit held a value back), tangents.
def _main(inp):
    seq = load_sequence(inp["sequence"])
    if not inp["sequence"].startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei keys only its own sequences under " + KEI_ROOT)
    rig = control_rig_of(seq)
    lib = unreal.ControlRigSequencerLibrary
    frame = unreal.FrameNumber(int(inp["frame"]))
    unit = unreal.MovieSceneTimeUnit.DISPLAY_RATE
    keyed, clipped = 0, []
    with unreal.ScopedEditorTransaction("Kei keys"):
        for ctrl, chans in inp["controls"].items():
            kind = inp["types"][ctrl]
            if kind == "euler_transform":
                cur = lib.get_local_control_rig_euler_transform(seq, rig, ctrl, frame, unit)
                loc = [cur.location.x, cur.location.y, cur.location.z]
                rot = [cur.rotation.roll, cur.rotation.pitch, cur.rotation.yaw]
                scl = [cur.scale.x, cur.scale.y, cur.scale.z]
                for ch, v in chans.items():
                    group, axis = ch.split(".")
                    target = {"location": loc, "rotation": rot, "scale": scl}[group]
                    target["xyz".index(axis)] = float(v)
                lib.set_local_control_rig_euler_transform(
                    seq, rig, ctrl, frame,
                    unreal.EulerTransform(location=loc, rotation=unreal.Rotator(rot[0], rot[1], rot[2]), scale=scl),
                    unit, True)
                got = lib.get_local_control_rig_euler_transform(seq, rig, ctrl, frame, unit)
                now = {"location": [got.location.x, got.location.y, got.location.z],
                       "rotation": [got.rotation.roll, got.rotation.pitch, got.rotation.yaw],
                       "scale": [got.scale.x, got.scale.y, got.scale.z]}
                for ch, v in chans.items():
                    group, axis = ch.split(".")
                    reached = now[group]["xyz".index(axis)]
                    if abs(reached - float(v)) > 1e-3:
                        clipped.append({"control": ctrl, "channel": ch, "asked": float(v), "reached": reached})
            elif kind == "float":
                lib.set_local_control_rig_float(seq, rig, ctrl, frame, float(chans["value"]), unit, True)
            elif kind == "bool":
                lib.set_local_control_rig_bool(seq, rig, ctrl, frame, bool(chans["value"]), unit, True)
            elif kind == "rotator":
                cur = lib.get_local_control_rig_rotator(seq, rig, ctrl, frame, unit)
                rot = [cur.roll, cur.pitch, cur.yaw]
                for ch, v in chans.items():
                    rot["xyz".index(ch.split(".")[1])] = float(v)
                lib.set_local_control_rig_rotator(seq, rig, ctrl, frame, unreal.Rotator(rot[0], rot[1], rot[2]), unit,
                                                  True)
            keyed += len(chans)
    tangents = "set"
    try:
        mode = {"step": unreal.RichCurveInterpMode.RCIM_CONSTANT, "linear": unreal.RichCurveInterpMode.RCIM_LINEAR,
                "spline": unreal.RichCurveInterpMode.RCIM_CUBIC, "flat": unreal.RichCurveInterpMode.RCIM_CUBIC}
        binding = seq.get_bindings()[0]
        for track in binding.get_tracks():
            if track.get_class().get_name() != "MovieSceneControlRigParameterTrack":
                continue
            for section in track.get_sections():
                for channel in section.get_all_channels():
                    name = str(channel.channel_name)
                    if name.split(".")[0] not in inp["controls"]:
                        continue
                    for key in channel.get_keys():
                        if key.get_time().frame_number.value == int(inp["frame"]):
                            key.set_interpolation_mode(mode[inp["tangent"]])
                            if inp["tangent"] == "flat":
                                key.set_tangent_mode(unreal.RichCurveTangentMode.RCTM_USER)
    except Exception as e:
        tangents = "skipped: " + str(e)[:160]
    return {"keyed": keyed, "clipped": clipped, "tangents": tangents}


kei_run(_main)
