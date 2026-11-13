"""A pose from an animation already in the project, on the character's Control Rig, exactly.

When a shot has to start, end or pass through a pose that exists in the project (the character's idle, the last frame
of the clip before it), the animator does not search for it by keying probes: Kei asks the Control Rig to solve it.

pose_from_anim(client, shot_dir, anim, frame) -> dict
  A new sequence of Kei's own for the pose (pass "pose"), one editor tick, the dirty list, load_pose.py (the rig's
  backwards solve keys every control from that animation frame, fingers included; the values are read back and
  checked bone by bone against the animation), the dirty list again, and the save of that one sequence by path.
  Writes rig/pose_<anim>_f<frame>.json: {"anim", "frame", "sequence", "check", "keys"}. "keys" is every keyable
  channel of rig/unreal_rig.json as "<control>.<channel>": value, in the units shot.json keys in, so a key in
  shot.json is {"f": <frame>, **keys}.
"""
from __future__ import annotations

import re
from pathlib import Path

from kei.apps.unreal import Claireon, run_script, tick
from kei.apps.unreal_rig import _write, check_dirty, kei_folder, load_character, load_rig, new_sequence
from kei.sample import ShotError

MEAN_DEG_OK = 1.0       # mean local rotation error over every bone the rig and the animation share
OFFSET_CM_OK = 2.0      # head, hands, fingertips and feet against the animation, relative to the pelvis


def pose_path(shot_dir: Path, anim: str, frame: int) -> Path:
    name = re.sub(r"[^A-Za-z0-9_]", "_", anim.rsplit("/", 1)[-1].split(".")[0]) or "anim"
    return Path(shot_dir) / "rig" / f"pose_{name}_f{int(frame)}.json"


def keys_for_rig(controls: dict, rig: dict) -> dict:
    """{"<control>.<channel>": value} for each channel the rig lets Kei key; locked controls are left out."""
    out = {}
    for c in rig["controls"]:
        if c.get("locked") or c["name"] not in controls:
            continue
        for ch in c["channels"]:
            if ch in controls[c["name"]]:
                v = controls[c["name"]][ch]
                out[f"{c['name']}.{ch}"] = v if isinstance(v, bool) else round(float(v), 4)
    return out


def within(check: dict) -> bool:
    mean = check.get("mean_deg")
    offsets = check.get("pelvis_relative_cm") or {}
    return mean is not None and mean <= MEAN_DEG_OK and all(v <= OFFSET_CM_OK for v in offsets.values())


def asset_path(anim: str) -> str:
    """An asset path as given; Git Bash on Windows turns /Game/... into C:/Program Files/Git/Game/..., so a path with
    a drive in front of a content root is taken from that root."""
    m = re.search(r"/(Game|Engine)/.+$", anim.replace("\\", "/"))
    if anim.startswith("/") or not m:
        return anim
    return m.group(0)


def pose_from_anim(client: Claireon, shot_dir: Path, anim: str, frame: int = 0) -> dict:
    anim = asset_path(anim)
    shot_dir = Path(shot_dir)
    rig = load_rig(shot_dir)
    character = load_character(shot_dir)
    if rig is None or character is None:
        raise ShotError("this Unreal shot has no rig read yet: run the shot (kei run) so Kei reads the "
                        "character's Control Rig first")
    seq = new_sequence(client, shot_dir, "pose", character, 30, 1)
    tick()                                  # the editor spawns the character one tick after the sequence opens
    before = run_script(client, "dirty.py", {})["dirty"]
    got = run_script(client, "load_pose.py", {"sequence": seq, "anim": anim, "frame": int(frame)})
    check_dirty(before, got.get("dirty", []), kei_folder(shot_dir))
    run_script(client, "save_asset.py", {"path": seq})
    keys = keys_for_rig(got.get("controls", {}), rig)
    if not keys:
        raise ShotError(f"the pose from {anim} gave no value for any control in rig/unreal_rig.json")
    report = {"anim": anim, "frame": int(frame), "sequence": seq, "check": got.get("check", {}),
              "matches": within(got.get("check", {})), "keys": keys}
    report["path"] = str(_write(pose_path(shot_dir, anim, frame), report))
    return report
