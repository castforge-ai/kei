# kei_script: load_pose
# Puts one frame of an animation already in the project onto the Control Rig of Kei's own sequence, exactly: the
# Control Rig's own backwards solve (load_anim_sequence_into_control_rig_section) keys every control at the
# sequence's first frame from that animation frame, fingers and toes included. Then it reads every animatable
# control's value back in the units Kei keys in (cm, degrees; rotation.x/y/z = roll/pitch/yaw, as set_keys.py), and
# checks the result: it runs the rig's forward solve on those values and compares every bone with the animation
# frame (local rotation in degrees, and head, hands, fingertips and feet relative to the pelvis in cm). Every control
# gets its original local transform back after the check.
# The sequence must be the one open in Sequencer (make_sequence.py opens it): the sequence getters return 0 for any
# other. The animation must be on the same skeleton as the sequence's mesh.
# Input: sequence, anim, frame. Output: controls {control: {channel: value}}, types {control: type}, check {...}.
CHECK_BONES = ["head", "hand_l", "hand_r", "index_03_l", "index_03_r", "foot_l", "foot_r", "ball_l", "ball_r"]


def _angle(a, b):
    import math
    d = min(1.0, abs(a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w))
    return math.degrees(2.0 * math.acos(d))


def _main(inp):
    if not inp["sequence"].startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei loads a pose only into its own sequences under " + KEI_ROOT)
    seq = load_sequence(inp["sequence"])
    current = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
    if current is None or current.get_path_name() != seq.get_path_name():
        raise RuntimeError("the sequence " + inp["sequence"] + " is not the one open in Sequencer: open it first")
    anim = unreal.load_asset(inp["anim"])
    if anim is None or not isinstance(anim, unreal.AnimSequence):
        raise RuntimeError("the animation " + inp["anim"] + " is not an animation sequence in the project")
    frame = int(inp.get("frame") or 0)
    last = int(unreal.AnimationLibrary.get_num_frames(anim))
    if frame < 0 or frame > last:
        raise RuntimeError("the animation " + inp["anim"] + " has frames 0 to " + str(last) + ", not " + str(frame))
    binding = binding_of(seq)
    bound = unreal.LevelSequenceEditorBlueprintLibrary.get_bound_objects(seq.get_binding_id(binding))
    if not bound:
        raise RuntimeError("the character of " + inp["sequence"] + " is not spawned yet: wait one editor tick")
    comp = bound[0].skeletal_mesh_component
    mesh = comp.get_skeletal_mesh_asset()
    if mesh is None or mesh.skeleton.get_path_name() != anim.get_editor_property("skeleton").get_path_name():
        raise RuntimeError("the animation " + inp["anim"] + " is on the skeleton "
                           + anim.get_editor_property("skeleton").get_path_name() + ", not on the character's")
    tracks = [t for t in binding.get_tracks() if t.get_class().get_name() == "MovieSceneControlRigParameterTrack"]
    if not tracks or not tracks[0].get_sections():
        raise RuntimeError("the sequence " + inp["sequence"] + " has no Control Rig section")
    lib = unreal.ControlRigSequencerLibrary
    unit = unreal.MovieSceneTimeUnit.DISPLAY_RATE
    ok = lib.load_anim_sequence_into_control_rig_section_with_range(
        tracks[0].get_sections()[0], anim, comp, unreal.FrameNumber(0), True, unreal.FrameNumber(frame),
        unreal.FrameNumber(frame), unit, False, 0.001, unreal.MovieSceneKeyInterpolation.LINEAR, True)
    if not ok:
        raise RuntimeError("the editor would not load " + inp["anim"] + " onto the Control Rig")

    rig = control_rig_of(seq)
    h = rig.get_hierarchy()
    f0 = unreal.FrameNumber(0)
    controls, types, euler_keys = {}, {}, []
    for el in h.get_controls():
        key = el.get_key() if hasattr(el, "get_key") else el
        settings = h.get_control_settings(key)
        if "ANIMATION_CONTROL" not in str(settings.animation_type).upper():
            continue
        name, kind = str(key.name), str(settings.control_type).split(".")[-1].upper()
        if "EULER" in kind:
            e = lib.get_local_control_rig_euler_transform(seq, rig, name, f0, unit)
            controls[name] = {"location.x": e.location.x, "location.y": e.location.y, "location.z": e.location.z,
                              "rotation.x": e.rotation.roll, "rotation.y": e.rotation.pitch,
                              "rotation.z": e.rotation.yaw,
                              "scale.x": e.scale.x, "scale.y": e.scale.y, "scale.z": e.scale.z}
            types[name] = "euler_transform"
            euler_keys.append((key, e))
        elif "FLOAT" in kind:
            controls[name] = {"value": lib.get_local_control_rig_float(seq, rig, name, f0, unit)}
            types[name] = "float"
        elif "BOOL" in kind:
            controls[name] = {"value": bool(lib.get_local_control_rig_bool(seq, rig, name, f0, unit))}
            types[name] = "bool"
        elif "ROTATOR" in kind:
            r = lib.get_local_control_rig_rotator(seq, rig, name, f0, unit)
            controls[name] = {"rotation.x": r.roll, "rotation.y": r.pitch, "rotation.z": r.yaw}
            types[name] = "rotator"

    A = unreal.AnimPoseExtensions
    pose = A.get_anim_pose_at_frame(anim, frame, unreal.AnimPoseEvaluationOptions())
    bones = {str(b.name): b for b in h.get_bones()}
    originals = {str(k.name): h.get_local_transform(k) for k, _ in euler_keys}
    worst, total, count, offsets = [], 0.0, 0, {}
    try:
        for k, e in euler_keys:
            h.set_local_transform(k, unreal.Transform(
                location=[e.location.x, e.location.y, e.location.z], rotation=e.rotation,
                scale=[e.scale.x, e.scale.y, e.scale.z]))
        rig.execute(unreal.Name("Forwards Solve"))
        for n in A.get_bone_names(pose):
            n = str(n)
            if n not in bones:
                continue
            deg = _angle(A.get_bone_pose(pose, n, unreal.AnimPoseSpaces.LOCAL).rotation,
                         h.get_local_transform(bones[n]).rotation)
            total += deg
            count += 1
            worst.append([n, round(deg, 2)])
        if "pelvis" in bones:
            ap = A.get_bone_pose(pose, "pelvis", unreal.AnimPoseSpaces.WORLD)
            rp = h.get_global_transform(bones["pelvis"])
            for n in CHECK_BONES:
                if n in bones:
                    a = ap.inverse_transform_location(A.get_bone_pose(pose, n, unreal.AnimPoseSpaces.WORLD).translation)
                    r = rp.inverse_transform_location(h.get_global_transform(bones[n]).translation)
                    offsets[n] = round((a - r).length(), 2)
    finally:
        for k, _ in euler_keys:
            h.set_local_transform(k, originals[str(k.name)])
    worst.sort(key=lambda x: -x[1])
    return {"sequence": inp["sequence"], "anim": inp["anim"], "frame": frame, "controls": controls, "types": types,
            "check": {"bones": count, "mean_deg": round(total / count, 3) if count else None, "worst_deg": worst[:8],
                      "pelvis_relative_cm": offsets}, "dirty": dirty_packages()}


kei_run(_main)
