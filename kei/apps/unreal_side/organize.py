# kei_script: organize
# Files Kei's own assets of a delivered shot by phase: each move renames one asset inside Kei's folder for the shot
# (/Game/Kei/<shot>/...) to a subfolder of the same folder, saves it there, and returns where each went. It never
# deletes an asset and never touches one outside Kei's folder. A sequence open in Sequencer is closed first, since
# an open sequence cannot move.
# Input: folder (/Game/Kei/<shot>), moves [[from, to]]. Output: moved [[from, to]], failed [[from, why]], dirty, and
# content_dir (the project's Content folder on disk, where Kei puts a copy of the shot's report).
def _main(inp):
    folder = inp["folder"]
    if not folder.startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei organizes only its own folder under " + KEI_ROOT + ", not " + folder)
    E = unreal.EditorAssetLibrary
    lib = unreal.LevelSequenceEditorBlueprintLibrary
    moved, failed = [], []
    current = lib.get_current_level_sequence()
    open_path = current.get_path_name().split(".")[0] if current is not None else ""
    for src, dst in inp["moves"]:
        if not (src.startswith(folder + "/") and dst.startswith(folder + "/")):
            failed.append([src, "outside Kei's folder for this shot"])
            continue
        if not E.does_asset_exist(src):
            failed.append([src, "no such asset"])
            continue
        if E.does_asset_exist(dst):
            failed.append([src, "the place it would go is taken: " + dst])
            continue
        if src == open_path:
            lib.close_level_sequence()
            open_path = ""
        if E.rename_asset(src, dst):
            E.save_asset(dst, only_if_is_dirty=True)
            moved.append([src, dst])
        else:
            failed.append([src, "the editor would not move it"])
    content = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())
    return {"moved": moved, "failed": failed, "dirty": dirty_packages(), "content_dir": content}


kei_run(_main)
