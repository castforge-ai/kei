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
  A shot may have second performers of the same character (shot.json "performers": {"ghost": {"offset_cm": [120,
  60, 0], "yaw_deg": 0, "look": [{"name": ..., "value": 1, "association": "blend", "layer": <layer function>}]}}):
  each is a second spawnable in the same sequence with its own Control Rig track, standing at the character's place
  plus its offset, in materials Kei makes from the look (make_look.py). Its keys carry its name as a prefix,
  "ghost/body_ctrl.location.x"; the character's keys have none, so every earlier shot still reads.
  From p2 on, a pass that changes the previous one (both keyed on every frame, same tangents) is written as a layer
  of it instead (kei.apps.unreal_layers): a copy of the previous pass's sequence, the changes as deltas on an
  additive section over the frames they bear on, merged down. The report's "layer" says which, and why not.
"""
from __future__ import annotations

import json
from pathlib import Path

import re

from kei.apps.unreal import Claireon, UnrealError, run_script, tick
from kei.apps.unreal_layers import layer_plan
from kei.apps.unreal_rig import check_dirty, kei_folder, load_character, load_rig, new_sequence, sequences
from kei.sample import ShotError, read_json

TANGENTS = ("step", "linear", "spline", "flat")
PERFORMER_NAME = re.compile(r"[a-z][a-z0-9_]{0,23}")
ASSOCIATIONS = ("global", "layer", "blend")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def performers_of(shot: dict) -> dict:
    """The shot's second performers, checked: {name: {"offset_cm": [x, y, z], "yaw_deg": d, "look": [scalar]}}."""
    raw = shot.get("performers") or {}
    if not isinstance(raw, dict):
        raise ShotError('"performers" in shot.json is an object, such as {"ghost": {"offset_cm": [120, 60, 0]}}')
    out = {}
    for name, p in raw.items():
        if not isinstance(name, str) or not PERFORMER_NAME.fullmatch(name):
            raise ShotError(f"the performer name {name!r} takes lower case letters, digits and _, starting with a "
                            "letter (at most 24)")
        if not isinstance(p, dict):
            raise ShotError(f"the performer {name} is an object with offset_cm, yaw_deg and look")
        off = p.get("offset_cm", [0, 0, 0])
        if not (isinstance(off, list) and len(off) == 3 and all(_num(v) for v in off)):
            raise ShotError(f"the performer {name}: offset_cm is [x, y, z] in centimetres, Unreal axes")
        yaw = p.get("yaw_deg", 0)
        if not _num(yaw):
            raise ShotError(f"the performer {name}: yaw_deg is a number of degrees")
        look = p.get("look") or []
        if not isinstance(look, list):
            raise ShotError(f"the performer {name}: look is a list of scalar parameters")
        for s in look:
            if not (isinstance(s, dict) and isinstance(s.get("name"), str) and _num(s.get("value"))):
                raise ShotError(f"the performer {name}: each look entry has a name and a number value")
            if s.get("association", "global") not in ASSOCIATIONS:
                raise ShotError(f"the performer {name}: a look parameter's association is global, layer or blend")
            if s.get("association", "global") != "global" and not isinstance(s.get("layer"), str):
                raise ShotError(f"the performer {name}: {s['name']} is a {s['association']} parameter, so it names "
                                "its layer function (\"layer\": \"/Game/...\")")
        out[name] = {"offset_cm": [float(v) for v in off], "yaw_deg": float(yaw),
                     "look": [{"name": s["name"], "value": float(s["value"]),
                               "association": s.get("association", "global"), "layer": s.get("layer", "")}
                              for s in look]}
    return out
NOT_CHANNELS = ("f", "tangent", "name", "note", "function", "kind")


