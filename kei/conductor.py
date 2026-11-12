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
from kei.book import BookError, Rule, Topic, load_rules, load_topics
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
from kei.seats import CliSeat, Seat, SeatPaused, SeatResult, pause_kind, with_dirs
from kei.sheet import SheetError, write_sheet
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


def carried_notes(state: ShotState) -> dict[str, list[str]]:
    """What the next try of the current stage must read, from the history since the stage last began:
    "gate": the misses of the last try when the gate (or the seat) refused it;
    "critics": the notes of the last send-back, kept through later gate misses, seat errors and retries;
    "author": every note the author gave for this stage (kei retry --note, kei note), oldest first."""
    gate: list[str] | None = None
    critics: list[str] | None = None
    author: list[str] = []
    for h in reversed(state.history):
        if h.get("stage") != state.stage or h.get("result") == "pass":
            break
        result = h.get("result")
        if gate is None and result in ATTEMPTS:
            gate = list(h.get("misses", [])) if result != "send_back" else []
        if critics is None and result in ("send_back", "question") and h.get("misses"):
            critics = list(h.get("misses", []))
        if result == "note":
            author[:0] = list(h.get("misses", []))
        author[:0] = list(h.get("notes", []))
    return {"gate": gate or [], "critics": critics or [], "author": author}


def carried_poses(state: ShotState) -> list[str]:
    """The pose files of the author's feedback notes for the current stage since it last began (kei maya feedback),
    oldest first: the next pass must reach their targets."""
    out: list[str] = []
    for h in reversed(state.history):
        if h.get("stage") != state.stage or h.get("result") == "pass":
            break
        if h.get("pose"):
            out.insert(0, h["pose"])
    return out


def _author_notes(state: ShotState, shot_dir: Path) -> list[str]:
    """The author's notes for the stage, then the targets of the poses they carry."""
    from kei.apps.maya_feedback import target_lines
    return carried_notes(state)["author"] + target_lines(shot_dir, carried_poses(state))


def carried_drawings(state: ShotState) -> list[str]:
    """The drawing files of the author's notes for the current stage since it last began (kei review), oldest first."""
    out: list[str] = []
    for h in reversed(state.history):
        if h.get("stage") != state.stage or h.get("result") == "pass":
            break
        if h.get("result") == "note":
            out[:0] = list(h.get("drawings", []))
    return out


def _had_records_round(state: ShotState) -> bool:
    """Whether the current stage already ran once more for records since it last began."""
    for h in reversed(state.history):
        if h.get("stage") != state.stage or h.get("result") == "pass":
            return False
        if h.get("result") == "records":
            return True
    return False


def earlier_send_backs(state: ShotState) -> list[list[str]]:
    """The notes of every send-back of the current stage since it last began, oldest first."""
    out = []
    for h in reversed(state.history):
        if h.get("stage") != state.stage or h.get("result") == "pass":
            break
        if h.get("result") in ("send_back", "question") and h.get("misses"):
            out.insert(0, list(h["misses"]))
    return out


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
    for s in STAGES:
        n = len(stage_block(s.id, topics, lessons, []))
        if n > config.max_rule_chars:
            raise BookError(f"stage {s.id}: its rules are {n} characters, over book.max_chars {config.max_rule_chars}")
    return topics, lessons


