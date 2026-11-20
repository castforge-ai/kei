"""The author's sign-off: approve, note and reject. The kei commands and the review page call these same functions,
so the two can never disagree about what a sign-off does."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from kei.book import ALL
from kei.lessons import add_lesson, remove_lesson, same_lesson, scope_name
from kei.notesign import sign, signed
from kei.stages import STAGES
from kei.state import ShotState, StateError, load_state, save_state


class SignOffError(ValueError):
    """A sign-off that cannot happen. The message says why in plain words and names the status."""


_ROUND = re.compile(r"r(\d+)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def round_ids(shot: Path) -> list[str]:
    """The review rounds of a shot (review/r<n>/round.json), oldest first."""
    found = []
    review = Path(shot) / "review"
    if review.is_dir():
        for d in review.iterdir():
            m = _ROUND.fullmatch(d.name)
            if m and (d / "round.json").is_file():
                found.append((int(m.group(1)), d.name))
    return [name for _, name in sorted(found)]


def round_is_stale(shot: Path, round_id: str) -> str | None:
    """Why a round no longer shows the shot's latest pass as it is now, or None: a newer pass exists, or the pass's
    shot.json changed after the round was drawn."""
    import hashlib
    import json
    from kei.characters import latest_pass
    try:
        meta = json.loads((Path(shot) / "review" / round_id / "round.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "its round.json cannot be read"
    newest = latest_pass(Path(shot))
    if newest is None:
        return "no pass is left in the shot"
    name = newest.parent.name[len("out_"):]
    if meta.get("pass") != name:
        return f"the latest pass is now {name}, the round shows {meta.get('pass')}"
    if meta.get("shot_sha256") != hashlib.sha256(newest.read_bytes()).hexdigest():
        return f"out_{name}/shot.json changed after the round was drawn"
    return None


def latest_round(shot: Path) -> str | None:
    ids = round_ids(shot)
    return ids[-1] if ids else None


def not_waiting(status: str) -> str:
    return f"this shot is not waiting for a sign-off (status: {status})"


def stage_refusal(stage: str) -> str | None:
    ids = [s.id for s in STAGES]
    return None if stage in ids else f"unknown stage {stage!r}: use one of {', '.join(ids)}"


CHAT = "chat"     # a note the author gave in the chat with their agent (the Kei skill): it can be undone
SNAPSHOT = ("stage", "attempts", "send_backs", "status", "approved_plan")   # what a note may change in the state
CLOSED = ("done", "rejected")


def pass_mark(shot: Path) -> dict:
    """The latest pass of the shot as it is on disk now: its name and the sha256 of its shot.json, or both None."""
    import hashlib
    from kei.characters import latest_pass
    p = latest_pass(Path(shot))
    if p is None:
        return {"pass": None, "pass_sha": None}
    return {"pass": p.parent.name[len("out_"):], "pass_sha": hashlib.sha256(p.read_bytes()).hexdigest()}


def note_refusal(state: ShotState, stage: str) -> str | None:
    """Why a note cannot be taken now, or None. A note is taken while the shot waits for the sign-off, after it
    (the author withdraws the approval) and after a reject (the author reopens the shot)."""
    if state.status not in ("needs_approval", "done", "rejected"):
        return not_waiting(state.status)
    return stage_refusal(stage)


def approve_shot(shot: Path, round_id: str | None = None, words: str | None = None) -> ShotState:
    """Close a shot the author signed off. With round_id (the page), only the latest round can be approved. words
    are the author's own sign-off words from the chat, kept verbatim with the approval."""
    shot = Path(shot)
    state = load_state(shot)
    if state.status != "needs_approval":
        raise SignOffError(not_waiting(state.status))
    entry = {"stage": state.stage, "attempt": 0, "result": "approved", "misses": [], "at": _now()}
    if words is not None:
        entry["words"] = words
    if round_id is None and latest_round(shot):
        entry["round"] = latest_round(shot)      # kei approve: the round the author last saw
    if round_id is not None:
        latest = latest_round(shot)
        if latest is None:
            raise SignOffError(f"there is no review round {round_id} in this shot: reload the page")
        if round_id != latest:
            raise SignOffError(f"round {round_id} is not the latest round ({latest}): the shot changed since this "
                               "page was loaded; reload it")
        stale = round_is_stale(shot, round_id)
        if stale:
            raise SignOffError(f"the shot changed since round {round_id} was drawn ({stale}): restart kei review "
                               "to see what changed before you approve")
        entry["round"] = round_id
    state.history.append(entry)
    state.status = "done"
    save_state(shot, state)
    return state


