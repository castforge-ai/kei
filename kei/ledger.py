"""The note ledger: the critics' notes that were fixed, kept for the whole shot, so a fault that comes back is caught.

In the heavy_lift benchmark, fixed faults came back: the walk-in at f7-11 four times, the stand-up at f148-153 three
times, often in a later stage than the one that fixed them. A critic marks an earlier note "fixed" in its verdict
("earlier"); Kei records that note with its frame range in the shot's state. Every later review, at any stage, sees
the fixed notes and is asked whether any came back, and Kei lists a hard body-check flag of the newest pass that
falls inside a fixed note's frames as a likely regression, before the critics judge.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_RANGE = re.compile(r"(?<![\w.])[fF]?(\d{1,4})\s*(?:-|to)\s*[fF]?(\d{1,4})(?![\w.])")
_ONE = re.compile(r"(?<![\w.])[fF](\d{1,4})(?![\w.])")
SHOWN = 30   # the latest fixed notes a critic sees


def note_frames(note: str) -> tuple[int, int] | None:
    """The frame range a note names first ("f7-11: ...", "149-152: ...", "at f58"), or None."""
    text = re.sub(r"^critic [^:]+:\s*", "", note)
    m = _RANGE.search(text)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    m = _ONE.search(text)
    return (int(m.group(1)), int(m.group(1))) if m else None


def _full_note(state, stage: str, start: str) -> str:
    """The earlier send-back note of the stage that starts like the critic's reference to it."""
    key = start.strip().lower()
    for h in reversed(state.history):
        if h.get("stage") == stage and h.get("result") == "send_back":
            for n in h.get("misses", []):
                bare = re.sub(r"^critic [^:]+:\s*", "", n).strip().lower()
                if bare.startswith(key) or key.startswith(bare[:40]):
                    return n
    return start


def close(state, stage: str, judged: list[dict], at: str) -> None:
    """Record the notes a critic judged fixed (entries of {"from", "note", "status"})."""
    have = {(x["stage"], x["note"]) for x in state.ledger}
    for j in judged:
        if j.get("status") != "fixed":
            continue
        note = _full_note(state, stage, j.get("note", ""))
        if (stage, note) in have:
            continue
        state.ledger.append({"stage": stage, "note": note, "frames": note_frames(note), "fixed_by": j.get("from"),
                             "at": at})
        have.add((stage, note))


def reopen(state, stage: str, judged: list[dict]) -> None:
    """A note a critic now judges not fixed leaves the ledger."""
    gone = {_full_note(state, stage, j.get("note", "")) for j in judged if j.get("status") == "not fixed"}
    state.ledger[:] = [x for x in state.ledger if not (x["stage"] == stage and x["note"] in gone)]


def regressions(shot_dir: Path, state, newest_pass: str | None) -> list[str]:
    """Hard flags of the newest pass's body check inside the frames of a fixed note."""
    if not newest_pass or not state.ledger:
        return []
    p = Path(shot_dir) / f"out_{newest_pass}" / "body_check" / "body_check.json"
    try:
        flags = json.loads(p.read_text(encoding="utf-8")).get("flags", [])
    except (OSError, ValueError):
        return []
    hard = [fl for fl in flags if fl.get("rule") == "hard" and not fl.get("note") and (fl.get("frames") or [None])[0]
            is not None]
    try:   # a flag GATES.md declares is accepted by the gate, so it is not a regression either
        from kei.explain import body_id
        from kei.gates.pipeline import open_flags
        gates = (Path(shot_dir) / "GATES.md").read_text(encoding="utf-8")
        hard = open_flags([{**fl, "id": body_id(fl)} for fl in hard], gates)
    except OSError:
        pass
    out = []
    for x in state.ledger:
        if not x.get("frames"):
            continue
        a, b = x["frames"]
        for fl in hard:
            fa, fb = fl["frames"][:2]
            if fa <= b and fb >= a:
                out.append(f"f{fa}-{fb} {fl.get('check')}: {fl.get('what')} (inside the fixed note "
                           f"\"{x['note'][:90]}\", fixed at {x['stage']})")
    return out


def ledger_block(state, shot_dir: Path, newest_pass: str | None) -> list[str]:
    """The prompt lines for a critic: the fixed notes, and the likely regressions."""
    if not state.ledger:
        return []
    shown = state.ledger[-SHOWN:]
    lines = ["Notes fixed earlier in this shot. Check that none came back; one that did is a blocking note again:"]
    lines += [f"- ({x['stage']}) {x['note']}" for x in shown]
    reg = regressions(shot_dir, state, newest_pass)
    if reg:
        lines += ["Kei measured these hard flags inside a fixed note's frames: likely regressions."]
        lines += [f"- {r}" for r in reg]
    return lines
