"""Key a pass on the character's Control Rig in the open editor, in Kei's own sequence, and touch no user asset.

The animator seat writes out_<pass>/shot.json: {"rig": "unreal", "fps": 24, "frames": 48, "keys": [{"f": 12,
"tangent": "step", "foot_l_ik_ctrl.location.z": 8.0}]}. A key names a control and a channel, in the units
rig/unreal_rig.json states (centimetres, degrees, Z up). The seat never talks to Claireon: Kei applies the file.

apply_keys(client, shot_dir, pass_name, mode) -> dict
  Checks every key against rig/unreal_rig.json before any call (an unknown or locked control or channel is refused,
  naming both, and nothing is keyed). Then: a new sequence for the pass, the dirty list, one set_keys call per key
  frame, the dirty list again, and the save of that one sequence by path. A package that became dirty outside
  /Game/Kei/<shot>/ stops the shot with needs_human, naming it. Writes out_<pass>/unreal_report.json (the sequence,
  the keys, and each pose a limit clipped: asked versus reached).
"""
from __future__ import annotations

import json
from pathlib import Path

from kei.apps.unreal import Claireon, UnrealError, run_script, tick
from kei.apps.unreal_rig import check_dirty, kei_folder, load_character, load_rig, new_sequence
from kei.sample import ShotError, read_json

TANGENTS = ("step", "linear", "spline", "flat")
NOT_CHANNELS = ("f", "tangent", "name", "note", "function", "kind")


def parse_keys(shot: dict, rig: dict, mode: str) -> list[dict]:
    """[{"f", "tangent", "controls": {control: {channel: value}}}] by frame, or a ShotError naming the control and
    channel that cannot be keyed. Keys at the same frame are merged."""
    if shot.get("rig") != "unreal":
        raise ShotError('an Unreal shot keeps "rig": "unreal" in shot.json, with keys such as '
                        '{"f": 12, "tangent": "step", "foot_l_ik_ctrl.location.z": 8.0}')
    by_name = {c["name"]: c for c in rig["controls"]}
    frames: dict[int, dict] = {}
    for i, k in enumerate(shot.get("keys") or []):
        if not isinstance(k, dict) or not isinstance(k.get("f"), (int, float)) or isinstance(k.get("f"), bool):
            raise ShotError(f'key {i + 1} needs a frame "f"')
        f = int(k["f"])
        tangent = k.get("tangent", "spline")
        if tangent not in TANGENTS:
            raise ShotError(f"key f {f}: tangent is one of {', '.join(TANGENTS)}")
        if mode == "step":
            tangent = "step"
        slot = frames.setdefault(f, {"f": f, "tangent": tangent, "controls": {}})
        for name, value in k.items():
            if name in NOT_CHANNELS:
                continue
            control = max((c for c in by_name if name.startswith(c + ".")), key=len, default=None)
            if control is None:
                raise ShotError(f"key f {f}: {name} names no control of the rig; the rig's controls are in "
                                "rig/unreal_rig.json")
            channel = name[len(control) + 1:]
            c = by_name[control]
            if c.get("locked"):
                raise ShotError(f"key f {f}: the control {control} is locked in the rig, so {channel} cannot be keyed")
            if channel not in c["channels"]:
                raise ShotError(f"key f {f}: the control {control} has no channel {channel} (it has "
                                f"{', '.join(c['channels'])})")
            if isinstance(value, bool):
                value = float(value) if c["type"] != "bool" else value
            elif not isinstance(value, (int, float)):
                raise ShotError(f"key f {f}: {name} needs a number")
            slot["controls"].setdefault(control, {})[channel] = value
    return [frames[f] for f in sorted(frames)]


BATCH = 15      # key frames in one editor call: few calls, and each one short enough to answer in time
INPUT_BUDGET = 40_000   # bytes of key input in one call: Claireon refuses a script over 64 KiB, and the script and
                        # Kei's helpers ride in the same call. A full-body pose keys every channel (about 1000)


def batches(keys: list[dict], types: dict, budget: int = INPUT_BUDGET, most: int = BATCH) -> list[list[dict]]:
    """The set_keys inputs in calls of at most `most` key frames and about `budget` bytes. A key frame too large for
    one call is split by control into several calls at the same frame: keys on one control never split."""
    items = []
    for k in keys:
        part: dict = {}
        size = 0
        for ctl, chans in k["controls"].items():
            cost = len(json.dumps({ctl: chans})) + len(json.dumps({ctl: types[ctl]}))   # its values and its type
            if part and size + cost > budget:
                items.append((k, part))
                part, size = {}, 0
            part[ctl] = chans
            size += cost
        items.append((k, part))
    out, cur, size = [], [], 0
    for k, controls in items:
        item = {"frame": k["f"], "tangent": k["tangent"], "controls": controls,
                "types": {c: types[c] for c in controls}}
        n = len(json.dumps(item))
        if cur and (len(cur) >= most or size + n > budget):
            out.append(cur)
            cur, size = [], 0
        cur.append(item)
        size += n
    if cur:
        out.append(cur)
    return out


def apply_keys(client: Claireon, shot_dir: Path, pass_name: str, mode: str | None = None) -> dict:
    shot_dir = Path(shot_dir)
    out = shot_dir / f"out_{pass_name}"
    shot = read_json(out / "shot.json", "shot")
    rig = load_rig(shot_dir)
    character = load_character(shot_dir)
    if rig is None or character is None:
        raise ShotError("this Unreal shot has no rig read yet: run the shot (kei run) so Kei reads the "
                        "character's Control Rig first")
    mode = mode or ("step" if pass_name == "blocking" else "spline")
    keys = parse_keys(shot, rig, mode)
    if not keys:
        raise ShotError("shot.json has no keys")
    frames = int(shot.get("frames") or keys[-1]["f"])
    fps = shot.get("fps") or 24
    types = {c["name"]: c["type"] for c in rig["controls"]}
    folder = kei_folder(shot_dir)
    seq = new_sequence(client, shot_dir, pass_name, character, fps, frames)
    tick()                                  # the editor spawns the character one tick after the sequence opens
    before = run_script(client, "dirty.py", {})["dirty"]
    clipped, tangents = [], "set"
    for batch in batches(keys, types):          # a batch of key frames in one call: one audit file, not one per frame
        got = run_script(client, "set_keys.py", {"sequence": seq, "keys": batch})
        clipped += got.get("clipped", [])
        if str(got.get("tangents", "set")) != "set":
            tangents = got["tangents"]
    after = run_script(client, "dirty.py", {})["dirty"]
    check_dirty(before, after, folder)     # a user asset Kei made dirty: nothing is saved, the shot stops
    saved = run_script(client, "save_asset.py", {"path": seq})
    report = {"target": "open", "sequence": seq, "mode": mode, "keys": len(keys), "clipped": clipped,
              "tangents": tangents, "saved": saved["saved"], "claireon": client.info, "frames": frames, "fps": fps,
              "said": f"Kei keyed {len(keys)} frames of {character['name']}'s Control Rig in {seq}"}
    out.mkdir(parents=True, exist_ok=True)
    (out / "unreal_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
