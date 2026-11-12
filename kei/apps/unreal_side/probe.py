# kei_script: probe
# Read only. Which project and level this editor has open, and the characters whose Control Rig Kei can key: each
# Control Rig asset under /Game with the skeletal mesh it previews on. Nothing is loaded for editing, nothing is saved.
def _main(inp):
    world = editor_world()
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    path = unreal.TopLevelAssetPath("/Script/ControlRigDeveloper", "ControlRigBlueprint")
    characters = []
    for data in registry.get_assets_by_class(path, True):
        package = str(data.package_name)
        if not package.startswith("/Game/"):
            continue
        rig = data.get_asset()
        mesh = None
        getter = getattr(rig, "get_preview_mesh", None)
        if getter is not None:
            mesh = getter()
        if mesh is None:
            try:
                mesh = rig.get_editor_property("preview_skeletal_mesh")
            except Exception:
                mesh = None
        mesh_path = str(mesh.get_path_name()).split(".")[0] if mesh is not None else ""
        if not mesh_path:
            continue
        characters.append({"name": str(mesh.get_name()), "mesh": mesh_path, "control_rig": package})
    return {"project": str(unreal.SystemLibrary.get_game_name()), "level": str(world.get_name()),
            "engine": str(unreal.SystemLibrary.get_engine_version()), "characters": characters}


kei_run(_main)
