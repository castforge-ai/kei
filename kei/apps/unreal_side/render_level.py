# kei_script: render_level
# Kei's own level for drawing the real mesh with Movie Render Queue: a floor, the template's light and sky, and
# nothing else. A project's own levels hold game actors whose BeginPlay can stop the editor during the render, so Kei
# never renders in them. Made once, from the engine's default template (never by copying a map, which can crash the
# editor): the template's Player Start and meshes are removed, a large plane is the floor, and the level's game mode
# is the engine's plain GameModeBase. The level that was open before is opened again at the end.
# Input: level (the level's path, under /Game/Kei). Output: level, made (True when it was made now), restored (the
# level opened again, or "").
TEMPLATE = "/Engine/Maps/Templates/Template_Default"
FLOOR_MESH = "/Engine/BasicShapes/Plane"
FLOOR_MATERIAL = "/Engine/BasicShapes/BasicShapeMaterial"


def _main(inp):
    path = inp["level"]
    if not path.startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei makes levels only under " + KEI_ROOT + ", not " + path)
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return {"level": path, "made": False, "restored": ""}
    dirty_maps = [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    if dirty_maps:
        raise RuntimeError("the open level has unsaved changes (" + ", ".join(dirty_maps) + "): save it first, "
                           "then render again; Kei opens its render level once to make it, and never saves yours")
    levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    world = editor_world()
    before = str(world.get_outermost().get_name()) if world is not None else ""
    if not levels.new_level_from_template(path, TEMPLATE):
        raise RuntimeError("the editor would not make the level " + path + " from " + TEMPLATE)
    try:
        for a in actors.get_all_level_actors():
            if isinstance(a, (unreal.PlayerStart, unreal.StaticMeshActor)):
                actors.destroy_actor(a)
        floor = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(0.0, 0.0, 0.0))
        floor.set_actor_label("KeiFloor")
        floor.set_actor_scale3d(unreal.Vector(2000.0, 2000.0, 1.0))
        comp = floor.static_mesh_component
        comp.set_static_mesh(unreal.load_asset(FLOOR_MESH))
        comp.set_material(0, unreal.load_asset(FLOOR_MATERIAL))
        editor_world().get_world_settings().set_editor_property("default_game_mode", unreal.GameModeBase)
        if not levels.save_current_level():
            raise RuntimeError("the editor would not save the level " + path)
    finally:
        restored = ""
        if before and not before.startswith("/Temp/") and before != path:
            if levels.load_level(before):
                restored = before
    return {"level": path, "made": True, "restored": restored}


kei_run(_main)
