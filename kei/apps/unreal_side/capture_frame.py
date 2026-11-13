# kei_script: capture_frame
# A test of drawing Kei's own character from the editor itself (the real mesh, not a line drawing). Two stages, because
# the pose appears one editor tick after the time is set. stage "pose": opens the sequence in Sequencer and sets the
# time to the frame. stage "shoot": for each view, a temporary SceneCapture2D camera that shows only the character
# (the level's other objects stay out of the picture), a temporary light, one render target; the picture is written as a
# PNG into out_dir. The temporary actors are deleted at the end. Nothing is saved and no asset is made.
# Input: stage, sequence, frame, and for "shoot" views [{name, yaw}], out_dir, size [w, h].
# Output (shoot): files [path], nonblack {name: fraction of the picture that is not the background}, found (how the
# character was found), errors.
import math


def _character(seq):
    lib = unreal.LevelSequenceEditorBlueprintLibrary
    try:
        bid = unreal.MovieSceneSequenceExtensions.get_binding_id(seq, seq.get_bindings()[0])
        objs = [o for o in lib.get_bound_objects(bid) if o is not None]
        if objs:
            return objs[0], "the sequence's bound object"
    except Exception:
        pass
    for actor in unreal.EditorLevelLibrary.get_all_level_actors():
        if isinstance(actor, unreal.SkeletalMeshActor):
            return actor, "the first skeletal mesh actor in the level"
    return None, "none found"


def _main(inp):
    lib = unreal.LevelSequenceEditorBlueprintLibrary
    seq = load_sequence(inp["sequence"])
    if not inp["sequence"].startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei opens only its own sequences under " + KEI_ROOT)
    if inp["stage"] == "pose":
        current = lib.get_current_level_sequence()
        if current is None or current.get_path_name() != seq.get_path_name():
            lib.open_level_sequence(seq)
        lib.set_current_time(int(inp["frame"]))
        return {"stage": "pose", "frame": int(inp["frame"])}
    out = {"stage": "shoot", "files": [], "nonblack": {}, "errors": [], "found": ""}
    world = editor_world()
    actor, out["found"] = _character(seq)
    if actor is None:
        raise RuntimeError("no character found to draw: open the shot's sequence and try again")
    w, h = int(inp["size"][0]), int(inp["size"][1])
    origin, extent = actor.get_actor_bounds(False)
    radius = max(extent.x, extent.y, extent.z) * 1.3
    fov = 30.0
    dist = radius / math.tan(math.radians(fov / 2.0))
    temps = []
    try:
        was_dirty = None
        try:
            level_pkg = world.get_outermost()
            was_dirty = level_pkg in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        except Exception:
            level_pkg = None
        light = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.DirectionalLight, origin,
                                                                 unreal.Rotator(0.0, -40.0, 35.0))
        temps.append(light)
        try:
            light.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property("intensity", 4.0)
        except Exception as e:
            out["errors"].append("light: " + str(e)[:100])
        rt = unreal.RenderingLibrary.create_render_target2d(world, w, h, unreal.TextureRenderTargetFormat.RTF_RGBA8)
        for view in inp["views"]:
            try:
                yaw = math.radians(float(view["yaw"]))
                pos = unreal.Vector(origin.x + dist * math.cos(yaw), origin.y + dist * math.sin(yaw), origin.z)
                look = unreal.MathLibrary.find_look_at_rotation(pos, origin)
                cam = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.SceneCapture2D, pos, look)
                temps.append(cam)
                comp = cam.get_editor_property("capture_component2d")
                comp.set_editor_property("texture_target", rt)
                comp.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
                comp.set_editor_property("primitive_render_mode",
                                         unreal.SceneCapturePrimitiveRenderMode.PRM_USE_SHOW_ONLY_LIST)
                comp.set_editor_property("show_only_actors", [actor])
                comp.set_editor_property("fov_angle", fov)
                comp.set_editor_property("capture_every_frame", False)
                comp.capture_scene()
                name = str(view["name"])
                unreal.RenderingLibrary.export_render_target(world, rt, inp["out_dir"], name)
                corner = unreal.RenderingLibrary.read_render_target_pixel(world, rt, 2, 2)
                total = on = 0
                for gx in range(8, w, max(1, w // 24)):
                    for gy in range(8, h, max(1, h // 24)):
                        p = unreal.RenderingLibrary.read_render_target_pixel(world, rt, gx, gy)
                        total += 1
                        if abs(p.r - corner.r) + abs(p.g - corner.g) + abs(p.b - corner.b) > 0.06:
                            on += 1
                out["nonblack"][name] = round(on / max(1, total), 3)
            except Exception as e:
                out["errors"].append(str(view.get("name")) + ": " + str(e)[:160])
    finally:
        for t in temps:
            try:
                unreal.EditorLevelLibrary.destroy_actor(t)
            except Exception:
                pass
        try:
            if was_dirty is False and level_pkg is not None:
                level_pkg.set_dirty_flag(False)        # the level was clean before the temporary actors
        except Exception:
            pass
    import os
    out["files"] = sorted(os.path.join(inp["out_dir"], f) for f in os.listdir(inp["out_dir"])) if os.path.isdir(inp["out_dir"]) else []
    return out


kei_run(_main)
