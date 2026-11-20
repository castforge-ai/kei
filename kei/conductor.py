"""The conductor: runs every stage of a shot in order, each behind its gate, and never skips one."""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from kei.apps import maya_stage, unreal_stage
from kei.apps.maya_feedback import target_misses
from kei.runlock import run_lock
from kei.book import BookError, Rule, Topic, lessons_for_shot, load_rules, load_topics
from kei import character_folder
from kei.config import Config
from kei.critic import look_at_paths, panel_review
from kei.gates.sources import source_misses
from kei.gates.stage_gate import stage_misses
from kei.characters import (CharacterError, character_misses, imported_characters, load_character,
                            pass_character_misses, plan_character, shot_character)
from kei.characters.imported import confirm
from kei.plan_lock import approve_plan, plan_changes, read_plan
from kei.prompts import stage_prompt
from kei.seats import CliSeat, Seat, SeatPaused, SeatResult, pause_kind, with_dirs, with_web
from kei.sheet import SheetError, write_sheet
from kei.pose_record import latest_pass, records_for_review
from kei.seats import reset_at
from kei.refinement import refinement_misses
from kei.ledger import close as ledger_close, ledger_block, regressions as ledger_regressions, reopen as ledger_reopen
from kei.stages import STAGES, Stage, next_stage, stage_by_id
from kei.topics import effective_subjects, shot_subjects, stage_block, subject_index, subject_misses
from kei.state import PAUSED, ShotState, load_state
from kei.state import save_state as _write_state


def save_state(shot_dir: Path, state: ShotState) -> None:
    """Every save of a run keeps the notes the author gave in a chat while the run was going (kei note --from chat):
    the run read the state before they were written, and would otherwise write over them."""
    from kei.signoff import keep_chat_notes
    keep_chat_notes(shot_dir, state)
    _write_state(shot_dir, state)


Review = Callable[[Stage, Path, list[str]], list[str]]   # (stage, shot, changed plan files) -> send-back notes



class NoCriticError(ValueError):
    """No critic is configured. The animating agent never reviews its own work, so the run does not start."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


ATTEMPTS = ("fail", "send_back", "seat_error")   # history results that are one try of the stage
SEAT_ERROR_CHARS = 2000   # a failed seat's output kept as the miss: its end, where the error is


def since_stage_began(state: ShotState, stage_id: str | None = None) -> list[dict]:
    """The history entries of a stage since it last began, newest first: the walk back stops at the first entry of
    another stage or at the stage's own pass. Every 'since the stage began' question reads this one list."""
    stage_id = stage_id or state.stage
    out = []
    for h in reversed(state.history):
        if h.get("stage") != stage_id or h.get("result") == "pass":
            break
        out.append(h)
    return out


def capped(text: str, limit: int = SEAT_ERROR_CHARS) -> str:
    """A seat's output cut to its last limit characters, saying how much was cut."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"(the first {len(text) - limit} characters of the seat's output are cut) ..." + text[-limit:]
MAX_TIMEOUTS = 2      # a stage's seat may run out of time this often before a timeout counts as a try
TIMEOUT_NOTE = ("Your last try ran out of time before it finished. Everything it wrote is still in the shot folder, "
                "and your session goes on: carry on from where it stopped, do not start again.")


def carried_notes(state: ShotState) -> dict[str, list[str]]:
    """What the next try of the current stage must read, from the history since the stage last began:
    "gate": the misses of the last try when the gate (or the seat) refused it;
    "critics": the notes of the last send-back, kept through later gate misses, seat errors and retries;
    "author": every note the author gave for this stage (kei note, kei answer), oldest first;
    "animator": instructions for the animator only (kei retry --note, an automatic retry), oldest first. The critics
    judge against the author's notes, never against the animator's instructions. Each list holds a note once."""
    gate: list[str] | None = None
    critics: list[str] | None = None
    author: list[str] = []
    animator: list[str] = []
    for h in since_stage_began(state):
        result = h.get("result")
        if gate is None and (result in ATTEMPTS or result == "timeout"):
            gate = list(h.get("misses", [])) if result != "send_back" else []
        if critics is None and result in ("send_back", "question") and h.get("misses"):
            critics = list(h.get("misses", [])) + [f"(minor) {m}" for m in h.get("minor", [])]
        if result == "note":
            author[:0] = list(h.get("misses", []))
        if h.get("for") == "animator":
            animator[:0] = list(h.get("notes", []))
        else:
            author[:0] = list(h.get("notes", []))
    return {"gate": gate or [], "critics": critics or [], "author": _once(author), "animator": _once(animator)}


def _once(notes: list[str]) -> list[str]:
    """The notes in order, each once."""
    seen: set[str] = set()
    return [n for n in notes if not (n.strip() in seen or seen.add(n.strip()))]


def carried_poses(state: ShotState) -> list[str]:
    """The pose files of the author's feedback notes for the current stage since it last began (kei maya feedback),
    oldest first: the next pass must reach their targets."""
    return [h["pose"] for h in reversed(since_stage_began(state)) if h.get("pose")]


def _author_notes(state: ShotState, shot_dir: Path) -> list[str]:
    """The author's notes for the stage, then the targets of the poses they carry."""
    from kei.apps.maya_feedback import target_lines
    return carried_notes(state)["author"] + target_lines(shot_dir, carried_poses(state))


