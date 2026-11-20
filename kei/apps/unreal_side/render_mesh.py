# kei_script: render_mesh
# Draws a pass on the real mesh with Movie Render Queue, from cameras placed off the character's own path, so the
# critics judge the character as the game shows it (feet and toes on the floor, the hands, the timing), not only Kei's
# line drawings. Two stages, because the bound character appears one editor tick after the sequence is opened.
# stage "open": opens the pass's sequence in Sequencer.
# stage "render": solves the rig at the first and the last frame for the pelvis path in the world, places the views
#   from it, closes the sequence, makes one view sequence per camera (a copy of the pass with a spawned CineCamera and a
#   camera cut, under <views_folder>), queues one job per view in Kei's render level (the PIE executor, PNG, no motion
#   blur, game mode GameModeBase) and starts the render. The frames land as <out_dir>/<view>/f0000.png ... while the
#   editor renders; Kei waits for them on the disk. Kei writes only under /Game/Kei: no user asset is changed, and a
#   queue holding someone else's jobs is never cleared.
# Input: stage, sequence; for "render" also out_dir, last (the last frame), views [names], level, views_folder,
#   size [w, h], pelvis (the bone the cameras follow).
# Output (render): views [{name, sequence, position, target}], frames (per view), travel_cm, warnings.
import math

SIDE_Z, THREE_Q_Z, AIM_Z = 95.0, 120.0, 80.0        # camera heights and the aim point, above the floor, in cm
FEET_Z, FEET_AIM_Z = 25.0, 12.0
HALF_FOV = math.radians(20.0)                      # the CineCamera's default lens, about 40 degrees across
DIST_SCALE = 1.6                                   # room around the travel: the first live test was framed too tight
FRAME_TALL = 230.0                                 # the height every view keeps in the picture, in cm


def _path_text(soft):
    try:
        return str(soft.export_text())
    except Exception:
        return str(soft)


def _unique(path):
    if not unreal.EditorAssetLibrary.does_asset_exist(path):
        return path
    n = 2
    while unreal.EditorAssetLibrary.does_asset_exist(path + "_" + str(n)):
        n += 1
    return path + "_" + str(n)


def _cameras(p0, p1, comp, size, names):
    d = unreal.Vector(p1.x - p0.x, p1.y - p0.y, 0.0)
    travel = math.hypot(d.x, d.y)
    if travel > 20.0:
        fwd = unreal.Vector(d.x / travel, d.y / travel, 0.0)
    else:
        r = comp.get_right_vector()
        n = math.hypot(r.x, r.y) or 1.0
        fwd = unreal.Vector(r.x / n, r.y / n, 0.0)
    side = unreal.Vector(-fwd.y, fwd.x, 0.0)
    floor = comp.get_world_transform().translation.z
    mid = unreal.Vector((p0.x + p1.x) / 2.0, (p0.y + p1.y) / 2.0, floor)
    across = (travel + 160.0) / (2.0 * math.tan(HALF_FOV)) * DIST_SCALE
    tall = (FRAME_TALL / 2.0) / (math.tan(HALF_FOV) * float(size[1]) / float(size[0]))
    dist = max(across, tall)
    up = lambda z: unreal.Vector(0.0, 0.0, z)
    feet_dir = side * 0.8 + fwd * 0.6      # a low three quarter: straight from the side, the near foot hides the far one
    every = {
        "side": (mid + side * dist + up(SIDE_Z), mid + up(AIM_Z)),
        "three_quarter": (mid + (side * 0.7 + fwd * 0.7) * dist + up(THREE_Q_Z), mid + up(AIM_Z)),
        "feet": (mid + feet_dir * (dist * 0.75) + up(FEET_Z), mid + up(FEET_AIM_Z)),
    }
    unknown = [n for n in names if n not in every]
    if unknown:
        raise RuntimeError("Kei has no camera named " + ", ".join(unknown) + "; it has " + ", ".join(sorted(every)))
    return {n: every[n] for n in names}, travel


def _pelvis_path(seq, comp, last, pelvis):
    lib = unreal.ControlRigSequencerLibrary
    rig = control_rig_of(seq)
    h = rig.get_hierarchy()
    bones = {str(b.name): b for b in h.get_bones()}
    if pelvis not in bones:
        raise RuntimeError("the Control Rig has no bone " + pelvis + " for the cameras to follow")
    unit = unreal.MovieSceneTimeUnit.DISPLAY_RATE
    keyed = []
    for c in h.get_controls():
        s = h.get_control_settings(c)
        if "ANIMATION_CONTROL" in str(s.animation_type).upper() and "EULER" in str(s.control_type).upper():
            keyed.append(c)
    ct = comp.get_world_transform()

    def at(f):
        for k in keyed:
            e = lib.get_local_control_rig_euler_transform(seq, rig, str(k.name), unreal.FrameNumber(f), unit)
            h.set_local_transform(k, unreal.Transform(location=[e.location.x, e.location.y, e.location.z],
                                                      rotation=e.rotation, scale=[e.scale.x, e.scale.y, e.scale.z]))
        rig.execute(unreal.Name("Forwards Solve"))
        return ct.transform_location(h.get_global_transform(bones[pelvis]).translation)
    return at(0), at(last)


def _no_blur(cfg, warnings):
    cv = cfg.find_or_add_setting_by_class(unreal.MoviePipelineConsoleVariableSetting)
    try:
        cv.add_or_update_console_variable("r.MotionBlurQuality", 0.0)
        return
    except Exception:
        pass
    try:
        values = dict(cv.get_editor_property("console_variables") or {})
        values["r.MotionBlurQuality"] = 0.0
        cv.set_editor_property("console_variables", values)
    except Exception as e:
        warnings.append("motion blur could not be turned off: " + str(e)[:120])


