"""The approved plan: the conductor keeps the hashes of the plan files the panel passed, so any later change is seen.

The hashes live in the shot state, which the conductor holds and rewrites; a copy of the approved files is also put in
<shot>/.kei/approved_plan/ for the critics to compare with. Deleting or editing that copy hides nothing.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

PLAN_FILES = ("plan/plan.json", "plan/plan_sheet.png", "PLAN.md")


def approved_dir(shot_dir: Path) -> Path:
    return Path(shot_dir) / ".kei" / "approved_plan"


def read_plan(shot_dir: Path) -> dict[str, bytes | None]:
    """The plan files as they are now; None for a file that does not exist."""
    out = {}
    for rel in PLAN_FILES:
        p = Path(shot_dir) / rel
        out[rel] = p.read_bytes() if p.is_file() else None
    return out


def _hash(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def approve_plan(shot_dir: Path, snapshot: dict[str, bytes | None] | None = None) -> dict[str, str | None]:
    """Make the plan files in `snapshot` (default: as they are now) the reference. Returns their hashes."""
    snapshot = read_plan(shot_dir) if snapshot is None else snapshot
    dest = approved_dir(shot_dir)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for rel, data in snapshot.items():
        if data is not None:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_bytes(data)
    return {rel: _hash(data) for rel, data in snapshot.items()}


def plan_changes(shot_dir: Path, approved: dict[str, str | None] | None,
                 snapshot: dict[str, bytes | None] | None = None) -> list[str]:
    """The plan files added, removed or changed since the approval. Empty when the plan was never approved."""
    if approved is None:
        return []
    snapshot = read_plan(shot_dir) if snapshot is None else snapshot
    return [rel for rel in PLAN_FILES if _hash(snapshot.get(rel)) != approved.get(rel)]
