"""What the live page shows: one read of the shot folder, as plain data.

snapshot(shot) -> dict
  The stages and where the shot is, every try and verdict, the question waiting for the author, the key poses of
  plan/plan.json and of each earlier plan, the references of REFS.md, the passes with their renders, and every
  sheet. Read only, except keep_plan.
keep_plan(shot) -> bool
  Keeps a copy of plan/plan.json under <shot>/.kei/live/plans/ each time its content changes, so the page can show
  how the key poses changed between tries. Nothing else is written.
files(shot) -> {id: path}
  The files the page may load: images and videos in the shot folder, by an id that is not a path.
signature(shot) -> a value that changes when any file in the shot changes.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from kei.layout import where
from kei.stages import STAGES

DOING = {
    "brief": "Reading the request", "rig": "Reading the rig", "weight": "Weighing the character",
    "understanding": "Scoring what it understands", "references": "Finding references",
    "study": "Studying the references", "plan": "Planning the key poses", "blocking": "Blocking the poses",
    "passes": "Breakdowns, spline and polish", "checks": "Running every check",
    "self_review": "Reviewing its own work", "deliver": "Delivering the shot",
}
SHORT = {"rig": "Rig", "weight": "Weight", "understanding": "Understanding", "references": "References",
         "passes": "Passes", "checks": "Checks", "deliver": "Delivery"}
STATUS_STATE = {"needs_answer": "waiting", "needs_human": "stopped", "needs_approval": "approval",
                "paused_machine": "paused", "paused_quota": "paused", "done": "done", "rejected": "stopped"}
TRIES = ("pass", "fail", "send_back", "question")
IMAGES = {".png", ".jpg", ".jpeg"}
VIDEOS = {".mp4"}


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _hidden(rel: Path) -> bool:
    return any(part.startswith(".") or part == "__pycache__" for part in rel.parts)


def _id(rel: str) -> str:
    return hashlib.sha256(rel.encode("utf-8")).hexdigest()[:20] + Path(rel).suffix.lower()


def plans_dir(shot: Path) -> Path:
    return Path(shot) / ".kei" / "live" / "plans"


def signature(shot: Path) -> tuple:
    shot = Path(shot)
    latest, count = 0.0, 0
    for p in shot.rglob("*"):
        rel = p.relative_to(shot)
        if _hidden(rel) and rel.as_posix() != ".kei/state.json":
            continue
        try:
            latest = max(latest, p.stat().st_mtime)
            count += 1
        except OSError:
            pass
    return round(latest, 3), count


def keep_plan(shot: Path) -> bool:
    src = where(shot, "plan/plan.json")
    if not src.is_file():
        return False
    data = src.read_bytes()
    digest = hashlib.sha256(data).hexdigest()[:16]
    d = plans_dir(shot)
    d.mkdir(parents=True, exist_ok=True)
    if any(p.stem.endswith(digest) for p in d.glob("plan_*.json")):
        return False
    n = len(list(d.glob("plan_*.json"))) + 1
    stamp = datetime.fromtimestamp(src.stat().st_mtime, timezone.utc).strftime("%Y%m%dT%H%M%S")
    shutil.copyfile(src, d / f"plan_{n:03d}_{stamp}_{digest}.json")
    return True


def files(shot: Path) -> dict[str, Path]:
    shot = Path(shot)
    out = {}
    for p in shot.rglob("*"):
        rel = p.relative_to(shot)
        if p.suffix.lower() in IMAGES | VIDEOS and not _hidden(rel) and p.is_file():
            out[_id(rel.as_posix())] = p
    return out


def _key(k: dict) -> dict:
    return {"f": k.get("f"), "function": k.get("function"), "kind": k.get("kind"), "note": k.get("note"),
            "drawing": k.get("drawing"), "views": k.get("views") or {}}


def _plain(s: str) -> str:
    return re.sub(r"\*\*|\*|`", "", s).strip()


def refs_table(md: str) -> list[dict]:
    """The rows of REFS.md's reference table: | Ref | Tier | What it gives | Our checks | Verdict |."""
    rows = []
    for line in md.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5 or not re.match(r"\d+\.", cells[0]):
            continue
        verdict = _plain(cells[4])
        rows.append({"ref": _plain(cells[0]), "tier": _plain(cells[1]), "gives": _plain(cells[2]),
                     "checks": _plain(cells[3]), "verdict": verdict,
                     "call": verdict.split(":")[0].strip().lower()})
    return rows


def plan_facts(md: str) -> dict:
    out = {}
    for key in ("Idea sentence", "Short look"):
        m = re.search(re.escape(key) + r":\s*(.+)", md)
        if m:
            out[key] = _plain(m.group(1))[:500]
    return out


