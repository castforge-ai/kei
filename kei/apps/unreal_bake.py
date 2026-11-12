"""Bake an approved Unreal shot to an animation asset in Kei's own folder, then check it bone by bone.

bake_shot(client, shot_dir, pass_name) -> dict
  Only on a shot at "done" (the author signed it off). Bakes Kei's sequence for the pass to
  /Game/Kei/<shot>/A_<shot>_<pass> with the recipe in BAKE.md: the delivery range (the last frame of a loop repeats
  frame 0, so a loop ends one frame sooner), then a copy-bones step so each ik_ bone follows its bone. Saves that
  asset only. Then reads the asset back and checks, on every frame, that every ik_ bone is where its bone is
  (BAKE_TOLERANCE_CM). A bone that lags is reported with the bone and the frame, and the asset is kept for the user to
  inspect. Writes out_<pass>/bake_report.json.
  SequencerTools.export_anim_sequence fails for Kei's spawnable (UE 5.8.3), so bake.py bakes in the Control Rig and
  writes the tracks through the animation's controller; the ik_ copy is done on the skeleton's reference pose ("ik_copy": "skeleton pose"). The
  sequence must be open in Sequencer, so Kei opens it and waits one tick first.
"""
from __future__ import annotations

import json
from pathlib import Path

from kei.apps.unreal import Claireon, UnrealError, run_script, tick
from kei.apps.unreal_rig import check_dirty, kei_folder, load_character, shot_name
from kei.apps.unreal_readback import pass_sequence
from kei.sample import ShotError, read_json
from kei.state import load_state

# BAKE.md: the UE mannequin names; another skeleton maps them. A pair whose ik_ bone the skeleton lacks is skipped.
PAIRS = (("foot_l", "ik_foot_l"), ("foot_r", "ik_foot_r"), ("hand_r", "ik_hand_gun"), ("hand_r", "ik_hand_r"),
         ("hand_l", "ik_hand_l"))
BAKE_TOLERANCE_CM = 0.1
IK_COPY = "skeleton pose"
CHUNK = 15


def lags(frames: dict, pairs=PAIRS, tolerance_cm: float = BAKE_TOLERANCE_CM) -> list[dict]:
    """[{"bone", "follows", "frame", "off_cm"}] for every ik_ bone that is further than the tolerance from its bone."""
    bad = []
    for f in sorted(frames, key=int):
        row = frames[f]
        for bone, ik in pairs:
            if bone in row and ik in row:
                d = sum((a - b) ** 2 for a, b in zip(row[bone], row[ik])) ** 0.5
                if d > tolerance_cm:
                    bad.append({"bone": ik, "follows": bone, "frame": int(f), "off_cm": round(d, 3)})
    return bad


def delivery_end(shot: dict) -> int:
    frames = int(shot.get("frames") or 0)
    return frames - 1 if shot.get("loop") and frames > 1 else frames


def bake_shot(client: Claireon, shot_dir: Path, pass_name: str) -> dict:
    shot_dir = Path(shot_dir)
    status = load_state(shot_dir).status
    if status != "done":
        raise ShotError(f"the bake is for an approved shot: this one is {status}. The author signs it off first "
                        "(kei approve), then run kei export again")
    out = shot_dir / f"out_{pass_name}"
    shot = read_json(out / "shot.json", "shot")
    character = load_character(shot_dir)
    if character is None:
        raise ShotError("this shot has no Unreal character recorded: it was not animated in Unreal")
    seq = pass_sequence(shot_dir, pass_name)
    end = delivery_end(shot)
    folder = kei_folder(shot_dir)
    before = run_script(client, "dirty.py", {})["dirty"]
    run_script(client, "open_sequence.py", {"sequence": seq})
    tick()
    done = None
    for n in range(1, 9):
        asset = f"{folder}/A_{shot_name(shot_dir)}_{pass_name}" + ("" if n == 1 else f"_{n}")
        try:
            done = run_script(client, "bake.py", {"sequence": seq, "asset": asset, "mesh": character["mesh"],
                                                  "end": end, "fps": shot.get("fps") or 24, "pairs": [list(p) for p in PAIRS]})
            break
        except UnrealError as e:
            if "already exists" not in str(e):
                raise
    if done is None:
        raise UnrealError(f"Kei could not find a free asset name for the bake of {pass_name} under {folder}")
    check_dirty(before, done.get("dirty", []), folder)
    bones = sorted({b for p in PAIRS for b in p})
    frames, missing = {}, set()
    for start in range(0, end + 1, CHUNK):
        got = run_script(client, "read_bake.py", {"asset": done["asset"], "bones": bones, "start": start,
                                                  "end": min(end, start + CHUNK - 1)})
        frames.update(got["frames"])
        missing |= set(got.get("missing", []))
    skipped = [list(p) for p in PAIRS if p[0] in missing or p[1] in missing]
    failures = lags(frames, [p for p in PAIRS if list(p) not in skipped])
    report = {"asset": done["asset"], "frames": done.get("frames"), "range": [0, end], "ik_copy": done.get("ik_copy"),
              "bones": done.get("bones"), "skipped_bones": done.get("skipped_bones"),
              "ok": not failures and done.get("ik_copy") == IK_COPY, "failures": failures[:50],
              "pairs_skipped": skipped, "claireon": client.info}
    out.mkdir(parents=True, exist_ok=True)
    (out / "bake_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def bake_lines(report: dict) -> list[str]:
    """The result in plain words, for the command line."""
    lines = [f"baked: {report['asset']} (frames 0 to {report['range'][1]})"]
    lines.append(f"{report['bones']} bones written ({report['skipped_bones']} helper bones of the rig are not in the "
                 "skeleton)")
    if report["ik_copy"] != IK_COPY:
        lines.append("the ik_ bones were not copied")
    for s in report["pairs_skipped"]:
        lines.append(f"not checked: the skeleton has no {s[1]}")
    for f in report["failures"][:10]:
        lines.append(f"{f['bone']} does not follow {f['follows']} on frame {f['frame']} ({f['off_cm']} cm off)")
    lines.append("every ik_ bone follows its bone on every frame" if report["ok"] else
                 "the bake did not pass its check; the asset is kept in the project for you to inspect")
    return lines
