"""Notes from several critics, merged before the animator reads them.

Two critics often send back the same fault in their own words, and now and then they pull opposite ways. A note's
frames (f12-18, frames 12 to 18, f40) and body part (from PARTS) are read from its text:
  - two notes from different critics on overlapping frames and the same part are one note: the first critic's words
    stay, and the other critic is named on it;
  - two such notes that ask for opposite things (OPPOSITES: faster and slower, higher and lower, more and less...) are
    a conflict: when a primary critic is set (limits.primary_critic), its note stands and the other is dropped with a
    word saying so; otherwise both are taken off the send-back list and become one question for the author.
A note with no frames or no part is kept as it is.
"""
from __future__ import annotations

import re

PARTS = ("head", "neck", "chest", "spine", "torso", "hips", "pelvis", "shoulder", "elbow", "wrist", "hand", "finger",
         "thumb", "knee", "ankle", "foot", "feet", "heel", "toe", "arm", "leg", "root", "crate", "box", "object")
OPPOSITES = (("faster", "slower"), ("higher", "lower"), ("more", "less"), ("wider", "narrower"), ("earlier", "later"),
             ("bigger", "smaller"), ("longer", "shorter"), ("raise", "lower"), ("forward", "back"),
             ("speed up", "slow down"), ("add", "remove"), ("increase", "reduce"))
_FRAMES = re.compile(r"\bf(?:rames?)?\s*(\d+)(?:\s*(?:-|to|–)\s*f?(\d+))?", re.I)
_LABEL = re.compile(r"^critic ([^:]+): (.*)$", re.S)


def _frames(text: str) -> tuple[int, int] | None:
    m = _FRAMES.search(text)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    return min(a, b), max(a, b)


def _parts(text: str) -> set[str]:
    low = text.lower()
    out = {p for p in PARTS if re.search(rf"\b{p}s?\b", low)}
    return {"foot" if p == "feet" else p for p in out}


def _wants(text: str) -> set[str]:
    low = text.lower()
    return {w for pair in OPPOSITES for w in pair if re.search(rf"\b{w}\b", low)}


def _opposed(a: str, b: str) -> bool:
    wa, wb = _wants(a), _wants(b)
    return any((x in wa and y in wb) or (y in wa and x in wb) for x, y in OPPOSITES)


def merge(notes: list[str], primary: str | None = None) -> tuple[list[str], list[dict]]:
    """The merged send-back notes, and the questions for the author that conflicts became."""
    items = []
    for n in notes:
        m = _LABEL.match(n)
        critic, body = (m.group(1), m.group(2)) if m else (None, n)
        items.append({"critic": critic, "body": body, "text": n, "frames": _frames(body), "parts": _parts(body),
                      "also": [], "drop": False})
    questions = []
    for i, a in enumerate(items):
        if a["drop"] or not a["frames"] or not a["parts"] or a["critic"] is None:
            continue
        for b in items[i + 1:]:
            if b["drop"] or not b["frames"] or b["critic"] in (None, a["critic"]):
                continue
            overlap = a["frames"][0] <= b["frames"][1] and b["frames"][0] <= a["frames"][1]
            if not overlap or not (a["parts"] & b["parts"]):
                continue
            if _opposed(a["body"], b["body"]):
                if primary in (a["critic"], b["critic"]):
                    keep, lose = (a, b) if a["critic"] == primary else (b, a)
                    lose["drop"] = True
                    keep["also"].append(f"critic {lose['critic']} asked the opposite; the primary critic's note "
                                        f"stands")
                else:
                    a["drop"] = b["drop"] = True
                    questions.append({"text": f"The critics disagree on f{a['frames'][0]}-{a['frames'][1]}: "
                                              f"{a['critic']} says \"{a['body']}\", {b['critic']} says "
                                              f"\"{b['body']}\". Which way should it go?", "look_at": [],
                                      "from": "Kei (critics disagree)"})
                    break
            else:
                b["drop"] = True
                a["also"].append(f"critic {b['critic']} said the same")
    out = []
    for it in items:
        if it["drop"]:
            continue
        out.append(it["text"] + (f" ({'; '.join(it['also'])})" if it["also"] else ""))
    return out, questions
