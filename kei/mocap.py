"""Motion capture as measured reference, never traced into keys.

read_bvh(path) -> Bvh: the skeleton (names, parents, offsets, channels), the frame time and the channel values.
world_positions(bvh) -> [{joint: (x, y, z)}] per frame, in the file's own units, y up (forward kinematics with each
  joint's own rotation order).
to_bones(bvh, units) -> [{mannequin bone: [x, y, z] cm, z up}] per frame. The file's joints are matched to the Unreal
  mannequin's bones by name (CMU, Mixamo, Rokoko and most others: Hips, LeftUpLeg, LeftLeg, LeftFoot, LeftToeBase,
  Spine, Neck, Head, LeftShoulder, LeftArm, LeftForeArm, LeftHand, with or without a "mixamorig:" style prefix). The
  five spine bones are spread along the file's spine chain. The floor is put under the lowest ankle of the clip.
  A bone Kei needs and the file lacks is a MocapError that names it.
import_reference(shot, path, licence, source, units, name) -> dict
  Writes <shot>/refs/mocap/<name>/: joints.json (Kei's joints per frame, metres), measures.json (what kei check
  measures on it, the root's bob and travel, each foot's contact frames), sheet.png (eight frames of the clip drawn
  in four views), SOURCE.md (the file, its licence and source as you gave them, the frame rate, the units, the bone
  map) and REF_ROW.md (a row for REFS.md). The keys are never made from it: it is a reference to measure against.
  Kei refuses a file with no licence stated.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from kei.rig import BONES


class MocapError(ValueError):
    """The capture cannot be read or matched to Kei's bones. The message says why and what to do."""


@dataclass
class Joint:
    name: str
    parent: int
    offset: tuple
    channels: list = field(default_factory=list)
    end: tuple | None = None      # the End Site offset, when the joint has one


@dataclass
class Bvh:
    joints: list
    frame_time: float
    motion: list     # one list of floats per frame


def read_bvh(path: Path) -> Bvh:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise MocapError(f"cannot read {path}: {e.strerror or e}") from e
    tokens = text.split()
    if not tokens or tokens[0] != "HIERARCHY":
        raise MocapError(f"{Path(path).name} is not a BVH file (it does not start with HIERARCHY)")
    joints: list[Joint] = []
    stack: list[int] = []
    i = 1
    try:
        while tokens[i] != "MOTION":
            t = tokens[i]
            if t in ("ROOT", "JOINT"):
                joints.append(Joint(tokens[i + 1], stack[-1] if stack else -1, ()))
                i += 2
            elif t == "End":
                i += 2           # End Site
                if tokens[i] != "{" or tokens[i + 1] != "OFFSET":
                    raise MocapError("an End Site has no OFFSET")
                joints[stack[-1]].end = tuple(float(x) for x in tokens[i + 2:i + 5])
                i += 6           # {, OFFSET, x, y, z, }
            elif t == "{":
                stack.append(len(joints) - 1)
                i += 1
            elif t == "}":
                stack.pop()
                i += 1
            elif t == "OFFSET":
                joints[stack[-1]].offset = tuple(float(x) for x in tokens[i + 1:i + 4])
                i += 4
            elif t == "CHANNELS":
                n = int(tokens[i + 1])
                joints[stack[-1]].channels = tokens[i + 2:i + 2 + n]
                i += 2 + n
            else:
                raise MocapError(f"unexpected {t!r} in the BVH hierarchy")
        i += 1
        if tokens[i] != "Frames:":
            raise MocapError("the MOTION part has no Frames: line")
        n_frames = int(tokens[i + 1])
        if tokens[i + 2] != "Frame" or tokens[i + 3] != "Time:":
            raise MocapError("the MOTION part has no Frame Time: line")
        frame_time = float(tokens[i + 4])
        i += 5
    except (IndexError, ValueError) as e:
        raise MocapError(f"{Path(path).name} is not a BVH Kei can read: {e}") from e
    per = sum(len(j.channels) for j in joints)
    values = [float(x) for x in tokens[i:i + per * n_frames]]
    if len(values) < per * n_frames or not n_frames:
        raise MocapError(f"{Path(path).name} says {n_frames} frames but holds fewer values")
    if not (frame_time > 0):
        raise MocapError("the frame time must be above 0")
    motion = [values[f * per:(f + 1) * per] for f in range(n_frames)]
    return Bvh(joints, frame_time, motion)


def _rot(axis: str, deg: float):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    if axis == "X":
        return ((1, 0, 0), (0, c, -s), (0, s, c))
    if axis == "Y":
        return ((c, 0, s), (0, 1, 0), (-s, 0, c))
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def _mul(a, b):
    return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)) for r in range(3))


