"""Local lessons: a person's note becomes a provisional rule in their own install, from the next shot on.

A local lesson gets a local ID (local.1, local.2, ...), never a permanent one. Permanent IDs are given only when a
reviewed lesson joins the shared book.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from kei.book import ALL, THIS_SHOT, BookError, parse_book, shot_key
from kei.stages import STAGES

PREAMBLE = "# Local lessons\n\nProvisional lessons from your own notes. They apply to your shots only.\n"
TITLE_CHARS = 80
SCOPES = {"shot": "this shot", "every": "every shot"}   # a note's scope: this shot (default), or a rule for every shot
_LOCAL_ID = re.compile(r"^### local\.(\d+)\. ", re.M)


def _title(note: str) -> str:
    first = next((line.strip().lstrip("#").strip() for line in note.splitlines() if line.strip()), "")
    return (first or "a note")[:TITLE_CHARS]


def _body(note: str) -> str:
    """The note as the lesson text. A line that would start a new rule is indented so the file stays one lesson."""
    return "\n".join(f"  {line}" if line.startswith("###") else line for line in note.strip().splitlines())


def scope_name(scope: str) -> str:
    """this shot or every shot, from either form ("shot", "every", "this shot", "every shot")."""
    name = SCOPES.get(scope, scope)
    if name not in SCOPES.values():
        raise BookError(f"unknown scope {scope!r}: use this shot or every shot")
    return name


def _words(text: str) -> str:
    return " ".join(text.split()).casefold()


def same_lesson(path: Path, note: str, stage_id: str, scope: str = "shot", shot: Path | None = None) -> str | None:
    """The ID of a lesson in the file that already says this note, for the same stage, scope and shot, else None.
    Spacing and letter case do not make two lessons different."""
    path = Path(path)
    if not path.is_file():
        return None
    scope = scope_name(scope)
    key = shot_key(shot) if shot is not None and scope == THIS_SHOT else ""
    words = _words(_body(note))
    for r in parse_book(path.read_text(encoding="utf-8-sig"), str(path)):
        if r.stages == (stage_id,) and r.scope == scope and r.shot == key and _words(r.text) == words:
            return r.id
    return None


def add_lesson(path: Path, note: str, stage_id: str, scope: str = "shot", shot: Path | None = None) -> str:
    """Append the note as a provisional local lesson for one stage (or all), with its scope: this shot (the
    default) or every shot (a rule, the only kind that can be shared). shot: the shot a "this shot" lesson is
    about, so it reaches no other shot. A note the file already holds is not written again: its lesson's ID comes
    back instead (same_lesson). Returns the local ID."""
    scope = scope_name(scope)
    if stage_id != ALL and stage_id not in {s.id for s in STAGES}:
        raise BookError(f"unknown stage {stage_id!r}: use one of {', '.join(s.id for s in STAGES)}, or all")
    path = Path(path)
    held = same_lesson(path, note, stage_id, scope, shot)
    if held is not None:
        return held
    old = path.read_text(encoding="utf-8-sig") if path.is_file() else PREAMBLE
    n = max((int(m) for m in _LOCAL_ID.findall(old)), default=0) + 1
    lesson_id = f"local.{n}"
    shot_line = f"shot: {shot_key(shot)}\n" if shot is not None and scope == THIS_SHOT else ""
    block = (f"### {lesson_id}. {_title(note)} (provisional)\nstages: {stage_id}\nscope: {scope}\n{shot_line}\n"
             f"{_body(note)}\n")
    new = old.rstrip("\n") + "\n\n" + block
    parse_book(new, str(path))   # refuse a write that would leave the file unreadable
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new, encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return lesson_id


_HEADING = re.compile(r"^### ", re.M)


def remove_lesson(path: Path, lesson_id: str, created: bool = False) -> bool:
    """Take a local lesson out of the file again, as if it had never been added (kei note --undo): the file holds
    what it held before, byte for byte, when add_lesson wrote it. created: the lesson's note made the file, so a file
    left with only the preamble is removed. Returns False when the lesson is not in the file."""
    path = Path(path)
    if not path.is_file():
        return False
    text = path.read_bytes().decode("utf-8")
    m = re.search(rf"^### {re.escape(lesson_id)}\. ", text, re.M)
    if not m:
        return False
    nxt = _HEADING.search(text, m.end())
    new = text[:m.start()] + text[nxt.start():] if nxt else text[:m.start()].rstrip("\n") + "\n"
    if created and new == PREAMBLE:
        path.unlink()
        return True
    parse_book(new, str(path))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(new.encode("utf-8"))
    os.replace(tmp, path)
    return True
