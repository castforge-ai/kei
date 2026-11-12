"""A maintainer's review of a shared lesson. The bundle is checked before anything is drawn; both cases are drawn
on the reference character; Kei measures them again on this machine and shows its numbers beside the bundle's,
flagging every difference. The verdict goes into the lesson folder. The page never merges and never pushes."""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from kei.book import BookError, load_topics, parse_book
from kei.review.drawings import write_drawings
from kei.review.rounds import case_rounds
from kei.share import (CHECKS, VERDICT, VERDICT_DRAWINGS, BundleError, _case, check_bundle, kei_version,
                       measure_case)

VERDICTS = ("accept", "needs_work", "reject")
STOP = {"that", "this", "with", "from", "when", "into", "over", "under", "keep", "never", "every", "each", "they",
        "them", "their", "have", "your", "what", "than", "then", "there", "only", "must", "does", "will", "after",
        "before", "stage", "rule", "shot", "frame", "frames", "pass", "passes", "same", "more", "less", "also"}
OVERLAP_WORDS = 3


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4 and w not in STOP}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LessonRoutes:
    def __init__(self, bundle: Path, book: Path, renders: Path, runner: Callable[[list[str]], int] | None = None,
                 author: str = "", size: int = 360):
        self.bundle = Path(bundle)
        self.meta = check_bundle(self.bundle)          # a bad bundle is refused here, with its reason
        self.book = Path(book)
        self.runner = runner                            # kept for gh reads only; the page never pushes or merges
        self.author = author
        md = (self.bundle / "lesson.md").read_text(encoding="utf-8")
        rules = parse_book(md, "lesson.md")
        if len(rules) != 1:
            raise BundleError("lesson.md must hold exactly one lesson")
        self.rule = rules[0]
        self.renders = Path(renders) / self.bundle.name     # the drawn cases; outside the bundle
        self.rounds = case_rounds(self.bundle, self.renders, size, prefix="lesson")
        self.numbers = json.loads((self.bundle / "numbers.json").read_text(encoding="utf-8"))
        self.own = {c: measure_case(_case(self.bundle / "cases" / c / "shot.json", c)) for c in ("fails", "passes")}
        self.routes = {"GET /api/mode": lambda req: (200, {"mode": "lesson"}),
                       "GET /api/lesson": lambda req: (200, self.lesson()),
                       "POST /api/lesson/verdict": self.verdict}

    def files(self) -> dict[str, Path]:
        out = {}
        for case, meta in self.rounds.items():
            frames = self.renders / case / "frames"
            out.update({f"{meta['round']}/{p.stem}": p for p in sorted(frames.glob("f*.png"))})
        return out

    # -- what the page shows --------------------------------------------------------------------------------------
    def _rows(self) -> list[dict]:
        rows = []
        for case in ("fails", "passes"):
            theirs = (self.numbers.get(case) or {}).get("counts", {}) if isinstance(self.numbers, dict) else {}
            ours = self.own[case]["counts"]
            for check in CHECKS:
                if check in theirs or check in ours:
                    a, b = theirs.get(check, 0), ours.get(check, 0)
                    rows.append({"case": case, "check": check, "bundle": a, "kei": b, "differs": a != b})
        return rows

    def _overlap(self) -> list[dict]:
        mine = _words(self.rule.title + " " + self.rule.text)
        out = []
        try:
            topics = load_topics(self.book)
        except BookError:
            return []
        for t in topics:
            for r in t.rules:
                if not ("all" in r.stages or "all" in self.rule.stages or set(r.stages) & set(self.rule.stages)):
                    continue
                shared = sorted(mine & _words(r.title + " " + r.text))
                if len(shared) >= OVERLAP_WORDS:
                    out.append({"id": r.id, "title": r.title, "topic": t.name, "words": shared})
        return sorted(out, key=lambda o: -len(o["words"]))

    def lesson(self) -> dict:
        rows = self._rows()
        verdict = None
        if (self.bundle / VERDICT).is_file():
            verdict = json.loads((self.bundle / VERDICT).read_text(encoding="utf-8"))
        return {"lesson": self.rule.id, "title": self.rule.title, "text": self.rule.text,
                "stage": ",".join(self.rule.stages), "author": self.author, "rounds": self.rounds,
                "check": self.numbers.get("check"), "measured": bool(self.numbers.get("measured")),
                "numbers": rows, "any_differs": any(r["differs"] for r in rows), "overlap": self._overlap(),
                "files": {"lesson.md": (self.bundle / "lesson.md").read_text(encoding="utf-8")},
                "verdict": verdict, "verdicts": list(VERDICTS)}

    # -- the verdict ---------------------------------------------------------------------------------------------
    def _next_id(self, topics, path: Path) -> str:
        """The next free ID in the prefix of the topic the rule lands in (the book's most used prefix when that
        topic has none). A book with no numbered IDs at all starts at K1."""
        ids = [r.id for t in topics for r in t.rules]

        def parsed(names):
            return [m.groups() for m in (re.fullmatch(r"([A-Za-z]+)(\d+)", i) for i in names) if m]
        here = parsed([r.id for t in topics if self.book.is_file() or t.name == path.stem for r in t.rules])
        every = parsed(ids)
        if not every:
            return "K1"
        prefixes = [p for p, _ in (here or every)]
        prefix = max(set(prefixes), key=prefixes.count)
        n = max(int(d) for p, d in every if p == prefix) + 1
        while f"{prefix}{n}" in ids:
            n += 1
        return f"{prefix}{n}"

    def _topic_file(self, topics) -> Path:
        if self.book.is_file():
            return self.book
        overlap = self._overlap()
        if overlap:
            return self.book / f"{overlap[0]['topic']}.md"
        principle = [t for t in topics if t.kind == "principle"]
        return self.book / f"{(principle or topics)[0].name}.md"

    def _add_rule(self) -> str:
        topics = load_topics(self.book)
        path = self._topic_file(topics)
        rid = self._next_id(topics, path)
        title = self.rule.title.replace(" (provisional)", "").strip()
        block = f"### {rid}. {title}\nstages: {', '.join(self.rule.stages)}\n\n{self.rule.text.strip()}\n"
        old = path.read_text(encoding="utf-8")
        new = old.rstrip("\n") + "\n\n" + block
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(new, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
        try:
            load_topics(self.book)       # the book must still read; else it goes back as it was
        except BookError:
            path.write_text(old, encoding="utf-8", newline="\n")
            raise
        return rid

    def verdict(self, req) -> tuple[int, dict]:
        body = req["body"] if isinstance(req.get("body"), dict) else {}
        verdict = body.get("verdict")
        if verdict not in VERDICTS:
            return 400, {"error": f"the verdict is one of {', '.join(VERDICTS)}"}
        text = body.get("text") if isinstance(body.get("text"), str) else ""
        old = self.lesson()["verdict"]
        if old and old.get("rule"):
            raise BundleError(f"this lesson was accepted already as {old['rule']}")
        drawings = body.get("drawings") or []
        written: list[str] = []
        if drawings:
            if not isinstance(drawings, dict):
                return 400, {"error": "drawings must be an object with strokes and pngs"}
            pngs = {}
            for key, data in (drawings.get("pngs") or {}).items():
                try:
                    pngs[key] = base64.b64decode(data, validate=True)
                except (TypeError, ValueError, binascii.Error):
                    return 400, {"error": f"the picture {key} is not base64"}
            fails = self.rounds["fails"]
            written = write_drawings(self.bundle / VERDICT_DRAWINGS, VERDICT_DRAWINGS, fails["round"],
                                     int(fails["frames"]), drawings.get("strokes") or [], pngs)
        record = {"verdict": verdict, "text": text, "at": _now(), "kei_version": kei_version(), "drawings": written}
        if verdict == "accept":
            record["rule"] = self._add_rule()
            record["book"] = str(self._topic_file(load_topics(self.book)).name)
        tmp = self.bundle / (VERDICT + ".tmp")
        tmp.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.bundle / VERDICT)
        return 200, record
