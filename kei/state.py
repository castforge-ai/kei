"""A shot's progress through the stages, kept in <shot>/.kei/state.json so a killed run resumes where it stopped."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

PAUSED = ("paused_usage", "paused_machine")   # a seat hit a usage limit or could not start: kei run resumes it
STATUSES = ("running", "needs_answer", "needs_human", "needs_approval", "done", "rejected", *PAUSED)
# rejected: the author stopped the shot with a reason (kei review); kei note reopens it


class StateError(ValueError):
    """The state file cannot be read. The message names the file."""


@dataclass
class ShotState:
    stage: str = "brief"
    attempts: int = 0
    send_backs: int = 0
    approved_plan: dict | None = None   # hashes of the plan files the panel passed
    approved_pass: dict | None = None   # the newest pass the panel passed: {"pass": "p9", "sha256": ...}
    ledger: list = field(default_factory=list)   # critic notes judged fixed: stage, note, frames (kei.ledger)
    sessions: dict = field(default_factory=dict)  # stage -> the animator's Claude Code session, resumed on each try
    subjects: list | None = None        # the subject topics named at the brief; None means every subject
    status: str = "running"
    request: str = ""
    history: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)   # open questions for the author: from, stage, text, look_at
    answers: list[dict] = field(default_factory=list)     # the author's replies: stage, question, answer, at
    sign_off: list[dict] = field(default_factory=list)    # checks left for the author's sign-off: stage, from, check
    accepted: list[dict] = field(default_factory=list)    # flags the author accepted by name: id, size, reason, at


def state_path(shot_dir: Path) -> Path:
    return Path(shot_dir) / ".kei" / "state.json"


def load_state(shot_dir: Path) -> ShotState:
    p = state_path(shot_dir)
    if not p.exists():
        return ShotState()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        state = ShotState(**data)
    except (OSError, ValueError, TypeError) as e:
        raise StateError(f"cannot read {p}: {e}") from e
    if state.status not in STATUSES:
        raise StateError(f"{p}: unknown status {state.status!r}")
    return state


def save_state(shot_dir: Path, state: ShotState) -> None:
    p = state_path(shot_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(asdict(state), indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