def _animator_notes(state: ShotState, shot_dir: Path) -> list[str]:
    """What the animator reads as notes: the author's, then the instructions meant for the animator alone."""
    return _author_notes(state, shot_dir) + carried_notes(state)["animator"]


LATE_STAGES = ("checks", "self_review", "deliver")   # stages that may make a new pass after the passes review
PASS_MARK = "pass:"   # a changed-files entry that names a new pass, not a plan file


def pass_stamp(shot_dir: Path) -> dict | None:
    """The newest pass (the highest out_p<N> with a shot.json) and the hash of its shot.json."""
    import hashlib
    from kei.pose_record import latest_pass
    name = latest_pass(shot_dir, "passes")
    if name is None:
        return None
    data = (Path(shot_dir) / f"out_{name}" / "shot.json").read_bytes()
    return {"pass": name, "sha256": hashlib.sha256(data).hexdigest()}


def pass_changes(shot_dir: Path, stage_id: str, approved: dict | None) -> list[str]:
    """At checks, self-review or delivery: the newest pass, when it is not the one the panel passed, so the critics
    review the motion that will be delivered."""
    if stage_id not in LATE_STAGES or approved is None:
        return []
    now = pass_stamp(shot_dir)
    if now is None or now == approved:
        return []
    return [f"{PASS_MARK}out_{now['pass']}/shot.json (the panel last passed out_{approved['pass']})"]


def _timeouts(state: ShotState, stage_id: str) -> int:
    """The timeouts of the current run of the stage (since it last began)."""
    return sum(1 for h in since_stage_began(state, stage_id) if h.get("result") == "timeout")


def _run_animator(animator, prompt: str, shot_dir: Path, state: ShotState, stage_id: str,
                  timeout_s: int | None = None):
    """Run the animator. A Claude Code seat keeps one session per stage: the first try starts it, later tries (a gate
    miss, a send-back, a retry) resume it, so the seat keeps what it read and the helpers it wrote. A session the CLI
    no longer has starts afresh."""
    import time
    import uuid
    from kei.seats import NO_SESSION, CliSeat, keep_run, with_session
    t0 = time.time()
    if timeout_s and isinstance(animator, CliSeat):     # the stage's own time limit ([timeouts] in kei.toml)
        from dataclasses import replace as _replace
        animator = CliSeat(_replace(animator.spec, timeout_s=timeout_s))
    before = _scripts(shot_dir)
    result = _run_animator_seat(animator, prompt, shot_dir, state, stage_id, CliSeat, NO_SESSION, uuid, with_session)
    state.last_run = keep_run(shot_dir, f"{stage_id}-animator", prompt, result, time.time() - t0)
    new = sorted(_scripts(shot_dir) - before)
    if new:   # the throwaway scripts this try wrote: the count shows what Kei's own tools still lack
        outside = [s for s in new if not s.startswith(".kei/scratch/")]
        state.last_run = {**state.last_run, "scripts": len(new), **({"scripts_outside_scratch": outside[:20]}
                                                                      if outside else {})}
    return result


def _scripts(shot_dir: Path) -> set[str]:
    """The Python scripts in the shot: its own folders and .kei/scratch, not Kei's other bookkeeping."""
    root = Path(shot_dir)
    out = set()
    for p in root.rglob("*.py"):
        rel = p.relative_to(root).as_posix()
        if not rel.startswith(".kei/") or rel.startswith(".kei/scratch/"):
            out.add(rel)
    return out


