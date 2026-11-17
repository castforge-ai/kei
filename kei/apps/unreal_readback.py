"""Read the motion Kei keyed in Unreal back, in metres with Y up, so every check runs on what the rig gives.

read_back(client, shot_dir, pass_name, character, mode) -> Path of out_<pass>/joints.json
  Opens Kei's sequence for the pass in Sequencer (one call), waits one editor tick, then one eval_rig call returns the
  world position of each rig bone on every frame, in RIG space (centimetres, Z up). The editor does not need to
  tick or scrub for that: a scrubbed actor's bones stop updating when the editor is in the background, so Kei never
  reads them. The result may be large, so it comes through a result file (kei.apps.unreal.run_script). Positions are
  converted by kei.apps.unreal_units with the character's frame (which way it faces, from the rig's rest pose, kept
  in rig/unreal_rig.json). The points the checks use that are not bones (head top, hand and toe tips, heels) are
  derived from the bones, and the centre of mass is Kei's own. joints.json says "source": "unreal", the frame, and
  names the derived points, so a check never reads them as measured. kei check runs on it as on a Maya pass.
  The fingers and toes come back in the same call (kei.apps.unreal_detail): their positions go in joints.json under
  "detail" on each frame (never in "joints", which the body checks read), and their curl and lift, with flags for a
  finger bent backward or toes pressed into the floor, go to out_<pass>/hands_toes.json.
  A second performer (shot.json "performers") is read the same way and stands where the sequence puts it (its
  offset and yaw from the character's place): its joints go on each frame under "performers" {name: joints}, which
  the renders draw and the body checks do not read.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from kei.apps.unreal import Claireon, UnrealError, run_script, tick
from kei.apps.unreal_rig import load_rig, sequences
from kei.apps.unreal_detail import DETAIL_BONES, measure as measure_detail
from kei.apps.unreal_units import Frame, MANNEQUIN, frame_from_rest, ue_to_kei
from kei.rig import BONES, com
from kei.sample import ShotError, read_json

DERIVED = ("head_top", "hand_l_tip", "hand_r_tip", "ball_l_tip", "ball_r_tip", "heel_l", "heel_r")
# Offsets (metres) for the points no bone gives, as a human foot and hand: documented here, listed in joints.json.
HEAD_TOP_M, HAND_TIP_M, BALL_TIP_M, HEEL_BACK_M, ANKLE_M = 0.17, 0.08, 0.07, 0.06, 0.08


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _unit(v, fallback=(0.0, 0.0, 1.0)):
    n = math.sqrt(sum(c * c for c in v))
    return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-9 else fallback


def _along(p, v, d):
    return (p[0] + v[0] * d, p[1] + v[1] * d, p[2] + v[2] * d)


def joints_from_bones(bones_cm: dict, frame: Frame = MANNEQUIN) -> dict:
    """One frame: the bones in Unreal centimetres to Kei's joints in metres, with the derived points and the centre
    of mass. Raises ShotError naming the bones the character lacks."""
    j = {n: ue_to_kei(tuple(bones_cm[n]), frame) for n in BONES if n in bones_cm}
    missing = [n for n in BONES if n not in j]
    if missing:
        raise ShotError("the character has no bone named " + ", ".join(missing[:6]) + ": Kei reads the Unreal "
                        "mannequin's bone names (pelvis, spine_01, thigh_l, foot_l, ball_l ...)")
    j["head_top"] = _along(j["head"], _unit(_sub(j["head"], j["neck_02"]), (0.0, 1.0, 0.0)), HEAD_TOP_M)
    for s in "lr":
        j[f"hand_{s}_tip"] = _along(j[f"hand_{s}"], _unit(_sub(j[f"hand_{s}"], j[f"lowerarm_{s}"])), HAND_TIP_M)
        step = _sub(j[f"ball_{s}"], j[f"foot_{s}"])
        j[f"ball_{s}_tip"] = _along(j[f"ball_{s}"], _unit(step), BALL_TIP_M)
        fwd = _unit((step[0], 0.0, step[2]))
        foot = j[f"foot_{s}"]
        j[f"heel_{s}"] = (foot[0] - fwd[0] * HEEL_BACK_M, foot[1] - ANKLE_M, foot[2] - fwd[2] * HEEL_BACK_M)
    j["com"] = com(j)
    return j


def _placed(p_cm, offset_cm, yaw_deg):
    """A performer's rig-space point where the sequence stands it: turned by its yaw, moved by its offset (cm)."""
    a = math.radians(yaw_deg)
    x, y, z = p_cm
    return (x * math.cos(a) - y * math.sin(a) + offset_cm[0], x * math.sin(a) + y * math.cos(a) + offset_cm[1],
            z + offset_cm[2])


