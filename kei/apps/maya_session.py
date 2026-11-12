"""Where Kei animates a Maya shot: in an open Maya (through its Kei host) or in the background. Kei never picks in
silence when Maya is open: it asks.

find_sessions(session_root, alive, ping, maya_pids) -> (sessions, hostless)
  Each <session_root>/<pid>/session.json is a Kei host. A file whose process is gone, whose process start time differs
  (Windows gives a dead process's pid to a new one), or whose server does not answer is stale: Kei removes it. The
  Maya windows with no live host are returned as hostless. Kei calls it again at each question, so a Maya opened
  after Kei started is found.
choose_target(sessions, hostless, setting) -> Target | Question
  setting is [apps.maya] session in kei.toml: "ask" (default), "open" or "background".
answer_choice(choices, text) -> the chosen choice, by its number.
The choice is kept in the shot folder (maya/target.json: the kind, and for an open session its pid and start time;
never the token).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from kei.apps.maya_side import kei_proc
from kei.apps.maya_side.kei_host import session_root

SETTINGS = ("ask", "open", "background")
SHELF_STEP = "run kei maya shelf once and follow its steps"


@dataclass
class Session:
    pid: int
    start_time: float
    port: int
    token: str
    scene: str = ""
    unsaved: bool = False
    rigs: list = field(default_factory=list)
    maya_version: str = ""
    busy: bool = False              # alive, but its host did not answer (a dialog or a long task in Maya)


@dataclass
class Target:
    kind: str                       # "background" or "open"
    session: Session | None = None


@dataclass
class Question:
    text: str
    choices: list


class HostError(RuntimeError):
    """The Kei host in the open Maya did not answer, or refused a call. The message says which."""


def call_host(port: int, token: str, tool: str, inputs: dict | None = None, timeout: float = 60) -> dict:
    """One named tool through a Kei host on 127.0.0.1."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/call",
                                 data=json.dumps({"tool": tool, "inputs": inputs or {}}).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error")
        except ValueError:
            msg = None
        raise HostError(f"the Kei host refused {tool}: {msg or e.code}") from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise HostError(f"the Kei host on port {port} did not answer: {e}") from e
    return body["result"]


def ping(port: int, token: str) -> dict | None:
    try:
        return call_host(port, token, "scene_info", timeout=3)
    except HostError:
        return None


def find_sessions(root: Path | None = None, alive: Callable[[int], float | None] = kei_proc.start_time,
                  ping: Callable[[int, str], dict | None] = ping,
                  maya_pids: Callable[[], list[int]] = kei_proc.maya_pids) -> tuple[list[Session], list[int]]:
    import shutil
    root = Path(root) if root else session_root()
    sessions = []
    for f in sorted(root.glob("*/session.json")) if root.is_dir() else []:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            pid, st = int(data["pid"]), float(data.get("start_time") or 0)
            port, token = int(data["port"]), str(data["token"])
        except (OSError, ValueError, KeyError, TypeError):
            shutil.rmtree(f.parent, ignore_errors=True)
            continue
        now = alive(pid)
        if now is None or abs(now - st) >= 1.0:     # gone, or a pid Windows gave to a new process: a stale file
            shutil.rmtree(f.parent, ignore_errors=True)
            continue
        info = ping(port, token)
        if info is None:            # alive but not answering: busy, never removed (Maya would not write it again)
            sessions.append(Session(pid, st, port, token, data.get("scene") or "", bool(data.get("unsaved")), [],
                                    str(data.get("maya_version") or ""), busy=True))
            continue
        sessions.append(Session(pid, st, port, token, info.get("scene") or "",
                                bool(info.get("unsaved")), list(info.get("rigs") or []),
                                str(info.get("maya_version") or data.get("maya_version") or "")))
    live = {s.pid for s in sessions}
    return sessions, [p for p in maya_pids() if p not in live]


def _line(s: Session) -> str:
    rigs = ", ".join(r.replace(":kei_rig", "") for r in s.rigs) or "no Kei rig found"
    unsaved = ", with unsaved changes (Kei works on a copy for the heavy work and never saves your file)" \
        if s.unsaved else ""
    return f"in the open Maya (session {s.pid}): scene {s.scene or 'untitled'}, rig {rigs}{unsaved}"


def choose_target(sessions: list[Session], hostless: list[int], setting: str = "ask") -> Target | Question:
    if setting not in SETTINGS:
        raise ValueError(f"apps.maya.session must be one of {', '.join(SETTINGS)}, not {setting!r}")
    if setting == "background" or (not sessions and not hostless):
        return Target("background")
    busy = [s for s in sessions if s.busy]
    sessions = [s for s in sessions if not s.busy]
    if setting == "open" and len(sessions) == 1 and not busy:
        return Target("open", sessions[0])
    choices = [{"n": i + 1, "kind": "open", "pid": s.pid, "start_time": s.start_time, "text": _line(s)}
               for i, s in enumerate(sessions)]
    choices.append({"n": len(choices) + 1, "kind": "background",
                    "text": "in the background (Maya with no window, on a copy in the shot folder)"})
    lines = ["Maya is open. Where should Kei animate this shot?"]
    lines += [f"{c['n']}. {c['text']}" for c in choices]
    for s in busy:
        lines.append(f"The open Maya (session {s.pid}, scene {s.scene or 'untitled'}) is busy and does not answer "
                     "(a dialog or a long task): finish it in Maya, then answer again to see it here.")
    for pid in hostless:
        lines.append(f"A Maya window (process {pid}) is open but Kei cannot reach it: {SHELF_STEP}, then answer "
                     "again; meanwhile the background works.")
    lines.append("Answer with the number.")
    return Question("\n".join(lines), choices)


def answer_choice(choices: list, text: str) -> dict:
    try:
        n = int(str(text).strip().rstrip("."))
    except ValueError:
        n = 0
    for c in choices:
        if c["n"] == n:
            return c
    raise ValueError(f"answer with a number from 1 to {len(choices)}")


def target_path(shot_dir: Path) -> Path:
    return Path(shot_dir) / "maya" / "target.json"


def save_target(shot_dir: Path, choice: dict) -> Path:
    p = target_path(shot_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: choice[k] for k in ("kind", "pid", "start_time") if k in choice}
    p.write_text(json.dumps(keep, indent=1), encoding="utf-8")
    return p


def load_target(shot_dir: Path) -> dict | None:
    p = target_path(shot_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def locate(target: dict, **finders) -> Session | None:
    """The open session a target names, found again (its port and token change when Maya restarts)."""
    sessions, _ = find_sessions(**finders)
    return next((s for s in sessions if not s.busy and s.pid == target.get("pid")
                 and abs(s.start_time - float(target.get("start_time") or 0)) < 1.0), None)
