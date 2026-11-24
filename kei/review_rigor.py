"""What keeps a pass with a visible fault from reaching the author: the gate and the critics check each other.

- A declared hard flag must fit its measurement. Past a cap (a planted foot that slides more than a peel can explain),
  or grown since it was first declared, the declaration no longer counts: the animator fixes it, or the author accepts
  it by name (kei accept <shot> <flag id>).
- A control that jumps in one frame while its neighbours barely move (a foot roll that drops back to rest, a hand-off
  from one control to another) is a hard fault, found on the keys themselves.
- The critics get evidence for every flagged or declared contact range and every author note: a plot of each foot's
  height and ground speed per frame, and the exact full-size mesh frames to open. They must say, per declared hard
  flag, whether its reason holds on those frames, and per author note, whether it is fixed. A missing answer counts
  as "does not hold" / "not fixed".
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

CAP_SLIDE = 4.0   # x the slide threshold: a declared planted-foot slide past this is a fault, not a peel or a pivot
CAP_DEPTH = 3.0   # x the penetration threshold: a declared foot this far under the ground is a fault
WORSE = 1.25      # a declared flag that grows past this factor (plus WORSE_ABS) since it was declared counts again
WORSE_ABS = 0.005
ACCEPT_TOL = 1.1  # an author's acceptance covers the size they accepted, and a little more
SNAP_DEG, SNAP_CM = 25.0, 8.0   # a control's change in one frame that counts as a snap ...
SNAP_RATIO = 2.0                # ... when it is this many times its neighbours' change
FEET_CHECKS = ("foot_slide", "contacts", "hover")
MARGIN = 2        # frames shown either side of a flagged range


def _flag_id(fl: dict) -> str:
    from kei.explain import body_id
    return fl.get("id") or body_id(fl)


def _thresholds(body: dict) -> dict:
    t = body.get("thresholds") or {}
    return {k: (v.get("value") if isinstance(v, dict) else v) for k, v in t.items()}


def accepted_sizes(shot_dir: Path) -> dict[str, float]:
    """The flags the author accepted by name, with the size they accepted."""
    from kei.state import load_state
    try:
        st = load_state(Path(shot_dir))
    except Exception:   # a broken state file is reported elsewhere
        return {}
    return {a["id"]: float(a.get("size") or 0.0) for a in (st.accepted or []) if a.get("id")}


def _cap(fl: dict, th: dict) -> float | None:
    if fl.get("check") == "foot_slide" and th.get("slide_m_per_frame"):
        return CAP_SLIDE * th["slide_m_per_frame"]
    if fl.get("check") == "contacts" and th.get("penetration_m"):
        return CAP_DEPTH * th["penetration_m"]
    return None


def declared_misses(shot_dir: Path, declared: list[dict], body: dict) -> list[str]:
    """Gate misses for declared hard flags that do not fit their measurement. Records each declared flag's first size
    in <shot>/.kei/declared_sizes.json, so a later pass that makes it worse is caught."""
    shot_dir = Path(shot_dir)
    th, acc = _thresholds(body), accepted_sizes(shot_dir)
    base_path = shot_dir / ".kei" / "declared_sizes.json"
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        base = {}
    miss = []
    for fl in declared:
        size = fl.get("size")
        if size is None:
            continue
        fid, (a, b) = _flag_id(fl), fl["frames"][:2]
        where = f"{fl.get('side', '')} f{a}-{b}".strip()
        if fid in acc and size <= acc[fid] * ACCEPT_TOL:
            continue
        cap = _cap(fl, th)
        if cap is not None and size > cap:
            miss.append(f"P10 {fid} ({where}): declared, but it measures {size:.3f} {fl.get('unit', 'm')}, past the "
                        f"{cap:.3f} a declaration may cover ({fl.get('what')}). No reason in GATES.md covers a fault "
                        f"this size: fix it. Only the author can accept it (kei accept <shot> {fid})")
            continue
        first = base.setdefault(fid, size)
        if size > first * WORSE + WORSE_ABS:
            miss.append(f"P10 {fid} ({where}): declared at {first:.3f}, now {size:.3f}: it grew since it was "
                        f"declared, so the declaration no longer covers it. Fix it, or bring it back to its declared "
                        f"size")
    try:
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.write_text(json.dumps(base, indent=1), encoding="utf-8")
    except OSError:
        pass
    return miss


def control_snaps(shot: dict) -> list[dict]:
    """Controls that jump in one frame while their neighbouring frames barely move, read on the pass's keys.
    Scale channels and two-valued switches are skipped."""
    keys = sorted((k for k in shot.get("keys") or [] if isinstance(k.get("f"), (int, float))), key=lambda k: k["f"])
    if len(keys) < 3:
        return []
    chans = [c for c in keys[0] if "." in c and ".scale." not in c and isinstance(keys[0][c], (int, float))]
    out = []
    for c in chans:
        thr = SNAP_DEG if ".rotation." in c else SNAP_CM
        vals = [(k["f"], k.get(c)) for k in keys if isinstance(k.get(c), (int, float))]
        if len({round(v, 3) for _, v in vals}) <= 2:   # a switch or a constant
            continue
        rates = [((f1 - f0), (v1 - v0) / (f1 - f0), f0, f1, v0, v1)
                 for (f0, v0), (f1, v1) in zip(vals, vals[1:]) if f1 > f0]
        for i, (df, r, f0, f1, v0, v1) in enumerate(rates):
            if df > 1 or abs(r) < thr:
                continue
            near = [abs(rates[j][1]) for j in (i - 1, i + 1) if 0 <= j < len(rates)]
            if near and abs(r) < SNAP_RATIO * max(near):
                continue
            ctrl = c.split(".")[0]
            out.append({"check": "control_snap", "channel": c, "frames": [int(f0), int(f1)], "size": round(abs(r), 2),
                        "unit": "deg" if ".rotation." in c else "cm", "id": f"control_snap.{ctrl}.f{int(f1)}",
                        "what": f"{c} jumps {v0:.1f} -> {v1:.1f} in one frame (f{int(f0)}-f{int(f1)}) while the "
                                f"frames around it move {max(near or [0]):.1f} a frame"})
    return out


def snap_misses(shot_dir: Path, pass_name: str) -> list[str]:
    """Gate misses for the control snaps of a pass that the author has not accepted by name."""
    p = Path(shot_dir) / f"out_{pass_name}" / "shot.json"
    try:
        shot = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    acc = accepted_sizes(shot_dir)
    return [f"P10 {s['id']}: {s['what']}: the control resets or hands off in one frame, and the part pops. Spread the "
            f"change over the frames around it, or key the controls that take over so the part keeps its path. Only "
            f"the author can accept a snap (kei accept <shot> {s['id']})"
            for s in control_snaps(shot) if not (s["id"] in acc and s["size"] <= acc[s["id"]] * ACCEPT_TOL)]


# --- the critics' evidence -----------------------------------------------------------------------------------------

def _declared_reasons(gates: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r"^## Declared[^\n]*\n(.*?)(?=^## |\Z)", gates or "", re.M | re.S):
        for fid, why in re.findall(r"^\s*[-*]\s*`?([a-z_]+(?:\.[\w-]+){1,2}\.f\d+)`?\s*[:-]\s*(.+)$", m.group(1), re.M):
            out.setdefault(fid, why.strip())
    return out


def _feet_plot(shot_dir: Path, pass_name: str, body: dict, marks: list[tuple[int, int]]) -> str | None:
    """out_<pass>/evidence/feet_paths.png: per foot, the height of heel, ball and toe tip, and the foot's ground speed,
    per frame, contact frames shaded and the flagged ranges marked. A planted foot reads as speed 0; a slide, a
    reversal or a snap reads as a spike."""
    from kei.sheet import _Canvas
    try:
        frames = json.loads((Path(shot_dir) / f"out_{pass_name}" / "joints.json").read_text(encoding="utf-8"))["frames"]
    except (OSError, ValueError, KeyError):
        return None
    if len(frames) < 2:
        return None
    W, PH, PAD = 960, 170, 48
    sides = [s for s in "lr" if f"ball_{s}" in frames[0]["joints"]]
    cv = _Canvas(W, PAD + len(sides) * 2 * (PH + PAD))
    n = len(frames) - 1
    contacts = body.get("contacts") or {}
    parts = {"heel": (200, 60, 40), "ball": (40, 110, 200), "ball_tip": (40, 150, 70)}

    def xf(i):
        return int(PAD + i / max(1, n) * (W - 2 * PAD))

    y0 = PAD
    for s in sides:
        for kind in ("height", "speed"):
            series = {}
            for p, col in parts.items():
                name = f"{p.replace('ball_tip', 'ball')}_{s}" + ("_tip" if p == "ball_tip" else "")
                if name not in frames[0]["joints"]:
                    continue
                pts = [fr["joints"][name] for fr in frames]
                if kind == "height":
                    series[p] = [v[1] for v in pts]
                else:
                    series[p] = [0.0] + [math.hypot(b[0] - a[0], b[2] - a[2]) for a, b in zip(pts, pts[1:])]
            vals = [v for vs in series.values() for v in vs] or [0.0]
            lo, hi = min(vals + [0.0]), max(vals) or 1.0
            span = (hi - lo) or 1.0
            for a, b in contacts.get(s, []):   # contact: a green band under the axis
                for dy in range(3):
                    cv.line(xf(a), y0 + PH + 10 + dy, xf(b), y0 + PH + 10 + dy, (60, 170, 60), False)
            for a, b in marks:                 # flagged or noted: a red band under it
                for dy in range(3):
                    cv.line(xf(a), y0 + PH + 15 + dy, xf(b), y0 + PH + 15 + dy, (220, 60, 60), False)
            for i in range(n + 1):
                cv.line(xf(i), y0, xf(i), y0 + PH, (236, 236, 236) if i % 5 else (210, 210, 210), False)
                cv.line(xf(i), y0 + PH, xf(i), y0 + PH + (3 if i % 5 else 7), (120, 120, 120), False)
                if i % 5 == 0:
                    cv.text(xf(i) + 2, y0 + PH + 19, f"f{frames[i]['f']}", (90, 90, 90), 40)
            for p, vs in series.items():
                pts = [(xf(i), int(y0 + PH - (v - lo) / span * PH)) for i, v in enumerate(vs)]
                for a, b in zip(pts, pts[1:]):
                    cv.line(*a, *b, parts[p])
                for q in pts:
                    cv.disk(*q, 2, parts[p])
            cv.text(PAD, y0 - 14, f"{s} foot {kind} ({'m' if kind == 'height' else 'm a frame along the ground'}) "
                    f"{pass_name} max {hi:.3f}. heel red, ball blue, toe green. bands: green contact, red flagged",
                    (40, 40, 40), W - 2 * PAD)
            y0 += PH + PAD
    out = Path(shot_dir) / f"out_{pass_name}" / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    (out / "feet_paths.png").write_bytes(cv.png())
    return f"out_{pass_name}/evidence/feet_paths.png"


def _frame_files(shot_dir: Path, pass_name: str, a: int, b: int, last: int) -> dict[str, list[str]]:
    out = {}
    for view in ("feet", "side"):
        folder = Path(shot_dir) / f"out_{pass_name}" / "mesh" / view
        files = [f"out_{pass_name}/mesh/{view}/f{f:04d}.png" for f in range(max(0, a - MARGIN), min(last, b + MARGIN) + 1)
                 if (folder / f"f{f:04d}.png").is_file()]
        if files:
            out[view] = files
    return out


def evidence(shot_dir: Path, pass_name: str | None, author_notes: list[str] = ()) -> dict:
    """The evidence a critic must open for a pass, and the answers it must give.
    Returns {"lines": prompt lines, "declared": [flag ids], "notes": [author notes with frames]}."""
    empty = {"lines": [], "declared": [], "notes": []}
    if not pass_name:
        return empty
    shot_dir = Path(shot_dir)
    from kei.ledger import note_frames
    try:
        body = json.loads((shot_dir / f"out_{pass_name}" / "body_check" / "body_check.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        body = {}
    try:
        gates = (shot_dir / "GATES.md").read_text(encoding="utf-8")
    except OSError:
        gates = ""
    try:
        shot = json.loads((shot_dir / f"out_{pass_name}" / "shot.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        shot = {}
    last = max(0, int(body.get("frames") or len(shot.get("keys") or []) or 1) - 1)
    reasons = _declared_reasons(gates)
    hard = [fl for fl in body.get("flags") or [] if fl.get("rule", "hard") == "hard" and not fl.get("note")
            and fl.get("check") in FEET_CHECKS]
    from kei.gates.pipeline import open_flags
    tagged = [{**fl, "id": _flag_id(fl)} for fl in hard]
    still_open = {id(f) for f in open_flags(tagged, gates)} if tagged else set()
    rows = []
    for fl in tagged:
        declared = id(fl) not in still_open
        why = reasons.get(fl["id"]) or next((w for k, w in reasons.items() if k.rsplit(".f", 1)[0] ==
                                             fl["id"].rsplit(".f", 1)[0]), None)
        rows.append({"id": fl["id"], "frames": fl["frames"][:2], "what": fl.get("what", ""), "size": fl.get("size"),
                     "declared": declared, "reason": why if declared else None})
    rows += [{"id": s["id"], "frames": s["frames"], "what": s["what"], "size": s["size"], "declared": False,
              "reason": None} for s in control_snaps(shot)]
    noted = [(n, note_frames(n)) for n in author_notes]
    noted = [(n, fr) for n, fr in noted if fr]
    if not rows and not noted:
        return empty
    marks = [tuple(r["frames"]) for r in rows] + [fr for _, fr in noted]
    plot = _feet_plot(shot_dir, pass_name, body, marks)
    lines = ["Evidence you must open for this pass (Kei made it; it is not the animator's). Open every file named. "
             "Judge contacts and foot paths on these frames, not on the contact sheets alone:"]
    if plot:
        lines.append(f"- {plot}: each foot's height and ground speed on every frame. A planted foot is flat at speed 0; "
                     "a spike, a dip or a step back inside a contact or a lift is a fault you can point to.")
    declared = []
    for r in rows:
        a, b = r["frames"]
        files = _frame_files(shot_dir, pass_name, a, b, last)
        size = f", {r['size']}" if r.get("size") is not None else ""
        state = f"DECLARED in GATES.md: \"{r['reason']}\"" if r["declared"] else "open"
        lines.append(f"- {r['id']} (f{a}-{b}{size}): {r['what']}. {state}.")
        for view, fs in files.items():
            lines.append(f"  {view}: {' '.join(fs)}")
        if r["declared"]:
            declared.append(r["id"])
    for n, (a, b) in noted:
        lines.append(f"- author note (f{a}-{b}): {n}")
        for view, fs in _frame_files(shot_dir, pass_name, a, b, last).items():
            lines.append(f"  {view}: {' '.join(fs)}")
    if declared or noted:
        lines.append('Your verdict line must also carry "declared": {"<flag id>": "holds" | "does not hold"} for '
                     f"every declared flag above ({', '.join(declared) or 'none'}), and \"author_notes\": "
                     '{"<the note\'s first words>": "fixed" | "not fixed"} for every author note above. Judge each on '
                     "its frames: a reason holds only when the frames show what it says, at the size measured. A "
                     "flag or note you leave out counts as \"does not hold\" / \"not fixed\", and sends the work back.")
    return {"lines": lines, "declared": list(dict.fromkeys(declared)), "notes": [n for n, _ in noted]}


def required_misses(critic: str, verdict_data: dict, ev: dict) -> list[str]:
    """Blocking notes from a critic's verdict for the declared flags and author notes it had to judge."""
    out = []
    judged = {str(k).strip(): str(v).strip().lower() for k, v in (verdict_data.get("declared") or {}).items()} \
        if isinstance(verdict_data.get("declared"), dict) else {}
    for fid in ev.get("declared") or []:
        v = judged.get(fid)
        if v != "holds":
            out.append(f"critic {critic}: {fid}: the declared reason " +
                       ("does not hold on its frames" if v else "was not judged on its frames, so it does not hold") +
                       ": fix the fault")
    notes = verdict_data.get("author_notes") if isinstance(verdict_data.get("author_notes"), dict) else {}
    marks = {str(k).strip().lower(): str(v).strip().lower() for k, v in notes.items()}
    for n in ev.get("notes") or []:
        bare = re.sub(r"^[^:]*:\s*", "", n) if n.lower().startswith("author") else n
        hit = next((v for k, v in marks.items() if k and (bare.lower().startswith(k[:40]) or k.startswith(bare.lower()[:40]))), None)
        if hit != "fixed":
            out.append(f"critic {critic}: author note not fixed on its frames: {n}" if hit else
                       f"critic {critic}: the author's note was not judged on its frames: {n}")
    return out


def accept(shot_dir: Path, flag_id: str, reason: str) -> dict:
    """The author accepts one flag of the newest pass by name, at its measured size. A later pass that makes it worse
    than that is a fault again."""
    from datetime import datetime, timezone
    from kei.pose_record import latest_pass
    from kei.state import load_state, save_state
    shot_dir = Path(shot_dir)
    p = latest_pass(shot_dir, "passes")
    if not p:
        raise ValueError("the shot has no pass yet")
    try:
        body = json.loads((shot_dir / f"out_{p}" / "body_check" / "body_check.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        body = {}
    try:
        shot = json.loads((shot_dir / f"out_{p}" / "shot.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        shot = {}
    found = [fl for fl in body.get("flags") or [] if _flag_id(fl) == flag_id] + \
            [s for s in control_snaps(shot) if s["id"] == flag_id]
    if not found:
        raise ValueError(f"{p} has no flag {flag_id}")
    size = max(float(fl.get("size") or 0.0) for fl in found)
    st = load_state(shot_dir)
    st.accepted = [a for a in st.accepted if a.get("id") != flag_id]
    entry = {"id": flag_id, "size": size, "pass": p, "reason": reason,
             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    st.accepted.append(entry)
    save_state(shot_dir, st)
    return entry
