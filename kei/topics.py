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


# The stages that make and judge the motion get the topics of their job in full, first; their other rules come as an
# index (ID, title, topic) that the agent reads one by one with `kei rule <ID>`. Sent whole, 300 rules drown the dozen
# that make the motion live: follow-through, overlap, spacing, arcs.
PRINCIPLE_TOPICS = ("overlap", "spacing", "arcs", "timing", "anticipation", "squash-stretch", "staging", "appeal",
                    "posing")
CORE: dict[str, tuple[str, ...]] = {
    "plan": ("posing", "staging", "timing", "anticipation", "appeal", "blocking", "weight"),
    "blocking": ("posing", "staging", "timing", "anticipation", "appeal", "blocking", "weight", "overlap"),
    "passes": ("overlap", "spacing", "arcs", "timing", "anticipation", "squash-stretch", "appeal", "weight", "posing"),
    "checks": ("review",) + PRINCIPLE_TOPICS,
    "self_review": ("review",) + PRINCIPLE_TOPICS,
}


def critic_block(stage_id: str, topics: list[Topic], lessons: list[Rule], subjects: list[str] | None,
                 book: Path | None = None) -> str:
    """The rules a critic gets: every rule the stage's animator gets, as a checklist by ID and title, grouped by topic
    with the file that holds its full text, and the author's local lessons in full. The animator's full rule text
    (about 150k characters at blocking and passes) costs every critic call and invites small notes; the critic reads
    the full text of the rules it judges by from the files."""
    every = subjects is None or ALL in subjects
    lines = ["The rules of this stage, by ID and title. Judge the work against them. The full text of each rule is in "
             "its topic's file below: read the ones you judge by, before you write a note on them."]
    for t in topics:
        if not (t.kind == "principle" or every or t.name in subjects):
            continue
        rules = rules_for(t.rules, stage_id)
        if not rules:
            continue
        where = ""
        if book is not None:
            p = Path(book)
            where = f" ({(p / (t.name + '.md')).as_posix() if p.is_dir() else p.as_posix()})"
        lines += ["", f"{t.title}{where}:"] + [f"- {r.id}. {r.title}" for r in rules]
    mine = rules_for(lessons, stage_id)
    if mine:
        lines += ["", rules_block(mine).replace("Rules for this stage:", "The author's own lessons, in full:")]
    return "\n".join(lines)


def stage_block(stage_id: str, topics: list[Topic], lessons: list[Rule], subjects: list[str] | None) -> str:
    """The rules one stage gets. subjects None or containing all means every subject topic. A stage in CORE gets its
    core topics, the subjects the shot named and the local lessons in full, and the rest of its rules as an index."""
    every = subjects is None or ALL in subjects
    core = CORE.get(stage_id)
    if core and not any(t.name in core for t in topics):
        core = None              # a book of other topics than Kei's own: every rule in full, as before
    full: list[Rule] = []
    index: list[tuple[Rule, str]] = []
    for t in topics:
        if not (t.kind == "principle" or every or t.name in subjects):
            continue
        named = t.kind == "subject" and not every and t.name in subjects
        if core is None or t.name in core or named:
            full += t.rules
        else:
            index += [(r, t.name) for r in rules_for(t.rules, stage_id)]
    text = rules_block(rules_for(full + lessons, stage_id))
    if index:
        text += ("\n\nMore rules for this stage, by title. Read any that bear on what you are doing with "
                 "`kei rule <ID> [<ID> ...]` before you decide it:\n"
                 + "\n".join(f"- {r.id}. {r.title} ({topic})" for r, topic in index))
    return text
