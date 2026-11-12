# kei_script: save_asset
# Saves ONE asset by its path, and only when it is under /Game/Kei/. Never a save-all, never a user asset.
def _main(inp):
    path = inp["path"]
    if not path.startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei saves only assets under " + KEI_ROOT + ", not " + path)
    if not unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False):
        raise RuntimeError("the editor would not save " + path)
    return {"saved": path, "dirty": dirty_packages()}


kei_run(_main)