def parse_keys(shot: dict, rig: dict, mode: str, performer: str = "") -> list[dict]:
    """[{"f", "tangent", "controls": {control: {channel: value}}}] by frame, or a ShotError naming the control and
    channel that cannot be keyed. Keys at the same frame are merged. performer "" reads the character's keys (no
    prefix); a performer's name reads its keys ("ghost/body_ctrl.location.x")."""
    named = set(performers_of(shot))
    if performer and performer not in named:
        raise ShotError(f"the shot has no performer {performer}")
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
        channels = [n for n in k if n not in NOT_CHANNELS]
        if not channels and not performer:
            frames.setdefault(f, {"f": f, "tangent": tangent, "controls": {}})
        for name, value in k.items():
            if name in NOT_CHANNELS:
                continue
            who = ""
            if "/" in name:
                who, name = name.split("/", 1)
                if who not in named:
                    raise ShotError(f"key f {f}: {who}/ names no performer of the shot; shot.json \"performers\" "
                                    "lists them")
            if who != performer:
                continue
            slot = frames.setdefault(f, {"f": f, "tangent": tangent, "controls": {}})
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


def previous_pass(shot_dir: Path, pass_name: str) -> str | None:
    """The pass before p<n> that Kei keyed in the editor (a sequence and a shot.json), or None (blocking, p1)."""
    m = re.fullmatch(r"p(\d+)", pass_name)
    if not m:
        return None
    made = sequences(shot_dir)
    for n in range(int(m.group(1)) - 1, 0, -1):
        if made.get(f"p{n}") and (Path(shot_dir) / f"out_p{n}" / "shot.json").is_file():
            return f"p{n}"
    return None


def _layer(shot_dir: Path, pass_name: str, shot: dict, keys: list[dict], rig: dict, types: dict, mode: str,
           frames: int, performer: str = "") -> tuple[str | None, dict]:
    """(the previous pass, its layer plan), or (None, {"full": why}), for the character or one performer."""
    if mode == "step":
        return None, {"full": "a stepped pass is keyed whole"}
    prev = previous_pass(shot_dir, pass_name)
    if prev is None:
        return None, {"full": "no earlier spline pass to layer on"}
    pshot = read_json(Path(shot_dir) / f"out_{prev}" / "shot.json", "shot")
    if int(pshot.get("frames") or -1) != frames or (pshot.get("fps") or 24) != (shot.get("fps") or 24):
        return None, {"full": f"the length or the frame rate differs from {prev}"}
    try:
        if performer and performers_of(pshot).get(performer) != performers_of(shot)[performer]:
            return None, {"full": f"the performer {performer} is new since {prev}, or stands or looks different"}
        return prev, layer_plan(parse_keys(pshot, rig, mode, performer), keys, types, frames)
    except ShotError as e:
        return None, {"full": f"{prev}'s keys no longer fit the rig: {e}"}


def _looks(client: Claireon, folder: str, character: dict, performers: dict) -> list[dict]:
    """The performers as make_sequence takes them, each in the materials Kei made from its look."""
    out = []
    for name, p in performers.items():
        mats = []
        if p["look"]:
            mats = run_script(client, "make_look.py", {"folder": folder, "performer": name,
                                                       "mesh": character["mesh"], "scalars": p["look"]})["materials"]
        out.append({"name": name, "offset_cm": p["offset_cm"], "yaw_deg": p["yaw_deg"], "materials": mats})
    return out


