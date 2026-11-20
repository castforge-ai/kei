"""The review in the chat (design Amendment 4): which shots are still open, which were asked about today, and which
the author parked until their next pass. Everything is read from the shot folders on disk at each call, so a shot
moved or renamed between two chats is found where it is now. The asked date and the park live in
<shot>/.kei/chat.json, apart from the shot's state, so they never touch its history."""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

from kei.signoff import CLOSED, SignOffError, open_notes, pass_mark
from kei.state import StateError, load_state, state_path

CHAT_FILE = "chat.json"


def _today() -> str:
    return date.today().isoformat()


def chat_path(shot: Path) -> Path:
    return state_path(shot).with_name(CHAT_FILE)


def read_chat(shot: Path) -> dict:
    try:
        data = json.loads(chat_path(shot).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_chat(shot: Path, data: dict) -> None:
    p = chat_path(shot)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def park(shot: Path) -> dict:
    """The author's "not now": the shot is left out of kei status --open until its next pass (a new pass, or the
    latest pass written again). Returns the pass it is parked on."""
    shot = Path(shot)
    state = load_state(shot)
    if state.status in CLOSED:
        raise SignOffError(f"this shot is closed (status: {state.status}): there is nothing to park")
    mark = pass_mark(shot)
    data = read_chat(shot)
    data["parked"] = mark
    _write_chat(shot, data)
    return mark


def mark_asked(shot: Path) -> None:
    data = read_chat(shot)
    data["asked"] = _today()
    _write_chat(shot, data)


def is_parked(shot: Path, data: dict | None = None) -> bool:
    parked = (read_chat(shot) if data is None else data).get("parked")
    return isinstance(parked, dict) and parked.get("pass_sha") == pass_mark(shot)["pass_sha"]


def shot_folders(folder: Path) -> list[Path]:
    """The folder itself when it is a shot, and its direct subfolders that are shots, by name."""
    folder = Path(folder)
    found = [folder] if state_path(folder).is_file() else []
    if folder.is_dir():
        found += sorted((d for d in folder.iterdir() if d.is_dir() and state_path(d).is_file()),
                        key=lambda d: d.name)
    return found


def _last_pass(shot: Path) -> dict | None:
    from kei.characters import latest_pass
    p = latest_pass(shot)
    if p is None:
        return None
    when = datetime.fromtimestamp(p.stat().st_mtime).date().isoformat()
    return {"name": p.parent.name[len("out_"):], "date": when}


def shot_summary(shot: Path) -> dict:
    """One shot as kei status <shot> --json gives it: name, path, status, stage, attempts, send-backs, last pass,
    open notes and the seat runs added up (runs, seconds, tokens)."""
    from kei.seats import run_totals
    from kei.unchecked import unchecked
    shot = Path(shot)
    state = load_state(shot)
    notes = [{k: n[k] for k in ("n", "lesson", "words", "scope", "from", "new_pass")} for n in open_notes(shot, state)]
    return {"shot": shot.resolve().name, "path": str(shot.resolve()), "status": state.status, "stage": state.stage,
            "attempts": state.attempts, "send_backs": state.send_backs, "last_pass": _last_pass(shot), "notes": notes,
            "seat_runs": run_totals(shot), "unchecked": len(unchecked(shot))}


def open_shots(folder: Path, show_all: bool = False) -> dict:
    """Every shot under the folder that is not done or rejected: name, path, status, stage, last pass (name and the
    date of its file) and open notes. A parked shot and a shot asked about today are left out unless show_all; they
    are counted in "hidden". A shot whose state cannot be read is listed with the reason."""
    shots, hidden, unreadable = [], 0, []
    for shot in shot_folders(folder):
        try:
            state = load_state(shot)
        except StateError as e:
            unreadable.append({"path": str(shot.resolve()), "error": str(e)})
            continue
        if state.status in CLOSED:
            continue
        data = read_chat(shot)
        parked, asked = is_parked(shot, data), data.get("asked") == _today()
        if (parked or asked) and not show_all:
            hidden += 1
            continue
        notes = [{k: n[k] for k in ("n", "lesson", "words", "scope", "from", "new_pass")}
                 for n in open_notes(shot, state)]
        shots.append({"shot": shot.resolve().name, "path": str(shot.resolve()), "status": state.status,
                      "stage": state.stage, "last_pass": _last_pass(shot), "notes": notes, "parked": parked,
                      "asked_today": asked})
    return {"folder": str(Path(folder).resolve()), "shots": shots, "hidden": hidden, "unreadable": unreadable}