def _run_animator_seat(animator, prompt, shot_dir, state, stage_id, CliSeat, NO_SESSION, uuid, with_session):
    if not isinstance(animator, CliSeat):
        return animator.run(prompt, shot_dir)
    sid = state.sessions.get(stage_id)
    from kei.seats import is_codex_exec
    if is_codex_exec(animator.spec):     # Codex names its own session: read it from the answer, resume it next try
        result = CliSeat(with_session(animator.spec, sid or "", resume=bool(sid))).run(prompt, shot_dir)
        if sid and result.exit_code != 0 and NO_SESSION.search(result.output or ""):
            result = CliSeat(with_session(animator.spec, "", resume=False)).run(prompt, shot_dir)
        if result.session:
            state.sessions[stage_id] = result.session
        return result
    seat = CliSeat(with_session(animator.spec, sid or str(uuid.uuid4()), resume=bool(sid)))
    if seat.spec is animator.spec:
        return animator.run(prompt, shot_dir)
    if not sid:
        state.sessions[stage_id] = seat.spec.cmd[2]
    result = seat.run(prompt, shot_dir)
    if sid and result.exit_code != 0 and NO_SESSION.search(result.output or ""):
        state.sessions[stage_id] = str(uuid.uuid4())
        result = CliSeat(with_session(animator.spec, state.sessions[stage_id], resume=False)).run(prompt, shot_dir)
    return result


def _limit_reached(state: ShotState, stage_id: str, config: Config, misses: list[str]) -> str:
    """The stage hit its send-back limit: what limits.on_send_back_limit says to do. "retry" runs the stage again
    from attempt 1 with limits.retry_note for the animator, up to limits.auto_retries times; "advance" moves the open
    notes to the author's sign-off checklist and goes on to the next stage; "stop" (and a used-up retry) stops for a
    person. Returns "retry", "advance" or "stop"."""
    policy = config.on_send_back_limit
    if policy == "retry":
        used = sum(1 for h in state.history if h.get("stage") == stage_id and h.get("result") == "auto_retry")
        if used < config.auto_retries:
            state.history.append({"stage": stage_id, "attempt": state.attempts, "result": "auto_retry", "misses": [],
                                  "for": "animator", "notes": [config.retry_note], "at": _now()})
            state.attempts = 0
            state.send_backs = 0
            return "retry"
        return "stop"
    if policy == "advance":
        _add_sign_off(state, stage_id, [{"from": "send-back limit", "check": f"left open at {stage_id}: {m}"}
                                        for m in misses])
        return "advance"
    return "stop"


def carried_drawings(state: ShotState) -> list[str]:
    """The drawing files of the author's notes for the current stage since it last began (kei review), oldest first."""
    return [d for h in reversed(since_stage_began(state)) if h.get("result") == "note" for d in h.get("drawings", [])]


def _had_records_round(state: ShotState) -> bool:
    """Whether the current stage already ran once more for records since it last began."""
    return any(h.get("result") == "records" for h in since_stage_began(state))


def earlier_send_backs(state: ShotState) -> list[list[str]]:
    """The notes of every send-back of the current stage since it last began, oldest first."""
    return [list(h["misses"]) for h in reversed(since_stage_began(state))
            if h.get("result") in ("send_back", "question") and h.get("misses")]


def _draw_sheet(shot_dir: Path) -> list[str]:
    """Draw plan/plan_sheet.png from plan/plan.json. The sheet is Kei's: it always matches the plan."""
    if not (Path(shot_dir) / "plan" / "plan.json").is_file():
        return []
    try:
        write_sheet(shot_dir)
    except SheetError as e:
        return [f"P7 the plan sheet cannot be drawn: {e}"]
    return []


def stage_rules(config: Config) -> tuple[list[Topic], list[Rule]]:
    """The book's topics and the local lessons. A stage whose principles alone are too much rule text stops the run."""
    topics = load_topics(config.book)
    lessons = load_rules([config.lessons])   # the local lessons file may not exist yet
    book_ids = {r.id for t in topics for r in t.rules}
    for r in lessons:
        if r.id in book_ids:
            raise BookError(f"rule {r.id} is in the book and again in {config.lessons}")
    for s in STAGES:   # the largest rule set a stage can get: every subject topic named, so no shot stops mid-run
        n = len(stage_block(s.id, topics, lessons, None))
        if n > config.max_rule_chars:
            raise BookError(f"stage {s.id}: its rules are {n} characters, over book.max_chars {config.max_rule_chars}")
    return topics, lessons


