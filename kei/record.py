"""KEI_RECORD.md: the shot's bookkeeping, written by Kei from its own state, never by the agent.

The benchmark's critics spent most of their record notes on paperwork: stale stage lines, version numbers, file
pointers and placeholders the agents kept by hand (57 of Claude's 87, 19 of GPT's 28). Kei knows all of it already.
Before every review it writes KEI_RECORD.md at the top of the shot: the stage and its tries, each pass with its keys,
frames, a hash of its shot.json and its open flags, the files a reviewer opens, and the (unchecked) count. The
animator does not keep stage or version lines, and the critics judge none of it.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

NAME = "KEI_RECORD.md"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def _passes(shot: Path) -> list[Path]:
    def order(p: Path):
        n = p.name[len("out_p"):]
        return (0, 0) if p.name == "out_blocking" else (1, int(n)) if n.isdigit() else (2, 0)
    found = [p for p in shot.glob("out_*") if (p / "shot.json").is_file()
             and (p.name == "out_blocking" or p.name[len("out_p"):].isdigit())]
    return sorted(found, key=order)


def _count(path: Path, key: str = "flags") -> int | None:
    try:
        return len(json.loads(path.read_text(encoding="utf-8")).get(key) or [])
    except (OSError, ValueError):
        return None


def write_record(shot_dir: Path, state) -> Path:
    """Write KEI_RECORD.md from the shot's state and folders. Returns its path."""
    from kei.gates.pipeline import open_flags
    from kei.stages import stage_by_id
    from kei.unchecked import unchecked
    shot = Path(shot_dir)
    gates = (shot / "GATES.md").read_text(encoding="utf-8") if (shot / "GATES.md").is_file() else ""
    try:
        title = stage_by_id(state.stage).title
    except Exception:   # noqa: BLE001
        title = state.stage
    lines = ["# Kei's record", "",
             "Written by Kei from its own state before each review. Do not edit it, and do not keep stage, version or",
             "hash lines in PLAN.md or GATES.md: this file is the record.", "",
             f"- Stage: {title} ({state.stage}), status {state.status}",
             f"- Tries at this stage: {state.attempts}; send-backs: {state.send_backs}",
             f"- Written: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", "",
             "## Passes", "",
             "| pass | frames | keys | shot.json | body flags | principle flags open | files |",
             "|---|---|---|---|---|---|---|"]
    for p in _passes(shot):
        try:
            data = json.loads((p / "shot.json").read_text(encoding="utf-8"))
            frames, keys = data.get("frames", "?"), len(data.get("keys") or [])
        except (OSError, ValueError):
            frames, keys = "?", "?"
        body = _count(p / "body_check" / "body_check.json")
        pr_path = p / "principles" / "principles.json"
        try:
            open_n = len(open_flags(json.loads(pr_path.read_text(encoding="utf-8")).get("flags") or [], gates))
        except (OSError, ValueError):
            open_n = None
        files = [f.name for f in (p / "playback.mp4", p / "blocking.mp4", p / "keys.png") if f.is_file()]
        files += [f"poses/{f.name}" for f in sorted((p / "poses").glob("pose_sheet*.png"))]
        lines.append(f"| {p.name[len('out_'):]} | {frames} | {keys} | {_sha(p / 'shot.json')} | "
                     f"{'-' if body is None else body} | {'-' if open_n is None else open_n} | "
                     f"{', '.join(files) or '-'} |")
    plan = [f for f in ("plan/plan.json", "plan/plan_sheet.png", "PLAN.md", "REFS.md", "GATES.md") if (shot / f).is_file()]
    marks = unchecked(shot)
    lines += ["", "## Files", "", *[f"- {f} ({_sha(shot / f)})" for f in plan], "",
              f"## Unchecked numbers: {len(marks)}", ""]
    lines += [f"- {m['file']}:{m['line']}" for m in marks[:30]]
    dst = shot / NAME
    dst.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return dst
