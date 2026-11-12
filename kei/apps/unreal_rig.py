"""Read the character's Control Rig in the open editor, and the shared steps every Unreal pass needs.

read_rig(client, shot_dir, character) -> dict
  Makes Kei's own probe sequence under /Game/Kei/<shot>/ (the user's sequences are never opened for writing), reads
  every control (type, keyable channels, locked), probes each transform control by a small step to see which bones it
  moves, and puts every control back. Kei then compares each control's value after the probe with its value before
  (within 1e-4): a control that is not back stops the shot with needs_human, naming it. Writes rig/unreal_rig.json
  (what the animator keys from, in the units it states) and rig/unreal_rig.md (the same in words, for the Rig line of
  CHARACTER.md: the seat writes that file, Kei does not edit it).
new_sequence(client, shot_dir, pass_name, character, fps, frames, copy_from) -> the new sequence's asset path
  One new asset per attempt, LS_<shot>_<pass>_<n> under /Game/Kei/<shot>/, recorded in unreal/sequences.json. Kei never
  deletes and recreates a loaded asset: a name taken gets the next number.
check_dirty(before, after, folder) -> raises NeedsHuman for a package that became dirty outside Kei's folder.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from kei.apps.unreal import Claireon, NeedsHuman, UnrealError, one_line, run_script, tick
from kei.apps.unreal_units import frame_from_rest

TOLERANCE = 1e-4
KEI_ROOT = "/Game/Kei"


def shot_name(shot_dir: Path) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", Path(shot_dir).resolve().name) or "shot"
    return name if not name[0].isdigit() else "S_" + name


def kei_folder(shot_dir: Path) -> str:
    return f"{KEI_ROOT}/{shot_name(shot_dir)}"


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path


def sequences_path(shot_dir: Path) -> Path:
    return Path(shot_dir) / "unreal" / "sequences.json"


def sequences(shot_dir: Path) -> dict:
    """{pass_name: [asset path of each attempt, oldest first]}"""
    return _read(sequences_path(shot_dir), {})


def character_path(shot_dir: Path) -> Path:
    return Path(shot_dir) / "unreal" / "character.json"


def save_character(shot_dir: Path, character: dict) -> None:
    _write(character_path(shot_dir), character)


def load_character(shot_dir: Path) -> dict | None:
    return _read(character_path(shot_dir), None)


def new_sequence(client: Claireon, shot_dir: Path, pass_name: str, character: dict, fps: float, frames: int,
                 copy_from: str | None = None) -> str:
    book = sequences(shot_dir)
    made = book.get(pass_name, [])
    n = len(made) + 1
    for _ in range(8):
        name = f"LS_{shot_name(shot_dir)}_{pass_name}_{n}"
        try:
            out = run_script(client, "make_sequence.py", {
                "folder": kei_folder(shot_dir), "name": name, "fps": fps, "frames": int(frames),
                "mesh": character["mesh"], "control_rig": character["control_rig"], "copy_from": copy_from or ""})
        except UnrealError as e:
            if "already exists" in str(e):
                n += 1
                continue
            raise
        book.setdefault(pass_name, []).append(out["path"])
        _write(sequences_path(shot_dir), book)
        return out["path"]
    raise UnrealError(f"Kei could not find a free sequence name for {pass_name} under {kei_folder(shot_dir)}")


def check_dirty(before: list[str], after: list[str], folder: str) -> None:
    mine = folder.rstrip("/") + "/"
    stray = sorted(p for p in set(after) - set(before) if not p.startswith(mine))
    if stray:
        raise NeedsHuman(f"Kei made {stray[0]} dirty in your editor, and it is not Kei's: Kei saved nothing and "
                         "will not go on. In the editor, undo the change (Ctrl+Z) or close the asset without "
                         "saving, then run the shot again")


def _flatten(values: dict) -> dict:
    return {n: list(v) for n, v in values.items()}


def unrestored(before: dict, after: dict) -> list[str]:
    """The controls whose value after the probe differs from the value before it by more than the tolerance."""
    bad = []
    for name, b in _flatten(before).items():
        a = after.get(name)
        if a is None or len(a) != len(b) or any(abs(x - y) > TOLERANCE for x, y in zip(a, b)):
            bad.append(name)
    return bad


def rig_summary(rig: dict) -> str:
    kinds: dict[str, int] = {}
    for c in rig["controls"]:
        kinds[c["type"]] = kinds.get(c["type"], 0) + 1
    parts = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
    return (f"Rig: {rig['character']}'s Control Rig {rig['control_rig']} in Unreal, {len(rig['controls'])} keyable "
            f"controls ({parts}). Units: {rig['units']['length']}, {rig['units']['angle']}, Z up. "
            f"Probe: {rig['probe']}.\n")


def read_rig(client: Claireon, shot_dir: Path, character: dict, fps: float = 24, frames: int = 24) -> dict:
    shot_dir = Path(shot_dir)
    folder = kei_folder(shot_dir)
    seq = new_sequence(client, shot_dir, "rig", character, fps, frames)
    tick()
    dirty_before = run_script(client, "dirty.py", {})["dirty"]
    got = run_script(client, "read_rig.py", {"sequence": seq})
    bad = unrestored(got.get("before", {}), got.get("after", {}))
    if bad:
        raise NeedsHuman(f"the rig probe left the control {bad[0]} changed ({len(bad)} in all): in the editor, "
                         f"undo or reload the sequence {seq} without saving, then run the shot again")
    check_dirty(dirty_before, got.get("dirty", []), folder)
    controls = [{k: c[k] for k in ("name", "type", "channels", "locked", "limited", "moves") if k in c}
                for c in got.get("controls", [])]
    if not controls:
        raise NeedsHuman(f"the Control Rig {character['control_rig']} has no keyable controls: pick another "
                         "character, or animate on Kei's own rig")
    rest = got.get("rest") or {}
    frame = (frame_from_rest(tuple(rest["thigh_l"]), tuple(rest["thigh_r"])).as_dict()
             if "thigh_l" in rest and "thigh_r" in rest else None)
    rig = {"source": "unreal", "frame": frame, "character": character["name"], "mesh": character["mesh"],
           "control_rig": character["control_rig"], "units": got["units"], "bones": got.get("bones"),
           "probe": got.get("probe", "done"), "controls": controls, "claireon": client.info,
           "probe_sequence": seq}
    _write(shot_dir / "rig" / "unreal_rig.json", rig)
    save_character(shot_dir, {k: character[k] for k in ("name", "mesh", "control_rig")})
    (shot_dir / "rig" / "unreal_rig.md").write_text(rig_summary(rig), encoding="utf-8")
    return rig


def load_rig(shot_dir: Path) -> dict | None:
    return _read(Path(shot_dir) / "rig" / "unreal_rig.json", None)
