"""This repository becomes public: no tracked file may point at private sources or say whose rules these are."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN = [r"\bfounder\b", r"day-job", r"CRAFT\.md", r"training school", r"—"]
# Kei was trained as a traditional animator: no tracked file presents a book, course, school, class or tutorial as a
# source. The patterns are narrow on purpose, so "of course", "the rule book" and code classes never match.
SCHOOLING = [r"\b(animation|training|online|drawing|art) (books?|courses?|schools?|class(es)?|lessons?)\b",
             r"\btutorials?\b", r"\bcourses? (of study|material)\b", r"\btextbooks?\b", r"\binstructors?\b",
             r"\bteachers?\b", r"\bcurricul(um|a)\b", r"\blesson plans?\b", r"\bhomework\b",
             r"\b(book|course|school)s? (or|and) (book|course|school|class)(es|s)?\b",
             r"\blearned (it )?from (a|an|the) (book|course|school|class|teacher)"]


def tracked_text_files():
    names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for n in names.splitlines():
        p = ROOT / n
        if p.suffix in {".py", ".md", ".toml", ".sh", ".txt", ".html", ".js", ".css", ""} and p.is_file() and p.name != Path(__file__).name:
            yield p


def test_no_private_pointers_in_tracked_files():
    hits = []
    for p in tracked_text_files():
        text = p.read_text(encoding="utf-8", errors="replace")
        for pat in FORBIDDEN + SCHOOLING:
            for m in re.finditer(pat, text, re.I):
                hits.append(f"{p.relative_to(ROOT)}: {m.group(0)!r}")
    assert hits == []


def test_the_schooling_patterns_catch_a_source_and_spare_ordinary_words():
    def hit(s):
        return any(re.search(p, s, re.I) for p in SCHOOLING)
    for bad in ("an animation course", "a walk tutorial", "a book or course about walks", "learned from a teacher"):
        assert hit(bad), bad
    for ok in ("of course", "in the course of a walk", "the rule book", "class Rig:", 'class="app"', "a weight class"):
        assert not hit(ok), ok