def _send_back(state: ShotState, stage: str) -> None:
    """A note sends the shot back to a stage: its tries start again there."""
    ids = [s.id for s in STAGES]
    state.stage, state.attempts, state.send_backs, state.status = stage, 0, 0, "running"
    if ids.index(stage) <= ids.index("plan"):
        state.approved_plan = None   # the plan is judged whole again when the shot reaches it


def _place_in_progress(state: ShotState, entry: dict, stage: str) -> None:
    """A note given while the shot is still being made (running, a question, a stop or a pause) is for the next try:
    a running shot already past the note's stage goes back to it; otherwise the note waits for the next try of the
    stage the shot is at, and an open question or stop is left as it is."""
    ids = [s.id for s in STAGES]
    if state.status == "running" and ids.index(state.stage) > ids.index(stage):
        _send_back(state, stage)
    entry["stage"] = state.stage


def note_shot(shot: Path, text: str, stage: str, lessons: Path, drawings: list[str] = (),
              cards: list[dict] = (), scope: str = "shot", round_id: str | None = None,
              source: str | None = None, reviewer: str | None = None) -> tuple[ShotState, str]:
    """Send the shot back to a stage with the author's words, kept verbatim as a local lesson. drawings are paths
    relative to the shot; the next prompt of that stage lists them. scope is this shot (default) or every shot (a
    rule). round_id is the round the note is about (default: the latest). source "chat" is a note the author gave in
    the chat: it is also taken while the shot is being made (for the next try), and it keeps what it changed so
    kei note --undo can put it back. Returns the state and the lesson ID."""
    shot = Path(shot)
    state = load_state(shot)
    chat = source == CHAT
    if source not in (None, CHAT):
        raise SignOffError(f"unknown note source {source!r}: the only one is chat")
    in_progress = chat and state.status not in ("needs_approval", *CLOSED)
    why = stage_refusal(stage) if in_progress else note_refusal(state, stage)
    if why:
        raise SignOffError(why)
    if not text.strip():
        raise SignOffError("a note needs words: say what is wrong")
    try:
        scope = scope_name(scope)
    except ValueError as e:
        raise SignOffError(str(e)) from e
    lessons = Path(lessons)
    lessons_new = not lessons.exists()
    held = same_lesson(lessons, text, stage, scope, shot)   # the same note again: its lesson is not written twice
    lesson = add_lesson(lessons, text, stage, scope, shot)
    entry = {"stage": stage, "attempt": 0, "result": "note", "lesson": lesson, "misses": [text], "at": _now(),
             "scope": scope, **pass_mark(shot)}
    if held is not None:
        entry["lesson_held"] = True     # an earlier note wrote this lesson: --undo leaves it in the file
    if reviewer:
        entry["reviewer"] = reviewer     # a reviewer's note from a kei pack notes file, brought in by the author
    if chat:
        entry["from"] = CHAT
        entry["before"] = {k: getattr(state, k) for k in SNAPSHOT}    # what --undo puts back
        if lessons_new:
            entry["lessons_new"] = True
    round_id = round_id or latest_round(shot)
    if round_id:
        entry["round"] = round_id     # the failing case of a rule, if a later round confirms its fix
    if drawings:
        entry["drawings"] = list(drawings)
    if cards:
        entry["cards"] = list(cards)     # the author's yes or no to each question, from the review page
    if in_progress:
        entry["send_to"] = stage
        entry["while"] = state.status
        _place_in_progress(state, entry, stage)
    else:
        if state.status == "done":
            entry["withdrew_approval"] = True     # the author changed their mind after the sign-off
        if state.status == "rejected":
            entry["reopened"] = True
        _send_back(state, stage)
    if chat:
        entry["sig"] = sign(entry)     # a running kei run merges a chat note only when this holds (kei.notesign)
    state.history.append(entry)
    save_state(shot, state)
    return state, lesson


def _note_key(h: dict) -> tuple:
    return h.get("lesson"), h.get("at")


