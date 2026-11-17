# kei_script: eval_rig
# Read only, apart from the controls it moves and puts back. For each frame, sets every animatable transform control
# of the Control Rig to the value Kei's sequence gives at that frame, runs the rig's forward solve and reads the world
# position of each named bone in RIG space (centimetres, Z up, independent of where the actor stands). It needs no
# editor tick and no scrubbing. Afterwards every control gets its original local transform back.
# The sequence must be the one open in Sequencer (open_sequence.py): the sequence getters return 0 for any other, so
# this raises instead of returning a rest pose.
# Input: sequence, frames [int], bones [name], performer ("" for the character, or a second performer's name). Output: frames {frame: {bone: [x, y, z]}}, rest {bone: [x, y, z]}
# (the rig's own rest pose: every control at its initial value, whatever frame the editor shows), controls (count),
# skipped (control types it did not set).
def _main(inp):
    seq = load_sequence(inp["sequence"])
    current = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
    if current is None or current.get_path_name() != seq.get_path_name():
        raise RuntimeError("the sequence " + inp["sequence"] + " is not the one open in Sequencer: open it first")
    lib = unreal.ControlRigSequencerLibrary
    rig = control_rig_of(seq, inp.get("performer", ""))
    h = rig.get_hierarchy()
    unit = unreal.MovieSceneTimeUnit.DISPLAY_RATE
    keys, skipped = [], {}
    for el in h.get_controls():
        key = el.get_key() if hasattr(el, "get_key") else el
        settings = h.get_control_settings(key)
        if "ANIMATION_CONTROL" not in str(settings.animation_type).upper():
            continue
        if "EULER" in str(settings.control_type).upper():
            keys.append(key)
        else:
            kind = str(settings.control_type).split(".")[-1]
            skipped[kind] = skipped.get(kind, 0) + 1
    originals = {str(k.name): h.get_local_transform(k) for k in keys}
    bones = {str(b.name): b for b in h.get_bones()}
    want = [b for b in inp["bones"] if b in bones]

    def read():
        rig.execute(unreal.Name("Forwards Solve"))
        out = {}
        for b in want:
            t = h.get_global_transform(bones[b]).translation
            out[b] = [round(t.x, 3), round(t.y, 3), round(t.z, 3)]
        return out

    frames, rest = {}, {}
    try:
        for k in keys:                           # the rest pose: every control at its initial value
            h.set_local_transform(k, h.get_local_transform(k, True))
        rest = read()
        for f in inp["frames"]:
            for k in keys:
                e = lib.get_local_control_rig_euler_transform(seq, rig, str(k.name), unreal.FrameNumber(int(f)), unit)
                h.set_local_transform(k, unreal.Transform(
                    location=[e.location.x, e.location.y, e.location.z], rotation=e.rotation,
                    scale=[e.scale.x, e.scale.y, e.scale.z]))
            frames[str(int(f))] = read()
    finally:
        for k in keys:
            h.set_local_transform(k, originals[str(k.name)])
    return {"frames": frames, "rest": rest, "controls": len(keys), "skipped": skipped,
            "missing": [b for b in inp["bones"] if b not in bones]}


kei_run(_main)
