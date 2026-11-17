# kei_script: kei_ue
# Shared helpers of Kei's editor scripts. Kei sends this text in front of every script, after the KEI_INPUT line.
# Every script prints exactly one line, KEI_RESULT <json>: Claireon reports a Python exception as a success with a
# traceback in the logs, so Kei reads its own result line and treats a missing line as a failure.
import json
import traceback

import unreal

KEI_ROOT = "/Game/Kei"


RESULT_INLINE_MAX = 3000     # Claireon truncates long output, so a larger result goes through a file


def kei_result(obj):
    text = json.dumps(obj)
    if len(text) > RESULT_INLINE_MAX:
        # Kei chose the folder (KEI_RESULTS_DIR) and accepts back only the bare token, never a path.
        import os
        import uuid
        token = uuid.uuid4().hex
        with open(os.path.join(KEI_RESULTS_DIR, token + ".json"), "w", encoding="utf-8") as f:
            f.write(text)
        text = json.dumps({"result_token": token})
    print("KEI_RESULT " + text)


def kei_run(fn):
    """Run fn(KEI_INPUT) and print its dict; an exception becomes {"error": <traceback>}."""
    try:
        kei_result(fn(KEI_INPUT))
    except Exception:
        kei_result({"error": traceback.format_exc()})


def dirty_packages():
    """The names of every dirty content package and dirty map package in the editor."""
    names = [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()]
    names += [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    return sorted(set(names))


def editor_world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def load_sequence(path):
    seq = unreal.load_asset(path)
    if seq is None:
        raise RuntimeError("the sequence " + path + " is not in the project")
    return seq


PERFORMER = "Kei performer: "   # the display name of a second performer's binding starts with this


def binding_of(seq, performer=""):
    """The binding of the shot's character (performer ""), or of the named second performer ("Kei performer: <name>")."""
    for b in seq.get_bindings():
        name = str(b.get_display_name())
        if (name == PERFORMER + performer) if performer else not name.startswith(PERFORMER):
            return b
    raise RuntimeError("the sequence " + seq.get_path_name() + " has no binding for "
                       + ("the performer " + performer if performer else "the character"))


def control_rig_of(seq, performer=""):
    """The Control Rig instance on the binding of the character, or of the named second performer."""
    rigs = unreal.ControlRigSequencerLibrary.get_control_rigs(seq)
    if not rigs:
        raise RuntimeError("the sequence " + seq.get_path_name() + " has no Control Rig track")
    tracks = {t.get_path_name() for t in binding_of(seq, performer).get_tracks()}
    for r in rigs:
        if r.track is not None and r.track.get_path_name() in tracks:
            return r.control_rig
    raise RuntimeError("the sequence " + seq.get_path_name() + " has no Control Rig track on "
                       + ("the performer " + performer if performer else "the character"))