def _key(client: Claireon, seq: str, keys: list[dict], types: dict, frames: int, plan: dict, prev: str | None,
         performer: str) -> tuple[dict, list, str]:
    """Key one performer on the sequence: as a layer when the plan allows, else whole. (layer report, clipped,
    tangents)"""
    clipped, tangents = [], "set"
    layer = {"from": prev, **plan} if prev is not None and "full" not in plan else plan
    if "full" not in plan and plan["channels"]:
        got = run_script(client, "layer_keys.py", {"sequence": seq, "frames": frames, "channels": plan["channels"],
                                                   "performer": performer})
        if got.get("missing") or not got.get("collapsed"):
            layer = {"full": "the editor could not layer it (" + (", ".join(got.get("missing", [])[:4]) or
                                                                   "no merge") + "): keyed whole on the copy"}
    if "full" in layer:
        for batch in batches(keys, types):      # a batch of key frames in one call: one audit file, not one per frame
            got = run_script(client, "set_keys.py", {"sequence": seq, "keys": batch, "performer": performer})
            clipped += got.get("clipped", [])
            if str(got.get("tangents", "set")) != "set":
                tangents = got["tangents"]
    else:
        layer = {k: v for k, v in layer.items() if k != "channels"} | {"channels": len(plan["channels"])}
    return layer, clipped, tangents


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
    performers = performers_of(shot)
    others = {name: parse_keys(shot, rig, mode, name) for name in performers}
    frames = int(shot.get("frames") or max(k["f"] for k in [*keys, *(k for ks in others.values() for k in ks)]))
    fps = shot.get("fps") or 24
    types = {c["name"]: c["type"] for c in rig["controls"]}
    folder = kei_folder(shot_dir)
    plans = {"": _layer(shot_dir, pass_name, shot, keys, rig, types, mode, frames)}
    for name, ks in others.items():
        plans[name] = _layer(shot_dir, pass_name, shot, ks, rig, types, mode, frames, name)
    prev = plans[""][0]
    layered = prev is not None and all(pv == prev and "full" not in pl for pv, pl in plans.values())
    if not layered:     # one performer keyed whole means a fresh sequence: a copy would keep its old keys
        plans = {name: (None, pl if "full" in pl else {"full": "another performer is keyed whole in this pass"})
                 for name, (_, pl) in plans.items()}
    looks = _looks(client, folder, character, performers)
    if layered:
        from kei.apps.unreal_readback import pass_sequence
        seq = new_sequence(client, shot_dir, pass_name, character, fps, frames,
                           copy_from=pass_sequence(shot_dir, prev), performers=looks)
    else:
        seq = new_sequence(client, shot_dir, pass_name, character, fps, frames, performers=looks)
    tick()                                  # the editor spawns the character one tick after the sequence opens
    before = run_script(client, "dirty.py", {})["dirty"]
    layer, clipped, tangents = _key(client, seq, keys, types, frames, plans[""][1], plans[""][0], "")
    keyed_others = {}
    for name, ks in others.items():
        if not ks:
            keyed_others[name] = {"keys": 0, "layer": {"full": "no keys: the performer stands in its rest pose"}}
            continue
        lay, clip, tan = _key(client, seq, ks, types, frames, plans[name][1], plans[name][0], name)
        clipped += [dict(c, performer=name) for c in clip]
        tangents = tan if tan != "set" else tangents
        keyed_others[name] = {"keys": len(ks), "layer": lay}
    after = run_script(client, "dirty.py", {})["dirty"]
    check_dirty(before, after, folder)     # a user asset Kei made dirty: nothing is saved, the shot stops
    saved = run_script(client, "save_asset.py", {"path": seq})
    report = {"target": "open", "sequence": seq, "mode": mode, "keys": len(keys), "clipped": clipped,
              "tangents": tangents, "layer": layer, "saved": saved["saved"], "claireon": client.info, "frames": frames, "fps": fps,
              "said": (f"Kei keyed {len(keys)} frames of {character['name']}'s Control Rig in {seq}" if "full" in layer
                       else f"Kei layered {layer['channels']} changed channel(s) of {character['name']}'s Control Rig "
                            f"on {layer['from']} ({layer['keys']} keys), merged down in {seq}")}
    if performers:
        report["performers"] = {name: {**keyed_others[name], "offset_cm": performers[name]["offset_cm"],
                                       "yaw_deg": performers[name]["yaw_deg"],
                                       "materials": next(lk["materials"] for lk in looks if lk["name"] == name)}
                                for name in performers}
        report["said"] += "; with " + ", ".join(f"{n} ({keyed_others[n]['keys']} frames)" for n in performers)
    out.mkdir(parents=True, exist_ok=True)
    (out / "unreal_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report
