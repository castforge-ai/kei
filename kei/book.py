"""The rule book: plain Markdown, one ### heading per rule, a stages: line under it. Each stage gets only its rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from kei.stages import STAGES

BUNDLED_BOOK = Path(__file__).resolve().parent / "book"   # a folder of topic files: the default book
ALL = "all"
_HEADING = re.compile(r"^### (\S+)\. (.+)$")
_STAGE_IDS = {s.id for s in STAGES}


class BookError(ValueError):
    """The book cannot be read. The message names the file and the rule."""


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    stages: tuple[str, ...]   # ("all",) means every stage
    text: str
    scope: str = ""           # a local lesson: "this shot" or "every shot" (a rule); "" in the book and older lessons
    shot: str = ""            # a "this shot" lesson: the shot folder it is about; "" in the book and older lessons


def _rule(lines: list[str], source: str) -> Rule:
    head = _HEADING.match(lines[0])
    if head is None:
        raise BookError(f"{source}: {lines[0]!r} is not a rule heading (### <ID>. <title>)")
    rid, title = head.group(1), head.group(2).strip()
    if len(lines) < 2 or not lines[1].startswith("stages:"):
        raise BookError(f"{source}: rule {rid} has no stages: line right under its heading")
    stages = tuple(s.strip() for s in lines[1][len("stages:"):].split(",") if s.strip())
    if not stages:
        raise BookError(f"{source}: rule {rid} lists no stage on its stages: line")
    for s in stages:
        if s != ALL and s not in _STAGE_IDS:
            raise BookError(f"{source}: rule {rid} names an unknown stage {s!r}")
    scope, body = "", lines[2:]
    if body and body[0].startswith("scope:"):
        scope, body = body[0][len("scope:"):].strip(), body[1:]
    shot = ""
    if scope and body and body[0].startswith("shot:"):
        shot, body = body[0][len("shot:"):].strip(), body[1:]
    return Rule(rid, title, stages, "\n".join(body).strip(), scope, shot)


THIS_SHOT = "this shot"


def shot_key(shot: Path) -> str:
    """How a "this shot" lesson names its shot: the shot folder's full path, written with forward slashes."""
    return Path(shot).resolve().as_posix()


def lessons_for_shot(lessons: list[Rule], shot: Path) -> list[Rule]:
    """The local lessons that apply to this shot: every rule, and the "this shot" lessons of this shot only. A
    "this shot" lesson from before lessons named their shot applies everywhere, as it always did."""
    key = shot_key(shot)
    return [r for r in lessons if r.scope != THIS_SHOT or not r.shot or r.shot == key]


def parse_book(text: str, source: str) -> list[Rule]:
    """Every rule in the text, in order. Text before the first ### heading is a preamble."""
    rules: list[Rule] = []
    block: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("### "):
            if block is not None:
                rules.append(_rule(block, source))
            block = [line]
        elif block is not None:
            block.append(line)
    if block is not None:
        rules.append(_rule(block, source))
    return rules


def load_rules(paths: list[Path]) -> list[Rule]:
    """The rules of each file that exists, in the order given. An ID used twice is refused."""
    rules: list[Rule] = []
    seen: dict[str, Path] = {}
    for path in paths:
        path = Path(path)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")   # a BOM from Notepad must not hide the first rule
        except (OSError, UnicodeDecodeError) as e:
            raise BookError(f"cannot read the rule book {path}: {e}") from e
        for r in parse_book(text, str(path)):
            if r.id in seen:
                raise BookError(f"rule {r.id} is in {seen[r.id]} and again in {path}")
            seen[r.id] = path
            rules.append(r)
    return rules


def rules_for(rules: list[Rule], stage_id: str) -> list[Rule]:
    return [r for r in rules if ALL in r.stages or stage_id in r.stages]


def rules_block(rules: list[Rule]) -> str:
    if not rules:
        return ""
    return "Rules for this stage:\n\n" + "\n\n".join(f"### {r.id}. {r.title}\n{r.text}" for r in rules)


KINDS = ("principle", "subject")


@dataclass(frozen=True)
class Topic:
    name: str
    kind: str      # "principle": every stage gets it; "subject": only shots that name it
    title: str
    rules: list[Rule]


def _topic(path: Path, single: bool) -> Topic:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as e:
        raise BookError(f"cannot read the rule book {path}: {e}") from e
    preamble = "" if text.startswith("### ") else text.split("\n### ", 1)[0]
    title = next((ln[2:].strip() for ln in preamble.splitlines() if ln.startswith("# ")), path.stem)
    kind = next((ln[5:].strip() for ln in preamble.splitlines() if ln.startswith("kind:")), None)
    if single:
        kind = "principle"   # a one-file book is all principle: every stage gets all of it
    if kind is None:
        if not single:
            raise BookError(f"{path}: a topic file needs a line kind: principle or kind: subject before its first rule")
        kind = "principle"
    if kind not in KINDS:
        raise BookError(f"{path}: unknown kind {kind!r}: use principle or subject")
    return Topic(path.stem, kind, title, parse_book(text, str(path)))


def load_topics(path: Path) -> list[Topic]:
    """A folder of topic files (one topic each, by file name), or one file read as a single principle topic."""
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob("*.md"))
        if not files:
            raise BookError(f"the rule book folder {path} has no topic files")
        topics = [_topic(f, single=False) for f in files]
        if any(t.name == ALL for t in topics):
            raise BookError(f"{path}: a topic may not be named {ALL}.md, the word is reserved for every subject")
    elif path.is_file():
        topics = [_topic(path, single=True)]
    else:
        raise BookError(f"the rule book {path} does not exist: fix book.path in kei.toml")
    seen: dict[str, str] = {}
    for t in topics:
        for r in t.rules:
            if r.id in seen:
                raise BookError(f"rule {r.id} is in {seen[r.id]} and again in {t.name}")
            seen[r.id] = t.name
    return topics
