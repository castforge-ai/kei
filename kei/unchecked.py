"""The (unchecked) marks: numbers about the real world that nobody read in a source during the shot.

Kei counts them itself, in the shot's written files (PLAN.md, REFS.md and the other notes at the top of the shot), so
the agent never keeps a tally and the critics never spend a note on a mark. kei status prints the count; the critics'
prompt gives the count and the list and tells them the marks are Kei's bookkeeping, not a fault.
"""
from __future__ import annotations

import re
from pathlib import Path

MARK = re.compile(r"\(unchecked\)", re.I)
FILES = ("PLAN.md", "REFS.md", "EXTENT.md", "CHARACTER.md", "QUESTIONS.md", "GATES.md", "CHECKS.md")


def unchecked(shot_dir: Path) -> list[dict]:
    """Every (unchecked) mark: {"file", "line", "text"} with the text of its line, shortened."""
    out = []
    for name in FILES:
        p = Path(shot_dir) / name
        if not p.is_file():
            continue
        try:
            lines = p.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(lines, start=1):
            for _ in MARK.finditer(line):
                out.append({"file": name, "line": i, "text": line.strip()[:160]})
    return out


def critic_lines(shot_dir: Path, shown: int = 12) -> list[str]:
    marks = unchecked(shot_dir)
    if not marks:
        return []
    lines = [f"Kei counted {len(marks)} (unchecked) number(s) in the shot's files: facts nobody read in a source "
             "during this shot. The author sees them. Do not send the stage back over a mark; note it only when a "
             "decision rests on an unchecked number that matters."]
    lines += [f"- {m['file']}:{m['line']}: {m['text']}" for m in marks[:shown]]
    if len(marks) > shown:
        lines.append(f"- and {len(marks) - shown} more")
    return lines