def _rules(stage_id: str, shot_dir: Path, topics: list[Topic], lessons: list[Rule], state: ShotState) -> str:
    """The brief gets every subject and the subject index; later stages get the principles and the shot's subjects."""
    if stage_id == "brief":
        return "\n\n".join(b for b in (stage_block("brief", topics, lessons, None), subject_index(topics)) if b)
    return stage_block(stage_id, topics, lessons, effective_subjects(state.subjects, shot_subjects(shot_dir)))


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
    state.history.append({**entry, "result": state.status, "seat": why.seat,
                          "misses": [why.output[:PAUSE_CHARS] or "(no output)"]})
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
    for h in reversed(state.history):
        if h.get("stage") != stage_id or h.get("result") == "pass":
            break
        if h.get("reused_all") and h.get("result") == "fail":
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
    if review is None:
        if critics is None:
            for c in config.critics:
                if shutil.which(c.cmd[0]) is None:
                    raise NoCriticError(f"critic {c.name}: command not found: {c.cmd[0]}; "
                                        "install it or remove that seat from kei.toml")
            critics = [CliSeat(with_dirs(c, [config.refs_library])) for c in config.critics]
        if not critics:
            raise NoCriticError("no critic is configured: add a [[critics]] seat to kei.toml")
        review = lambda stage, d, changed: panel_review(stage, d, state.request, critics, changed,  # noqa: E731
                                                        held["rules"], state.answers, earlier_send_backs(state),
                                                        _author_notes(state, shot_dir))
    held = {"rules": ""}   # the critics judge with the rules of this stage, read after the animator's run
    animator = animator or CliSeat(with_dirs(config.animator, [config.refs_library]))
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
                              critic_notes=carried["critics"], author_notes=_author_notes(state, shot_dir),
                              questions=_open_questions(state), answers=state.answers,
                              character=_character(shot_dir, config), look_at=carried_drawings(state),
                              kei_notes=folder_notes, refs_library=config.refs_library)
        if at_review:
            at_review = False
            result = SeatResult(0, "resumed at the review")
        elif reuse is not None and reuse.whole:
            result = SeatResult(0, "reused")   # no seat measures the body again
        else:
            result = animator.run(prompt, shot_dir)
            if reuse is not None:
                character_folder.apply_reuse(shot_dir, reuse)   # a reused section the animator dropped is put back
        entry = {"stage": stage.id, "attempt": state.attempts + 1, "at": _now()}
        if reuse is not None and reuse.whole:
            entry["reused_all"] = True
        kind = pause_kind(result)
        if kind:
            return _pause(shot_dir, state, entry, SeatPaused(kind, animator.name, result.output.strip()))
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
            misses = [result.output.strip() or f"the seat exited with code {result.exit_code}"]
            entry["result"] = "seat_error"
        else:
            misses = _draw_sheet(shot_dir)
            misses += stage_misses(shot_dir, stage)
            misses += subject_misses(shot_dir, topics, required=stage.id == "brief")
            misses += character_misses(shot_dir)
            misses += target_misses(shot_dir, carried_poses(state))   # the author's feedback pose, if any
            misses += source_misses(shot_dir, config.banned_names)   # names the author banned, kept on their machine
            if not misses:
                held["rules"] = _rules(stage.id, shot_dir, topics, lessons, state)
                stop = _too_much(stage.id, held["rules"], config.max_rule_chars)
                if stop:
                    misses = [stop]
                    size_stop = True
            entry["result"] = "fail" if misses else "pass"
            if not misses and not entry.get("reused_all"):   # a reused evaluation was reviewed when it was made
                snapshot = read_plan(shot_dir)   # what the critics judge; a later edit is not approved with it
                changed = plan_changes(shot_dir, state.approved_plan, snapshot)
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
                entry["result"] = "send_back" if misses else "pass"
                if not misses and records and not _had_records_round(state):
                    # only records asked for: a note for the animator's next try, which spends no send-back and no
                    # try; asked again after that round, they go on with the stage
                    entry["result"], entry["notes"] = "records", records
                if entry["result"] == "pass" and (stage.id == "plan" or changed):
                    state.approved_plan = approve_plan(shot_dir, snapshot)
        entry["misses"] = misses
        state.history.append(entry)
        if entry["result"] == "pass":
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
            if state.send_backs >= config.max_send_backs:
                state.status = "needs_human"
        else:
            state.attempts += 1
            if state.attempts >= config.max_attempts or size_stop:
                state.status = "needs_human"   # too much rule text goes to a person, never to a retry
        save_state(shot_dir, state)
    return state
