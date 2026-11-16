# kei_script: layer_keys
# Writes a pass as a layer of the one before it, then merges it down. The sequence is Kei's own copy of the previous
# pass (make_sequence.py with copy_from), open in Sequencer for an editor tick. A new additive section goes on the
# Control Rig track over the whole range; each named channel gets its delta keyed on each listed frame (cubic, as
# Kei's spline keys); then collapse_control_rig_anim_layers bakes the layers into one section, without key reduction.
# The whole call is one undo transaction.
# Input: sequence, frames (the last frame), channels {section channel name: [[frame, delta], ...]}.
# Output: keyed (key count), channels (count), missing (channel names the section does not have), collapsed, sections.
def _main(inp):
    if not inp["sequence"].startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei layers only its own sequences under " + KEI_ROOT)
    seq = load_sequence(inp["sequence"])
    tracks = [t for t in seq.get_bindings()[0].get_tracks()
              if t.get_class().get_name() == "MovieSceneControlRigParameterTrack"]
    if not tracks:
        raise RuntimeError("the sequence " + inp["sequence"] + " has no Control Rig track")
    track = tracks[0]
    if len(track.get_sections()) != 1:
        raise RuntimeError("the Control Rig track of " + inp["sequence"] + " already has layers: Kei merges each "
                           "pass down, so this is not a sequence Kei left")
    keyed, missing = 0, []
    cubic = unreal.MovieSceneKeyInterpolation.AUTO
    with unreal.ScopedEditorTransaction("Kei layer"):
        layer = track.add_section()
        layer.set_blend_type(unreal.MovieSceneBlendType.ADDITIVE)
        layer.set_range(0, int(inp["frames"]) + 1)
        by_name = {str(c.channel_name): c for c in layer.get_all_channels()}
        for name, keys in inp["channels"].items():
            ch = by_name.get(name)
            if ch is None:
                missing.append(name)
                continue
            for f, v in keys:
                ch.add_key(unreal.FrameNumber(int(f)), float(v), 0.0, unreal.MovieSceneTimeUnit.DISPLAY_RATE, cubic)
                keyed += 1
        if missing:
            track.remove_section(layer)
            return {"keyed": 0, "channels": len(inp["channels"]), "missing": missing, "collapsed": False,
                    "sections": len(track.get_sections())}
        collapsed = unreal.ControlRigSequencerLibrary.collapse_control_rig_anim_layers(seq, track, False, 0.001)
    unreal.SystemLibrary.collect_garbage()
    return {"keyed": keyed, "channels": len(inp["channels"]), "missing": [], "collapsed": bool(collapsed),
            "sections": len(track.get_sections())}


kei_run(_main)
