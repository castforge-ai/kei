"""Which rules a stage gets: every principle topic, the subject topics the shot names, and the local lessons.

The brief names the subjects in PLAN.md ("Subjects: locomotion, arms-hands", or "all"). The set only grows: what the
brief named is kept in the shot state, and a later line can add subjects but never remove one. When in doubt Kei sends
more rules, never fewer: the brief itself gets every subject, and a shot with no recorded subjects gets every subject.
"""
from __future__ import annotations

import re
from pathlib import Path

from kei.book import ALL, Rule, Topic, rules_block, rules_for

# "Subjects: a, b" at the start of a line, also as a bullet, in bold, or in lower case.
_LINE = re.compile(r"^[ \t>*+-]*\**subjects\**[ \t]*:[ \t]*\**(.*)$", re.I | re.M)


def subject_names(topics: list[Topic]) -> list[str]:
    return [t.name for t in topics if t.kind == "subject"]


def shot_subjects(shot_dir: Path) -> list[str] | None:
    """Every name on every Subjects line of PLAN.md, in order, once each. None when there is no such line."""
    plan = Path(shot_dir) / "PLAN.md"
    if not plan.is_file():
        return None
    lines = _LINE.findall(plan.read_text(encoding="utf-8"))
    if not lines:
        return None
    names: list[str] = []
    for line in lines:
        for s in line.replace("*", "").split(","):
            s = s.strip()
            if s and s not in names:
                names.append(s)
    return names


def effective_subjects(recorded: list[str] | None, current: list[str] | None) -> list[str] | None:
    """The subjects a stage gets: the recorded set plus anything the current line adds. None means every subject."""
    if recorded is None:
        return None
    names = list(recorded) + [s for s in (current or []) if s not in recorded]
    return None if ALL in names else names


def subject_misses(shot_dir: Path, topics: list[Topic], required: bool) -> list[str]:
    """The Subjects line must name known topics; at the brief it must also exist. No subject topics, no check."""
    names = subject_names(topics)
    if not names:
        return []
    valid = ", ".join(names)
    chosen = shot_subjects(shot_dir)
    if not chosen:
        if not required:
            return []
        return [f'P1 PLAN.md needs a line "Subjects: <names>" naming the subject topics this shot needs, '
                f"or all: {valid}"]
    bad = [s for s in chosen if s != ALL and s not in names]
    if bad:
        return [f"P1 PLAN.md Subjects names unknown topics: {', '.join(bad)}; use some of: {valid}, or all"]
    return []


def subject_index(topics: list[Topic]) -> str:
    rows = [f"- {t.name}: {t.title}" for t in topics if t.kind == "subject"]
    if not rows:
        return ""
    return ('Subject topics. Name the ones this shot needs on a line "Subjects: <names>" in PLAN.md, or write '
            '"Subjects: all". When unsure, include the topic:\n' + "\n".join(rows))


def stage_block(stage_id: str, topics: list[Topic], lessons: list[Rule], subjects: list[str] | None) -> str:
    """The rules one stage gets. subjects None or containing all means every subject topic."""
    every = subjects is None or ALL in subjects
    rules: list[Rule] = []
    for t in topics:
        if t.kind == "principle" or every or t.name in subjects:
            rules += t.rules
    return rules_block(rules_for(rules + lessons, stage_id))
