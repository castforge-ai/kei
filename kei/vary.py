"""Variations of an approved shot: the same action in another mood or weight, without starting from the brief.

vary(source, note, dest, from_stage) -> Path
  source must be signed off (status done). Kei copies the source shot into dest, keeps every stage before from_stage
  as it was approved, and starts the new shot at from_stage with the note as the author's note for that stage:
    plan      (default) the brief, the evaluations, the references and the study are kept; the plan is kept as a draft
              the animator revises, and the critics judge it again. Use it when the change moves the timing.
    blocking  the plan is kept and stays approved; the poses are keyed again. Use it when the timing holds.
    passes    blocking is kept too, and the passes refine it again. Use it for a change of texture, not of poses.
  Never copied: Kei's state, the passes after the start point, the delivery report, a pack, exports and the
  record of the source, so nothing of the source's sign-off reaches the variation. The new shot's history starts
  with a "variation" entry naming the source, the note and the stage.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from kei.signoff import SignOffError
from kei.state import ShotState, load_state, save_state

FROM_STAGES = ("plan", "blocking", "passes")
NEVER = (".kei", "KEI_RECORD.md", "export", "production")
NEVER_SUFFIX = ("_report.html", "_pack.html", ".glb", ".fbx", "_notes.json")


def default_dest(source: Path, note: str) -> Path:
    words = re.findall(r"[a-z0-9]+", note.lower())[:4]
    base = source.parent / f"{source.name}-{'-'.join(words) or 'variation'}"
    dest, n = base, 2
    while dest.exists():
        dest, n = Path(f"{base}-{n}"), n + 1
    return dest


def _keep_pass(name: str, from_stage: str) -> bool:
    if from_stage == "passes":
        return name == "out_blocking"
    return False


def _ignore(source: Path, from_stage: str):
    def ignore(folder: str, names: list[str]) -> set[str]:
        here = Path(folder)
        out = set()
        for n in names:
            top = here == source
            if top and (n in NEVER or n.endswith(NEVER_SUFFIX)):
                out.add(n)
            elif top and n.startswith("out_") and not _keep_pass(n, from_stage):
                out.add(n)
            elif n == "__pycache__":
                out.add(n)
        return out
    return ignore


def vary(source: Path, note: str, dest: Path | None = None, from_stage: str = "plan") -> Path:
    source = Path(source)
    if not note or not note.strip():
        raise SignOffError('a variation needs a note: kei vary <shot> --note "heavier crate, tired"')
    if from_stage not in FROM_STAGES:
        raise SignOffError(f"--from-stage is one of {', '.join(FROM_STAGES)}, not {from_stage!r}")
    state = load_state(source)
    if not (source / ".kei" / "state.json").is_file() or state.status != "done":
        raise SignOffError(f"{source} is not a signed-off shot (status {state.status}): a variation starts from an "
                           "approved shot")
    if from_stage == "blocking" and state.approved_plan is None:
        raise SignOffError(f"{source} has no approved plan to keep: start the variation at the plan")
    if from_stage == "passes" and not (source / "out_blocking" / "shot.json").is_file():
        raise SignOffError(f"{source} has no out_blocking/shot.json to keep: start the variation at blocking")
    dest = Path(dest) if dest else default_dest(source, note)
    if dest.exists():
        raise SignOffError(f"{dest} exists already: name another folder with --to")
    shutil.copytree(source, dest, ignore=_ignore(source, from_stage))
    entry = {"stage": from_stage, "attempt": 0, "result": "variation", "from": str(source.resolve()),
             "from_request": state.request, "notes": [f"Variation of the approved shot {source.name}: {note.strip()}"],
             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    new = ShotState(stage=from_stage, status="running", subjects=state.subjects,
                    request=f"{state.request} (variation: {note.strip()})", history=[entry])
    if from_stage in ("blocking", "passes"):
        from kei.plan_lock import approve_plan
        new.approved_plan = approve_plan(dest)
    save_state(dest, new)
    return dest