def _main(inp):
    lib = unreal.LevelSequenceEditorBlueprintLibrary
    path = inp["sequence"]
    if not path.startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei renders only its own sequences under " + KEI_ROOT)
    seq = load_sequence(path)
    if inp["stage"] == "open":
        current = lib.get_current_level_sequence()
        if current is None or current.get_path_name() != seq.get_path_name():
            lib.open_level_sequence(seq)
        return {"stage": "open", "sequence": path}
    level, folder = inp["level"], inp["views_folder"]
    for p in (level, folder):
        if not p.startswith(KEI_ROOT + "/"):
            raise RuntimeError("Kei writes only under " + KEI_ROOT + ", not " + p)
    if not unreal.EditorAssetLibrary.does_asset_exist(level):
        raise RuntimeError("Kei's render level " + level + " is not in the project: make it first (render_level)")
    queue_sub = unreal.get_editor_subsystem(unreal.MoviePipelineQueueSubsystem)
    if queue_sub.is_rendering():
        raise RuntimeError("Movie Render Queue is rendering already: wait for it to finish, then render again")
    queue = queue_sub.get_queue()
    others = [t for t in (_path_text(j.sequence) for j in queue.get_jobs()) if KEI_ROOT + "/" not in t]
    if others:
        raise RuntimeError("the Movie Render Queue holds jobs that are not Kei's (" + ", ".join(others[:3]) + "): "
                           "render or remove them, then render again; Kei never clears your queue")
    current = lib.get_current_level_sequence()
    if current is None or current.get_path_name() != seq.get_path_name():
        raise RuntimeError("the sequence " + path + " is not open in Sequencer: open it first (stage open)")
    bid = seq.get_binding_id(binding_of(seq))
    objs = [o for o in lib.get_bound_objects(bid) if o is not None]
    if not objs:
        raise RuntimeError("the character of " + path + " is not bound yet: the sequence opens one editor tick "
                           "before it can be read; render again")
    comp = objs[0].get_component_by_class(unreal.SkeletalMeshComponent)
    if comp is None:
        raise RuntimeError("the character of " + path + " has no skeletal mesh to draw")
    last = int(inp["last"])
    size = [int(inp["size"][0]), int(inp["size"][1])]
    p0, p1 = _pelvis_path(seq, comp, last, inp.get("pelvis") or "pelvis")
    cams, travel = _cameras(p0, p1, comp, size, list(inp["views"]))
    lib.close_level_sequence()
    queue.delete_all_jobs()                          # Kei's own earlier jobs only: any other job stopped us above
    warnings, out_views = [], []
    base = path.rsplit(".", 1)[0]
    name_of = base.rsplit("/", 1)[-1]
    for name, (pos, tgt) in cams.items():
        dst = _unique(folder + "/" + name_of + "_" + name)
        view = unreal.EditorAssetLibrary.duplicate_asset(base, dst)
        if view is None:
            raise RuntimeError("the editor would not copy " + base + " to " + dst)
        cam = view.add_spawnable_from_class(unreal.CineCameraActor)
        d = tgt - pos
        track = cam.add_track(unreal.MovieScene3DTransformTrack)
        sec = track.add_section()
        sec.set_range(0, last + 1)
        pitch = math.degrees(math.atan2(d.z, math.hypot(d.x, d.y)))
        yaw = math.degrees(math.atan2(d.y, d.x))
        for i, val in enumerate([pos.x, pos.y, pos.z, 0.0, pitch, yaw]):
            sec.get_all_channels()[i].set_default(val)
        cut = view.add_track(unreal.MovieSceneCameraCutTrack)
        cs = cut.add_section()
        cs.set_range(0, last + 1)
        cs.set_camera_binding_id(view.get_binding_id(cam))
        if not unreal.EditorAssetLibrary.save_asset(dst, only_if_is_dirty=False):
            raise RuntimeError("the editor would not save the view " + dst)
        job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
        job.sequence = unreal.SoftObjectPath(dst)
        job.map = unreal.SoftObjectPath(level + "." + level.rsplit("/", 1)[-1])
        cfg = job.get_configuration()
        cfg.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
        cfg.find_or_add_setting_by_class(unreal.MoviePipelineImageSequenceOutput_PNG)
        o = cfg.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
        o.output_directory = unreal.DirectoryPath(inp["out_dir"] + "/" + name)
        o.output_resolution = unreal.IntPoint(size[0], size[1])
        o.file_name_format = "f{frame_number}"
        o.zero_pad_frame_numbers = 4
        game = cfg.find_or_add_setting_by_class(unreal.MoviePipelineGameOverrideSetting)
        game.game_mode_override = unreal.GameModeBase
        aa = cfg.find_or_add_setting_by_class(unreal.MoviePipelineAntiAliasingSetting)
        aa.engine_warm_up_count = 16
        _no_blur(cfg, warnings)
        out_views.append({"name": name, "sequence": dst, "position": [round(pos.x, 1), round(pos.y, 1), round(pos.z, 1)],
                          "target": [round(tgt.x, 1), round(tgt.y, 1), round(tgt.z, 1)]})
    queue_sub.render_queue_with_executor(unreal.MoviePipelinePIEExecutor)
    return {"stage": "render", "views": out_views, "frames": last + 1, "travel_cm": round(travel, 1),
            "warnings": warnings}


kei_run(_main)
