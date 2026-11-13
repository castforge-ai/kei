# kei_script: unload_kei
# Gives the editor its memory back after a pass: closes the Level Sequence editor, unloads the Kei sequences of this
# shot that are saved (an unsaved one stays loaded, so nothing is lost), clears the undo history, and collects garbage.
# Only assets under /Game/Kei/ are touched. Every step reports on its own and a step that fails never stops the next.
# Input: paths [asset path of each Kei sequence of the shot]. Output: closed, unloaded, kept_dirty, undo_cleared, gc,
# errors [why a step did not work].
def _main(inp):
    out = {"closed": False, "unloaded": 0, "kept_dirty": [], "undo_cleared": False, "gc": False, "errors": []}
    try:
        unreal.LevelSequenceEditorBlueprintLibrary.close_level_sequence()
        out["closed"] = True
    except Exception as e:
        out["errors"].append("close: " + str(e)[:120])
    packages = []
    try:
        dirty = set(str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
        for path in inp.get("paths", []):
            if not path.startswith(KEI_ROOT + "/"):
                continue
            if path in dirty or path.rsplit("/", 1)[0] + "/" + path.rsplit("/", 1)[-1] in dirty:
                out["kept_dirty"].append(path)
                continue
            asset = unreal.load_asset(path)
            if asset is not None:
                packages.append(asset.get_outermost())
        if packages:
            result = unreal.EditorLoadingAndSavingUtils.unload_packages(packages)
            ok = result[0] if isinstance(result, (tuple, list)) else bool(result)
            out["unloaded"] = len(packages) if ok else 0
            if not ok:
                out["errors"].append("unload: the editor refused: " + str(result[1] if isinstance(result, (tuple, list)) else ""))
    except Exception as e:
        out["errors"].append("unload: " + str(e)[:160])
    try:
        unreal.SystemLibrary.execute_console_command(editor_world(), "TRANS RESET")
        out["undo_cleared"] = True
    except Exception as e:
        out["errors"].append("undo: " + str(e)[:120])
    try:
        unreal.SystemLibrary.collect_garbage()
        out["gc"] = True
    except Exception as e:
        out["errors"].append("gc: " + str(e)[:120])
    return out


kei_run(_main)