def pass_sequence(shot_dir: Path, pass_name: str) -> str:
    made = sequences(shot_dir).get(pass_name)
    if not made:
        raise ShotError(f"no Unreal sequence for {pass_name}: run kei unreal key {shot_dir} {pass_name} first")
    return made[-1]


def read_back(client: Claireon, shot_dir: Path, pass_name: str, character: str, mode: str | None = None) -> Path:
    shot_dir = Path(shot_dir)
    out = shot_dir / f"out_{pass_name}"
    shot = read_json(out / "shot.json", "shot")
    seq = pass_sequence(shot_dir, pass_name)
    last = int(shot.get("frames") or max(int(k["f"]) for k in shot["keys"]))
    run_script(client, "open_sequence.py", {"sequence": seq})
    tick()                                  # the sequence's rig must be live before it is read
    got = run_script(client, "eval_rig.py", {"sequence": seq, "bones": list(BONES) + list(DETAIL_BONES),
                                             "frames": list(range(last + 1))})
    rig = load_rig(shot_dir) or {}
    if rig.get("frame"):
        frame = Frame.from_dict(rig["frame"])
    elif "thigh_l" in got.get("rest", {}) and "thigh_r" in got.get("rest", {}):
        frame = frame_from_rest(tuple(got["rest"]["thigh_l"]), tuple(got["rest"]["thigh_r"]))
    else:
        raise UnrealError("Kei cannot tell which way the character faces: the rig read returned no rest pose of "
                          "the thighs")
    frames, detail = [], []
    kei = lambda bones: {n: ue_to_kei(tuple(p), frame) for n, p in bones.items() if n in DETAIL_BONES or n in BONES}
    for f in range(last + 1):
        bones = got["frames"].get(str(f))
        if bones is None:
            raise UnrealError(f"the editor returned no frame {f}: run the shot again")
        j = joints_from_bones(bones, frame)
        row = {"f": f, "joints": {n: [round(c, 6) for c in p] for n, p in j.items()}}
        extra = {n: [round(c, 6) for c in ue_to_kei(tuple(p), frame)] for n, p in bones.items() if n in DETAIL_BONES}
        if extra:
            row["detail"] = extra
            detail.append({"f": f, "bones": kei(bones)})
        frames.append(row)
    from kei.apps.unreal_keys import performers_of
    for name, perf in performers_of(shot).items():
        other = run_script(client, "eval_rig.py", {"sequence": seq, "bones": list(BONES), "performer": name,
                                                   "frames": list(range(last + 1))})
        for row in frames:
            bones = other["frames"].get(str(row["f"]))
            if bones is None:
                raise UnrealError(f"the editor returned no frame {row['f']} of {name}: run the shot again")
            moved = {b: _placed(tuple(pt), perf["offset_cm"], perf["yaw_deg"]) for b, pt in bones.items()}
            row.setdefault("performers", {})[name] = {n: [round(c, 6) for c in pt]
                                                      for n, pt in joints_from_bones(moved, frame).items()}
    mode = mode or ("step" if pass_name == "blocking" else "spline")
    dst = out / "joints.json"
    dst.write_text(json.dumps({"source": "unreal", "fps": shot.get("fps") or 24, "mode": mode,
                               "character": character, "frame": frame.as_dict(), "derived": list(DERIVED),
                               "skipped_control_types": got.get("skipped", {}), "frames": frames}),
                   encoding="utf-8")
    if detail:
        report = measure_detail(detail, kei(got.get("rest") or {}))
        (out / "hands_toes.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return dst