def keep_chat_notes(shot: Path, state: ShotState) -> None:
    """Before a running kei run saves its state: the chat notes another process wrote to the shot since the run read
    it are added to the run's state, each placed for the next try, so a note given during a run is never lost."""
    try:
        disk = load_state(Path(shot))
    except StateError:
        return
    have = {_note_key(h) for h in state.history if h.get("result") == "note"}
    for h in disk.history:
        if h.get("result") != "note" or h.get("from") != CHAT or _note_key(h) in have:
            continue
        if not signed(h):
            print(f"kei: a chat note in {Path(shot) / '.kei' / 'state.json'} is not signed by kei note, so it is "
                  f"not taken as the author's: {(h.get('misses') or [''])[0][:80]!r}", file=sys.stderr)
            continue
        entry = dict(h)
        stage = entry.get("send_to") or entry["stage"]
        if state.status == "needs_approval":
            _send_back(state, stage)
            entry["stage"] = stage
        else:
            _place_in_progress(state, entry, stage)
        state.history.append(entry)


def undo_note(shot: Path, lessons: Path, lesson: str | None = None) -> tuple[ShotState, dict]:
    """The author's "not a note": remove a note given in the chat (the one whose lesson ID is given, else the last
    note), while no pass ran after it. The history entry and its lesson go, and the shot is put back as it was before
    the note. Each chat removes only its own note: a later chat note stays, and takes over what the removed one kept.
    Returns the state and the removed entry."""
    shot = Path(shot)
    state = load_state(shot)
    notes = [i for i, h in enumerate(state.history) if h.get("result") == "note"]
    if lesson is not None:
        notes = [i for i in notes if state.history[i].get("lesson") == lesson]
        if not notes:
            raise SignOffError(f"there is no note {lesson} in this shot")
    elif not notes:
        raise SignOffError("this shot has no note to remove")
    i = notes[-1]
    h = state.history[i]
    if h.get("from") != CHAT:
        raise SignOffError(f"note {h.get('lesson')} was not given in the chat (kei note --from chat): only a chat note "
                           "can be undone; give a new note instead")
    later = state.history[i + 1:]
    if any(e.get("result") != "note" or e.get("from") != CHAT for e in later):
        raise SignOffError(f"Kei already worked on the shot after note {h['lesson']}: it cannot be undone; give a new "
                           "note instead")
    if pass_mark(shot)["pass_sha"] != h.get("pass_sha"):
        raise SignOffError(f"a new pass was made after note {h['lesson']}: it cannot be undone; give a new note "
                           "instead")
    if not h.get("lesson_held"):
        remove_lesson(lessons, h["lesson"], created=bool(h.get("lessons_new")))
    del state.history[i]
    if later:
        nxt = later[0]                       # its state before was this note's state after, which is gone now
        nxt["before"] = h["before"]
        if h.get("lessons_new"):
            nxt["lessons_new"] = True
    else:
        for k, v in h["before"].items():
            setattr(state, k, v)
    save_state(shot, state)
    return state, h


def note_words(h: dict) -> str:
    return (h.get("misses") or [""])[0]