def _stages(state: dict) -> list[dict]:
    hist = state.get("history") or []
    order = [s.id for s in STAGES]
    cur = state.get("stage") if state.get("stage") in order else order[0]
    ci = order.index(cur)
    status = state.get("status") or "running"
    out = []
    for i, s in enumerate(STAGES):
        ev = [h for h in hist if h.get("stage") == s.id]
        passed = next((h for h in reversed(ev) if h.get("result") == "pass"), None)
        start = None
        for h in hist:
            if h.get("stage") in order and order.index(h["stage"]) < i and h.get("result") == "pass":
                start = h.get("at")
        if i < ci:
            st = "done"
        elif i == ci:
            st = STATUS_STATE.get(status, "working")
        else:
            st = "todo"
        out.append({"id": s.id, "title": SHORT.get(s.id, s.title), "doing": DOING.get(s.id, s.title), "state": st,
                    "tries": sum(1 for h in ev if h.get("result") in TRIES),
                    "start": start, "end": passed.get("at") if passed else None})
    return out


def _versions(shot: Path) -> list[dict]:
    out = []
    d = plans_dir(shot)
    for p in sorted(d.glob("plan_*.json")) if d.is_dir() else []:
        m = re.match(r"plan_(\d+)_(\d{8}T\d{6})_", p.name)
        data = _json(p) or {}
        at = (datetime.strptime(m.group(2), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).isoformat()
              if m else None)
        out.append({"n": int(m.group(1)) if m else len(out) + 1, "at": at,
                    "keys": [_key(k) for k in data.get("keys") or [] if isinstance(k, dict)]})
    return out


def _pass_dirs(shot: Path) -> list[Path]:
    """The pass folders, on top while the shot is worked on, under production/<phase>/ once it is delivered."""
    dirs = [p for p in shot.glob("out_*") if p.is_dir()] + [p for p in shot.glob("production/*/out_*") if p.is_dir()]
    return sorted(dirs, key=lambda p: p.stat().st_mtime)


def _passes(shot: Path) -> list[dict]:
    out = []
    for p in _pass_dirs(shot):
        frames = sorted((p / "frames").glob("*.png")) if (p / "frames").is_dir() else []
        rel = lambda f: f.relative_to(shot).as_posix()
        out.append({"name": p.name.removeprefix("out_"),
                    "videos": [{"id": _id(rel(v)), "name": v.name} for v in sorted(p.glob("*.mp4"))],
                    "frames": [{"id": _id(rel(f)), "name": f.name} for f in frames]})
    return out


def _images(shot: Path) -> list[dict]:
    out = []
    for p in shot.rglob("*"):
        rel = p.relative_to(shot)
        if p.suffix.lower() not in IMAGES or _hidden(rel) or "frames" in rel.parts or not p.is_file():
            continue
        parts = rel.parts[1:] if rel.parts[0] == "production" else rel.parts
        out.append({"id": _id(rel.as_posix()), "name": p.stem, "group": parts[0] if len(parts) > 1 else "delivered",
                    "mtime": p.stat().st_mtime})
    return sorted(out, key=lambda x: -x["mtime"])


def _frames(v):
    """The plan's length as one number: a seat may write it as a range [first, last]; the page wants the last frame."""
    if isinstance(v, (list, tuple)):
        v = v[-1] if v else None
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _travel(root) -> list:
    """The root's forward travel as [frame, metres] pairs, from plan.json's root keys; [] when it stays in place."""
    if not isinstance(root, dict):
        return []
    out = []
    for k in root.get("keys") or []:
        if isinstance(k, (list, tuple)) and len(k) == 2 and all(isinstance(v, (int, float)) for v in k):
            out.append([k[0], k[1]])
    return sorted(out) if any(v for _, v in out) else []


def snapshot(shot: Path) -> dict:
    shot = Path(shot)
    state = _json(shot / ".kei" / "state.json") or {}
    plan = _json(where(shot, "plan/plan.json"))
    pending = None
    if state.get("status") == "needs_answer":
        pending = _text(where(shot, "QUESTIONS.md")) or next(
            (q.get("text") or q.get("question") for q in reversed(state.get("questions") or [])
             if isinstance(q, dict)), None)
    return {
        "shot": shot.name,
        "request": state.get("request"),
        "status": state.get("status"),
        "stage": state.get("stage"),
        "stages": _stages(state),
        "history": state.get("history") or [],
        "answers": state.get("answers") or [],
        "pending": pending,
        "character": _json(where(shot, "unreal/character.json")),
        "plan": None if not isinstance(plan, dict) else {
            "fps": plan.get("fps"), "frames": _frames(plan.get("frames")), "loop": bool(plan.get("loop")),
            "travel": _travel(plan.get("root")),
            "keys": [_key(k) for k in plan.get("keys") or [] if isinstance(k, dict)]},
        "plan_versions": _versions(shot),
        "refs": refs_table(_text(where(shot, "REFS.md"))),
        "facts": plan_facts(_text(where(shot, "PLAN.md"))),
        "images": _images(shot),
        "passes": _passes(shot),
        "now": datetime.now(timezone.utc).isoformat(),
    }
