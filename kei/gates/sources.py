"""Names the author never wants in a shot: a private list of patterns, kept on the author's machine.

    load_banned(path) -> [(line number, compiled pattern)]
    source_misses(shot_dir, path) -> ["SRC ..."]

The list is a text file, one pattern per line (a regular expression, matched without case; a line that is not a valid
expression is matched as plain text), with # for comments. Kei ships no list: each author keeps their own, so the names
never travel with Kei. A miss names the file, the line and the list's line, never the banned name itself, so the name
does not reach the shot's history, the critics or the live page either.
"""
from __future__ import annotations

import re
from pathlib import Path

TEXT = {".md", ".json", ".txt", ".toml", ".csv"}
SKIP = {".kei", ".git", "__pycache__", "frames", "review"}
MAX_MISSES = 12


def load_banned(path: Path | None) -> list[tuple[int, re.Pattern]]:
    if path is None or not Path(path).is_file():
        return []
    out = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append((n, re.compile(line, re.I)))
        except re.error:
            out.append((n, re.compile(re.escape(line), re.I)))
    return out


def source_misses(shot_dir: Path, path: Path | None) -> list[str]:
    banned = load_banned(path)
    if not banned:
        return []
    shot_dir = Path(shot_dir)
    misses = []
    for p in sorted(shot_dir.rglob("*")):
        rel = p.relative_to(shot_dir)
        if p.suffix.lower() not in TEXT or SKIP.intersection(rel.parts) or not p.is_file():
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, text in enumerate(lines, 1):
            for n, pat in banned:
                if pat.search(text):
                    misses.append(f"SRC {rel.as_posix()} line {i} names a source on the author's banned-names list "
                                  f"(its line {n}): say what it teaches in your own words, without its title or "
                                  "author, and cite research by author and year")
                    break
            if len(misses) >= MAX_MISSES:
                return misses
    return misses
