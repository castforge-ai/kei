# kei_script: make_sequence
# Makes Kei's own Level Sequence for one pass under /Game/Kei/<shot>/, binds the character as a spawnable (nothing is
# added to the user's level) with its Control Rig track, sets the frame rate and range, saves THAT asset only, and
# opens it in Sequencer. Keys and reads need one editor tick after this call: Kei calls them separately.
# Input: folder, name, fps, frames, mesh, control_rig, copy_from (the previous pass's sequence, or "").
# Never deletes anything: a name that exists returns an error and Kei picks a new one.
# The character is placed on the floor of the open level, so it is never buried in the level's geometry: at the
# level's first Player Start, on the floor a trace straight down finds; with no Player Start, on the floor under the
# origin; with no floor found, at the origin. Only the spawnable's own template moves: the level is never touched.
def _floor_under(world, x, y, top, ignore):
    hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, top), unreal.Vector(x, y, top - 100000.0),
                                                 unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, ignore,
                                                 unreal.DrawDebugTrace.NONE, True)
    if hit is None:       # the trace returns nothing while the level is still loading: no floor found
        return None
    t = hit.to_tuple()
    return float(t[4].z) if t[0] else None


def _place(binding):
    world = editor_world()
    starts = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.PlayerStart))
    x = y = z = 0.0
    how = "origin"
    if starts:
        loc = starts[0].get_actor_location()
        x, y = float(loc.x), float(loc.y)
        found = _floor_under(world, x, y, float(loc.z) + 50.0, starts)
        if found is not None:
            z, how = found, "the floor under the Player Start"
        else:
            cap = starts[0].get_component_by_class(unreal.CapsuleComponent)
            z = float(loc.z) - (cap.get_scaled_capsule_half_height() if cap else 92.0)
            how = "the foot of the Player Start"
    else:
        found = _floor_under(world, 0.0, 0.0, 50000.0, [])
        if found is not None:
            z, how = found, "the floor under the origin"
    binding.get_object_template().skeletal_mesh_component.set_editor_property(
        "relative_location", unreal.Vector(x, y, z))
    return {"how": how, "at_cm": [round(x, 2), round(y, 2), round(z, 2)], "level": world.get_path_name().split(".")[0]}


def _main(inp):
    folder, name = inp["folder"], inp["name"]
    if not folder.startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei writes only under " + KEI_ROOT + ", not " + folder)
    path = folder + "/" + name
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        raise RuntimeError("the asset " + path + " already exists: Kei never overwrites or deletes an asset")
    unreal.LevelSequenceEditorBlueprintLibrary.close_level_sequence()
    if inp.get("copy_from"):
        seq = unreal.EditorAssetLibrary.duplicate_asset(inp["copy_from"], path)
        if seq is None:
            raise RuntimeError("could not copy " + inp["copy_from"] + " to " + path)
        binding = seq.get_bindings()[0]
    else:
        tools = unreal.AssetToolsHelpers.get_asset_tools()
        seq = tools.create_asset(name, folder, unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
        if seq is None:
            raise RuntimeError("the editor would not create " + path)
        binding = seq.add_spawnable_from_class(unreal.SkeletalMeshActor)
        template = binding.get_object_template()
        component = template.skeletal_mesh_component
        mesh = unreal.load_asset(inp["mesh"])
        if mesh is None:
            raise RuntimeError("the mesh " + inp["mesh"] + " is not in the project")
        component.set_editor_property("skeletal_mesh_asset", mesh)
        binding.set_display_name("Kei " + str(mesh.get_name()))
        rig_asset = unreal.load_asset(inp["control_rig"])
        if rig_asset is None:
            raise RuntimeError("the Control Rig " + inp["control_rig"] + " is not in the project")
        track = unreal.ControlRigSequencerLibrary.find_or_create_control_rig_track(
            editor_world(), seq, rig_asset.generated_class(), binding)
        if track is None:
            raise RuntimeError("the editor would not add the Control Rig track")
    placed = _place(binding)
    fps = int(round(float(inp.get("fps") or 24)))
    seq.set_display_rate(unreal.FrameRate(fps, 1))
    seq.set_playback_start(0)
    seq.set_playback_end(int(inp["frames"]) + 1)
    if not unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False):
        raise RuntimeError("the editor would not save " + path)
    unreal.LevelSequenceEditorBlueprintLibrary.open_level_sequence(seq)
    return {"path": path, "fps": fps, "frames": int(inp["frames"]), "placed": placed,
            "dirty": dirty_packages()}


kei_run(_main)
