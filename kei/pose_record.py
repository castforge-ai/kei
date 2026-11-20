"""kei poses: a fixed record of each key pose of a pass, and a pose sheet in four views.

The agent writes the creative half of a key in plan/plan.json: "function" (contact, down, passing, antic, apex...),
"kind" (key, extreme, breakdown), "intent" (one line: what the pose says) and "judged_in" (the view it was judged
in). Kei measures the physical half on the pass's shot.json, on the shot's character, and writes both into
out_<pass>/poses/poses.json, one record per key pose of the plan (a pass with no plan: per key of its shot.json):

  planted          each foot: a sole point (heel, ball or toe tip) at or under kei check's CONTACT_H.
  support          "both", "left", "right" or "none" (airborne).
  weight_side      the foot the centre of mass, dropped to the ground, sits nearer: "left", "right", or "between"
                   when the two distances differ by less than BETWEEN of their sum. One foot down: that foot.
  com              {"inside": bool, "outside_m": d}: the centre of mass against the support outline, with kei check's
                   balance tolerance. None when airborne. A held object's mass_kg is in the centre of mass, and a
                   grounded object the hands press on is part of the support (kei.objects.with_loads).
  line_of_action   the pelvis-to-head line's lean from vertical in degrees: "side" (+ forward, along z) and "front"
                   (+ toward the character's left, along x).
  hip_height_m     the pelvis's height.
  objects          each object of the shot (kei.objects): who holds it on that frame ("hand_l", "hand_r", "hands")
                   or null.

out_<pass>/poses/pose_sheet.png draws each key in four views (side, three quarter, front, back), a row per key, with
its frame, function and the measured facts printed under it. The critics read the records and the sheet: measured
facts, not prose. The free-text "note" in plan.json stays: it carries the acting.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from kei.body_check import BALANCE_TOL, CHARACTER_BASE, CONTACT_H, SOLE, _hull, outside
from kei.sample import bake, check_shot, normalize_keys, read_json

BETWEEN = 0.2          # share of the two feet's distances: closer than this, the weight sits between the feet
PANEL = 200            # pixels per view panel on the pose sheet
FACT_ROWS = 3          # text lines of measured facts under each row
ROW_TEXT = 14          # pixels per text line
SIDE = {"l": "left", "r": "right"}
CREATIVE = ("function", "kind", "intent", "judged_in")


class PoseRecordError(ValueError):
    pass


def _plan_keys(shot_dir: Path) -> dict[int, dict]:
    p = Path(shot_dir) / "plan" / "plan.json"
    if not p.is_file():
        return {}
    try:
        plan = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    keys = plan.get("keys") if isinstance(plan, dict) else None
    out = {}
    for k in keys if isinstance(keys, list) else []:
        if isinstance(k, dict) and isinstance(k.get("f"), (int, float)) and float(k["f"]).is_integer():
            out[int(k["f"])] = k
    return out


def measure_pose(joints: dict, k: float = 1.0, support_extra=()) -> dict:
    """The measured half of one record (see the module docstring), from one frame's joints."""
    contact_h, tol = CONTACT_H * k, BALANCE_TOL * k
    soles = {s: [joints[p.format(s=s)] for p in SOLE] for s in "lr"}
    planted = {s: any(q[1] <= contact_h for q in soles[s]) for s in "lr"}
    down = [s for s in "lr" if planted[s]]
    support = "both" if len(down) == 2 else SIDE[down[0]] if down else "none"
    c = joints["com"]
    com = weight = None
    if down:
        pts = [(q[0], q[2]) for s in down for q in soles[s] if q[1] <= contact_h] + list(support_extra)
        d = outside((c[0], c[2]), _hull(pts))
        com = {"inside": d <= tol, "outside_m": round(d, 4)}
        if len(down) == 1:
            weight = SIDE[down[0]]
        else:
            dist = {}
            for s in "lr":
                mx = sum(q[0] for q in soles[s]) / len(soles[s])
                mz = sum(q[2] for q in soles[s]) / len(soles[s])
                dist[s] = math.hypot(c[0] - mx, c[2] - mz)
            total = dist["l"] + dist["r"]
            weight = ("between" if total <= 1e-9 or abs(dist["l"] - dist["r"]) < BETWEEN * total
                      else "left" if dist["l"] < dist["r"] else "right")
    pel, head = joints["pelvis"], joints["head"]
    v = (head[0] - pel[0], head[1] - pel[1], head[2] - pel[2])
    loa = {"side": round(math.degrees(math.atan2(v[2], v[1])), 1),
           "front": round(math.degrees(math.atan2(v[0], v[1])), 1)}
    return {"planted": {SIDE[s]: planted[s] for s in "lr"}, "support": support, "weight_side": weight,
            "com": com, "line_of_action": loa, "hip_height_m": round(pel[1], 4), **acting_reads(joints, k)}