def _apply(m, v):
    return tuple(sum(m[r][k] * v[k] for k in range(3)) for r in range(3))


def world_positions(bvh: Bvh) -> list[dict]:
    out = []
    ident = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    for row in bvh.motion:
        pos, rot = {}, {}
        k = 0
        for idx, j in enumerate(bvh.joints):
            local_t = list(j.offset) if j.offset else [0.0, 0.0, 0.0]
            m = ident
            for ch in j.channels:
                v = row[k]
                k += 1
                if ch.endswith("position"):
                    local_t["XYZ".index(ch[0])] = v if j.parent < 0 else local_t["XYZ".index(ch[0])] + v
                else:
                    m = _mul(m, _rot(ch[0], v))
            if j.parent < 0:
                rot[idx], pos[j.name] = m, tuple(local_t)
            else:
                pm = rot[j.parent]
                pp = pos[bvh.joints[j.parent].name]
                d = _apply(pm, local_t)
                pos[j.name] = (pp[0] + d[0], pp[1] + d[1], pp[2] + d[2])
                rot[idx] = _mul(pm, m)
            if j.end is not None:
                d = _apply(rot[idx], j.end)
                p = pos[j.name]
                pos[j.name + "_end"] = (p[0] + d[0], p[1] + d[1], p[2] + d[2])
        out.append(pos)
    return out


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.split(":")[-1].lower())


SIDES = {"l": ("left", "l"), "r": ("right", "r")}
PARTS = {  # mannequin bone stem -> name stems the files use (after the side word is taken off)
    "thigh": ("upleg", "thigh", "hip", "upperleg"),
    "calf": ("leg", "shin", "knee", "lowerleg", "calf"),
    "foot": ("foot", "ankle"),
    "ball": ("toebase", "toe", "toes", "ball"),
    "clavicle": ("shoulder", "collar", "clavicle"),
    "upperarm": ("arm", "uparm", "upperarm"),
    "lowerarm": ("forearm", "elbow", "lowerarm"),
    "hand": ("hand", "wrist"),
}
SPINE = ("spine", "spine1", "spine2", "spine3", "spine4", "chest", "upperchest", "chest1", "chest2", "abdomen", "torso")


def _side_of(k: str) -> tuple[str | None, str]:
    for s, words in SIDES.items():
        for w in words:
            if k.startswith(w) and len(k) > len(w):
                return s, k[len(w):]
            if k.endswith(w) and len(k) > len(w) and w != "l" and w != "r":
                return s, k[:-len(w)]
    return None, k


def bone_map(names: list[str]) -> dict[str, str]:
    """Mannequin bone -> the file's joint name, for every bone Kei can match (spine bones are spread later)."""
    found: dict[str, str] = {}
    keys = {n: _key(n) for n in names}
    for n, k in keys.items():
        if k in ("hips", "hip", "pelvis", "root") and "pelvis" not in found:
            found["pelvis"] = n
        elif k in ("neck", "neck1", "neck01") and "neck_01" not in found:
            found["neck_01"] = n
        elif k in ("head",) and "head" not in found:
            found["head"] = n
    for n, k in keys.items():
        side, rest = _side_of(k)
        if side is None:
            continue
        for bone, stems in PARTS.items():
            if rest in stems and f"{bone}_{side}" not in found:
                if bone == "thigh" and rest == "hip" and any(_side_of(x)[1] == "upleg" for x in keys.values()):
                    continue      # CMU: LHipJoint is not the thigh when LeftUpLeg exists
                found[f"{bone}_{side}"] = n
    return found


def _lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


UNITS = {"cm": 1.0, "m": 100.0, "in": 2.54, "mm": 0.1, "cmu": 2.54 / 0.45}   # cmu: the CMU database, 1/0.45 inch


def guess_units(frames: list[dict], head: str, feet: list[str]) -> str:
    h = frames[0][head][1] - min(frames[0][f][1] for f in feet)
    for unit, lo, hi in (("m", 0.8, 2.6), ("cmu", 15, 31), ("in", 32, 100), ("cm", 80, 260), ("mm", 800, 2600)):
        if lo <= h <= hi:
            return unit
    raise MocapError(f"the skeleton is {h:.1f} file units from foot to head, which reads as no unit Kei knows: "
                     "give --units cm, m, in, mm or cmu")


