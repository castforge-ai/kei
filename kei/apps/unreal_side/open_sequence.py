# kei_script: open_sequence
# Opens Kei's own sequence in Sequencer when it is not the one in focus. Control Rig reads (eval_rig.py) work only on
# the sequence that is open, so Kei calls this, waits one editor tick, then calls eval_rig.py.
def _main(inp):
    if not inp["sequence"].startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei opens only its own sequences under " + KEI_ROOT)
    lib = unreal.LevelSequenceEditorBlueprintLibrary
    seq = load_sequence(inp["sequence"])
    current = lib.get_current_level_sequence()
    reopened = current is None or current.get_path_name() != seq.get_path_name()
    if reopened:
        lib.open_level_sequence(seq)
    return {"sequence": inp["sequence"], "reopened": reopened}


kei_run(_main)
