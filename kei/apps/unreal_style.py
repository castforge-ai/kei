"""A character's style range from their own clips in the project (kei unreal style), written to rig/style.json.

style_shot(client, shot_dir, anims, character, fps) -> dict
  For each animation: read_bake.py reads the world position of every bone Kei measures, a few frames per call, the
  same way Kei reads its own bakes. The bones become Kei's joints (kei.apps.unreal_readback.joints_from_bones, with
  the character's facing from rig/unreal_rig.json, else from the clip's own first frame). The body checks run on
  them as on a pass, and the twelve-principle measure gives each part's largest move. kei.style keeps, for each
  soft check, the furthest any clip goes. Read only: nothing in the project changes.
"""
from __future__ import annotations

import json
from pathlib import Path

from kei.apps.unreal import Claireon, run_script
from kei.apps.unreal_bake import CHUNK
from kei.apps.unreal_readback import joints_from_bones
from kei.apps.unreal_rig import load_rig
from kei.apps.unreal_units import Frame, frame_from_rest
from kei.rig import BONES
from kei.style import range_from_clips, style_path


def clip_joints(bones_by_frame: dict, frame: Frame | None) -> tuple[list[dict], Frame]:
    """{"<f>": {bone: [x, y, z] cm}} to Kei frames, in frame order."""
    order = sorted(bones_by_frame, key=int)
    if frame is None:
        first = bones_by_frame[order[0]]
        frame = frame_from_rest(tuple(first["thigh_l"]), tuple(first["thigh_r"]))
    return [{"f": i, "joints": joints_from_bones(bones_by_frame[f], frame)} for i, f in enumerate(order)], frame


def measure_clip(name: str, frames: list[dict], fps: float, proportions: dict, height: float) -> dict:
    """One clip's soft-check flags and largest moves, the input of kei.style.range_from_clips."""
    from kei.body_check import measure
    from kei.principles import measure as principles
    report = measure({"fps": fps, "loop": False, "keys": []}, "spline", proportions, height, frames)
    moves = principles(frames, fps, height)["principles"]["exaggeration"]["measured"]["largest_move_cm"]
    return {"name": name, "frames": len(frames), "flags": [f for f in report["flags"] if f.get("measure")],
            "move_cm": moves}


def style_shot(client: Claireon, shot_dir: Path, anims: list[str], character, fps: float = 30.0) -> dict:
    shot_dir = Path(shot_dir)
    rig = load_rig(shot_dir) or {}
    facing = Frame.from_dict(rig["frame"]) if rig.get("frame") else None
    clips = []
    for anim in anims:
        got = run_script(client, "read_bake.py", {"asset": anim, "bones": list(BONES), "start": 0, "end": 0})
        last = int(got.get("total") or 1) - 1
        bones = dict(got["frames"])
        for start in range(1, last + 1, CHUNK):
            bones.update(run_script(client, "read_bake.py", {"asset": anim, "bones": list(BONES), "start": start,
                                                             "end": min(last, start + CHUNK - 1)})["frames"])
        frames, used = clip_joints(bones, facing)
        clips.append(measure_clip(anim, frames, fps, character.proportions, character.height))
    style = {**range_from_clips(clips), "character": character.name, "fps": fps,
             "per_clip": [{"name": c["name"], "frames": c["frames"],
                           "soft_flags": [{k: f[k] for k in ("measure", "value", "frames")} for f in c["flags"]]}
                          for c in clips]}
    dst = style_path(shot_dir)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(style, indent=1), encoding="utf-8")
    return {**style, "path": str(dst)}
