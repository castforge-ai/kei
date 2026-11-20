"""Matched IK/FK switching on the character's Control Rig in Unreal (kei unreal switch).

switch(client, shot_dir, pass_name, limb, to, frame) -> dict
  limb: arm_l, arm_r, leg_l or leg_r (the rig's <limb>_fk_ik_switch, true for IK). In the open editor, on the pass's
  own sequence, match_switch.py places the new mode's controls where the limb's bones are at that frame and measures
  what the switch would move. When the gap is under MATCH_CM, Kei writes the switch into out_<pass>/shot.json: the
  frame before holds the old mode (the switch keyed at its old value), and the frame keys the switch and the new
  mode's controls, stepped. Then kei unreal key <shot> <pass> keys it and reads the joints back for the checks.
  A gap over MATCH_CM writes nothing and says how far it was.
"""
from __future__ import annotations

import json
from pathlib import Path

from kei.apps.unreal import UnrealError, run_script, tick
from kei.apps.unreal_readback import pass_sequence
from kei.sample import ShotError, read_json

MATCH_CM = 0.5
LIMBS = ("arm_l", "arm_r", "leg_l", "leg_r")


def _merge(keys: list[dict], f: int, channels: dict) -> None:
    k = next((k for k in keys if k.get("f") == f), None)
    if k is None:
        keys.append({"f": f, "tangent": "step", **channels})
    else:
        k.update(channels)


def switch(client, shot_dir: Path, pass_name: str, limb: str, to: str, frame: int) -> dict:
    if limb not in LIMBS:
        raise ShotError(f"--limb is one of {', '.join(LIMBS)}, not {limb!r}")
    if to not in ("ik", "fk"):
        raise ShotError(f"--to is ik or fk, not {to!r}")
    shot_dir = Path(shot_dir)
    src = shot_dir / f"out_{pass_name}" / "shot.json"
    shot = read_json(src, "shot")
    seq = pass_sequence(shot_dir, pass_name)
    run_script(client, "open_sequence.py", {"sequence": seq})
    tick()
    got = run_script(client, "match_switch.py", {"sequence": seq, "frame": int(frame), "limb": limb, "to": to})
    if got.get("error"):
        raise UnrealError(f"the switch match failed in the editor: {str(got['error'])[-300:]}")
    gap = float(got["gap_cm"])
    report = {"limb": limb, "to": to, "frame": frame, "gap_cm": gap, "was": "ik" if got.get("was_ik") else "fk"}
    if report["was"] == to:
        report["written"] = False
        report["why"] = f"{limb} is already {to.upper()} at f{frame}"
        return report
    if gap > MATCH_CM:
        report["written"] = False
        report["why"] = f"the switch would move the limb {gap:.2f} cm (more than {MATCH_CM} cm): nothing written"
        return report
    sw = f"{limb}_fk_ik_switch"
    keys = shot.setdefault("keys", [])
    def flat(by_control: dict) -> dict:
        return {f"{c}.{ch}": round(v, 4) if isinstance(v, float) else v
                for c, vals in by_control.items() for ch, v in vals.items() if not ch.startswith("scale") or c == sw}
    hold = got.get("hold") or {}
    if frame > 0:      # the frame before: the old mode, pinned as it played when the match was measured
        _merge(keys, frame - 1, {f"{sw}.value": to != "ik", **flat(hold.get(str(frame - 1), {}))})
    _merge(keys, frame, {**flat(hold.get(str(frame), {})), **flat(got["values"])})
    keys.sort(key=lambda k: k["f"])
    src.write_text(json.dumps(shot, indent=1), encoding="utf-8")
    report["written"] = True
    report["controls"] = sorted(c for c in got["values"] if c != sw)
    return report