def _rules(stage_id: str, shot_dir: Path, topics: list[Topic], lessons: list[Rule], state: ShotState) -> str:
    """The brief gets every subject and the subject index; later stages get the principles and the shot's subjects."""
    if stage_id == "brief":
        return "\n\n".join(b for b in (stage_block("brief", topics, lessons, None), subject_index(topics)) if b)
    return stage_block(stage_id, topics, lessons, effective_subjects(state.subjects, shot_subjects(shot_dir)))


def _critic_rules(stage_id: str, shot_dir: Path, topics: list[Topic], lessons: list[Rule], state: ShotState,
                  book: Path | None) -> str:
    """What the critics get: the stage's rules as a checklist with the files of their full text (kei.topics)."""
    if stage_id == "brief":
        return _rules(stage_id, shot_dir, topics, lessons, state)
    from kei.topics import critic_block
    return critic_block(stage_id, topics, lessons, effective_subjects(state.subjects, shot_subjects(shot_dir)), book)


def _book_dir(book: Path | None) -> Path | None:
    """The folder of the rule book, for the critics to read its files."""
    if book is None:
        return None
    p = Path(book)
    return p if p.is_dir() else p.parent


def _too_much(stage_id: str, rules: str, limit: int) -> str | None:
    """A prompt over the limit stops for a person. Kei never answers it by sending fewer rules."""
    if len(rules) <= limit:
        return None
    return (f"the rules for stage {stage_id} are {len(rules)} characters, over book.max_chars {limit}: "
            "raise book.max_chars in kei.toml, then kei retry")


def _questions(shot_dir: Path) -> Path | None:
    q = Path(shot_dir) / "QUESTIONS.md"
    return q if q.exists() and q.read_text(encoding="utf-8").strip() else None


PAUSE_CHARS = 300


def _ask(shot_dir: Path, state: ShotState, entry: dict, questions: list[dict]) -> ShotState:
    """Stop the stage for the author's answer. Neither a try nor a send-back is counted."""
    state.status = "needs_answer"
    state.questions = questions
    state.history.append({**entry, "result": "question"})
    save_state(shot_dir, state)
    return state


def _same_check(text: str) -> str:
    return " ".join(re.sub(r"[^\w/.]+", " ", text.lower()).split()).strip(" .")


def _add_sign_off(state: ShotState, stage_id: str, items: list[dict]) -> None:
    """Checks a critic left for the author's sign-off. A critic's new review of a stage replaces the checks it left
    on that stage before (they were about work that has since changed), and the same check is listed once."""
    seats = {it.get("from") for it in items}
    if items:
        state.sign_off = [s for s in state.sign_off if not (s.get("stage") == stage_id and s.get("from") in seats)]
    have = {_same_check(s["check"]) for s in state.sign_off}
    for it in items:
        key = _same_check(it["check"])
        if key not in have:
            state.sign_off.append({"stage": stage_id, **it})
            have.add(key)


def _open_questions(state: ShotState) -> list[dict]:
    return state.questions


def _pause(shot_dir: Path, state: ShotState, entry: dict, why: SeatPaused) -> ShotState:
    """Stop the stage for a usage limit or a machine fault. The try is not counted; kei run resumes it."""
    state.status = f"paused_{why.kind}"
    when = reset_at(why.output) if why.kind == "usage" else None
    state.history.append({**entry, "result": state.status, "seat": why.seat,
                          "misses": [why.output[:PAUSE_CHARS] or "(no output)"],
                          **({"resume_at": when.strftime("%Y-%m-%d %H:%M")} if when else {})})
    save_state(shot_dir, state)
    return state


CHARACTER_ENV = "KEI_CHARACTER"   # the configured default character, for the kei render and kei bake the seats run
FIT_REFUSED = "fit_refused"


YES = re.compile(r"\s*(yes|y|ok|okay|approve|approved)\s*[.!]?\s*", re.I)