def to_bones(bvh: Bvh, units: str | None = None) -> tuple[list[dict], dict, str]:
    frames = world_positions(bvh)
    names = [j.name for j in bvh.joints]
    m = bone_map(names)
    if "neck_01" not in m:
        raise MocapError("the file has no Neck joint: Kei needs Hips, a spine, Neck, Head, both legs to the toes and "
                         "both arms to the hands")
    need = [b for b in BONES if b not in ("root", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_02")]
    missing = [b for b in need if b not in m]
    if missing:
        raise MocapError("Kei found no joint for " + ", ".join(missing) + " in the file (its joints: "
                         + ", ".join(names[:12]) + ("..." if len(names) > 12 else "") + ")")
    # the spine chain: the file's joints between the hips and the neck, in order
    chain, j = [], names.index(m["neck_01"])
    while bvh.joints[j].parent >= 0 and names[bvh.joints[j].parent] != m["pelvis"]:
        j = bvh.joints[j].parent
        chain.insert(0, names[j])
    unit = units or guess_units(frames, m["head"], [m["foot_l"], m["foot_r"]])
    if unit not in UNITS:
        raise MocapError(f"--units is one of {', '.join(UNITS)}, not {unit!r}")
    k = UNITS[unit]
    out = []
    for fr in frames:
        # BVH is right handed with y up; Unreal's space is left handed with z up: swap y and z, in centimetres
        z_up = {n: (p[0] * k, p[2] * k, p[1] * k) for n, p in fr.items()}
        b = {bone: z_up[n] for bone, n in m.items()}
        pts = [b["pelvis"], *[z_up[c] for c in chain], b["neck_01"]]
        lengths = [0.0]
        for a, c in zip(pts, pts[1:]):
            lengths.append(lengths[-1] + math.dist(a, c))
        total = lengths[-1] or 1.0
        for s in range(5):
            t = (s + 1) / 6 * total
            seg = next(i for i in range(1, len(lengths)) if lengths[i] >= t - 1e-9)
            u = (t - lengths[seg - 1]) / max(lengths[seg] - lengths[seg - 1], 1e-9)
            b[f"spine_0{s + 1}"] = _lerp(pts[seg - 1], pts[seg], u)
        b["neck_02"] = _lerp(b["neck_01"], b["head"], 0.5)
        b["root"] = (b["pelvis"][0], b["pelvis"][1], 0.0)
        out.append(b)
    skipped = 0
    while len(out) > 1 and _t_pose(out[0]):     # CMU and others start on a T-pose frame: it is no part of the motion
        out.pop(0)
        skipped += 1
    from kei.apps.unreal_readback import ANKLE_M
    lows = sorted(min(f["foot_l"][2], f["foot_r"][2]) for f in out)
    floor = lows[len(lows) // 20] - ANKLE_M * 100    # a low percentile, so one noisy frame does not set the floor
    for f in out:
        for bone, p in f.items():
            f[bone] = [p[0], p[1], p[2] - floor] if bone != "root" else [p[0], p[1], 0.0]
    mapping = {**m, "spine": ", ".join(chain) or "(none: spread from the hips to the neck)"}
    return out, mapping, unit, skipped


def _t_pose(b: dict) -> bool:
    """Both arms out level: each hand and elbow within 12 cm of its shoulder's height, and far out to the side."""
    for s in "lr":
        up, low, hand = b[f"upperarm_{s}"], b[f"lowerarm_{s}"], b[f"hand_{s}"]
        if abs(low[2] - up[2]) > 12 or abs(hand[2] - up[2]) > 12:
            return False
    return math.dist(b["hand_l"][:2], b["hand_r"][:2]) > 2.2 * math.dist(b["upperarm_l"][:2], b["upperarm_r"][:2])


def _contacts(frames: list[dict], s: str, fps: float) -> list[str]:
    """A foot is planted while its ankle is within 3 cm of its lowest height in the clip and it moves under 0.5 m/s."""
    hs = [fr["joints"][f"foot_{s}"][1] for fr in frames]
    base = sorted(hs)[len(hs) // 10]
    on = []
    for i, fr in enumerate(frames):
        a = fr["joints"][f"foot_{s}"]
        near = [frames[j]["joints"][f"foot_{s}"] for j in (i - 1, i + 1) if 0 <= j < len(frames)] or [a]
        speed = min(math.dist((a[0], a[2]), (b[0], b[2])) for b in near) * fps   # the slower side: a frame at lift-off is still down
        if hs[i] < base + 0.03 and speed < 0.5:
            on.append(i)
    filled = []
    for f in on:      # a break of 3 frames or less inside a contact is capture noise, not a lift
        if filled and 1 < f - filled[-1] <= 4:
            filled.extend(range(filled[-1] + 1, f))
        filled.append(f)
    on = filled
    runs, start, prev = [], None, None
    for f in on:
        if start is None:
            start = prev = f
        elif f == prev + 1:
            prev = f
        else:
            runs.append(f"f{start}-{prev}")
            start = prev = f
    if start is not None:
        runs.append(f"f{start}-{prev}")
    return runs


def import_reference(shot: Path, path: Path, licence: str, source: str = "", units: str | None = None,
                     name: str | None = None) -> dict:
    from kei.apps.unreal_readback import joints_from_bones
    from kei.apps.unreal_units import frame_from_rest
    from kei.render import draw_views, fit
    if not licence or not licence.strip():
        raise MocapError("say the capture's licence with --licence (for example \"CC0\" or \"CMU: free for any use\"): "
                         "Kei imports only capture you may use")
    shot, path = Path(shot), Path(path)
    if path.suffix.lower() != ".bvh":
        raise MocapError(f"{path.name}: Kei reads BVH capture; convert C3D marker data to BVH in your capture tool")
    bvh = read_bvh(path)
    bones, mapping, unit, skipped = to_bones(bvh, units)
    frame = frame_from_rest(tuple(bones[0]["thigh_l"]), tuple(bones[0]["thigh_r"]))
    frames = [{"f": i, "joints": joints_from_bones(b, frame)} for i, b in enumerate(bones)]
    fps = round(1.0 / bvh.frame_time, 3)
    height = max(fr["joints"]["head_top"][1] for fr in frames[:1])
    name = name or re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-") or "capture"
    out = shot / "refs" / "mocap" / name
    if out.exists():
        raise MocapError(f"{out} exists already: give another --name")
    out.mkdir(parents=True)
    from kei.body_check import measure
    from kei.characters import load_character
    ch = load_character("kei")
    report = measure({"fps": fps, "loop": False, "keys": []}, "spline", ch.proportions, height, frames)
    roots = [fr["joints"]["pelvis"] for fr in frames]
    seconds = (len(frames) - 1) / fps if len(frames) > 1 else 0.0
    travel = math.dist((roots[0][0], roots[0][2]), (roots[-1][0], roots[-1][2]))
    measures = {"frames": len(frames), "fps": fps, "seconds": round(seconds, 3), "height_m": round(height, 3),
                "pelvis_bob_cm": round((max(r[1] for r in roots) - min(r[1] for r in roots)) * 100, 1),
                "travel_m": round(travel, 3), "speed_m_s": round(travel / seconds, 3) if seconds else 0.0,
                "contacts": {"left": _contacts(frames, "l", fps), "right": _contacts(frames, "r", fps)},
                "skipped_t_pose_frames": skipped,
                "flags": [{k: v for k, v in f.items() if k in ("check", "frames", "measure", "value", "limit")}
                          for f in report["flags"]]}
    (out / "joints.json").write_text(json.dumps([{"f": fr["f"], "joints": {k: [round(c, 4) for c in v]
                                                                            for k, v in fr["joints"].items()}}
                                                 for fr in frames]), encoding="utf-8")
    (out / "measures.json").write_text(json.dumps(measures, indent=1), encoding="utf-8")
    picks = [round(i * (len(frames) - 1) / 7) for i in range(8)] if len(frames) > 1 else [0]
    bounds = fit([frames[i]["joints"] for i in picks])
    from kei.sheet import _Canvas
    from kei.characters.profile import decode_png
    size = 180
    sheet = _Canvas(4 * 2 * size, 2 * 2 * size)
    for n, i in enumerate(picks):
        w, h, rows = decode_png(draw_views(frames[i]["joints"], size, bounds[n], f"f{i}"))
        ox, oy = (n % 4) * 2 * size, (n // 4) * 2 * size
        for y in range(h):
            for x in range(w):
                sheet.dot(ox + x, oy + y, rows[y][x])
    (out / "sheet.png").write_bytes(sheet.png())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    src_lines = ["# Capture used as reference", "", f"- File: {path.name}", f"- Licence: {licence.strip()}",
                 f"- Source: {source.strip() or 'not given'}", f"- Imported: {now}", f"- Frame rate: {fps:g} fps",
                 f"- Units in the file: {unit}", f"- Frames: {len(frames)}", "",
                 "This capture is a measured stand-in reference. Its numbers inform the plan; the keys are never "
                 "traced from it.", "", "## Bone map (Kei's bone: the file's joint)", ""]
    src_lines += [f"- {b}: {n}" for b, n in sorted(mapping.items())]
    (out / "SOURCE.md").write_text("\n".join(src_lines) + "\n", encoding="utf-8", newline="\n")
    row = (f"| {name} | capture ({licence.strip()}) | measured motion: {measures['seconds']} s at {fps:g} fps, "
           f"pelvis bob {measures['pelvis_bob_cm']} cm, speed {measures['speed_m_s']} m/s | refs/mocap/{name}/"
           f"measures.json | measured |")
    (out / "REF_ROW.md").write_text("A row for the REFS.md table (Ref | Tier | What it gives | Our checks | "
                                    "Verdict):\n\n" + row + "\n", encoding="utf-8", newline="\n")
    return {"folder": out, "measures": measures, "unit": unit, "map": mapping, "skipped": skipped}
