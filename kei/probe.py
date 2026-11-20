"""kei probe: read a pass frame by frame, in place of a one-off script.

  kei probe <shot> <pass> --frames 140-155 --joints elbow_l,hand_l,com

For each frame in the range and each name asked:
  a bend   elbow_l, elbow_r, knee_l, knee_r: the joint's bend in degrees (0 straight), measured as kei check does,
           and its change from the frame before.
  a joint  any joint of the rig (hand_l, pelvis, head, com...): its position in metres and how far it moved from the
           frame before (a jump shows as a large move on one frame).
Every row also gives each foot's contact (a sole point at or under kei check's CONTACT_H) and the objects' holders.
It reads only: it never changes a key.
"""
from __future__ import annotations

import math
from pathlib import Path

from kei.body_check import CHARACTER_BASE, CONTACT_H, SOLE, _angle, _hull, _sub, outside
from kei.objects import palm, surface_gap
from kei.sample import bake, check_shot, read_json

BENDS = {f"{part}_{s}": (a.format(s=s), b.format(s=s), c.format(s=s))
         for s in "lr" for part, (a, b, c) in (("elbow", ("upperarm_{s}", "lowerarm_{s}", "hand_{s}")),
                                                ("knee", ("thigh_{s}", "calf_{s}", "foot_{s}")))}


class ProbeError(ValueError):
    pass


def _name_kind(n: str):
    """What a probe name asks for: (kind, argument)."""
    if n in BENDS:
        return "bend", n
    if n == "com_margin":
        return "com_margin", None
    if n.startswith("ch:"):
        return "channel", n[3:]
    if n.startswith("palm_gap:"):
        return "palm_gap", n[len("palm_gap:"):]
    if "@" in n:
        part, _, base = n.partition("@")
        return "rel", (part, base)
    return "joint", n


def parse_frames(text: str, last: int) -> list[int]:
    """'140-155', '150' or '140-155,160' to frame numbers inside 0..last."""
    out = []
    for part in str(text).split(","):
        part = part.strip()
        try:
            a, _, b = part.partition("-")
            lo, hi = int(a), int(b) if b else int(a)
        except ValueError:
            raise ProbeError(f"--frames: {part!r} is not a frame or a range like 140-155") from None
        if lo > hi or lo < 0 or hi > last:
            raise ProbeError(f"--frames: {part} is outside the pass's frames 0-{last}")
        out += range(lo, hi + 1)
    return sorted(set(out))


