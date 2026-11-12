# kei_script: read_bake
# Read only. The world position of each named bone of a baked animation asset, for a range of frames, in Unreal
# centimetres. Kei calls it in chunks of a few frames so that a result stays small. A bone the skeleton lacks is
# named in "missing" and left out.
def _main(inp):
    anim = unreal.load_asset(inp["asset"])
    if anim is None:
        raise RuntimeError("the baked asset " + inp["asset"] + " is not in the project")
    have = set(str(b) for b in unreal.AnimPoseExtensions.get_bone_names(
        unreal.AnimPoseExtensions.get_anim_pose_at_frame(anim, 0, unreal.AnimPoseEvaluationOptions())))
    bones = [b for b in inp["bones"] if b in have]
    frames = {}
    for f in range(int(inp["start"]), int(inp["end"]) + 1):
        pose = unreal.AnimPoseExtensions.get_anim_pose_at_frame(anim, f, unreal.AnimPoseEvaluationOptions())
        row = {}
        for b in bones:
            t = unreal.AnimPoseExtensions.get_bone_pose(pose, b, unreal.AnimPoseSpaces.WORLD).translation
            row[b] = [round(t.x, 3), round(t.y, 3), round(t.z, 3)]
        frames[str(f)] = row
    return {"frames": frames, "missing": [b for b in inp["bones"] if b not in have],
            "total": int(unreal.AnimationLibrary.get_num_frames(anim))}


kei_run(_main)
