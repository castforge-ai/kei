"""The author's sign-off checklist as a person reads it: only the critics' checks about the pass being signed off,
the same request from two critics merged into one item, plain words first. Every check stays in state.json; this
only chooses what is shown (kei status, kei run and the review page all use it). Nothing here ticks anything."""
from __future__ import annotations

import re
from pathlib import Path

_PREFIX = re.compile(r"^\s*author viewing at sign-off:\s*", re.I)
_ID = r"(?:[A-Z]{2,}\d+|local\.\d+)"
_IDS = re.compile(rf"^({_ID}(?:\s*[,/]\s*{_ID})*)\s*:\s*")
_PATH = re.compile(r"\bout_([A-Za-z0-9_]+)/[\w./-]*[\w]")
_FRAME = re.compile(r"\b[fF](\d+)(?:\s*[-–/→]\s*[fF]?(\d+))?\b")
_STOP = {"watch", "confirm", "reads", "read", "play", "with", "that", "this", "from", "into", "over", "each", "they",
         "than", "then", "whether", "still", "check", "checking", "at", "fps", "loop", "loops", "playback", "times",
         "row", "repeats", "camera", "delivery", "compare", "rather", "full", "speed", "frame", "frames"}


WORDING = ('"Frame 13-18: the left hand\'s arc looks off": the frames, the body part and what to look at, in '
           f"12 words or fewer, with no rule ID, file name or critic name")
MAX_WORDS = 12
_LEAD = re.compile(r"^Frames? (\d+)(?:\s*-\s*(\d+))?: \S")
_FILE = re.compile(r"\b\w+\.(?:mp4|png|gif|json|md|txt|glb|fbx)\b|\bout_\w+|/")


def check_wording(check: str) -> str | None:
    """Why a sign-off check is not in the author's plain wording, or None when it is."""
    text = check.strip()
    if not _LEAD.match(text):
        return 'it must start with the frames, as "Frame 13-18: "'
    if re.search(rf"\b{_ID}\b", text):
        return "it names a rule ID; say what to look at instead"
    if _FILE.search(text):
        return "it names a file; say the frames and the body part instead"
    if re.search(r"\bcritic\b", text, re.I):
        return "it names a critic; the check speaks for itself"
    if len(text.split()) > MAX_WORDS:
        return f"it is {len(text.split())} words; keep it to {MAX_WORDS} words or fewer"
    return None


def frame_range(check: str) -> list[int] | None:
    """[first, last] from "Frame 13-18: ..." (or the first frame reference in an older check), else None."""
    m = _LEAD.match(check.strip()) or _FRAME.search(_PREFIX.sub("", check))
    if not m:
        return None
    a = int(m.group(1))
    return [a, int(m.group(2)) if m.group(2) else a]


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4 and w not in _STOP}


def _frames(text: str) -> set[int]:
    out = set()
    for a, b in _FRAME.findall(text):
        out.add(int(a))
        if b:
            out.add(int(b))
    return out


def _video_label(path: str) -> str:
    camera = "delivery camera" if "/delivery/" in path else "follow camera" if "/follow/" in path else "four views"
    return ("ten loops, " if "_x10" in path else "") + camera


def parse_check(check: str) -> dict:
    """Plain words, rule IDs, the passes it names, and the parts the page turns into buttons."""
    rest = _PREFIX.sub("", check).strip()
    rules: list[str] = []
    m = _IDS.match(rest)
    if m:
        rules = re.findall(_ID, m.group(1))
        rest = rest[m.end():]
    passes = set(_PATH.findall(rest))
    videos = list(dict.fromkeys(p.group(0) for p in _PATH.finditer(rest)))
    text = _PATH.sub("\x00", rest)
    text = re.sub(r"(?:\s*(?:,|\band\b|\bin\b|\bwith\b)?\s*\x00)+", "", text)    # "in <path> and <path>" goes
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+([,;.:?)])", r"\1", re.sub(r"\s{2,}", " ", text)).strip(" ,;")
    text = re.sub(r"\b(?:in|and)\s*([;.])", r"\1", text).strip(" ,;")
    text = re.sub(r"^(?:watch|play)\s*[;:,]\s*", "", text, flags=re.I)    # its video went to a button
    if not _FRAME.match(text):          # "f19-f24, ..." keeps its frame reference as written
        text = text[:1].upper() + text[1:]
    parts = [{"t": text}]
    for v in videos:
        if {"play": _video_label(v)} not in parts:
            parts.append({"play": _video_label(v)})
    for a, b in _FRAME.findall(rest):
        part = {"frame": int(a), "label": f"f{a}" + (f"-f{b}" if b else "")}
        if not any(x.get("frame") == part["frame"] for x in parts):
            parts.append(part)
    return {"text": text, "rules": rules, "passes": passes, "parts": parts, "words": _words(text),
            "frames": _frames(rest), "range": frame_range(check)}


def _same(a: dict, b: dict) -> bool:
    ra, rb = a.get("range"), b.get("range")
    if ra and rb and (ra[1] < rb[0] or rb[1] < ra[0]):
        return False                      # different frames: a different question, however alike the words
    shared = a["words"] & b["words"]
    if a["frames"] & b["frames"] and len(shared) >= 2:
        return True
    small = min(len(a["words"]), len(b["words"]))
    return small > 0 and len(shared) / small >= 0.5


def current_checks(sign_off: list[dict], pass_name: str | None) -> list[dict]:
    """The checks about pass_name (or naming no pass at all), the same request merged. Each item lists the
    original check texts it stands for: ticking the item ticks those."""
    groups: list[dict] = []
    for item in sign_off:
        p = parse_check(item.get("check", ""))
        if pass_name is not None and p["passes"] and pass_name not in p["passes"]:
            continue
        who, stage = item.get("from", "a critic"), item.get("stage", "")
        for g in groups:
            if _same(g, p):
                g["checks"].append(item["check"])
                g["from"] += [who] if who not in g["from"] else []
                g["stages"] += [stage] if stage not in g["stages"] else []
                g["rules"] += [r for r in p["rules"] if r not in g["rules"]]
                g["parts"] += [x for x in p["parts"][1:] if x not in g["parts"]
                               and not ("frame" in x and any(y.get("frame") == x["frame"] for y in g["parts"]))]
                g["words"] |= p["words"]
                g["frames"] |= p["frames"]
                break
        else:
            groups.append({**p, "checks": [item["check"]], "from": [who], "stages": [stage]})
    return [{**{k: g[k] for k in ("text", "rules", "from", "stages", "checks", "parts")},
             "range": frame_range(g["checks"][0])} for g in groups]


def shot_pass(shot: Path) -> str | None:
    """The pass a sign-off is about: the latest pass, as kei review renders it."""
    from kei.characters import latest_pass
    p = latest_pass(Path(shot))
    return p.parent.name[len("out_"):] if p else None