def acting_reads(joints: dict, k: float = 1.0) -> dict:
    """What an acting read rests on, for a critic who cannot watch the shot: where the chest faces (degrees from
    forward, + toward the character's right), the head's tilt against the chest (side and front, degrees), and for each
    hand whether it reads clear of the torso in silhouette from the front and from the side."""
    need = ("pelvis", "spine_03", "neck_01", "head")
    if not all(n in joints for n in need):
        return {}
    from kei.principles import CLAVICLE_MIN, _len, _sub
    a, b = ("clavicle_l", "clavicle_r")
    if not (a in joints and b in joints) or _len(_sub(joints[b], joints[a])) < CLAVICLE_MIN:
        a, b = "upperarm_l", "upperarm_r"
    out = {}
    if a in joints and b in joints:
        r = _sub(joints[b], joints[a])
        fwd = (-r[2], 0.0, r[0])     # the chest's forward, on the ground plane
        out["chest_facing_deg"] = round(math.degrees(math.atan2(-fwd[0], fwd[2])), 1)
    neck, head, chest = joints["neck_01"], joints["head"], joints["spine_03"]
    h, c = _sub(head, neck), _sub(neck, chest)
    out["head_tilt_deg"] = {"side": round(math.degrees(math.atan2(h[2], h[1]) - math.atan2(c[2], c[1])), 1),
                            "front": round(math.degrees(math.atan2(h[0], h[1]) - math.atan2(c[0], c[1])), 1)}
    lo, hi = joints["pelvis"][1], neck[1]
    xs = sorted([joints[a][0], joints[b][0]]) if a in joints and b in joints else None
    clear = {}
    for s in "lr":
        p = joints.get(f"hand_{s}")
        if p is None or xs is None:
            continue
        front = xs[0] < p[0] < xs[1] and lo < p[1] < hi
        side = abs(p[2] - chest[2]) < 0.12 * k and lo < p[1] < hi
        clear[SIDE[s]] = not (front and side)
    if clear:
        out["hands_clear"] = clear
    return out


def _facts(r: dict) -> list[str]:
    com = r["com"]
    where = "AIRBORNE" if com is None else ("COM IN" if com["inside"] else f"COM OUT {com['outside_m']:.2f}")
    held = ", ".join(f"{n} {h}" for n, h in (r.get("objects") or {}).items() if h)
    loa = r["line_of_action"]
    return [f"F{r['f']} {r.get('function') or '-'} ({r.get('kind') or '-'}). SUPPORT {r['support']}. "
            f"WEIGHT {r['weight_side'] or '-'}. {where}.",
            f"LEAN SIDE {loa['side']:+.0f} FRONT {loa['front']:+.0f}. HIP {r['hip_height_m']:.2f}"
            + (f". HOLDS: {held}" if held else "")
            + (f". JUDGED {r['judged_in']}" if r.get("judged_in") else ""),
            "CHEST " + (f"{r['chest_facing_deg']:+.0f}" if "chest_facing_deg" in r else "-")
            + (f". HEAD TILT SIDE {r['head_tilt_deg']['side']:+.0f} FRONT {r['head_tilt_deg']['front']:+.0f}"
               if "head_tilt_deg" in r else "")
            + (". HANDS " + " ".join(f"{s} {'clear' if ok else 'hidden'}" for s, ok in r["hands_clear"].items())
               if r.get("hands_clear") else "")]