def probe(shot_dir: Path, pass_name: str, frames_text: str, names: list[str], character: str | None = None,
          mode: str | None = None) -> dict:
    """The probe table (see the module docstring) as {"frames": [...], "rows": [{"f", <name>: {...}, ...}]}."""
    from kei.characters import load_character, on_character, shot_character
    from kei.objects import read_objects, track
    src = Path(shot_dir) / f"out_{pass_name}" / "shot.json"
    if not src.is_file():
        raise ProbeError(f"no {src}: write the pass's keys there first")
    shot = read_json(src, "shot")
    check_shot(shot)
    ch = load_character(shot_character(shot_dir, shot, character or "kei"))
    shot = on_character(shot, ch)
    mode = mode or ("step" if pass_name == "blocking" else "spline")
    frames = bake(shot, mode)
    wanted = parse_frames(frames_text, len(frames) - 1)
    joints0 = frames[0]["joints"]
    objects = {o["name"]: o for o in read_objects(shot)}
    pose0 = frames[0].get("pose") or {}
    for n in names:
        kind, arg = _name_kind(n)
        ok = {"bend": n in BENDS, "joint": n in joints0, "com_margin": True,
              "rel": all(p in joints0 for p in arg) if kind == "rel" else False,
              "channel": arg in pose0 if kind == "channel" else False,
              "palm_gap": arg in objects if kind == "palm_gap" else False}[kind]
        if not ok:
            raise ProbeError(f"{n!r} is no joint and no bend, nor anything else kei probe reads; bends: {', '.join(BENDS)}; joints: e.g. "
                             f"hand_l, pelvis, head, com; also com_margin, <joint>@<joint> (hand_l@spine_03), "
                             f"ch:<channel> (a rig channel), palm_gap:<object>")
    contact_h = CONTACT_H * ch.height / CHARACTER_BASE
    tracks = {name: track(o, frames) for name, o in objects.items()}
    fps = float(shot.get("fps") or 24)

    def bend(j, n):
        a, b, c = BENDS[n]
        return 180.0 - _angle(_sub(j[a], j[b]), _sub(j[c], j[b]))
    rows = []
    for f in wanted:
        j = frames[f]["joints"]
        prev = frames[f - 1]["joints"] if f > 0 else None
        row = {"f": f}
        nxt = frames[f + 1]["joints"] if f + 1 < len(frames) else None
        for n in names:
            kind, arg = _name_kind(n)
            if kind == "bend":
                v = bend(j, n)
                row[n] = {"bend_deg": round(v, 1),
                          "change_deg": round(v - bend(prev, n), 1) if prev else None}
            elif kind == "joint":
                p = j[n]
                speed = math.dist(p, prev[n]) * fps if prev else None
                accel = None
                if prev and nxt:
                    acc = [(nxt[n][i] - 2 * p[i] + prev[n][i]) * fps * fps for i in range(3)]
                    accel = round(math.sqrt(sum(a * a for a in acc)) / 9.81, 2)
                row[n] = {"pos_m": [round(x, 4) for x in p],
                          "moved_m": round(math.dist(p, prev[n]), 4) if prev else None,
                          "speed_mps": round(speed, 3) if speed is not None else None, "accel_g": accel}
            elif kind == "rel":
                part, base = arg
                row[n] = {"offset_m": [round(j[part][i] - j[base][i], 4) for i in range(3)]}
            elif kind == "channel":
                row[n] = {"value": (frames[f].get("pose") or {}).get(arg)}
            elif kind == "palm_gap":
                c = tracks[arg][f][0]
                row[n] = {s: round(surface_gap(objects[arg], c, palm(j, s)), 4) for s in "lr"}
            else:   # com_margin: how far the centre of mass, on the ground, is outside the support (0 inside)
                pts = [(j[q.format(s=s)][0], j[q.format(s=s)][2]) for s in "lr" for q in SOLE
                       if j[q.format(s=s)][1] <= contact_h]
                row[n] = {"outside_m": round(outside((j["com"][0], j["com"][2]), _hull(pts)), 4) if pts else None}
        row["contact"] = {s: any(j[q.format(s=s)][1] <= contact_h for q in SOLE) for s in "lr"}
        if tracks:
            row["objects"] = {name: t[f][1] for name, t in tracks.items()}
        rows.append(row)
    return {"tool": "kei probe", "pass": pass_name, "mode": mode, "character": ch.name, "names": names,
            "rows": rows}


def format_table(table: dict) -> str:
    """The table as text lines, one per frame."""
    lines = [f"character: {table['character']}, pass: {table['pass']}, mode: {table['mode']}"]
    for r in table["rows"]:
        cells = [f"f{r['f']}"]
        for n in table["names"]:
            c = r[n]
            if "bend_deg" in c:
                ch = "" if c["change_deg"] is None else f" ({c['change_deg']:+.1f})"
                cells.append(f"{n} {c['bend_deg']:.1f} deg{ch}")
            elif "pos_m" in c:
                mv = "" if c["moved_m"] is None else f" moved {c['moved_m']:.3f}"
                sp = "" if c.get("speed_mps") is None else f" {c['speed_mps']:.2f} m/s"
                ac = "" if c.get("accel_g") is None else f" {c['accel_g']:.1f} g"
                cells.append(f"{n} ({', '.join(f'{x:.3f}' for x in c['pos_m'])}){mv}{sp}{ac}")
            elif "offset_m" in c:
                cells.append(f"{n} ({', '.join(f'{x:+.3f}' for x in c['offset_m'])})")
            elif "value" in c:
                v = c["value"]
                cells.append(f"{n} " + (", ".join(f"{x:.3f}" for x in v) if isinstance(v, (list, tuple))
                                        else f"{v:.3f}" if isinstance(v, (int, float)) else str(v)))
            elif "outside_m" in c:
                cells.append(f"{n} " + ("airborne" if c["outside_m"] is None else
                                        "inside" if c["outside_m"] == 0 else f"{c['outside_m']:.3f} m out"))
            else:
                cells.append(f"{n} palms l {c['l']:.3f} r {c['r']:.3f} m")
        cells.append("feet " + "".join(s.upper() if on else "-" for s, on in r["contact"].items()))
        if r.get("objects"):
            cells.append(", ".join(f"{n}: {h or 'free'}" for n, h in r["objects"].items()))
        lines.append(" | ".join(cells))
    return "\n".join(lines)
