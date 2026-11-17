# kei_script: bake
# Bakes Kei's own sequence to an animation asset under /Game/Kei/<shot>/. SequencerTools.export_anim_sequence fails for
# a spawnable (UE 5.8.3), so the bake is done in the Control Rig: for each frame it sets every animatable transform
# control from the sequence, runs the forward solve and records every bone's local transform. The ik_ bones are in
# the mesh's skeleton but usually not in the rig, so the copy-bones step of BAKE.md is done on the skeleton's own
# reference pose: root takes the rig's root, then each ik_ bone is set to its bone's world transform (parents first,
# in the order of the pairs) and its local transform is read back. Then it writes those tracks to a
# new AnimSequence through its controller, for the bones the mesh's skeleton has, and saves that one asset by path.
# The sequence must be the one open in Sequencer (open_sequence.py). Every control gets its original value back.
# A name that exists is an error (Kei never deletes and recreates an asset).
# Input: sequence, asset, mesh, end (last frame of the delivery range), fps, pairs [[bone, ik_bone]], performer ("" for
# the character, or the name of a second performer, baked from its own Control Rig track, in its own rig space).
# Output: asset, frames, ik_copy ("rig"), bones (written), skipped_bones (count the skeleton lacks).
def _main(inp):
    asset = inp["asset"]
    if not asset.startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei writes only under " + KEI_ROOT + ", not " + asset)
    if unreal.EditorAssetLibrary.does_asset_exist(asset):
        raise RuntimeError("the asset " + asset + " already exists: Kei never overwrites or deletes an asset")
    seq = load_sequence(inp["sequence"])
    current = unreal.LevelSequenceEditorBlueprintLibrary.get_current_level_sequence()
    if current is None or current.get_path_name() != seq.get_path_name():
        raise RuntimeError("the sequence " + inp["sequence"] + " is not the one open in Sequencer: open it first")
    mesh = unreal.load_asset(inp["mesh"])
    if mesh is None:
        raise RuntimeError("the mesh " + inp["mesh"] + " is not in the project")
    lib = unreal.ControlRigSequencerLibrary
    rig = control_rig_of(seq, inp.get("performer", ""))
    h = rig.get_hierarchy()
    unit = unreal.MovieSceneTimeUnit.DISPLAY_RATE
    keys = []
    for el in h.get_controls():
        key = el.get_key() if hasattr(el, "get_key") else el
        settings = h.get_control_settings(key)
        if "ANIMATION_CONTROL" in str(settings.animation_type).upper() and "EULER" in str(settings.control_type).upper():
            keys.append(key)
    originals = {str(k.name): h.get_local_transform(k) for k in keys}
    bones = {str(b.name): b for b in h.get_bones()}
    A = unreal.AnimPoseExtensions
    ref = A.get_reference_pose(mesh.skeleton)
    skel = set(str(n) for n in A.get_bone_names(ref))
    pairs = [(b, ik) for b, ik in inp["pairs"] if b in bones and ik in skel]
    ik_tracks = {ik: ([], [], []) for _, ik in pairs}
    last = int(inp["end"])
    tracks = {n: ([], [], []) for n in bones}
    try:
        for f in range(last + 1):
            for k in keys:
                e = lib.get_local_control_rig_euler_transform(seq, rig, str(k.name), unreal.FrameNumber(f), unit)
                h.set_local_transform(k, unreal.Transform(
                    location=[e.location.x, e.location.y, e.location.z], rotation=e.rotation,
                    scale=[e.scale.x, e.scale.y, e.scale.z]))
            rig.execute(unreal.Name("Forwards Solve"))
            if pairs:
                pose = A.get_reference_pose(mesh.skeleton)
                if "root" in bones and "root" in skel:
                    pose = A.set_bone_pose(pose, h.get_local_transform(bones["root"]), "root",
                                           unreal.AnimPoseSpaces.LOCAL)
                for b, ik in pairs:
                    pose = A.set_bone_pose(pose, h.get_global_transform(bones[b]), ik, unreal.AnimPoseSpaces.WORLD)
                for _, ik in pairs:
                    t = A.get_bone_pose(pose, ik, unreal.AnimPoseSpaces.LOCAL)
                    ik_tracks[ik][0].append(t.translation)
                    ik_tracks[ik][1].append(t.rotation)
                    ik_tracks[ik][2].append(t.scale3d)
            for n, bone_key in bones.items():
                t = h.get_local_transform(bone_key)
                tracks[n][0].append(t.translation)
                tracks[n][1].append(t.rotation)
                tracks[n][2].append(t.scale3d)
    finally:
        for k in keys:
            h.set_local_transform(k, originals[str(k.name)])
    tracks.update(ik_tracks)
    folder, _, name = asset.rpartition("/")
    factory = unreal.AnimSequenceFactory()
    factory.set_editor_property("target_skeleton", mesh.skeleton)
    anim = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, folder, unreal.AnimSequence, factory)
    if anim is None:
        raise RuntimeError("the editor would not create " + asset)
    c = anim.get_editor_property("controller")
    written, skipped = 0, 0
    c.open_bracket(unreal.Text("Kei bake"), False)
    try:
        c.set_frame_rate(unreal.FrameRate(int(round(float(inp.get("fps") or 24))), 1), False)
        c.set_number_of_frames(unreal.FrameNumber(last), False)
        for n, (p, r, s) in tracks.items():
            try:
                c.add_bone_curve(unreal.Name(n), False)
                c.set_bone_track_keys(unreal.Name(n), p, r, s, False)
                written += 1
            except Exception:
                skipped += 1        # a helper bone of the rig that the mesh's skeleton does not have
    finally:
        c.close_bracket(False)
    if written == 0:
        raise RuntimeError("no bone of the rig could be written to the animation asset " + asset)
    if not unreal.EditorAssetLibrary.save_asset(asset, only_if_is_dirty=False):
        raise RuntimeError("the editor would not save " + asset)
    return {"asset": asset, "frames": int(unreal.AnimationLibrary.get_num_frames(anim)), "ik_copy": "skeleton pose", "ik_bones": [ik for _, ik in pairs],
            "bones": written, "skipped_bones": skipped, "dirty": dirty_packages()}


kei_run(_main)