def write_records(shot_dir: Path, pass_name: str, character: str | None = None, mode: str | None = None,
                  sheet: bool = True) -> Path:
    """Write out_<pass>/poses/poses.json (and pose_sheet.png). Returns the json path."""
    from kei.characters import load_character, on_character, shot_character
    from kei.objects import ObjectError, read_objects, track
    out = Path(shot_dir) / f"out_{pass_name}"
    src = out / "shot.json"
    if not src.is_file():
        raise PoseRecordError(f"no {src}: write the pass's keys there first")
    shot = read_json(src, "shot")
    check_shot(shot)
    ch = load_character(shot_character(shot_dir, shot, character or "kei"))
    shot = on_character(shot, ch)
    mode = mode or ("step" if pass_name == "blocking" else "spline")
    frames = bake(shot, mode)
    k = ch.height / CHARACTER_BASE
    from kei.objects import body_mass, with_loads
    try:
        frames = with_loads(shot, frames, body_mass(shot_dir, ch.height), k)
    except ObjectError as e:
        raise PoseRecordError(str(e)) from None
    try:
        objs = read_objects(shot)
    except ObjectError as e:
        raise PoseRecordError(str(e)) from None
    tracks = {o["name"]: track(o, frames) for o in objs}
    plan = _plan_keys(shot_dir)
    # the key poses are the plan's; a pass without a plan (or keyed on every frame) falls back to its own keys
    key_fs = sorted(f for f in plan if 0 <= f < len(frames)) or         sorted({int(kk["f"]) for kk in normalize_keys(shot) if float(kk["f"]).is_integer() and 0 <= kk["f"] < len(frames)})
    records = []
    for f in key_fs:
        pk = plan.get(f, {})
        rec = {"f": f, **{c: pk.get(c) for c in CREATIVE}, "in_plan": f in plan,
               **measure_pose(frames[f]["joints"], k, frames[f].get("support_extra", ()))}
        if tracks:
            rec["objects"] = {n: t[f][1] for n, t in tracks.items()}
        records.append(rec)
    dst = out / "poses" / "poses.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps({"tool": "kei poses", "pass": pass_name, "mode": mode, "character": ch.name,
                               "keys": records}, indent=1), encoding="utf-8")
    if sheet:
        for old in dst.parent.glob("pose_sheet*.png"):
            old.unlink()
        for n, page in enumerate(_sheet(ch, shot, frames, records), start=1):
            (dst.parent / sheet_name(n)).write_bytes(page)
    return dst


PER_PAGE = 10    # keys a page of the pose sheet: one image of 45 keys was 10,530 pixels tall


def sheet_name(n: int) -> str:
    """Page n of the pose sheet: pose_sheet.png, then pose_sheet_2.png, pose_sheet_3.png..."""
    return "pose_sheet.png" if n == 1 else f"pose_sheet_{n}.png"


def _sheet(ch, shot: dict, frames: list[dict], records: list[dict]) -> list[bytes]:
    from kei.objects import read_objects
    from kei.render import POST_VIEWS, _Canvas, _character_panel, _character_parts, character_points, fit, \
        with_objects
    rows = records or [{"f": 0, **measure_pose(frames[0]["joints"])}]
    fs = [r["f"] for r in rows]
    ch2 = ch
    if read_objects(shot):   # an object's place depends on every frame before it: track the whole shot
        every = [_character_parts(ch, fr["pose"]) for fr in frames]
        ch2, every = with_objects(ch, shot, frames, every)
        parts_all = [every[f] for f in fs]
    else:
        parts_all = [_character_parts(ch, frames[f]["pose"]) for f in fs]
    pts = [{**character_points(p), "pelvis": frames[f]["joints"]["pelvis"]} for p, f in zip(parts_all, fs)]
    bounds = fit(pts, POST_VIEWS)
    text_h = FACT_ROWS * ROW_TEXT + 6
    row_h = PANEL + text_h
    w = len(POST_VIEWS) * PANEL
    pages = []
    for start in range(0, len(rows), PER_PAGE):
        page = list(range(start, min(start + PER_PAGE, len(rows))))
        cv = _Canvas(w, row_h * len(page))
        for k, i in enumerate(page):
            r, parts, y = rows[i], parts_all[i], k * row_h
            for j, view in enumerate(POST_VIEWS):
                _character_panel(cv, j * PANEL, y, view, ch2, parts, bounds[i], PANEL,
                                 f"F{r['f']} {r.get('function') or ''}".strip(), 0.6, False, ss=1)
            for n, line in enumerate(_facts(r)):
                cv.text(4, y + PANEL + 4 + n * ROW_TEXT, line, (20, 20, 20), w - 8)
        pages.append(cv.png())
    return pages


def latest_pass(shot_dir: Path, stage_id: str) -> str | None:
    """The pass a stage made: blocking for the blocking stage, the highest out_p<N> for the passes stage."""
    shot_dir = Path(shot_dir)
    if stage_id == "blocking":
        return "blocking" if (shot_dir / "out_blocking" / "shot.json").is_file() else None
    if stage_id == "passes":
        ns = [int(p.name[5:]) for p in shot_dir.glob("out_p*")
              if p.name[5:].isdigit() and (p / "shot.json").is_file()]
        return f"p{max(ns)}" if ns else None
    return None


def records_for_review(shot_dir: Path, stage_id: str, character: str | None) -> None:
    """Before a blocking or passes review, write the records of the pass the stage made, so the critics read them.
    A pass that cannot be measured is left to the stage gates: the records are only an aid."""
    name = latest_pass(shot_dir, stage_id)
    if name is None:
        return
    try:
        write_records(shot_dir, name, character)
    except Exception:   # noqa: BLE001
        return