def note_pass(shot: Path, h: dict) -> dict | None:
    """The pass a note was given on: recorded on the note, else the pass of the round it names, else None."""
    if "pass_sha" in h:      # None: the shot had no pass yet when the note was given
        return {"pass": h.get("pass"), "pass_sha": h["pass_sha"]}
    if h.get("round"):
        import json
        try:
            meta = json.loads((Path(shot) / "review" / h["round"] / "round.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if meta.get("shot_sha256"):
            return {"pass": meta.get("pass"), "pass_sha": meta["shot_sha256"]}
    return None


def open_notes(shot: Path, state: ShotState | None = None) -> list[dict]:
    """The author's notes that nothing closed yet, numbered from 1 in the order given. A later approval or reject
    closes a note, and so does a later yes to it (kei fixed, or the review page's yes card), by the same rule that
    confirms a rule's fix (kei.share.confirms). Each: n, lesson, words (verbatim), scope, from, at, and new_pass (a
    pass newer than the note is on disk)."""
    from kei.share import confirms
    shot = Path(shot)
    history = (state or load_state(shot)).history
    now = pass_mark(shot)
    out = []
    for i, h in enumerate(history):
        if h.get("result") != "note" or not h.get("lesson"):
            continue
        if any(later.get("result") in ("approved", "rejected") or confirms(h, later) for later in history[i + 1:]):
            continue
        given = note_pass(shot, h)
        out.append({"n": len(out) + 1, "lesson": h["lesson"], "words": note_words(h),
                    "scope": h.get("scope") or "this shot", "from": h.get("from", ""), "at": h.get("at", ""),
                    "new_pass": bool(given and now["pass_sha"] and now["pass_sha"] != given["pass_sha"])})
    return out


def reject_shot(shot: Path, reason: str, keep_as_lesson: bool, lessons: Path, cards: list[dict] = (),
                round_id: str | None = None, words: str | None = None, open_ok: bool = False) -> ShotState:
    """Stop a shot for good with the author's reason. The reason becomes a lesson only when the author asks: a
    rejected shot may be a wrong brief, not a craft fault. kei note reopens it. words are the author's own words from
    the chat, kept verbatim; open_ok also stops a shot that is still being made (kei drop)."""
    shot = Path(shot)
    state = load_state(shot)
    if state.status != "needs_approval" and not (open_ok and state.status not in CLOSED):
        raise SignOffError(not_waiting(state.status) if not open_ok else
                           f"this shot is closed (status: {state.status}): there is nothing to drop")
    if not reason.strip():
        raise SignOffError("a reject needs a reason: say why")
    entry = {"stage": state.stage, "attempt": 0, "result": "rejected", "reason": reason, "misses": [reason],
             "at": _now()}
    if words is not None:
        entry["words"] = words
    if cards:
        entry["cards"] = list(cards)     # a yes given before the reject still confirms a rule's fix
    round_id = round_id or latest_round(shot)
    if round_id:
        entry["round"] = round_id
    if keep_as_lesson:
        entry["lesson"] = add_lesson(lessons, reason, ALL)
    state.history.append(entry)
    state.status = "rejected"
    save_state(shot, state)
    return state


DROPPED = "dropped by the author"


def drop_shot(shot: Path, words: str, lessons: Path) -> ShotState:
    """The author's "drop" in the chat: the shot is rejected with the reason "dropped by the author" and the author's
    words verbatim, from any status but done or rejected. Confirmed rules then share as at any rejection."""
    if not words.strip():
        raise SignOffError("a drop needs the author's words: what they said")
    state = reject_shot(shot, DROPPED, False, lessons, words=words, open_ok=True)
    state.history[-1]["dropped"] = True
    save_state(Path(shot), state)
    return state


def rejection(state: ShotState) -> str:
    """The reason of the last reject, for kei run and kei status."""
    last = next((h for h in reversed(state.history) if h.get("result") == "rejected"), {})
    return last.get("reason", "")


def _numbered(notes: list[dict]) -> str:
    return "; ".join(f"{n['n']}. {n['words']}" for n in notes)


def fixed_shot(shot: Path, not_fixed: list[int] = ()) -> tuple[ShotState, list[dict], list[dict]]:
    """The author's answer to "fixed?" after a new pass: every open note given before that pass is closed as fixed,
    except the numbers in not_fixed, which stay open. The answer is a yes to each fixed note, the same yes the review
    page's card gives, so a fixed rule (a note for every shot) is confirmed by kei.share.rule_status and nothing else.
    A note given on the pass now shown stays open. Returns the state, the notes closed and the notes left open."""
    shot = Path(shot)
    state = load_state(shot)
    notes = open_notes(shot, state)
    if not notes:
        raise SignOffError("this shot has no open note to close")
    wrong = [n for n in not_fixed if n not in {o["n"] for o in notes}]
    if wrong:
        raise SignOffError(f"there is no open note {', '.join(map(str, wrong))}: the open notes are "
                           + _numbered(notes))
    shown = [o for o in notes if o["new_pass"]]
    if not shown:
        raise SignOffError("show the new pass first: no pass was made since the open notes (" + _numbered(notes) + ")")
    closing = [o for o in shown if o["n"] not in not_fixed]
    entry = {"stage": state.stage, "attempt": 0, "result": "fixed", "misses": [], "at": _now(), **pass_mark(shot),
             "fixed": [o["lesson"] for o in closing], "not_fixed": [o["lesson"] for o in shown if o not in closing],
             "cards": [{"check": o["words"], "answer": "yes", "lesson": o["lesson"]} for o in closing]}
    rounds = {h.get("round") for h in state.history if h.get("result") == "note"
              and h.get("lesson") in entry["fixed"]}
    round_id = latest_round(shot)
    if round_id and round_id not in rounds:
        entry["round"] = round_id     # the passing case of a rule, when a review round shows the new pass
    state.history.append(entry)
    save_state(shot, state)
    left = [o for o in notes if o not in closing]
    return state, closing, left