def _reachable(shot_dir: Path, config: Config) -> list[str]:
    """Every character the shot can play: the PLAN.md line or the config's default, and every pass's shot.json."""
    names = []
    try:
        names.append(shot_character(shot_dir, None, config.character))
    except CharacterError:
        pass                             # an unknown character is the stage gate's to report
    for f in sorted(Path(shot_dir).glob("out_*/shot.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("character"), str):
            names.append(data["character"].strip().lower())
    return list(dict.fromkeys(names))


def _fit_gate(shot_dir: Path, state: ShotState, config: Config, stage_id: str) -> ShotState | None:
    """An imported character whose fit nobody has approved: ask the author to look at its fit sheet before any stage
    runs. Only a plain yes, given to the question about this import, approves it; anything else stops the shot for a
    new import."""
    for name in _reachable(shot_dir, config):
        if name in imported_characters():
            stopped = _fit_gate_one(shot_dir, state, stage_id, name)
            if stopped is not None:
                return stopped
    return None


def _fit_gate_one(shot_dir: Path, state: ShotState, stage_id: str, name: str) -> ShotState | None:
    ch = load_character(name)
    if ch.confirmed:
        return None
    tag = f"[fit:{name}:{ch.import_id}]"
    answered = [a for a in state.answers if tag in a.get("question", "")]
    refused = sum(1 for h in state.history if h.get("result") == FIT_REFUSED and h.get("fit") == tag)
    entry = {"stage": stage_id, "attempt": state.attempts + 1, "at": _now()}
    if len(answered) > refused:
        text = answered[-1]["answer"].strip()
        if YES.fullmatch(text):
            confirm(ch.folder)
            state.history.append({**entry, "result": "fit_approved", "character": name, "misses": []})
            save_state(shot_dir, state)
            return None
        state.status = "needs_human"
        state.history.append({**entry, "result": FIT_REFUSED, "character": name, "fit": tag, "misses": [
            f"the fit of {name} was not approved: {text}. Import the model again (kei import <model> --name {name} "
            "with --height, --map or --unrigged), look at its fit.png, then: kei retry"]})
        save_state(shot_dir, state)
        return state
    return _ask(shot_dir, state, {**entry, "misses": []}, [{
        "from": "kei", "stage": stage_id, "look_at": [str(ch.folder / "fit.png")],
        "text": f"{tag} {name} is an imported character, and nobody has approved its fitted skeleton yet. Look at its "
                "fit sheet: does every joint sit where the body bends (shoulders, elbows, wrists, hips, knees, "
                "ankles, neck), with the character's left side tinted? Answer yes to animate it, or say what is "
                "wrong."}])


REUSE_STAGES = ("rig", "weight")   # facts about the body: a character folder's saved evaluation stands in for them


def _reuse(shot_dir: Path, state: ShotState, config: Config, stage_id: str) -> character_folder.Reuse | None:
    """The character folder's saved evaluations this try of the rig or weight stage reuses. A whole reuse the gate
    refused since the stage began is not tried again: the stage evaluates."""
    if stage_id not in REUSE_STAGES:
        return None
    if any(h.get("reused_all") and h.get("result") == "fail" for h in since_stage_began(state, stage_id)):
        return None
    return character_folder.plan_reuse(shot_dir, config.character)


def run_shot(shot_dir: Path, request: str, config: Config, animator: Seat | None = None,
             review: Review | None = None, critics: list[Seat] | None = None) -> ShotState:
    """Run the shot. The seats inherit KEI_CHARACTER, the config's default character, while it runs."""
    from kei.apps.maya_feedback import RUN_ENV    # kei maya feedback, run by a seat, asks the author through the shot
    old = {k: os.environ.get(k) for k in (CHARACTER_ENV, RUN_ENV)}
    os.environ[CHARACTER_ENV] = config.character
    os.environ[RUN_ENV] = "1"
    try:
        with run_lock(shot_dir):    # one kei run per shot: a second one stops here, before it touches anything
            return _run_shot(shot_dir, request, config, animator, review, critics)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _character(shot_dir: Path, config: Config) -> str:
    """The character the shot uses, as kei render and kei check find it: the latest pass's, else PLAN.md's, else the
    config's."""
    from kei.characters import latest_pass
    p = latest_pass(shot_dir)
    try:
        shot = json.loads(p.read_text(encoding="utf-8")) if p else None
    except ValueError:
        shot = None
    try:
        return shot_character(shot_dir, shot if isinstance(shot, dict) else None, config.character)
    except CharacterError:
        return plan_character(shot_dir) or config.character


def _run_shot(shot_dir: Path, request: str, config: Config, animator: Seat | None,
              review: Review | None, critics: list[Seat] | None) -> ShotState:
    shot_dir = Path(shot_dir)
    topics, lessons = stage_rules(config)
    lessons = lessons_for_shot(lessons, shot_dir)   # a "this shot" lesson of another shot stays out
    if review is None:
        if critics is None:
            for c in config.critics:
                if shutil.which(c.cmd[0]) is None:
                    raise NoCriticError(f"critic {c.name}: command not found: {c.cmd[0]}; "
                                        "install it or remove that seat from kei.toml")
            critics = [CliSeat(with_web(with_dirs(c, [config.refs_library, _book_dir(config.book)]), config.web))
                       for c in config.critics]
        if not critics:
            raise NoCriticError("no critic is configured: add a [[critics]] seat to kei.toml")
        review = lambda stage, d, changed: panel_review(stage, d, state.request, critics, changed,  # noqa: E731
                                                        held.get("critic_rules") or held["rules"], state.answers,
                                                        earlier_send_backs(state),
                                                        _author_notes(state, shot_dir),
                                                        ledger_block(state, shot_dir, latest_pass(shot_dir, "passes")),
                                                        config.primary_critic)
    held = {"rules": ""}   # the critics judge with the rules of this stage, read after the animator's run
    animator = animator or CliSeat(with_web(with_dirs(config.animator, [config.refs_library]), config.web))
    state = load_state(shot_dir)
    at_review = False
    if state.status in PAUSED:   # a usage limit or a machine fault: the stage goes on where it paused
        paused = next((h for h in reversed(state.history) if h.get("result") == state.status), {})
        at_review = paused.get("phase") == "review"   # the animator's work was done: only the review is owed
        state.history.append({"stage": state.stage, "attempt": state.attempts + 1, "at": _now(), "result": "resume",
                              "misses": []})
        state.status = "running"
        save_state(shot_dir, state)
    if state.status != "running":
        return state
    named = plan_character(shot_dir)
    wrong = pass_character_misses(shot_dir, named) if named else []
    if wrong:   # refused before any stage: the animator's file is the person's to correct, never rewritten
        raise CharacterError("; ".join(wrong))
    if not state.request:
        state.request = request
        save_state(shot_dir, state)
    if maya_stage.wants_maya(shot_dir, config.app):   # where to animate (asked when Maya is open), the scene, the rig
        need = maya_stage.prepare(shot_dir, config)
        entry = {"stage": state.stage, "attempt": state.attempts + 1, "at": _now(), "misses": []}
        if need and "question" in need:
            return _ask(shot_dir, state, entry, [{"from": "kei", "stage": state.stage, "kind": "maya_target",
                                                  "text": need["question"], "choices": need["choices"]}])
        if need:
            return _pause(shot_dir, state, entry, SeatPaused("machine", "maya", need["pause"]))
    if unreal_stage.wants_unreal(shot_dir, config.app):   # where to animate (always asked), then the character's rig
        need = unreal_stage.prepare(shot_dir, config)
        entry = {"stage": state.stage, "attempt": state.attempts + 1, "at": _now(), "misses": []}
        if need and "question" in need:
            return _ask(shot_dir, state, entry, [{"from": "kei", "stage": state.stage, "kind": "unreal_target",
                                                  "text": need["question"], "choices": need["choices"]}])
        if need and "pause" in need:
            return _pause(shot_dir, state, entry, SeatPaused("machine", "unreal", need["pause"]))
        if need:        # a person must act in the editor (a rig the probe changed, several characters)
            state.status = "needs_human"
            state.history.append({**entry, "result": "fail", "misses": [need["human"]]})
            save_state(shot_dir, state)
            return state
    while state.status == "running":
        stage = stage_by_id(state.stage)
        rules = _rules(stage.id, shot_dir, topics, lessons, state)
        stop = _too_much(stage.id, rules, config.max_rule_chars)
        if stage.id == "brief":
            rules += (f"\n\nThe configured default is {config.character}: with no Character line in PLAN.md, "
                      f"{config.character} performs.")
        if stop:
            state.status = "needs_human"
            state.history.append({"stage": stage.id, "attempt": state.attempts + 1, "at": _now(),
                                  "result": "fail", "misses": [stop]})
            save_state(shot_dir, state)
            return state
        if not at_review:
            stopped = _fit_gate(shot_dir, state, config, stage.id)
            if stopped is not None:
                return stopped
        reuse = None if at_review else _reuse(shot_dir, state, config, stage.id)
        if reuse is not None:   # the character folder's evaluation goes into the shot; the gate still checks it
            character_folder.apply_reuse(shot_dir, reuse)
            state.history.append({"stage": stage.id, "attempt": state.attempts + 1, "at": _now(), "result": "reused",
                                  "reused": "; ".join(reuse.messages()), "misses": []})
            save_state(shot_dir, state)
        carried = carried_notes(state)
        folder_notes = character_folder.reuse_notes(reuse) if reuse else []
        if stage.id == "references":   # a vetted REFS.md of the same action on this character, as a draft
            folder_notes += character_folder.draft_notes(
                character_folder.draft_refs(shot_dir, state.request, config.character))
        prompt = stage_prompt(stage, shot_dir, state.request, carried["gate"], rules,
                              critic_notes=carried["critics"], author_notes=_animator_notes(state, shot_dir),
                              questions=_open_questions(state), answers=state.answers,
                              character=_character(shot_dir, config), look_at=carried_drawings(state),
                              kei_notes=folder_notes, refs_library=config.refs_library)
        if at_review:
            at_review = False
            result = SeatResult(0, "resumed at the review")
        elif reuse is not None and reuse.whole:
            result = SeatResult(0, "reused")   # no seat measures the body again
        else:
            result = _run_animator(animator, prompt, shot_dir, state, stage.id, config.stage_timeouts.get(stage.id))
            if reuse is not None:
                character_folder.apply_reuse(shot_dir, reuse)   # a reused section the animator dropped is put back
        entry = {"stage": stage.id, "attempt": state.attempts + 1, "at": _now(),
                 **(state.__dict__.pop("last_run", None) or {})}
        if reuse is not None and reuse.whole:
            entry["reused_all"] = True
        kind = pause_kind(result)
        if kind:
            return _pause(shot_dir, state, entry, SeatPaused(kind, animator.name, result.output.strip()))
        if result.exit_code == 124 and _timeouts(state, stage.id) < MAX_TIMEOUTS:
            # out of time: the work stays (files, and the resumed session), and the try is not counted
            state.history.append({**entry, "result": "timeout", "misses": [TIMEOUT_NOTE]})
            save_state(shot_dir, state)
            continue
        lost = maya_stage.take_pause(shot_dir)   # the open Maya stopped answering mid-pass: never on in silence
        if lost:
            return _pause(shot_dir, state, entry, SeatPaused("machine", "maya", lost))
        lost = unreal_stage.take_pause(shot_dir)   # the open Unreal Editor stopped answering: never on in silence
        if lost:
            return _pause(shot_dir, state, entry, SeatPaused("machine", "unreal", lost))
        stuck = unreal_stage.take_human(shot_dir)   # Kei made a user asset dirty: a person acts first
        if stuck:
            state.status = "needs_human"
            state.history.append({**entry, "result": "fail", "misses": [stuck]})
            save_state(shot_dir, state)
            return state
        size_stop = False
        q = _questions(shot_dir)
        if q is not None and result.exit_code == 0:   # any stage may ask the author; it stops until kei answer
            text = q.read_text(encoding="utf-8").strip()
            return _ask(shot_dir, state, {**entry, "misses": []},
                        [{"from": "animator", "stage": stage.id, "text": text, "look_at": look_at_paths(text)}])
        if result.exit_code != 0:
            misses = [capped(result.output) or f"the seat exited with code {result.exit_code}"]
            entry["result"] = "seat_error"
        else:
            misses = _draw_sheet(shot_dir)
            records_for_review(shot_dir, stage.id, _character(shot_dir, config))   # the critics read the records
            misses += stage_misses(shot_dir, stage)
            misses += subject_misses(shot_dir, topics, required=stage.id == "brief")
            misses += character_misses(shot_dir)
            misses += target_misses(shot_dir, carried_poses(state))   # the author's feedback pose, if any
            misses += source_misses(shot_dir, config.banned_names)   # names the author banned, kept on their machine
            if stage.id in ("blocking", "passes", "checks", "self_review", "deliver"):
                # a fault fixed earlier in the shot that came back fails the try before any critic runs
                newest = "blocking" if stage.id == "blocking" else latest_pass(shot_dir, "passes")
                misses += [f"regression of a fixed note: {r}" for r in ledger_regressions(shot_dir, state, newest)]
            if stage.id in ("passes", "checks", "self_review", "deliver"):
                misses += refinement_misses(shot_dir)   # a pass that changes nothing, or one keyed on every frame
            if not misses:
                held["rules"] = _rules(stage.id, shot_dir, topics, lessons, state)
                held["critic_rules"] = _critic_rules(stage.id, shot_dir, topics, lessons, state, config.book)
                stop = _too_much(stage.id, held["rules"], config.max_rule_chars)
                if stop:
                    misses = [stop]
                    size_stop = True
            entry["result"] = "fail" if misses else "pass"
            if not misses and not entry.get("reused_all"):   # a reused evaluation was reviewed when it was made
                snapshot = read_plan(shot_dir)   # what the critics judge; a later edit is not approved with it
                changed = plan_changes(shot_dir, state.approved_plan, snapshot)
                changed += pass_changes(shot_dir, stage.id, state.approved_pass)
                try:
                    from kei.record import write_record
                    write_record(shot_dir, state)      # the bookkeeping, from Kei's state: nobody keeps it by hand
                except OSError:
                    pass
                try:
                    panel = review(stage, shot_dir, changed)
                except SeatPaused as e:
                    return _pause(shot_dir, state, {**entry, "phase": "review"}, e)
                misses = list(panel)
                _add_sign_off(state, stage.id, getattr(panel, "sign_off", []))
                asked = getattr(panel, "questions", [])
                if asked:   # a critic asks the author: no send-back is counted; the answer goes to the next try
                    return _ask(shot_dir, state, {**entry, "misses": misses},
                                [{**qq, "stage": stage.id} for qq in asked])
                records = list(getattr(panel, "records", []))
                if records:
                    entry["records"] = records
                minor = list(getattr(panel, "minor", []))
                if minor:
                    entry["minor"] = minor      # read by the animator with a send-back; never a send-back itself
                judged = list(getattr(panel, "earlier", []))
                if judged:
                    entry["earlier"] = [{"from": c, "note": n, "status": st} for c, n, st in judged]
                    ledger_reopen(state, stage.id, entry["earlier"])
                    ledger_close(state, stage.id, entry["earlier"], _now())
                entry["result"] = "send_back" if misses else "pass"
                if misses and state.send_backs + 1 >= config.send_backs_for(stage.id) \
                        and config.on_send_back_limit == "advance":
                    _limit_reached(state, stage.id, config, misses)
                    entry["result"] = "escalated"      # never silent: the open notes wait at the sign-off
                if not misses and records and not _had_records_round(state):
                    # only records asked for: a note for the animator's next try, which spends no send-back and no
                    # try; asked again after that round, they go on with the stage
                    entry["result"], entry["notes"] = "records", records
                if entry["result"] in ("pass", "escalated") and (stage.id == "passes" or
                                                                 any(c.startswith(PASS_MARK) for c in changed)):
                    state.approved_pass = pass_stamp(shot_dir)
                if entry["result"] in ("pass", "escalated") and (stage.id == "plan" or
                                                                 any(not c.startswith(PASS_MARK) for c in changed)):
                    state.approved_plan = approve_plan(shot_dir, snapshot)
        entry["misses"] = misses
        state.history.append(entry)
        if entry["result"] in ("pass", "escalated"):
            current = shot_subjects(shot_dir)
            if stage.id == "brief":
                state.subjects = current   # the set only grows from here
            elif state.subjects is not None:
                state.subjects = effective_subjects(state.subjects, current)
            if stage.id == "weight":   # a complete evaluation made in a character folder is kept there
                character_folder.save_evaluations(shot_dir, config.character)
            nxt = next_stage(stage.id)
            state.attempts = 0
            state.send_backs = 0
            if nxt is None:
                state.status = "needs_approval"   # a person signs off every shot: kei approve, or kei note
            else:
                state.stage = nxt.id
        elif entry["result"] == "records":
            pass                                   # the stage runs again for the records, its budgets untouched
        elif entry["result"] == "send_back":
            state.send_backs += 1
            if state.send_backs >= config.send_backs_for(stage.id) and _limit_reached(state, stage.id, config, misses) == "stop":
                state.status = "needs_human"
        else:
            state.attempts += 1
            if state.attempts >= config.attempts_for(stage.id) or size_stop:
                state.status = "needs_human"   # too much rule text goes to a person, never to a retry
        save_state(shot_dir, state)
    return state
