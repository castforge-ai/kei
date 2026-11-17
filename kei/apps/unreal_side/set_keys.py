# kei_script: set_keys
# Keys the Control Rig controls of Kei's own sequence. Kei sends a batch of key frames in one call (one audit file in
# the project, not one per frame) and the whole batch is one undo transaction: the editor keeps what an undo step
# touches in memory, so fewer steps keep less. The sequence has been open for an editor tick before the call.
# Input: sequence and keys [{frame, tangent (step, linear, spline, flat), controls {control: {channel: value}}, types
# {control: euler_transform | float | bool | rotator}}], and performer ("" for the character, or the name of a
# second performer in the sequence). One frame may also be given flat: sequence, frame, tangent,
# controls, types. Values are in the rig's own units (cm, degrees).
# A transform key writes all nine channels of the control, so the channels Kei does not name keep their value there.
# Output: keyed (channel count), clipped (asked versus reached, when a limit held a value back), tangents.
class _NoTransaction:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _set_tangents(seq, frames, controls, performer=""):
    """Each key of these controls at these frames gets its frame's tangent. Each channel's keys are read once: every
    key read makes a scripting object, and reading every channel once per key frame made millions of them a pass,
    enough to exhaust the editor's object limit. Returns "set", or "skipped: <why>"."""
    try:
        mode = {"step": unreal.RichCurveInterpMode.RCIM_CONSTANT, "linear": unreal.RichCurveInterpMode.RCIM_LINEAR,
                "spline": unreal.RichCurveInterpMode.RCIM_CUBIC, "flat": unreal.RichCurveInterpMode.RCIM_CUBIC}
        binding = binding_of(seq, performer)
        for track in binding.get_tracks():
            if track.get_class().get_name() != "MovieSceneControlRigParameterTrack":
                continue
            for section in track.get_sections():
                for channel in section.get_all_channels():
                    if str(channel.channel_name).split(".")[0] not in controls:
                        continue
                    for key in channel.get_keys():
                        tangent = frames.get(key.get_time().frame_number.value)
                        if tangent is None:
                            continue
                        key.set_interpolation_mode(mode[tangent])
                        if tangent == "flat":
                            key.set_tangent_mode(unreal.RichCurveTangentMode.RCTM_USER)
    except Exception as e:
        return "skipped: " + str(e)[:160]
    return "set"


def _one(inp, own_transaction=True, tangents_now=True):
    seq = load_sequence(inp["sequence"])
    if not inp["sequence"].startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei keys only its own sequences under " + KEI_ROOT)
    rig = control_rig_of(seq, inp.get("performer", ""))
    lib = unreal.ControlRigSequencerLibrary
    frame = unreal.FrameNumber(int(inp["frame"]))
    unit = unreal.MovieSceneTimeUnit.DISPLAY_RATE
    keyed, clipped = 0, []
    with (unreal.ScopedEditorTransaction("Kei keys") if own_transaction else _NoTransaction()):
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
    tangents = (_set_tangents(seq, {int(inp["frame"]): inp["tangent"]}, set(inp["controls"]), inp.get("performer", ""))
                if tangents_now else "set")
    return {"keyed": keyed, "clipped": clipped, "tangents": tangents}


def _main(inp):
    if "keys" not in inp:
        return _one(inp)
    keyed, clipped = 0, []
    seq = load_sequence(inp["sequence"])
    with unreal.ScopedEditorTransaction("Kei keys"):         # one undo step for the whole batch
        for k in inp["keys"]:
            got = _one({"sequence": inp["sequence"], "frame": k["frame"], "tangent": k["tangent"],
                        "controls": k["controls"], "types": k["types"], "performer": inp.get("performer", "")},
                       own_transaction=False, tangents_now=False)
            keyed += got["keyed"]
            clipped += [dict(c, f=k["frame"]) for c in got["clipped"]]
        # the tangents of the whole batch in one read of each channel's keys
        tangents = _set_tangents(seq, {int(k["frame"]): k["tangent"] for k in inp["keys"]},
                                 {c for k in inp["keys"] for c in k["controls"]}, inp.get("performer", ""))
    unreal.SystemLibrary.collect_garbage()     # the key objects that read made are not kept until the next idle GC
    return {"keyed": keyed, "clipped": clipped, "tangents": tangents}


kei_run(_main)
