"""The kei command: run a shot through every stage, answer its questions, or show where it stands."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from kei.book import BookError
from kei.characters import (CHARACTERS, CharacterError, characters_dir, imported_characters, load_character,
                            plan_character, rest_pose, shot_character)
from kei.conductor import CHARACTER_ENV, NoCriticError, run_shot
from kei.config import ConfigError, example_config, load_config
from kei.settings import SettingError
from kei.signoff import SignOffError, approve_shot, note_refusal, note_shot, rejection
from kei.models.model import ModelError
from kei.retarget import RetargetError
from kei.apps.maya import MayaError
from kei.apps.unreal import UnrealError
from kei.apps import maya_shot
from kei.body_check import CheckError, check_pass
from kei.pose_record import PoseRecordError, write_records
from kei.probe import ProbeError, format_table, probe
from kei.unattended import AnswersError
from kei.keys import OPS as KEY_OPS, KeysError, apply as apply_keys
from kei.skill_install import SkillError
from kei.trails import TrailsError
from kei.curves import CurvesError
from kei.bench import BenchError
from kei.pack import PackError
from kei.sound import SoundError
from kei.mocap import MocapError
from kei.share import BundleError
from kei.export_fbx import export_fbx
from kei.export_gltf import export_glb
from kei.render import CHARACTER_VIEWS, Camera, draw_character_views, draw_silhouette, render_post, render_shot
from kei.rig import PoseError, check_channels, solve
from kei.sample import MODES, ShotError, bake, check_shot, read_json
from kei.sheet import SheetError, write_sheet
from kei.stages import STAGES
from kei.state import PAUSED, StateError, load_state, save_state

EXIT_DONE, EXIT_ERROR, EXIT_NEEDS_HUMAN, EXIT_NEEDS_ANSWER, EXIT_NEEDS_APPROVAL, EXIT_PAUSED = 0, 1, 2, 3, 4, 5
EXIT_CODES_HELP = """exit codes (kei run, and every command where they apply):
  0  done, or the command did what it was asked
  1  error: the message is on stderr, starting with "kei: "
  2  the shot needs a person (kei status <shot> says why)
  3  the shot needs an answer to a question (kei answer)
  4  the shot waits for your approval (kei approve, or kei note)
  5  paused: a usage limit, a seat fault or a stop (kei status <shot> says which; run kei run again to go on)
messages for people go to stdout, errors to stderr."""
SIGN_OFF = 'approve with: kei approve <shot>, or send it back with: kei note <shot> --text "..."'
EXAMPLE_CONFIG = example_config()


def _config_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    local = Path.cwd() / "kei.toml"
    return local if local.exists() else EXAMPLE_CONFIG


def _last_misses(state) -> list[str]:
    return state.history[-1]["misses"] if state.history else []


def _pause_reason(state, shot) -> list[str]:
    """Why a paused shot stopped, in plain words, and how to go on."""
    last = next((h for h in reversed(state.history) if h.get("result") == state.status), {})
    seat = f"the {last['seat']} seat" if last.get("seat") else "a seat"
    said = (last.get("misses") or [""])[0].strip().splitlines()
    said = f" It said: {said[0]}" if said else ""
    if state.status == "paused_usage":
        why = f"Stopped: {seat} hit a usage or rate limit.{said}"
        then = "When the limit resets, run"
    else:
        why = f"Stopped: {seat} could not start on this machine.{said}"
        then = "When the machine is ready (close programs, free memory), run"
    return [why, "This was not counted as a try of the stage.", f"{then}: kei run {shot}"]


def _question_lines(state, shot) -> list[str]:
    """The open questions, who asked, and the files to look at."""
    out = []
    qs = state.questions
    if not qs and (Path(shot) / "QUESTIONS.md").is_file():
        qs = [{"from": "animator", "text": (Path(shot) / "QUESTIONS.md").read_text(encoding="utf-8").strip()}]
    for q in qs:
        out.append(f"Question from {q.get('from', 'the animator')} at {q.get('stage', state.stage)}:")
        out.append(q.get("text", ""))
        for p in q.get("look_at", []):
            out.append(f"Look at: {p} (in {shot})")
    out.append(f'Answer with: kei answer {shot} --text "..."')
    return out


def _checklist(state, shot) -> list[str]:
    """The checks the critics left for the author's sign-off about the pass being signed off, the same request from
    two critics listed once. Checks about other passes stay in .kei/state.json."""
    if not state.sign_off:
        return []
    from kei.checklist import current_checks, shot_pass
    items = current_checks(state.sign_off, shot_pass(shot))
    if not items:
        return []
    out = ["Before you approve, check these yourself (the critics could not):"]
    for i in items:
        where = ", ".join(p.get("label") or p.get("play") for p in i["parts"][1:])
        tag = "; ".join(x for x in (", ".join(i["rules"]), ", ".join(i["from"]), where) if x)
        out.append(f"- [ ] {i['text']} ({tag})")
    hidden = len(state.sign_off) - sum(len(i["checks"]) for i in items)
    if hidden:
        out.append(f"({hidden} older check(s) about other passes are kept in .kei/state.json)")
    return out


REOPEN = 'reopen it with: kei note {shot} --stage <stage> --text "..."'


WAIT_DEFAULT_MIN = 30   # minutes to wait for a limit whose message gives no reset time


def _cmd_run(a) -> int:
    config_path = _config_path(a.config)
    config = load_config(config_path)
    if not config.web_asked and config_path != EXAMPLE_CONFIG:   # a kei.toml from before the question: ask once
        _save_web(config_path)
        config = load_config(config_path)
    shot = Path(a.shot)
    if load_state(shot).status == "rejected":
        print(f"this shot was rejected: {rejection(load_state(shot))}")
        print(REOPEN.format(shot=shot))
        return EXIT_ERROR
    if not a.request and not load_state(shot).request:
        print('kei: a new shot needs --request "what to animate"', file=sys.stderr)
        return EXIT_ERROR
    if a.app == "maya" or a.scene:
        from kei.apps.maya_stage import record_source
        record_source(shot, Path(a.scene) if a.scene else None)
    if a.app == "unreal":
        (shot / "unreal").mkdir(parents=True, exist_ok=True)     # the mark of an Unreal shot: the conductor asks where
    _live_page(shot, config)
    answers = None
    if getattr(a, "answers", None):
        from kei.unattended import load_answers
        answers = load_answers(Path(a.answers))
    before = len(load_state(shot).history)
    state = run_shot(shot, a.request or "", config)
    if answers is not None:   # unattended: answer the plain questions from the file and run on
        from kei.unattended import MAX_ANSWERS, answer_from_file
        for _ in range(MAX_ANSWERS):
            if state.status != "needs_answer" or not answer_from_file(shot, state, answers, _now):
                break
            print(f"{state.stage}: answered from {a.answers}")
            state = run_shot(shot, a.request or "", config)
    if getattr(a, "wait_on_limit", False):   # unattended: wait for a usage limit to reset, then run on
        import time
        from datetime import datetime, timedelta
        deadline = datetime.now() + timedelta(hours=a.max_wait_hours)
        while state.status == "paused_usage":
            last = state.history[-1] if state.history else {}
            try:
                when = datetime.strptime(last["resume_at"], "%Y-%m-%d %H:%M") + timedelta(minutes=1)
            except (KeyError, ValueError):
                when = datetime.now() + timedelta(minutes=WAIT_DEFAULT_MIN)
            if when > deadline:
                print(f"{state.stage}: the limit resets at {when:%Y-%m-%d %H:%M}, after --max-wait-hours "
                      f"{a.max_wait_hours:g}: stopping")
                break
            print(f"{state.stage}: usage limit; waiting until {when:%Y-%m-%d %H:%M}, then running on")
            time.sleep(max(0.0, (when - datetime.now()).total_seconds()))
            state = run_shot(shot, a.request or "", config)
    for h in state.history[before:]:
        if h.get("result") == "reused":   # which character folder's evaluation the run reused, and from when
            print(f"{h.get('stage')}: {h.get('reused')}")
    print(f"{state.stage}: {state.status}")
    if state.status in PAUSED:
        for line in _pause_reason(state, shot):
            print(line)
        return EXIT_PAUSED
    if state.status == "needs_answer":
        for line in _question_lines(state, shot):
            print(line)
        return EXIT_NEEDS_ANSWER
    if state.status == "needs_human":
        for m in _last_misses(state):
            print(f"- {m}")
        return EXIT_NEEDS_HUMAN
    if state.status == "needs_approval":
        for line in _checklist(state, shot):
            print(line)
        print(SIGN_OFF)
        return EXIT_NEEDS_APPROVAL
    return EXIT_DONE


def _live_page(shot: Path, config) -> None:
    """Start the shot's live page (kei live) unless kei.toml turns it off. The run never waits on it or fails for it."""
    if config.live_page != "on" or os.environ.get("KEI_NO_LIVE"):
        return
    shot.mkdir(parents=True, exist_ok=True)
    from kei.live.serve import ensure
    url = ensure(shot, open_browser=config.live_open == "on")
    if url:
        print(f"live page: {url}")


def _cmd_rule(a) -> int:
    from kei.book import load_rules, load_topics
    config = load_config(_config_path(a.config))
    rules = {r.id: r for t in load_topics(config.book) for r in t.rules}
    rules.update({r.id: r for r in load_rules([config.lessons])})
    missing = [i for i in a.ids if i not in rules]
    for i in a.ids:
        if i in rules:
            r = rules[i]
            print(f"### {r.id}. {r.title}\n{r.text}\n")
    if missing:
        print("kei: no rule " + ", ".join(missing), file=sys.stderr)
        return EXIT_ERROR
    return EXIT_DONE


def _cmd_live(a) -> int:
    from kei.live.serve import serve
    shot = Path(a.shot)
    if not shot.is_dir():
        print(f"kei: no shot folder at {shot}", file=sys.stderr)
        return EXIT_ERROR
    open_browser = not a.no_open
    if not a.no_open and not a.quiet:
        try:
            open_browser = load_config(_config_path(a.config)).live_open == "on"
        except ConfigError:
            pass
    serve(shot, port=a.port, open_browser=open_browser, announce=(lambda _m: None) if a.quiet else print)
    return EXIT_DONE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _share_after_sign_off(shot: Path, config_arg: str | None, rejected: bool) -> None:
    """After kei approve or kei drop: in auto mode Kei sends each confirmed rule with no dialog; otherwise it says
    where to share them. Only rules whose fix was confirmed can be shared."""
    from kei.share import shareable as new_lessons
    try:
        config = load_config(_config_path(config_arg))
    except ConfigError:
        config = None
    mode = config.share if config else "ask"
    if mode == "auto" and new_lessons(shot):     # no dialog: Kei sends each lesson that is ready
        from kei.review.app import _sharer
        sharer = _sharer(shot, config)
        for r in (sharer.on_reject() if rejected else sharer.on_accept()).get("results", []):
            print(f"lesson {r['lesson']}: {r.get('message') or r.get('error')}")
    elif mode != "never" and new_lessons(shot):
        print(f"this shot taught Kei new lessons; to share them, open: kei review {shot}")


# Commands that read a delivered shot as it is: they never need the working files back in place.
AS_DELIVERED = {"status", "live", "approve"}


def _in_working_layout(a) -> int:
    """Run the command. A delivered shot keeps its work in production/ (kei.layout); a command that works on the shot
    gets the working layout back first, and the shot is packed again after when it is still approved."""
    from kei import layout
    if getattr(a, "shot_arg", None) and not getattr(a, "shot", None):
        a.shot = a.shot_arg                            # kei export <shot>: the same shot as --shot
    shot = getattr(a, "shot", None)
    if not shot or a.command in AS_DELIVERED or not layout.is_packed(Path(shot)):
        return a.fn(a)
    layout.unpack(Path(shot))
    try:
        return a.fn(a)
    finally:
        if load_state(Path(shot)).status == "done":     # signed off: still delivered
            layout.pack(Path(shot))
            from kei.live.report import refresh
            refresh(Path(shot))                      # the report, and its copy beside the Unreal assets


def _cmd_approve(a) -> int:
    try:
        approve_shot(Path(a.shot), words=a.words)
    except SignOffError as e:
        print(f"kei: {e}", file=sys.stderr)
        return EXIT_ERROR
    from kei import layout
    from kei.apps import unreal_stage
    tidied = None
    if unreal_stage.is_unreal_shot(Path(a.shot)):   # the editor's folder too, while the working files are in place
        try:
            tidied = unreal_stage.tidy_shot(Path(a.shot))
            _print_tidy(tidied)
        except (UnrealError, ShotError) as e:
            print(f"the Unreal folder is not tidied yet: {e}")
    layout.pack(Path(a.shot))       # the finished files on top, the work in production/<phase>/
    from kei.live.report import write_report
    report = write_report(Path(a.shot))   # the live page, saved as one file to read the shot's story later
    print("approved; the shot is done")
    print(f"the shot's report: {report}")
    _unreal_report_copy(Path(a.shot), tidied)
    print(f"the delivered files are on top of {a.shot}; the work is in {Path(a.shot) / layout.PRODUCTION}")
    _share_after_sign_off(Path(a.shot), None, rejected=False)
    return EXIT_DONE


def _cmd_drop(a) -> int:
    from kei.signoff import drop_shot
    config = load_config(_config_path(a.config))
    drop_shot(Path(a.shot), a.words, config.lessons)
    print("dropped by the author; the shot is rejected (kei note reopens it)")
    _share_after_sign_off(Path(a.shot), a.config, rejected=True)
    return EXIT_DONE


def _cmd_note_undo(a, shot: Path) -> int:
    from kei.signoff import undo_note
    if a.text is not None or a.every_shot or a.from_:
        print("kei: --undo takes no --text, --every-shot or --from: it removes a note given in the chat", file=sys.stderr)
        return EXIT_ERROR
    config = load_config(_config_path(a.config))
    state, removed = undo_note(shot, config.lessons, None if a.undo == "last" else a.undo)
    print(f"removed note {removed['lesson']}: {removed['misses'][0]}")
    print(f"the shot is back to {state.status} at {state.stage}")
    return EXIT_DONE


def _cmd_note_from_file(a, shot: Path) -> int:
    from kei.pack import PackError, mark_imported, read_notes
    from kei.signoff import CHAT
    if a.text is not None or a.every_shot or a.from_ or a.undo:
        print("kei: --from-file takes no --text, --every-shot, --from or --undo: the notes come from the file",
              file=sys.stderr)
        return EXIT_ERROR
    try:
        got = read_notes(shot, Path(a.from_file))
    except PackError as e:
        print(f"kei: {e}", file=sys.stderr)
        return EXIT_ERROR
    config = load_config(_config_path(a.config))
    lessons = []
    for text in got["notes"]:
        state, lesson = note_shot(shot, text, a.stage, config.lessons, scope="shot", source=CHAT,
                                  reviewer=got["reviewer"])
        lessons.append(lesson)
        print(f"noted from {got['reviewer']}: {text}")
    mark_imported(shot, got)
    print(f"{len(lessons)} note(s) from {got['reviewer']} added to {config.lessons} for this shot only")
    print(f"the shot is at {state.stage} ({state.status}); to remove one: kei note {shot} --undo <lesson>")
    return EXIT_DONE


def _cmd_pack(a) -> int:
    from kei.pack import pack
    r = pack(Path(a.shot), Path(a.out) if a.out else None, max_mb=a.max_mb, videos=not a.no_video)
    print(f"written: {r['path']} ({r['bytes'] / 2**20:.1f} MB, {r['files']} image(s) and video(s) inside it)")
    for rel, why in r["skipped"]:
        print(f"- left out: {rel}: {why}")
    print("Send that one file. The reviewer opens it in a browser, writes notes and saves a notes file; bring it in "
          f"with: kei note {a.shot} --from-file {Path(a.shot).name}_notes.json")
    return EXIT_DONE


def _cmd_share_check(a) -> int:
    from kei.share_tools import bundle_folders, check_folders
    folders = [f for root in a.folders for f in bundle_folders(Path(root))]
    if not folders:
        print("no lesson bundle found (a bundle is a folder with a bundle.json)")
        return EXIT_DONE if a.allow_none else EXIT_ERROR
    bad = 0
    for folder, why in check_folders(folders):
        print(f"ok    {folder}" if why is None else f"fail  {folder}: {why}")
        bad += why is not None
    print(f"{len(folders) - bad} of {len(folders)} bundle(s) pass")
    return EXIT_ERROR if bad else EXIT_DONE


def _cmd_share_export(a) -> int:
    from kei.share_tools import export_zip
    out = export_zip(Path(a.bundle), Path(a.out) if a.out else None)
    print(f"written: {out}")
    print("Send it by any means. The maintainers bring it in with kei share import <zip>, then review it with "
          "kei review --lesson. Share only lessons you have the right to share (CONTRIBUTING.md).")
    return EXIT_DONE


def _cmd_share_import(a) -> int:
    from kei.share_tools import import_zip
    dest = import_zip(Path(a.zip), Path(a.into))
    print(f"brought in and checked: {dest}")
    print(f"review it with: kei review --lesson {dest}")
    return EXIT_DONE


def _cmd_share_list(a) -> int:
    from kei.share_tools import accepted, accepted_md
    text = accepted_md(accepted(Path(a.root) / "lessons"))
    if a.write:
        out = Path(a.root) / "lessons" / "ACCEPTED.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8", newline="\n")
        print(f"written: {out}")
    else:
        print(text, end="")
    return EXIT_DONE


def _cmd_schema(a) -> int:
    from kei.schemas import SCHEMAS, dump, write_all
    if a.write:
        for path in write_all(Path(a.write)):
            print(f"written: {path}")
        return EXIT_DONE
    if not a.name:
        print("schemas: " + ", ".join(SCHEMAS) + " (kei schema <name>, or --write <folder> for all)")
        return EXIT_DONE
    print(dump(a.name), end="")
    return EXIT_DONE


def _cmd_vary(a) -> int:
    from kei.vary import vary
    dest = vary(Path(a.shot), a.note, Path(a.to) if a.to else None, a.from_stage)
    print(f"variation made: {dest}, starting at {a.from_stage}, with your note for that stage")
    print(f"run it with: kei run {dest}")
    return EXIT_DONE


def _cmd_sound(a) -> int:
    from kei.characters import latest_pass
    from kei.sound import add_sound
    shot = Path(a.shot)
    src = latest_pass(shot)
    plan = shot / "plan" / "plan.json"
    data = read_json(src, "shot") if src else (read_json(plan, "plan") if plan.is_file() else {})
    fps = a.fps or (data.get("fps") if isinstance(data, dict) else None) or 24
    frames = data.get("frames") if isinstance(data, dict) else None
    words = Path(a.words).read_text(encoding="utf-8").splitlines() if a.words else []
    got = add_sound(shot, Path(a.file), float(fps), frames, a.offset, words)
    print(f"sound: {got['source']} at {got['fps']:g} fps, {got['frames']} frames from sound frame {got['offset']}")
    print(f"{len(got['beats'])} beat(s) at " + (", ".join(f"f{b}" for b in got["beats"][:20]) or "none")
          + (" ..." if len(got["beats"]) > 20 else ""))
    print(f"{len(got['phrases'])} phrase(s): " + (", ".join(f"f{p[0]}-{p[1]}" for p in got["phrases"]) or "none"))
    print(f"written: {shot / 'sound' / 'sound.json'}, waveform.png and XSHEET.md; "
          f"snap keys with: kei keys {shot} <pass> snap --by 2")
    return EXIT_DONE


def _cmd_ref_import(a) -> int:
    from kei.mocap import import_reference
    got = import_reference(Path(a.shot), Path(a.file), a.licence, a.source or "", a.units, a.name)
    m = got["measures"]
    print(f"reference written: {got['folder']} ({m['frames']} frames at {m['fps']:g} fps, file units {got['unit']})")
    print(f"pelvis bob {m['pelvis_bob_cm']} cm, travel {m['travel_m']} m, speed {m['speed_m_s']} m/s; "
          f"{len(m['flags'])} kei check flag(s) on the capture itself")
    print("It is a measured reference: plan against its numbers; the keys are never traced from it. Add the row in "
          "REF_ROW.md to refs/REFS.md.")
    return EXIT_DONE


def _cmd_note(a) -> int:
    shot = Path(a.shot)
    if a.from_file:
        return _cmd_note_from_file(a, shot)
    if a.undo:
        return _cmd_note_undo(a, shot)
    if a.text is None:
        print('kei: a note needs words: kei note <shot> --text "..."', file=sys.stderr)
        return EXIT_ERROR
    if not a.from_:
        why = note_refusal(load_state(shot), a.stage)
        if why:
            print(why if why.startswith("this shot") else f"kei: {why}", file=sys.stderr)
            return EXIT_ERROR
    config = load_config(_config_path(a.config))
    state, lesson = note_shot(shot, a.text, a.stage, config.lessons, scope="every" if a.every_shot else "shot",
                              source=a.from_)
    entry = state.history[-1]
    if entry.get("withdrew_approval"):
        print("approval withdrawn: the shot is open again")
    if a.from_:
        print(f"noted for {entry['scope']}: {a.text}")
        print(f"note {lesson} added to {config.lessons}")
        if entry.get("while"):
            print(f"the shot is still being made ({entry['while']}): the note is for the next try of {entry['stage']}")
        else:
            print(f"the shot goes back to {state.stage}")
        print(f"to remove it: kei note {shot} --undo {lesson}")
        return EXIT_DONE
    print(f"lesson {lesson} ({entry['scope']}) added to {config.lessons}; the shot goes back to "
          f"{a.stage}")
    print(f"continue with: kei run {shot} --request \"...\"")
    return EXIT_DONE


def _not_numbers(text: str) -> list[int]:
    try:
        nums = [int(x) for x in text.replace(" ", "").split(",") if x]
    except ValueError:
        raise SignOffError(f"--not takes the numbers of the notes that are not fixed, such as 2 or 1,3; got {text!r}")
    if not nums:
        raise SignOffError("--not needs at least one note number")
    return nums


def _cmd_fixed(a) -> int:
    from kei.signoff import fixed_shot
    nums = [] if a.all else _not_numbers(a.not_)
    state, closed, left = fixed_shot(Path(a.shot), nums)
    for n in closed:
        print(f"fixed: {n['n']}. {n['words']} ({n['scope']})")
    for n in left:
        print(f"still open: {n['n']}. {n['words']} ({n['scope']})")
    rules = [n for n in closed if n["scope"] == "every shot"]
    if rules:
        print(f"{len(rules)} rule(s) for every shot confirmed: they can be shared at the sign-off or a drop")
    return EXIT_DONE


def _cmd_park(a) -> int:
    from kei import chat
    mark = chat.park(Path(a.shot))
    on = f"pass {mark['pass']}" if mark["pass"] else "no pass yet"
    print(f"parked on {on}: kei status --open leaves it out until its next pass")
    return EXIT_DONE


def _cmd_answer(a) -> int:
    shot = Path(a.shot)
    state = load_state(shot)
    if state.status != "needs_answer":
        print(f"this shot is not waiting for an answer (status: {state.status})")
        return EXIT_ERROR
    q = shot / "QUESTIONS.md"
    asked = [x.get("text", "") for x in state.questions]
    if not asked and q.is_file():
        asked = [q.read_text(encoding="utf-8").strip()]
    from kei.apps import maya_feedback
    feedback = maya_feedback.asked_feedback(asked)
    if feedback is not None and (shot / maya_feedback.FOLDER / str(feedback) / "note.json").is_file():
        feedback = None             # that feedback already has its note: never rewritten
    if a.every_shot and feedback is None:
        print("kei: --every-shot is for an answer to a feedback question (kei maya feedback); a note on a delivered "
              f'shot takes it through: kei note {shot} --text "..." --every-shot', file=sys.stderr)
        return EXIT_ERROR
    if feedback is not None and not a.text.strip():
        print("kei: the reason needs words, in one sentence; Kei never writes it for you", file=sys.stderr)
        return EXIT_ERROR
    unreal_q = next((x for x in state.questions if x.get("kind") == "unreal_target"), None)
    if unreal_q is not None:     # where to animate an Unreal shot: the answer is a choice's number
        from kei.apps.unreal_session import answer_choice as unreal_choice, save_target as unreal_save
        try:
            choice = unreal_choice(unreal_q["choices"], a.text)
        except ValueError as e:
            print(f"kei: {e}", file=sys.stderr)
            return EXIT_ERROR
        if choice["kind"] != "retry":      # "look again" keeps nothing: the next run asks again, after a fresh probe
            unreal_save(shot, choice)
    target_q = next((x for x in state.questions if x.get("kind") == "maya_target"), None)
    if target_q is not None:     # where to animate a Maya shot: the answer is a choice's number
        from kei.apps.maya_session import answer_choice, save_target
        try:
            choice = answer_choice(target_q["choices"], a.text)
        except ValueError as e:
            print(f"kei: {e}", file=sys.stderr)
            return EXIT_ERROR
        save_target(shot, choice)
    entry = {"stage": state.stage, "attempt": state.attempts, "result": "answer", "misses": [], "at": _now()}
    note = None
    if feedback is not None:        # the reason for the animator's feedback layer: the stage's note, verbatim
        scope = maya_feedback.SCOPES["every" if a.every_shot else "shot"]
        lessons = load_config(_config_path(a.config)).lessons
        note = maya_feedback.answer_note(shot, feedback, a.text, scope, state.stage, state.attempts, lessons)
    state.answers.append({"stage": state.stage, "question": "\n".join(asked), "answer": a.text, "at": _now()})
    state.history.append(entry)
    if note is not None:
        state.history.append(note)
    state.questions = []
    state.status = "running"
    if q.exists():
        q.unlink()
    save_state(shot, state)
    if note is not None:
        print(f"your reason is the note for {state.stage}, with the pose in {note['pose']}"
              + f"; lesson {note['lesson']} ({note['scope']}) added")
    print(f"answer recorded; the animator and the critics read it on the next try. Continue with: kei run {shot}")
    return EXIT_DONE


def _cmd_retry(a) -> int:
    shot = Path(a.shot)
    state = load_state(shot)
    if state.status != "needs_human":
        print(f"this shot has not stopped for a person (status: {state.status})")
        return EXIT_ERROR
    entry = {"stage": state.stage, "attempt": state.attempts, "result": "retry", "misses": [], "at": _now()}
    if a.note:   # an instruction for the animator: the critics do not judge the work against it
        entry["notes"] = [a.note]
        entry["for"] = "animator"
    state.history.append(entry)
    state.attempts = 0
    state.send_backs = 0
    state.status = "running"
    save_state(shot, state)
    print(f"{state.stage}: running again from attempt 1; the next try reads the critics' last notes"
          + (" and your note" if a.note else "") + "; run the shot to continue")
    return EXIT_DONE


def _open_lines(data: dict) -> list[str]:
    """kei status --open in plain words: one block per shot, its open notes numbered."""
    out = []
    for s in data["shots"]:
        last = s["last_pass"]
        when = f", last pass {last['name']} on {last['date']}" if last else ", no pass yet"
        tags = [t for t, on in (("parked", s["parked"]), ("asked today", s["asked_today"])) if on]
        out.append(f"{s['shot']}: {s['status']} at {s['stage']}{when}" + (f" ({', '.join(tags)})" if tags else ""))
        out.append(f"  {s['path']}")
        for n in s["notes"]:
            out.append(f"  {n['n']}. {n['words']} ({n['scope']})")
    for u in data["unreadable"]:
        out.append(f"cannot read {u['path']}: {u['error']}")
    if not data["shots"]:
        out.append("no open shot here")
    if data["hidden"]:
        out.append(f"{data['hidden']} more shot(s) parked or asked about today; show them with --all")
    return out


def _cmd_status_open(a) -> int:
    from kei import chat
    data = chat.open_shots(Path(a.shot or "."), show_all=a.all)
    if a.mark_asked:
        for s in data["shots"]:
            chat.mark_asked(Path(s["path"]))
    if a.json:
        print(json.dumps(data, indent=1, ensure_ascii=False))
    else:
        for line in _open_lines(data):
            print(line)
    return EXIT_DONE


def _cmd_status(a) -> int:
    if a.open:
        return _cmd_status_open(a)
    if a.all or a.mark_asked:
        print("kei: --all and --mark-asked go with --open", file=sys.stderr)
        return EXIT_ERROR
    if not a.shot:
        print("kei: give a shot: kei status <shot>, or list the open shots here: kei status --open", file=sys.stderr)
        return EXIT_ERROR
    if a.json:
        from kei import chat
        print(json.dumps(chat.shot_summary(Path(a.shot)), indent=1, ensure_ascii=False))
        return EXIT_DONE
    state = load_state(Path(a.shot))
    print(f"stage: {state.stage}")
    print(f"attempts: {state.attempts}")
    print(f"send-backs: {state.send_backs}")
    print(f"status: {state.status}")
    from kei.unchecked import unchecked
    marks = unchecked(Path(a.shot))
    if marks:
        print(f"unchecked numbers: {len(marks)} (facts nobody read in a source yet; "
              f"{', '.join(sorted({m['file'] for m in marks}))})")
    from kei.seats import run_totals
    tot = run_totals(Path(a.shot))
    if tot["runs"]:
        tok = tot["tokens"]
        print(f"seat runs: {tot['runs']}, {tot['seconds'] / 3600:.1f} h"
              + (f", tokens {tok.get('input', 0) + tok.get('cache_read', 0) + tok.get('cache_write', 0):,} in, "
                 f"{tok.get('output', 0):,} out" if tok else ""))
    if state.status in PAUSED:
        for line in _pause_reason(state, Path(a.shot)):
            print(line)
        return EXIT_DONE
    if state.status == "needs_answer":
        for line in _question_lines(state, Path(a.shot)):
            print(line)
        return EXIT_DONE
    if state.status == "rejected":
        print(f"rejected: {rejection(state)}")
        print(REOPEN.format(shot=a.shot))
        return EXIT_DONE
    for m in _last_misses(state):
        print(f"- {m}")
    if state.status == "needs_approval":
        for line in _checklist(state, Path(a.shot)):
            print(line)
        print(SIGN_OFF)
    return EXIT_DONE


def _cmd_shots_tidy(a) -> int:
    from kei.character_folder import apply_moves, tidy_moves
    root = Path(a.folder)
    if not root.is_dir():
        print(f"kei: no folder {root}", file=sys.stderr)
        return EXIT_ERROR
    moves = tidy_moves(root)
    if not moves:
        print("every shot is in its character folder already")
        return EXIT_DONE
    apply = a.apply and not a.dry_run
    for m in moves:
        rel = f"{m.shot.name} -> {m.dest.parent.name}/{m.dest.name}"
        print(f"refused: {rel}: {m.refused}" if m.refused else (f"moved: {rel}" if apply else rel))
    if apply:
        apply_moves(moves)
    else:
        print("nothing was moved; to move them: kei shots tidy " + str(root) + " --apply")
    return EXIT_DONE


def _cmd_sheet(a) -> int:
    print(write_sheet(Path(a.shot)))
    return EXIT_DONE


def _cmd_poses(a) -> int:
    _, src, _ = _pass_shot(a)
    shot = read_json(src, "shot") if src.is_file() else None
    path = write_records(Path(a.shot), a.pass_name, _character_of(a, shot), a.mode)
    data = json.loads(path.read_text(encoding="utf-8"))
    for r in data["keys"]:
        com = r["com"]
        where = "airborne" if com is None else ("com inside" if com["inside"] else f"com {com['outside_m']:.3f} m out")
        print(f"f{r['f']} {r['function'] or '-'}: support {r['support']}, weight {r['weight_side'] or '-'}, {where}, "
              f"lean side {r['line_of_action']['side']:+.0f} front {r['line_of_action']['front']:+.0f}"
              + ("" if r["in_plan"] else " (not a key of plan/plan.json)"))
    print(f"written: {path}")
    for page in sorted(path.parent.glob("pose_sheet*.png"), key=lambda q: (len(q.name), q.name)):
        print(f"written: {page}")
    return EXIT_DONE


def _cmd_probe(a) -> int:
    _, src, _ = _pass_shot(a)
    shot = read_json(src, "shot") if src.is_file() else None
    names = [n.strip() for n in a.joints.split(",") if n.strip()]
    table = probe(Path(a.shot), a.pass_name, a.frames, names, _character_of(a, shot), a.mode)
    print(format_table(table))
    if a.json:
        Path(a.json).write_text(json.dumps(table, indent=1), encoding="utf-8")
        print(f"written: {a.json}")
    return EXIT_DONE


def _cmd_demo(a) -> int:
    from kei.demo import run_demo
    folder = Path(a.folder)
    print(f"Kei's tools on an approved walk cycle, in {folder} (no agent, no subscription):")
    for what, path in run_demo(folder):
        print(f"- {what}: {path}")
    print("Open the playback and the sheets. A real shot starts with: kei run <shot> --request \"...\"")
    return EXIT_DONE


def _cmd_trails(a) -> int:
    from kei.trails import draw_trails
    parts = [x.strip() for x in a.parts.split(",") if x.strip()]
    print(f"written: {draw_trails(Path(a.shot), a.passes, parts, a.frames, a.character)}")
    return EXIT_DONE


def _cmd_skill(a) -> int:
    from kei.skill_install import install
    dst = install(a.agent, a.project, a.force)
    print(f"the Kei skill is in {dst}. Start a new chat so your agent reads it.")
    return EXIT_DONE


def _cmd_doctor(a) -> int:
    from kei.doctor import checks, report
    text, fails = report(checks(_config_path(a.config)))
    print(text)
    return EXIT_ERROR if fails else EXIT_DONE


def _cmd_keys(a) -> int:
    dst, said = apply_keys(Path(a.shot), a.pass_name, a.op, to=a.to, frame=a.frame, frames=a.frames,
                           channel=a.channel, value=a.value, by=a.by, src=a.from_)
    print(said)
    print(f"written: {dst} (the version before is in {dst.parent / 'history'}; the edit is in "
          f"{dst.parent / 'edits.json'})")
    return EXIT_DONE


def _cmd_try(a) -> int:
    from kei.trial import trial
    shot = read_json(Path(a.shot) / f"out_{a.pass_name}" / "shot.json", "shot")
    a.character = _character_of(a, shot)
    e = {"op": a.op, "frame": a.frame, "frames": a.frames, "channel": a.channel, "value": a.value, "by": a.by,
         "src": a.from_}
    r = trial(Path(a.shot), a.pass_name, a.character, [e])[0]
    print(f"{r['did']} (on a copy; the shot is unchanged)")
    print(f"flags: {r['before']} before, {r['after']} after")
    for fid in r["gone"]:
        print(f"- gone: {fid}")
    for fid in r["new"]:
        print(f"- new: {fid}: {r['new_what'][fid]}")
    print(f"make it with: kei keys {a.shot} {a.pass_name} {a.op} ..." if r["after"] <= r["before"] and not r["new"]
          else "it adds flags: change the edit, or make it and fix what it brings")
    return EXIT_DONE


def _cmd_bench(a) -> int:
    from kei.bench import read_bench, run_bench
    from kei.state import load_state as _load
    folder = Path(a.folder)
    bench = read_bench(folder)
    first = folder / bench["seat"][0]["name"]
    camera = "delivery" if (first / "plan" / "plan.json").is_file() and "camera" in (
        read_json(first / "plan" / "plan.json", "plan") or {}) else "fixed"

    def run(shot: Path, brief: str, config_path: Path, answers_path: Path | None) -> None:
        try:
            if _load(shot).status in ("done", "needs_approval"):
                return                          # a seat that finished is not run again
        except StateError:
            pass
        args = ["run", str(shot), "--request", brief, "--config", str(config_path)]
        if answers_path is not None:
            args += ["--answers", str(answers_path)]
        main(args)

    def render(shot: Path, pass_name: str) -> Path:
        cam = camera if camera == "fixed" or (shot / "plan" / "plan.json").is_file() else "fixed"
        main(["render", str(shot), pass_name, "--camera", cam])
        out = shot / f"out_{pass_name}" / ("delivery" if cam == "delivery" else "")
        name = "blocking" if pass_name == "blocking" else "playback"
        return next((p for p in (out / f"{name}.mp4", out / f"{name}.gif") if p.is_file()), out / f"{name}.mp4")
    r = run_bench(folder, run=run, render=render)
    for row in r["rows"]:
        print(f"{row['seat']}: {row['status']}, {row['tries']} tries, {row['hours']} h, {row['scripts']} scripts")
    print(f"blind videos: {', '.join(r['blind'])} in {folder / 'blind'}; key sealed, sha256 {r['seal'][:16]}...")
    print(f"written: {folder / 'RUNS.md'}")
    return EXIT_DONE


def _cmd_curves(a) -> int:
    from kei.curves import draw_curves
    for p in draw_curves(Path(a.shot), a.pass_name, [c.strip() for c in a.channels.split(",") if c.strip()],
                         a.frames, a.mode):
        print(f"written: {p}")
    return EXIT_DONE


def _cmd_sweep(a) -> int:
    from kei.trial import sweep_edits, trial
    shot = read_json(Path(a.shot) / f"out_{a.pass_name}" / "shot.json", "shot")
    character = _character_of(a, shot)
    edits = sweep_edits(shot, a.frame, a.channel, a.lo, a.hi, a.steps, a.index)
    results = trial(Path(a.shot), a.pass_name, character, edits)
    print(f"{a.channel} at f{a.frame}, number {a.index}, on a copy (the shot is unchanged); "
          f"{results[0]['before']} flags as it is")
    best = min(results, key=lambda r: (r["after"], len(r["new"])))
    for e, r in zip(edits, results):
        mark = "  <- fewest flags" if r is best else ""
        print(f"- {e['value']}: {r['after']} flags, {len(r['gone'])} gone, {len(r['new'])} new{mark}")
    return EXIT_DONE


def _round(p) -> list[float]:
    return [round(v, 6) for v in p]


def _cmd_pose(a) -> int:
    pose = read_json(Path(a.pose), "pose")
    check_channels(pose)
    print(json.dumps({n: _round(p) for n, p in solve(pose).items()}, indent=1))
    return EXIT_DONE


def _pass_shot(a) -> tuple[Path, Path, str]:
    out = Path(a.shot) / f"out_{a.pass_name}"
    mode = a.mode or ("step" if a.pass_name == "blocking" else "spline")
    return out, out / "shot.json", mode


CHARACTER_PANEL = 540   # pixels per view panel of a character render: large enough to read, smooth
POST_PANEL = 540        # a post is two panels a side: 1080 x 1080


def _render_rest(a) -> int:
    ch = load_character(a.character)
    out = Path(a.out or ".")
    out.mkdir(parents=True, exist_ok=True)
    rest = out / f"{ch.name}_rest.png"
    rest.write_bytes(draw_character_views(ch, rest_pose(ch), size=a.size or 360, emission=a.emission, overlay=a.overlay))
    sil = out / f"{ch.name}_silhouette.png"
    sil.write_bytes(draw_silhouette(ch, size=a.size or 360))
    print(f"rest views ({', '.join(CHARACTER_VIEWS)}): {rest}")
    print(f"silhouette: {sil}")
    return EXIT_DONE


def _character_of(a, shot) -> str:
    """The shot's character: --character, else shot.json's "character", else PLAN.md, else the default: KEI_CHARACTER
    (set by the conductor for its seats), else the config's. The config is read only when it is needed."""
    if a.character:
        return shot_character(a.shot, {"character": a.character}, "")
    if (isinstance(shot, dict) and shot.get("character") is not None) or plan_character(a.shot) is not None:
        return shot_character(a.shot, shot, "")
    default = os.environ.get(CHARACTER_ENV) or load_config(_config_path(a.config)).character
    return shot_character(a.shot, shot, default)


RENDER_DEFAULTS = {"style": "character", "camera": "fixed", "size": None, "emission": 1.0, "overlay": False,
                   "onion": 0, "mode": None}


def _pin_render_settings(a) -> None:
    """Settings kei render did not get on its command line come from the shot's render.json, so every render of a
    stage looks the same: {"all": {...}, "blocking": {...}, "passes": {...}, "p6": {...}}, the pass's own entry over
    its stage's over all. What neither gives takes Kei's default."""
    pinned = {}
    path = Path(a.shot) / "render.json" if a.shot else None
    if path is not None and path.is_file():
        data = read_json(path, "render settings")
        if not isinstance(data, dict):
            raise ShotError(f"{path} must be a JSON object of settings by stage")
        stage = "blocking" if a.pass_name == "blocking" else "passes"
        for k in ("all", stage, a.pass_name):
            entry = data.get(k) or {}
            if not isinstance(entry, dict):
                raise ShotError(f"{path}: {k!r} must be an object of settings")
            unknown = set(entry) - set(RENDER_DEFAULTS)
            if unknown:
                raise ShotError(f"{path}: {k!r} names {', '.join(sorted(unknown))}; the settings are "
                                f"{', '.join(RENDER_DEFAULTS)}")
            pinned.update(entry)
    for k, default in RENDER_DEFAULTS.items():
        if getattr(a, k, None) is None:
            setattr(a, k, pinned.get(k, default))


def _cmd_render(a) -> int:
    if a.shot is not None and a.pass_name is None:
        raise ShotError("kei render <shot> needs a pass too (blocking, p1, ...)")
    _pin_render_settings(a)
    if a.shot is None:
        if a.character is None:
            raise ShotError("kei render needs a shot and a pass (kei render <shot> <pass>), or --character")
        return _render_rest(a)
    if maya_shot.is_maya_shot(Path(a.shot)):
        return _render_maya(a)
    from kei.apps import unreal_stage
    if unreal_stage.is_unreal_shot(Path(a.shot)):
        return _render_unreal(a)
    out, src, mode = _pass_shot(a)
    if not src.is_file():
        raise ShotError(f"no {src}: write the pass's keys there first")
    shot = read_json(src, "shot")
    check_shot(shot)
    ch = load_character(_character_of(a, shot))
    if a.post:      # a clean video to post: four smooth views, no review marks, into --out (default out_<pass>/post)
        dst = Path(a.out) if a.out else out / "post"
        r = render_post(src, dst, mode, ch, height=2 * (a.size or POST_PANEL), emission=a.emission, workers=a.workers,
                        name=f"{Path(a.shot).resolve().name}_{a.pass_name}")
        print(f"character: {ch.name}, post: {len(r['frames'])} frames in {dst / 'frames'}")
        print(f"video: {r['video']}" + (f", ten loops: {r['loops']}" if r.get("loops") else ""))
        return EXIT_DONE
    name = "blocking" if a.pass_name == "blocking" else "playback"
    camera = None
    if a.camera == "follow":
        camera, out = "follow", out / "follow"
    elif a.camera == "delivery":
        plan = Path(a.shot) / "plan" / "plan.json"
        data = read_json(plan, "plan") if plan.is_file() else {}
        if not isinstance(data, dict) or "camera" not in data:
            raise ShotError('plan/plan.json has no "camera": add the locked delivery camera to the plan (yaw_deg, '
                            'target_m, lens_mm and distance_m or span_m, aspect, follow) to render through it')
        camera, out = Camera.from_plan(data["camera"]), out / "delivery"
    if a.style == "stick":      # the diagnostic stick figure, on the character's proportions
        r = render_shot(src, out, mode, size=a.size or 360, name=name, proportions=ch.proportions, camera=camera,
                        onion=a.onion)
    else:
        if a.onion:
            raise ShotError("--onion draws on the stick figure: add --style stick")
        r = render_shot(src, out, mode, size=a.size or CHARACTER_PANEL, name=name, character=ch, workers=a.workers,
                        emission=a.emission,
                        overlay=a.overlay, camera=camera)
    print(f"character: {ch.name}, style: {a.style}, camera: {a.camera}")
    if isinstance(camera, Camera):
        from kei.camera_check import framing
        report = framing(shot, mode, ch, camera)
        (out / "framing.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"camera: {len(report['setups'])} setup(s), cuts at "
              f"{', '.join(f'f{c}' for c in camera.cuts()) or 'none'}; staging notes in {out / 'framing.json'}")
        for n in report["notes"]:
            print(f"- {n}")
    print(f"rendered {len(r['frames'])} frames, mode {mode}")
    print(f"frames: {out / 'frames'}")
    print(f"key stills: {', '.join(p.name for p in r['stills'])}")
    print(f"key sheet: {r['keys']}")
    print(f"playback ({r['kind']}): {r['playback']}")
    if r.get("loops"):
        print(f"ten loops at the shot's frame rate: {r['loops']}")
    return EXIT_DONE


def _render_unreal(a) -> int:
    from kei.apps.unreal_render import render_pass
    if a.camera != "fixed":
        raise ShotError("an Unreal pass is drawn by Kei's renderer on the joints Unreal gave back, from its fixed "
                        f"views; --camera {a.camera} is for a pass on Kei's own rig")
    r = render_pass(Path(a.shot), a.pass_name, size=a.size or 360)
    print(f"renderer: {r['renderer']} (Kei's own, on the joints from Unreal)")
    print(f"rendered {len(r['frames'])} frames in {Path(a.shot) / f'out_{a.pass_name}' / 'frames'}")
    print(f"key sheet: {r['keys']}")
    print(f"playback ({r['kind']}): {r['playback']}")
    if r.get("loops"):
        print(f"ten loops at the shot's frame rate: {r['loops']}")
    return EXIT_DONE


def _render_maya(a) -> int:
    if a.camera != "fixed":
        raise ShotError("a Maya shot renders through Maya's cameras (front, side, top, three quarter); --camera "
                        f"{a.camera} is for Kei's own renderer")
    r = maya_shot.render_pass(Path(a.shot), a.pass_name)
    print(f"renderer: {r['renderer']}")
    for view, n in r["frames"].items():
        print(f"{view}: {n} frames in {r['folder'] / view.replace(' ', '_')}")
    for view, p in r["videos"].items():
        print(f"playback ({view}): {p}")
    if r["side_by_side"]:
        print(f"the views side by side: {r['side_by_side']}")
    if r["loops"]:
        print(f"ten loops at the shot's frame rate: {r['loops']}")
    return EXIT_DONE


def _cmd_maya_setup(a) -> int:
    if a.scene and a.character:
        raise ShotError("kei maya setup takes --character or --scene, not both")
    r = maya_shot.setup_shot(Path(a.shot), character=a.character, scene=Path(a.scene) if a.scene else None,
                             fps=a.fps)
    print(f"Maya {r['maya_version']}: {r['scene']}" + (f" ({r['character']} with its control rig)"
                                                      if r["character"] else " (a copy of your scene)"))
    print(f"the rig: {Path(a.shot) / 'rig' / 'maya_rig.json'}")
    return EXIT_DONE


def _cmd_maya_key(a) -> int:
    r = maya_shot.key_pass(Path(a.shot), a.pass_name, a.mode)
    out = Path(a.shot) / f"out_{a.pass_name}"
    where = f"the open Maya (session {r['session']}), layer {r['layer']}" if r.get("target") == "open" else "the background"
    if r.get("said"):
        print(r["said"])
    print(f"{r['keys']} keys in {where}, mode {r['mode']}, the pass's scene {out / 'scene.ma'}")
    if (out / "joints.json").is_file():
        print(f"joints for the checks: {out / 'joints.json'}")
    for c in r["clipped"]:
        print(f"- f{c['f']} {c['channel']}: asked {c['asked']:.3f}, a limit holds it at {c['reached']:.3f}")
    fb = r.get("feedback")
    if fb:
        if not fb.get("created"):
            print(f"{fb['layer']} is already there and was left as it is")
        print(f"pose corrections on layer {fb['layer']}, then run: kei maya feedback {a.shot}")
    return EXIT_DONE


def _cmd_maya_feedback(a) -> int:
    from kei.apps import maya_feedback as fb
    from kei.signoff import note_refusal
    shot = Path(a.shot)
    in_run = bool(os.environ.get(fb.RUN_ENV))     # a seat of kei run: nobody at the keyboard
    if a.text is not None and not a.text.strip():
        print("kei: the reason needs words, in one sentence; Kei never writes it for you", file=sys.stderr)
        return EXIT_ERROR
    if not in_run:
        why = note_refusal(load_state(shot), a.stage)
        if why:
            print(why if why.startswith("this shot") else f"kei: {why}", file=sys.stderr)
            return EXIT_ERROR
        if a.text is None and not sys.stdin.isatty():
            print('kei: give the reason in one sentence with --text "..." (and --every-shot when it applies to every '
                  "shot); Kei never writes it for you", file=sys.stderr)
            return EXIT_ERROR
    c = fb.collect(shot, Path(a.scene) if a.scene else None)
    found = c["found"]
    for line in fb.other_pass_lines(found):
        print(line)
    if not fb.has_feedback(found):
        print(f"no correction found in {c['source']} (pass {c['pass']}): no animation layer named feedback "
              f"(feedback_{c['pass']}, or feedback_<anything> of your own) holds a key. Key the corrections on the "
              "rig's controls on that layer, then run this again. Nothing was recorded.")
        for line in fb.outside_lines(found):
            print(f"- {line}")
        return EXIT_ERROR
    lines = fb.describe(found)
    print(f"the feedback on pass {c['pass']}, read on a copy of {c['source']}:")
    for line in lines:
        print(f"- {line}")
    for line in fb.outside_lines(found):
        print(f"- {line}")
    n = fb.next_number(shot)
    renders = None if a.no_render else fb.render(c, shot / fb.FOLDER / str(n))
    for name, r in (renders or {}).items():
        what = "Kei's pass" if name == "before" else "with your correction"
        where = r["side_by_side"] or ", ".join(str(p) for p in r["videos"].values()) or \
            str(shot / fb.FOLDER / str(n) / name)
        print(f"{name} ({what}, {len(r['views'])} views): {where}")
    if in_run:
        pose = fb.save_pose(shot, n, c, lines, renders)
        q = fb.ask_in_run(shot, n, lines, renders)
        print(f"the pose is in {pose}; the question for the author is in {q} (the shot waits for kei answer)")
        return EXIT_DONE
    text, every = a.text, a.every_shot
    if text is None:
        text = input("Why? Give the reason in one sentence (Kei keeps it word for word): ")
        if not text.strip():
            print("no reason given: nothing was recorded")
            return EXIT_ERROR
        if not every:
            every = input("Is it for this shot or every shot? (this / every, default this): ").strip().lower() \
                .startswith("every")
    scope = fb.SCOPES["every" if every else "shot"]
    pose = fb.save_pose(shot, n, c, lines, renders)
    config = load_config(_config_path(a.config))
    state, lesson = fb.record_note(shot, text, scope, a.stage, config.lessons, pose)
    fb.write_note(shot, n, text, scope, a.stage)
    if state.history[-1].get("withdrew_approval"):
        print("approval withdrawn: the shot is open again")
    print(f"note {n} recorded word for word for {scope}, the pose in {pose}; the shot goes back to {a.stage}")
    print(f"lesson {lesson} ({scope}) added to {config.lessons}")
    print(f"continue with: kei run {shot}")
    return EXIT_DONE


SHELF_FILES = ("kei_host.py", "kei_tools.py", "kei_math.py", "kei_proc.py", "kei_control_rig.py")
USER_SETUP = "import maya.utils, kei_host; maya.utils.executeDeferred(kei_host.start)"


def _cmd_maya_shelf(a) -> int:
    import shutil
    from kei.apps.maya import MAYA_SIDE, NO_REPORTS
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in SHELF_FILES:
        shutil.copyfile(MAYA_SIDE / name, out / name)
    (out / "kei_start.py").write_text('"""The Kei shelf button: start the Kei host in this Maya (once is enough)."""\n'
                                      "import kei_host\n\nkei_host.start()\n", encoding="utf-8")
    scripts = Path.home() / "Documents" / "maya" / "scripts"
    print(f"Kei host files written to {out}. Kei installs nothing in Maya; to let Kei work in your open Maya:")
    print(f"1. Copy the files in {out} into your Maya scripts folder (usually {scripts}).")
    print(f"2. Add this line to userSetup.py in that folder (make the file if it is not there):")
    print(f"   {USER_SETUP}")
    print("   Or start the host by hand: a shelf button with the Python command in kei_start.py.")
    print("3. Optional, so Maya itself sends no crash report, usage data or messages: add these lines to Maya.env "
          "(in your Maya preferences folder):")
    for k, v in NO_REPORTS.items():
        print(f"   {k}={v}")
    print("The host answers on 127.0.0.1 only and only to Kei's session token.")
    return EXIT_DONE


def _cmd_unreal_setup(a) -> int:
    print("Kei animates in your open Unreal Editor through Claireon. Kei installs nothing by itself. One time:")
    print("1. Install Claireon in your project: https://github.com/believer-oss/claireon (Kei was tested with "
          "Claireon 2.2.0 on Unreal 5.8.3).")
    print("2. In the editor, enable the Python Editor Script Plugin (Edit, Plugins, Scripting), then restart it.")
    print("3. Start the editor with the flag -StartMCPServer, or click the Claireon button in the editor toolbar. "
          "Claireon writes its port to <your project>/Saved/Claireon/MCPServer.json, and Kei reads it there.")
    print("4. Keep Kei's working assets out of your repository: add Content/Kei/ to your project's ignore file "
          "(for git, a line Content/Kei/ in .gitignore).")
    print("5. Add these lines to kei.toml (or run kei run <shot> --app unreal):")
    for line in ("[apps]", 'app = "unreal"', "[apps.unreal]",
                 'project = "C:/path/to/YourProject"   # the folder with the .uproject file', 'session = "ask"'):
        print("   " + line)
    print("Kei connects to 127.0.0.1 only. It writes and saves only assets under /Game/Kei/<shot>/, never a "
          "save-all and never one of your assets. A shot always asks which open editor to use.")
    print("Then run kei unreal check: it reads the project, asks the open editor, and compares both to the tested "
          "combinations.")
    return EXIT_DONE


def _cmd_unreal_check(a) -> int:
    from kei.apps.unreal_check import checks, compatibility_lines
    from kei.doctor import report
    project, url = a.project, a.url
    if project is None and url is None:
        try:
            config = load_config(_config_path(a.config))
            project, url = config.unreal_project, config.unreal_url
        except ConfigError:
            pass
    text, fails = report(checks(project, url))
    print(text)
    print("Tested combinations:")
    for line in compatibility_lines():
        print("   " + line)
    return EXIT_ERROR if fails else EXIT_DONE


def _print_tidy(r: dict) -> None:
    print(f"Unreal: {len(r['moved'])} of Kei's sequences filed under Production/<phase>; on top: "
          + (", ".join(p.rsplit('/', 1)[-1] for p in r.get("kept", [])) or "nothing kept"))
    for src, why in r.get("failed", []):
        print(f"- not moved: {src}: {why}")


def _unreal_report_copy(shot: Path, tidied: dict | None) -> None:
    """A copy of the report beside Kei's Unreal assets for the shot, when the editor said where its Content is."""
    if not tidied or not tidied.get("content_dir"):
        return
    from kei.apps.unreal_rig import kei_folder
    from kei.live.report import write_unreal_copy
    print(f"a copy beside the Unreal assets: {write_unreal_copy(shot, tidied['content_dir'], kei_folder(shot))}")


def _cmd_unreal_tidy(a) -> int:
    from kei.apps import unreal_stage
    r = unreal_stage.tidy_shot(Path(a.shot))
    _print_tidy(r)
    _unreal_report_copy(Path(a.shot), r)   # a delivered shot's copy is written again once the folder is packed
    return EXIT_DONE


def _cmd_unreal_capture_test(a) -> int:
    from kei.apps import unreal_stage
    r = unreal_stage.capture_test(Path(a.shot), a.pass_name, a.frame)
    print(f"frame {r['frame']} of {r['sequence']}; the character was found as {r['found']}")
    for name, shown in sorted(r["nonblack"].items()):
        print(f"  {name}: {shown:.0%} of the picture is the character")
    for f in r["files"]:
        print(f"  {f}")
    for e in r["errors"]:
        print(f"  not drawn: {e}")
    print("It looks drawn: open the pictures and check that they show your character."
          if r["looks_drawn"] else
          "It does NOT look drawn (empty or black): send these lines and the pictures to the Kei author.")
    return EXIT_DONE if r["looks_drawn"] else EXIT_ERROR


def _cmd_unreal_switch(a) -> int:
    from kei.apps import unreal_stage
    r = unreal_stage.switch_limb(Path(a.shot), a.pass_name, a.limb, a.to, a.frame)
    if not r["written"]:
        print(f"nothing written: {r['why']}")
        return EXIT_ERROR
    print(f"{r['limb']} switches to {r['to'].upper()} at f{r['frame']}, matched within {r['gap_cm']:.2f} cm in the "
          f"editor; keyed in out_{a.pass_name}/shot.json: the switch on f{r['frame'] - 1} and f{r['frame']}, and "
          + ", ".join(r["controls"]))
    print(f"key it with: kei unreal key {a.shot} {a.pass_name}")
    return EXIT_DONE


def _cmd_unreal_key(a) -> int:
    from kei.apps import unreal_stage
    r = unreal_stage.key_pass(Path(a.shot), a.pass_name, load_config(_config_path(a.config)))
    print(f"{r['said']}; saved {r['saved']}")
    if r["clipped"]:
        print(f"{len(r['clipped'])} pose(s) a limit held back: see out_{a.pass_name}/unreal_report.json")
    print(f"joints for the checks: {r['joints']}")
    return EXIT_DONE


def _cmd_unreal_pose(a) -> int:
    from kei.apps import unreal_stage
    r = unreal_stage.pose_shot(Path(a.shot), a.anim, a.frame)
    c = r["check"]
    print(f"the pose of {r['anim']} frame {r['frame']} on the rig: {len(r['keys'])} channels, written to {r['path']}")
    print(f"check: mean {c.get('mean_deg')} deg over {c.get('bones')} bones; head, hands, fingertips and feet "
          f"against the animation (cm, from the pelvis): {c.get('pelvis_relative_cm')}")
    if not r["matches"]:
        print("the rig does not reach this pose closely (more than 1 deg on average, or more than 2 cm at a hand, "
              "the head or a foot): say so to the author before building on it")
    return EXIT_DONE


def _cmd_unreal_style(a) -> int:
    from kei.apps import unreal_stage
    from kei.characters import load_character
    src = Path(a.shot) / "out_blocking" / "shot.json"
    shot = read_json(src, "shot") if src.is_file() else None
    ch = load_character(_character_of(a, shot))
    r = unreal_stage.style(Path(a.shot), a.anim, ch, a.fps)
    print(f"her style range, from {len(r['clips'])} clip(s) of her own: {r['path']}")
    for m, v in sorted(r["range"].items()):
        print(f"- {m}: up to {v['max']} ({v['clip'].rsplit('/', 1)[-1]}, f{v['frames'][0]}-{v['frames'][1]})")
    if not r["range"]:
        print("- no soft check goes past Kei's realism thresholds in these clips: the range adds nothing")
    print("largest move per part (cm): " + ", ".join(f"{p} {cm}" for p, cm in sorted(r["move_cm"].items())))
    return EXIT_DONE


def _export_unreal(a) -> int:
    from kei.apps import unreal_stage
    from kei.apps.unreal_bake import bake_lines
    if not a.shot or not a.pass_name:
        raise ShotError("kei export --to unreal needs --shot and --pass: kei export --shot <shot> --pass <pass> "
                        "--to unreal")
    report = unreal_stage.bake(Path(a.shot), a.pass_name)
    for line in bake_lines(report):
        print(line)
    return EXIT_DONE if report["ok"] else EXIT_ERROR


def _cmd_export(a) -> int:
    if a.shot_arg and a.shot and Path(a.shot_arg) != Path(a.shot):
        raise ShotError("give the shot once: kei export <shot>, or --shot <shot>")
    a.shot = a.shot or a.shot_arg
    if a.to == "unreal":
        return _export_unreal(a)
    if a.shot and maya_shot.is_maya_shot(Path(a.shot)):
        if (a.format or "fbx") != "fbx" or not a.pass_name:
            raise ShotError("a Maya shot exports FBX from a keyed pass: kei export --shot <shot> --pass <pass> "
                            "--format fbx")
        r = maya_shot.export_pass(Path(a.shot), a.pass_name, Path(a.out or f"{Path(a.shot).name}_{a.pass_name}.fbx"))
        print(f"{r['fbx']} ({r['joints']} joints, baked from the controls)")
        return EXIT_DONE
    shot, mode = None, None
    if a.shot:
        if not a.pass_name:
            a.pass_name = _final_pass(Path(a.shot))
        _, src, mode = _pass_shot(a)
        shot = read_json(src, "shot")
        check_shot(shot)
    elif not a.character:
        raise ShotError("kei export needs a shot (kei export <shot>) or --character for the rest pose")
    ch = load_character(_character_of(a, shot) if a.shot else a.character)
    suffix = Path(a.out).suffix.lower() if a.out else ""
    fmt = a.format or ("fbx" if suffix == ".fbx" else "gltf")
    if fmt == "both" and a.out:
        raise ShotError("--format both writes two files: give a folder with --out-dir, not --out")
    if suffix in (".fbx", ".glb") and suffix != (".fbx" if fmt == "fbx" else ".glb"):
        raise ShotError(f"--format {fmt} does not write a {suffix} file")
    for f in (("gltf", "fbx") if fmt == "both" else (fmt,)):
        ext = "fbx" if f == "fbx" else "glb"
        if a.out:
            dst = Path(a.out)
        elif a.shot:
            folder = Path(a.out_dir) if a.out_dir else Path(a.shot)   # on top: a delivered shot keeps it there
            folder.mkdir(parents=True, exist_ok=True)
            dst = folder / f"{Path(a.shot).resolve().name}_{a.pass_name}.{ext}"
        else:
            dst = (Path(a.out_dir) if a.out_dir else Path(".")) / f"{ch.name}.{ext}"
        write = export_fbx if f == "fbx" else export_glb
        path = write(ch, dst, a.emission, shot, mode or "spline")
        print(f"{ch.title}: {path}" + (f" (pass {a.pass_name}, animated, mode {mode})" if shot else " (rest pose)"))
    return EXIT_DONE


def _final_pass(shot: Path) -> str:
    """The pass kei export takes when none is named: the approved pass of a delivered shot, else the newest numbered
    pass, else blocking."""
    import re as _re
    try:
        final = json.loads((Path(shot) / ".kei" / "layout.json").read_text(encoding="utf-8")).get("final_pass")
    except (OSError, ValueError):
        final = None
    if final and (Path(shot) / f"out_{final}" / "shot.json").is_file():
        return final
    nums = [int(m.group(1)) for p in Path(shot).glob("out_p*") if p.is_dir() and (p / "shot.json").is_file()
            and (m := _re.fullmatch(r"out_p(\d+)", p.name))]
    if nums:
        return f"p{max(nums)}"
    if (Path(shot) / "out_blocking" / "shot.json").is_file():
        return "blocking"
    raise ShotError(f"{shot} has no pass to export yet (no out_p<N>/shot.json or out_blocking/shot.json)")


def _cmd_import(a) -> int:
    from kei.characters.imported import check_name, confirm
    from kei.models.importer import import_model, joint_errors_text
    check_name(a.name)
    if a.confirm and a.model:
        raise ModelError(f"kei import {a.model} --confirm: --confirm approves the fit of an import already made and "
                         "reads no model. Import the model first (without --confirm), look at its fit.png, then run "
                         f"kei import --confirm --name {a.name}")
    if a.confirm:
        if a.name not in imported_characters():
            raise CharacterError(f"no imported character {a.name!r} in {characters_dir()}")
        confirm(characters_dir() / a.name)
        print(f"{a.name}: fit approved. Shots can animate it now (Character: {a.name} in PLAN.md, or shot.character "
              "in kei.toml).")
        return EXIT_DONE
    if not a.model:
        raise ModelError("kei import needs a model file (.glb, .gltf or binary .fbx), or --confirm")
    maps = {}
    for pair in a.map or []:
        if "=" not in pair:
            raise ModelError(f"--map {pair}: write it as <model bone>=<kei bone>, for example mixamorig:Spine2=spine_05")
        theirs, ours = pair.split("=", 1)
        maps[theirs.strip()] = ours.strip()
    folder, report = import_model(a.model, a.name, a.height, maps, a.unrigged)
    print(f"imported {a.name} into {folder}")
    print(f"skeleton: {report['skeleton']}; parts: {report['parts']['rigid']} rigid, {report['parts']['smooth']} "
          "smooth")
    if report.get("unmapped"):
        print(f"model bones Kei did not use (their weights went to the nearest mapped parent): "
              f"{', '.join(report['unmapped'])}")
    for w in report.get("warnings", []):
        print(f"warning: {w}")
    print(f"fit errors: {joint_errors_text(report)}")
    print(f"Question: does every joint of the fitted skeleton sit where {a.name}'s body bends, and does the last "
          "panel (a shot's neutral stance: trunk upright, head stacked) stand it as you want it to play?")
    print(f"Look at: {folder / 'fit.png'}")
    print(f"If it is right: kei import --confirm --name {a.name}")
    print("If it is wrong: import it again with another --height, --map, or --unrigged. A shot on it asks this too.")
    return EXIT_NEEDS_ANSWER


WEB_QUESTION = ("Kei's agents look for references on the web: research papers, and clips to study (linked at a "
                "timestamp, never downloaded). Allow web access? [Y/n] ")


def _web_answer(given: str | None) -> tuple[str, bool]:
    """The web access answer: the flag when given, else the person's answer at a terminal, else on (the default).
    The second value is True when a person or a flag chose it."""
    if given:
        return given, True
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            reply = input(WEB_QUESTION).strip().lower()
        except EOFError:
            reply = ""
        return ("off" if reply in ("n", "no", "off") else "on"), True
    return "on", False


def _save_web(config_path: Path, given: str | None = None) -> str:
    """Ask once for web access and write seats.web into kei.toml, so no later run asks again."""
    from kei.settings import apply_change
    web, chosen = _web_answer(given)
    apply_change(config_path, {"seats.web": web}, which=lambda _: "checked elsewhere")   # init names missing CLIs
    how = "" if chosen else " (the default; nobody was at a terminal to ask)"
    print(f"web access: {web}{how}, saved in {config_path}. Change it with: kei settings set seats.web on|off")
    return web


def _cmd_init(a) -> int:
    """Write ./kei.toml from the example, so a new folder is ready for `kei run`. Never overwrites a kei.toml."""
    dest = Path.cwd() / "kei.toml"
    if dest.exists():
        print(f"kei.toml is already here ({dest}); left as it is. Start a shot with: kei run <shot> --request \"...\"")
        return EXIT_DONE
    dest.write_bytes(EXAMPLE_CONFIG.read_bytes())
    print(f"wrote {dest} from the example: one animator seat and two critic seats, your own agent command lines.")
    _save_web(dest, getattr(a, "web", None))
    seats = load_config(dest)
    missing = sorted({s.cmd[0] for s in [seats.animator, *seats.critics] if s.cmd and not shutil.which(s.cmd[0])})
    if missing:
        print("not found on your PATH: " + ", ".join(missing) + ". Install them, or change the seats with kei settings.")
    print("Check the rest of the setup (ffmpeg, gh, the rule book, the seats' versions) with: kei doctor")
    print('Start a shot with: kei run <shot> --request "what to animate"')
    return EXIT_DONE


def _cmd_characters(a) -> int:
    print("built in: " + ", ".join(CHARACTERS))
    names = imported_characters()
    print(f"imported ({characters_dir()}):" + ("" if names else " none"))
    for n in names:
        ch = load_character(n)
        state = "fit approved" if ch.confirmed else f"fit not approved: look at {ch.folder / 'fit.png'}"
        print(f"  {n}: {ch.height:.2f} m, {state}")
    print("Use one in a shot with a 'Character: <name>' line in PLAN.md, or shot.character in kei.toml.")
    return EXIT_DONE


def _cmd_bake(a) -> int:
    from kei.apps import unreal_stage
    if unreal_stage.is_unreal_shot(Path(a.shot)):
        raise ShotError(f"{a.shot} is an Unreal shot: kei unreal key {a.shot} {a.pass_name} keys it in Unreal and "
                        "writes the joints Unreal gives back; kei bake would replace them with Kei's own rig")
    if maya_shot.is_maya_shot(Path(a.shot)):
        raise ShotError(f"{a.shot} is a Maya shot: kei maya key {a.shot} {a.pass_name} keys it in Maya and writes "
                        "the joints Maya gives back; kei bake would replace them with Kei's own rig")
    out, src, mode = _pass_shot(a)
    shot = read_json(src, "shot")
    check_shot(shot)
    ch = load_character(_character_of(a, shot))
    from kei.characters import on_character
    frames = [{"f": fr["f"], "pose": fr["pose"], "joints": {n: _round(p) for n, p in fr["joints"].items()}}
              for fr in bake(on_character(shot, ch), mode)]
    dst = out / "joints.json"
    dst.write_text(json.dumps({"fps": shot.get("fps") or 24, "mode": mode, "character": ch.name, "frames": frames}),
                   encoding="utf-8")
    print(f"{len(frames)} frames, mode {mode}, character {ch.name}: {dst}")
    return EXIT_DONE


def _cmd_check(a) -> int:
    _, src, _ = _pass_shot(a)
    shot = read_json(src, "shot") if src.is_file() else None
    character = _character_of(a, shot)
    path = check_pass(Path(a.shot), a.pass_name, character, a.mode)
    report = json.loads(path.read_text(encoding="utf-8"))
    print(f"character: {character}, mode: {report['mode']}")
    for f in report["flags"]:
        tag = ""
        if f.get("inside_style"):
            tag = f" (note: inside her style range, as in {f['style_clip']})"
        elif f.get("note"):
            tag = " (note: the register is pushed)"
        print(f"- {f['check']} f{f['frames'][0]}-{f['frames'][1]}: {f['what']}{tag}")
    if "style" in report:
        print(f"register: {report['style']['register']}; style range: "
              + ("rig/style.json" if report["style"]["style_range"] else "none yet (kei unreal style)"))
    print(report["summary"])
    print(f"written: {path}")
    pr_path = path.parent.parent / "principles" / "principles.json"
    if pr_path.is_file():
        from kei.principles import undeclared
        pr = json.loads(pr_path.read_text(encoding="utf-8"))
        gates = Path(a.shot) / "GATES.md"
        open_ = undeclared(pr, gates.read_text(encoding="utf-8") if gates.is_file() else "")
        print("the twelve principles: " + ", ".join(f"{k} {v}" for k, v in pr["summary"].items()))
        for f in open_:
            print(f"- {f['id']} f{f['frames'][0]}-{f['frames'][1]}: {f['what']}")
        print(f"{len(open_)} principle flag(s) open: fix each, or declare it in GATES.md under \"## Declared\" as "
              "\"- <id>: <reason>\"" if open_ else "no principle flag open")
        print(f"written: {pr_path}")
    if getattr(a, "explain", None):
        from kei.explain import explain
        lines = explain(path.parent.parent, a.explain)
        print(f"\nexplain {a.explain}:")
        for line in lines:
            print(line)
        if not lines:
            print(f"kei: no flag matches {a.explain!r} on this pass: copy an id or a check name from the list above",
                  file=sys.stderr)
            return EXIT_ERROR
    return EXIT_DONE


def _cmd_retarget(a) -> int:
    from kei.retarget import retarget_pass
    dst, r = retarget_pass(Path(a.shot), a.pass_name, a.from_, a.to, a.out, keep=a.keep)
    print(f"refitted {a.pass_name} -> {a.out}: {dst}")
    print(f"- foot targets: height {r['ankle_shift_m']:+.4f} m on every key (ankle height {r['old_ankle']} -> "
          f"{r['new_ankle']}); kept along the ground")
    print(f"- root: height {r['root_shift_m']:+.4f} m on every key (standing root {r['old_standing_root']:.5f} -> "
          f"{r['new_standing_root']:.5f})")
    print(f"- the contacts about the same ankle: heel {r['heel_moves_m']:+.4f} m, ball {r['ball_moves_m']:+.4f} m, "
          f"toe tip {r['toe_moves_m']:+.4f} m forward; hip width {r['hip_width_change_m']:+.4f} m")
    if r["knee_offsets_m"]:
        o = r["knee_offsets_m"]
        print(f"- root, to keep the knees: {min(o.values()):+.4f} to {max(o.values()):+.4f} m more per key, smoothed: "
              + ", ".join(f"f{f:g} {v:+.4f}" for f, v in sorted(o.items())))
    if r["lowered_for_reach"]:
        print("- root lowered further for the leg's reach: "
              + ", ".join(f"f{f:g} {v:.4f} m" for f, v in sorted(r["lowered_for_reach"].items())))
    else:
        print("- no key lowered for reach")
    if r["beyond_reach_frames"]:
        print(f"- still beyond reach between keys (over {0.005} m): frames {r['beyond_reach_frames']}")
    print("Check it with: kei check <shot> " + a.out)
    return EXIT_DONE


def _cmd_review(a) -> int:
    from kei.review import app
    from kei.review.drawings import DrawingError
    from kei.review.rounds import ReviewError
    from kei.share import BundleError
    target = Path(a.config) if a.config else Path.cwd() / "kei.toml"   # the Settings tab saves here
    try:
        if a.lesson or a.pr:
            server = app.lesson_server(a, _config_path(a.config))
        elif a.shot:
            config = load_config(_config_path(a.config))
            app.check_shot(Path(a.shot))
            print(f"making the review round of {a.shot} (each frame in four views)")
            server, routes = app.shot_server(Path(a.shot), config, size=a.size, port=a.port, settings=target,
                                             shown=_config_path(a.config))
            print(f"after: {routes.after}" + (f", before: {routes.before['round']}" if routes.before else ""))
        else:
            server, mode = app.list_server(Path.cwd(), port=a.port, settings=target, shown=_config_path(a.config))
            print(f"{len(mode['shots'])} shot(s) waiting for a sign-off, {len(mode['lessons'])} shared lesson(s)")
            for item in mode["shots"] + mode["lessons"]:
                print(f"- {item['path']}: {item['command']}")
    except (app.ReviewAppError, ReviewError, StateError, BundleError, DrawingError) as e:
        print(f"kei: {e}", file=sys.stderr)
        return EXIT_ERROR
    app.open_page(server, browser=not a.no_browser)
    app.serve(server)
    return EXIT_DONE


def _share_target(rows: list[dict]) -> tuple:
    values = {r["key"]: r["value"] for r in rows}
    return values.get("share.mode"), values.get("share.repo")


def _cmd_settings(a) -> int:
    from kei import settings as st
    args = list(a.args)
    verb = args[0] if args and args[0] in ("set", "unset", "add-critic", "remove-critic") else None
    if verb is None:
        if len(args) > 1:
            raise st.SettingError("kei settings takes one key to show, or: set, unset, add-critic, remove-critic")
        rows = st.current(_config_path(a.config))
        if args:
            st.setting(args[0])
            rows = [r for r in rows if r["key"] == args[0]]
            if not rows:
                raise st.SettingError(f"{args[0]} is not in this kei.toml")
        for r in rows:
            print(f"{r['key']} = {st.show(r['value'])}  ({r['source']})  {r['meaning']}")
            if args:
                print(f"default: {st.show(r['default'])}")
                if r["help"]:
                    print(r["help"])
                if r["choices"]:
                    print("one of: " + ", ".join(r["choices"]))
        return EXIT_DONE
    target = Path(a.config) if a.config else Path.cwd() / "kei.toml"   # never the example itself
    notes: list[str] = []
    need = {"set": 3, "unset": 2, "add-critic": 2, "remove-critic": 2}[verb]
    if len(args) != need:
        usage = {"set": "set <key> <value>", "unset": "unset <key>", "add-critic": "add-critic <name> --preset "
                 "claude|codex", "remove-critic": "remove-critic <name>"}[verb]
        raise st.SettingError(f"kei settings {usage}")
    if verb in ("set", "unset"):
        value = st.parse_cli_value(st.setting(args[1]), args[2]) if verb == "set" else None
        before = _share_target(st.current(target))
        changes = st.apply_change(target, {args[1]: value}, notes=notes)
        lines = [f"{k}: {st.show(old)} -> {st.show(new)}" for k, old, new in changes]
        after = _share_target(st.current(target))
        if after[0] == "auto" and after != before:     # said once: when auto starts, or starts sending elsewhere
            from kei import share
            lines += share.auto_notice(after[1], share.local_reader).splitlines()
    elif verb == "add-critic":
        st.add_critic(target, args[1], a.preset or "claude", notes=notes)
        lines = [f"critic {args[1]} added ({a.preset or 'claude'} preset)"]
    else:
        st.remove_critic(target, args[1], notes=notes)
        lines = [f"critic {args[1]} removed"]
    for line in notes + lines:
        print(line)
    print(f"saved {target} (the old file is {target.name}.bak); applies from the next kei run")
    return EXIT_DONE


def _safe_output() -> None:
    """Print any character: piped on Windows, stdout is the ANSI code page, and a note with an arrow would crash."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("kei-animator")
    except Exception:       # not installed as a package (a source checkout)
        return "unknown"


COMMAND_GROUPS = (
    ("set up", ("init", "doctor", "skill", "settings", "characters", "demo")),
    ("run a shot", ("run", "status", "live", "review", "answer", "retry", "bench", "vary")),
    ("sign off", ("approve", "note", "fixed", "park", "drop", "pack", "share")),
    ("characters, apps and files", ("import", "export", "refit-pass", "maya", "unreal", "shots", "sound", "ref")),
    ("tools the agents use (you rarely need them)", ("render", "bake", "check", "poses", "probe", "keys", "try",
                                                     "sweep", "curves", "pose", "trails", "sheet", "rule", "schema")),
)
SUMMARIES = {   # one line each for kei --help; a command's own --help has the whole story
    "init": "write kei.toml here, ready for kei run", "doctor": "check the setup before a run",
    "skill": "install the Kei skill for your agent", "settings": "show or change the settings in kei.toml",
    "characters": "list the characters a shot can use", "demo": "see Kei's tools on a walk, offline, no agent",
    "run": "run the shot until it is done or needs you", "status": "where a shot stands (--open: every open shot)",
    "live": "open the shot's live page", "review": "open the review page: watch, accept or send back",
    "answer": "answer the questions a shot stopped on", "retry": "let a stopped stage try again",
    "bench": "run one brief with several seats, compared blind",
    "vary": "a new shot from an approved one, in another mood or weight",
    "sound": "time a shot to a sound or dialogue track",
    "ref": "import licensed motion capture as a measured reference",
    "approve": "sign off a delivered shot", "note": "send a shot back with a note",
    "fixed": "close open notes as fixed after a new pass", "park": "leave a shot out of the open list for now",
    "drop": "drop a shot", "pack": "one file to send a reviewer, notes come back", "share": "check, zip or list shared lessons", "schema": "the JSON Schema of a Kei file", "import": "make a character from your own model", "export": "write a shot or a character "
    "as glTF or FBX", "refit-pass": "play a pass on a character's new proportions (was retarget)", "maya": "animate in Maya",
    "unreal": "animate in your open Unreal Editor", "shots": "look after a folder of shots",
    "render": "draw a pass: frames, key sheet, playback", "bake": "write the joints of every frame",
    "check": "measure a pass: contacts, balance, arcs, principles", "poses": "write the record of each key pose",
    "probe": "print bends, positions, speeds and contacts per frame", "keys": "edit a pass's keys",
    "try": "test a key edit on a copy: flags gone and new", "sweep": "try a range of values of one channel",
    "curves": "draw a curve image per channel",
    "pose": "print the joints of one pose", "trails": "draw part paths with a dot per frame",
    "sheet": "draw the plan sheet", "rule": "print rules of the book in full, by ID",
}


def _group_help(ap, sub) -> None:
    """kei --help lists the commands in groups, the ones for people first, instead of one flat list."""
    helps = {c.dest.split(" ")[0]: (c.help or "") for c in sub._choices_actions}
    listed = {n for _, names in COMMAND_GROUPS for n in names}
    groups = list(COMMAND_GROUPS) + ([("other", tuple(n for n in helps if n not in listed))]
                                     if set(helps) - listed else [])
    lines = []
    for title, names in groups:
        lines.append(f"{title}:")
        for n in names:
            if n in helps:
                h = SUMMARIES.get(n) or helps[n].split(";")[0].split(": ")[0][:88]
                lines.append(f"  {n:<11} {h}")
        lines.append("")
    ap.description = ((ap.description or "") + "\n\n" + "\n".join(lines).rstrip()
                      + "\n\nkei <command> --help shows a command's options.")
    ap.usage = "kei <command> [options]"
    sub.help = argparse.SUPPRESS
    sub.metavar = "<command>"


def main(argv: list[str] | None = None) -> int:
    _safe_output()
    ap = argparse.ArgumentParser(prog="kei", description="Kei Animator, by Castforge: run a shot through every stage.",
                                 epilog=EXIT_CODES_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version="kei-animator " + _version())
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run the shot until it is done or needs a person")
    r.add_argument("shot")
    r.add_argument("--request", help="what to animate, in plain words (needed for a new shot only)")
    r.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    r.add_argument("--app", choices=("kei", "maya", "unreal"), help="where the keys live (default: kei.toml [apps] app)")
    r.add_argument("--scene", help="with --app maya: your Maya scene, copied into the shot (never written)")
    r.add_argument("--wait-on-limit", action="store_true",
                   help="on a usage limit, wait until it resets (the time the CLI gives, else 30 min) and run on")
    r.add_argument("--max-wait-hours", type=float, default=12.0, help="with --wait-on-limit: the longest wait in all")
    r.add_argument("--answers", help="an answers file (TOML: default, [[answer]] match and text): plain questions are "
                                     "answered from it and the run goes on, for unattended runs")
    r.set_defaults(fn=_cmd_run)
    ru = sub.add_parser("rule", help="print rules of the book (or local lessons) in full, by ID")
    ru.add_argument("ids", nargs="+", metavar="ID")
    ru.add_argument("--config", default=None, help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    ru.set_defaults(fn=_cmd_rule)
    lv = sub.add_parser("live", help="open the shot's live page: the stage, the key poses of each try, the critics' "
                        "notes on their frames, the references and the renders, updated as Kei works (kei run "
                        "starts it unless [live] page = \"off\")")
    lv.add_argument("shot")
    lv.add_argument("--port", type=int, default=0, help="the port on 127.0.0.1 (default: any free port)")
    lv.add_argument("--no-open", action="store_true", help="print the link, do not open the browser")
    lv.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)
    lv.add_argument("--config", default=None, help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    lv.set_defaults(fn=_cmd_live)
    an = sub.add_parser("answer", help="answer the questions the shot stopped on (from any stage or critic)")
    an.add_argument("shot")
    an.add_argument("--text", required=True)
    an.add_argument("--every-shot", action="store_true",
                    help="for a feedback question (kei maya feedback): the reason is a rule for every shot, as kei "
                         "note --every-shot; without it, it is for this shot")
    an.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    an.set_defaults(fn=_cmd_answer)
    rt = sub.add_parser("retry", help="after fixing what stopped a shot, let the stage try again")
    rt.add_argument("shot")
    rt.add_argument("--note", help="a note for the next try, in plain words; it reads it with the critics' last notes")
    rt.set_defaults(fn=_cmd_retry)
    s = sub.add_parser("status", help="show the stage, attempts and status of a shot; with --open, every shot "
                       "under a folder still open, with its notes")
    s.add_argument("shot", nargs="?", help="the shot; with --open, the folder (default: the current folder)")
    s.add_argument("--open", action="store_true",
                   help="list the shots in the folder and its direct subfolders that are not done or rejected")
    s.add_argument("--all", action="store_true", help="with --open: also the parked shots and those asked today")
    s.add_argument("--mark-asked", action="store_true", help="with --open: stamp each listed shot as asked today")
    s.add_argument("--json", action="store_true", help="the shot as JSON; with --open, the list as JSON")
    s.set_defaults(fn=_cmd_status)
    ap_ = sub.add_parser("approve", help="sign off a shot that finished delivery")
    ap_.add_argument("shot", nargs="?", default=".", help="the shot folder (default: the current folder)")
    ap_.add_argument("--words", help="the author's own sign-off words from the chat, kept verbatim with the approval")
    ap_.set_defaults(fn=_cmd_approve)
    dr = sub.add_parser("drop", help="the author drops the shot: it is rejected with the reason \"dropped by the "
                        "author\" and their words; confirmed rules share as at any rejection")
    dr.add_argument("shot")
    dr.add_argument("--words", required=True, help="the author's words, kept verbatim")
    dr.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    dr.set_defaults(fn=_cmd_drop)
    n = sub.add_parser("note", help="send a delivered shot back with a note, approved or not (a note after the sign-off withdraws it); the note becomes a local lesson")
    n.add_argument("shot")
    n.add_argument("--text", help="what is wrong, in plain words")
    n.add_argument("--stage", default="passes", help="the stage the shot goes back to (default: passes)")
    n.add_argument("--every-shot", action="store_true",
                   help="the note is a rule for every shot, not only this one; a rule can be shared once a later "
                        "round confirms its fix")
    n.add_argument("--from", dest="from_", choices=("chat",),
                   help="chat: the author said it in the chat with their agent; taken while the shot is being made "
                        "too (for the next try), and it can be undone")
    n.add_argument("--undo", nargs="?", const="last", metavar="LESSON",
                   help="remove a note given with --from chat (the one named, else the last one) while no pass ran "
                        "after it; the shot and the lessons file are put back as they were")
    n.add_argument("--from-file", dest="from_file", metavar="NOTES_JSON",
                   help="bring in a reviewer's notes file saved from a kei pack page; each note is for this shot only")
    n.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    n.set_defaults(fn=_cmd_note)
    pk = sub.add_parser("pack", help="write the shot's review as one HTML file anyone can open, with a notes panel "
                                     "the reviewer saves a notes file from (kei note --from-file brings it back)")
    pk.add_argument("shot")
    pk.add_argument("--out", help="the file to write (default: <shot>/<shot>_pack.html)")
    pk.add_argument("--max-mb", type=float, default=200, help="the largest the file may get, in MB (default 200)")
    pk.add_argument("--no-video", action="store_true", help="leave the videos out (a much smaller file)")
    pk.set_defaults(fn=_cmd_pack)
    vy = sub.add_parser("vary", help="start a new shot from an approved one, in another mood or weight: keep the "
                                     "stages the change does not need, and give the note to the first stage it does")
    vy.add_argument("shot")
    vy.add_argument("--note", required=True, help='what changes, in plain words: "heavier crate, tired"')
    vy.add_argument("--from-stage", choices=("plan", "blocking", "passes"), default="plan",
                    help="plan (default): the timing may change; blocking: the plan holds; passes: the poses hold")
    vy.add_argument("--to", help="the new shot folder (default: <shot>-<words of the note>, beside it)")
    vy.set_defaults(fn=_cmd_vary)
    so = sub.add_parser("sound", help="put a sound or dialogue track in the shot: its level, beats and phrases per "
                                      "frame (sound/), a waveform sheet and a sound X-sheet to time the keys against")
    so.add_argument("shot")
    so.add_argument("file", help="a .wav (any other format needs ffmpeg)")
    so.add_argument("--offset", type=int, default=0, help="the sound frame that plays on the shot's frame 0")
    so.add_argument("--fps", type=float, help="the shot's frame rate (default: the newest pass's, else the plan's, else 24)")
    so.add_argument("--words", help="a text file: the words of each phrase, one line per phrase, in order")
    so.set_defaults(fn=_cmd_sound)
    rf = sub.add_parser("ref", help="references: import licensed motion capture (BVH) as a measured reference")
    rfs = rf.add_subparsers(dest="ref_command", required=True)
    ri = rfs.add_parser("import", help="read a BVH capture into <shot>/refs/mocap/<name>/: Kei's joints per frame, "
                                       "the measures, a sheet and the source; never turned into keys")
    ri.add_argument("shot")
    ri.add_argument("file", help="a .bvh file")
    ri.add_argument("--licence", required=True, help="the capture's licence, as its source states it (CC0, ...)")
    ri.add_argument("--source", help="where it comes from (a URL or a name)")
    ri.add_argument("--units", choices=("cm", "m", "in", "mm", "cmu"),
                    help="the file's units; cmu is the CMU database's 1/0.45 inch (default: guessed from the height)")
    ri.add_argument("--name", help="the reference's folder name (default: from the file name)")
    ri.set_defaults(fn=_cmd_ref_import)
    sm = sub.add_parser("schema", help="print the JSON Schema of a Kei file (shot, plan, bundle, notes), made from "
                                       "the code; --write writes them all")
    sm.add_argument("name", nargs="?", choices=("shot", "plan", "bundle", "notes"))
    sm.add_argument("--write", metavar="FOLDER", help="write every schema to FOLDER/<name>.schema.json")
    sm.set_defaults(fn=_cmd_schema)
    sh = sub.add_parser("share", help="lesson bundles without the review page: check them, move one as a zip, "
                                      "list the accepted lessons")
    shs = sh.add_subparsers(dest="share_command", required=True)
    sc = shs.add_parser("check", help="check lesson bundles as the review page does (the CI job on lesson pull "
                                      "requests runs this); exit 1 when one fails")
    sc.add_argument("folders", nargs="+", help="bundle folders, or folders holding them (such as lessons/incoming)")
    sc.add_argument("--allow-none", action="store_true", help="exit 0 when no bundle is found")
    sc.set_defaults(fn=_cmd_share_check)
    se = shs.add_parser("export", help="write a prepared lesson bundle as one zip, for a studio without GitHub")
    se.add_argument("bundle", help="the bundle folder (lessons/incoming/<name> beside your lessons file)")
    se.add_argument("--out", help="the zip to write (default: beside the folder)")
    se.set_defaults(fn=_cmd_share_export)
    si = shs.add_parser("import", help="unpack a lesson zip from kei share export into lessons/incoming and check it")
    si.add_argument("zip")
    si.add_argument("--into", default="lessons/incoming", help="where it goes (default: lessons/incoming)")
    si.set_defaults(fn=_cmd_share_import)
    sl = shs.add_parser("list", help="the lessons the maintainers accepted (verdict accept under lessons/)")
    sl.add_argument("root", nargs="?", default=".", help="the repository folder (default: here)")
    sl.add_argument("--write", action="store_true", help="write lessons/ACCEPTED.md instead of printing")
    sl.set_defaults(fn=_cmd_share_list)
    fx = sub.add_parser("fixed", help="after a new pass: close the shot's open notes as fixed, except the ones "
                        "named with --not; a fixed note for every shot is a confirmed rule")
    fx.add_argument("shot")
    which = fx.add_mutually_exclusive_group(required=True)
    which.add_argument("--all", action="store_true", help="every open note given before the new pass is fixed")
    which.add_argument("--not", dest="not_", metavar="N[,N]", help="the numbers of the notes that are not fixed "
                       "(as kei status --open numbers them); they stay open")
    fx.set_defaults(fn=_cmd_fixed)
    pk = sub.add_parser("park", help="not now: leave the shot out of kei status --open until its next pass")
    pk.add_argument("shot")
    pk.set_defaults(fn=_cmd_park)
    sh = sub.add_parser("sheet", help="draw plan/plan_sheet.png from the pose drawings in plan/plan.json")
    sh.add_argument("shot")
    sh.set_defaults(fn=_cmd_sheet)
    dm = sub.add_parser("demo", help="see Kei's tools on an approved walk, offline, with no agent: render, checks, "
                        "pose records, trails and the four-view video")
    dm.add_argument("folder", nargs="?", default="kei-demo")
    dm.set_defaults(fn=_cmd_demo)
    tr = sub.add_parser("trails", help="draw the paths of chosen parts with a dot per frame (a spacing chart), one "
                        "pass or several overlaid, into out_<last pass>/trails/trails.png")
    tr.add_argument("shot")
    tr.add_argument("passes", nargs="+", metavar="pass", help="one pass, or several to overlay (p5 p6)")
    tr.add_argument("--parts", required=True, help="parts, comma separated: hand_l_tip, hand_r_tip, head, pelvis...")
    tr.add_argument("--frames", help="a range like 140-160 (default: the whole pass)")
    tr.add_argument("--character", help="the character (default: the shot's)")
    tr.set_defaults(fn=_cmd_trails)
    sk = sub.add_parser("skill", help="install the Kei skill where your agent reads skills")
    sk_sub = sk.add_subparsers(dest="skill_cmd", required=True)
    si = sk_sub.add_parser("install", help="copy the skill to ~/.claude/skills/kei (or Codex's ~/.agents/skills/kei)")
    si.add_argument("--agent", choices=("claude", "codex"), default="claude")
    si.add_argument("--project", action="store_true", help="into this folder (.claude/skills or .agents/skills)")
    si.add_argument("--force", action="store_true", help="replace a copy that differs from this version's skill")
    si.set_defaults(fn=_cmd_skill)
    dr = sub.add_parser("doctor", help="check the setup before a run (Python, config, rule book, seats, ffmpeg, gh, "
                        "mayapy) and say how to fix each problem")
    dr.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    dr.set_defaults(fn=_cmd_doctor)
    ks = sub.add_parser("keys", help="edit a pass's keys: set, offset, insert, copy, delete, or shift (retime); keeps "
                        "every version and logs the edit")
    ks.add_argument("shot")
    ks.add_argument("pass_name", metavar="pass", help="blocking, p1, p2, ...")
    ks.add_argument("op", choices=KEY_OPS)
    ks.add_argument("--frame", type=int, help="the key's frame (set, insert, copy, delete)")
    ks.add_argument("--frames", help="a frame range like 40-60 (offset)")
    ks.add_argument("--channel", help="a channel: root, yaw, spine, armL, footR, ikL... (set, offset)")
    ks.add_argument("--value", help="the channel's numbers, comma separated (set)")
    ks.add_argument("--by", help="the amount: numbers to add (offset), or frames to move (shift)")
    ks.add_argument("--from", dest="from_", type=int, help="the source frame (copy), or the first frame moved (shift)")
    ks.add_argument("--to", help="write the result as this pass instead of editing in place (a new out_<pass>)")
    ks.set_defaults(fn=_cmd_keys)
    tr = sub.add_parser("try", help="test a kei keys edit on a copy of the pass: the flags it removes and adds; the "
                                    "shot is not changed")
    tr.add_argument("shot")
    tr.add_argument("pass_name", metavar="pass", help="blocking, p1, p2, ...")
    tr.add_argument("op", choices=KEY_OPS)
    for flag, kw in (("--frame", {"type": int}), ("--frames", {}), ("--channel", {}), ("--value", {}), ("--by", {}),
                     ("--from", {"dest": "from_", "type": int})):
        tr.add_argument(flag, help="as in kei keys", **kw)
    tr.add_argument("--character", help="default: the shot's character")
    tr.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    tr.set_defaults(fn=_cmd_try)
    sw = sub.add_parser("sweep", help="try a range of values of one channel at one key on a copy of the pass, and "
                                      "print the flags for each value; the shot is not changed")
    sw.add_argument("shot")
    sw.add_argument("pass_name", metavar="pass", help="blocking, p1, p2, ...")
    sw.add_argument("--frame", type=int, required=True, help="the key's frame")
    sw.add_argument("--channel", required=True, help="the channel: spine, armL, root...")
    sw.add_argument("--from", dest="lo", type=float, required=True, help="the first value")
    sw.add_argument("--to", dest="hi", type=float, required=True, help="the last value")
    sw.add_argument("--steps", type=int, default=5, help="how many values from --from to --to (default 5)")
    sw.add_argument("--index", type=int, default=0, help="which number of a channel of several (default 0)")
    sw.add_argument("--character", help="default: the shot's character")
    sw.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    sw.set_defaults(fn=_cmd_sweep)
    bn = sub.add_parser("bench", help="run one brief with several seats, check, render and compare them blind "
                                      "(a bench folder with bench.toml)")
    bn.add_argument("folder", help="the bench folder: bench.toml, each seat's kei.toml, optional answers.toml")
    bn.set_defaults(fn=_cmd_bench)
    cu = sub.add_parser("curves", help="draw a curve image per channel of a pass (out_<pass>/curves/<channel>.png), "
                                       "the graph editor's view; it reads only")
    cu.add_argument("shot")
    cu.add_argument("pass_name", metavar="pass", help="blocking, p1, p2, ...")
    cu.add_argument("--channels", required=True, help="channels, comma separated: spine, armL, root...")
    cu.add_argument("--frames", help="a range like 140-160 (default: the whole pass)")
    cu.add_argument("--mode", choices=MODES, help="default: step for blocking, spline after")
    cu.set_defaults(fn=_cmd_curves)
    po = sub.add_parser("pose", help="print the joint positions of one pose (a JSON file of channels)")
    po.add_argument("pose")
    po.set_defaults(fn=_cmd_pose)
    for cmd, fn, text in (("render", _cmd_render, "draw out_<pass>/shot.json: frames, key stills, a key sheet and a "
                                                   "playback (blocking.mp4 for the blocking pass); with --character "
                                                   "and no shot, the character's rest views and silhouette"),
                          ("bake", _cmd_bake, "write out_<pass>/joints.json, the joints of every frame"),
                          ("check", _cmd_check, "measure a pass on the character (contacts, a hovering foot, "
                                                "foot slide, balance, knee snaps, "
                                                "joint ranges, arcs) into out_<pass>/body_check/body_check.json, "
                                                "and the twelve principles into "
                                                "out_<pass>/principles/principles.json"),
                          ("poses", _cmd_poses, "write the record of each key pose of a pass (the plan's function, "
                                                "kind, intent and view, with the planted feet, weight side, centre "
                                                "of mass and lean measured) into out_<pass>/poses/poses.json, and "
                                                "draw out_<pass>/poses/pose_sheet.png, four views per key"),
                          ("probe", _cmd_probe, "print joint bends, positions, moves and foot contacts of a pass, "
                                                "frame by frame, without changing a key")):
        c = sub.add_parser(cmd, help=text)
        if cmd == "render":
            c.add_argument("shot", nargs="?")
            c.add_argument("pass_name", metavar="pass", nargs="?", help="blocking, p1, p2, ...")
            c.add_argument("--style", choices=("character", "stick"), default=None,
                           help="the character's shapes (default) or the stick figure, a diagnostic")
            c.add_argument("--emission", type=float, default=None, help="the chest C's glow, 0 (off) to 1 (default 1)")
            c.add_argument("--overlay", action="store_true", default=None, help="tint the left side, for reviews")
            c.add_argument("--onion", type=int, default=None, metavar="N",
                           help="with --style stick: the N frames before and after each frame as pale figures")
            c.add_argument("--workers", type=int, default=None,
                           help="processes that draw the frames (default: KEI_RENDER_WORKERS, else half the cores, "
                                "at most 8; renders under 24 frames use one)")
            c.add_argument("--size", type=int, default=None,
                           help="pixels per view panel (default 540 for the character, 360 for the stick figure)")
            c.add_argument("--camera", choices=("fixed", "follow", "delivery"), default=None,
                           help="fixed (default); follow: ride the shot's even travel, into out_<pass>/follow/; "
                                "delivery: the plan's locked camera (plan/plan.json \"camera\"), into "
                                "out_<pass>/delivery/")
            c.add_argument("--post", action="store_true",
                           help="a clean video to post: the side, three quarter, front and back views two by two, "
                                "drawn smooth with no label, border or tick, H.264; --size is a panel (default 540, "
                                "so 1080 x 1080)")
            c.add_argument("--out", help="with --character and no shot: the folder for the rest views (default: here); "
                                         "with --post: the folder for the video (default: out_<pass>/post)")
        else:
            c.add_argument("shot")
            c.add_argument("pass_name", metavar="pass", help="blocking, p1, p2, ...")
        if cmd == "probe":
            c.add_argument("--frames", required=True, help="a frame or ranges, such as 140-155 or 12,40-44")
            c.add_argument("--joints", required=True,
                           help="names, comma separated: bends (elbow_l, elbow_r, knee_l, knee_r) or joints "
                                "(hand_l, pelvis, head, com...)")
            c.add_argument("--json", help="also write the table to this JSON file")
        if cmd == "check":
            c.add_argument("--explain", metavar="FLAG",
                           help="after the check, explain one flag: its measure, frames, value and the limits it "
                                "broke (a principle id such as solid_drawing.twin_pose.hands.f95, a body check such "
                                "as balance or arcs.hand_r_tip, or the start of one)")
        c.add_argument("--character", help="the character (" + ", ".join(CHARACTERS) + ", or one made with kei import); "
                                           "default: shot.json's "
                                           "\"character\", else PLAN.md's Character line, else the config's")
        c.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
        c.add_argument("--mode", choices=MODES, help="default: step for blocking, spline after")
        c.set_defaults(fn=fn)
    ex = sub.add_parser("export", help="write a character as binary glTF (.glb) or FBX (.fbx), at rest or animated")
    ex.add_argument("--character", help=", ".join(CHARACTERS) + ", or one made with kei import (default with a shot: "
                                        "the shot's character)")
    ex.add_argument("shot_arg", nargs="?", metavar="shot", help="the shot to export (same as --shot)")
    ex.add_argument("--format", choices=("gltf", "fbx", "both"),
                    help="default: fbx when --out ends in .fbx, else gltf; both writes the .glb and the .fbx")
    ex.add_argument("--out", help="the .glb or .fbx file (default: <shot>/<shot>_<pass>.glb, or "
                                  "<character>.glb here for the rest pose)")
    ex.add_argument("--out-dir", help="the folder for the file(s) (default: the shot folder, where a delivered shot "
                                      "keeps its exports)")
    ex.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    ex.add_argument("--emission", type=float, default=1.0, help="the chest C's glow, 0 (off) to 1")
    ex.add_argument("--to", choices=("unreal",), help="with --shot and --pass on an approved Unreal shot: bake Kei's "
                    "sequence to an animation asset in the open editor, in Kei's own folder (/Game/Kei/<shot>/)")
    ex.add_argument("--shot", help="a shot folder: bake out_<pass>/shot.json into an animation")
    ex.add_argument("--pass", dest="pass_name", help="the pass to bake (default: the newest pass, else blocking)")
    ex.add_argument("--mode", choices=MODES, help="default: step for blocking, spline after")
    ex.set_defaults(fn=_cmd_export)
    im = sub.add_parser("import", help="make a character from an outside humanoid model (.glb, .gltf, binary .fbx), "
                                       "rigged or not; it waits for you to approve its fit sheet")
    im.add_argument("model", nargs="?", help="the model file")
    im.add_argument("--name", required=True, help="the character's name (lower case, digits and _)")
    im.add_argument("--height", type=float, help="metres; needed for a model with no skeleton")
    im.add_argument("--map", action="append", metavar="MODEL_BONE=KEI_BONE",
                    help="map a bone of a rigged model to Kei's, when Kei cannot tell (repeat it)")
    im.add_argument("--unrigged", action="store_true", help="ignore the model's skeleton and fit Kei's to the mesh")
    im.add_argument("--confirm", action="store_true", help="approve the fit sheet of an imported character")
    im.set_defaults(fn=_cmd_import)
    rg = sub.add_parser("refit-pass", aliases=["retarget"], help="write a new pass that plays a pass made for a character's old "
                                         "proportions on its new ones (after a re-import): foot heights by the "
                                         "ankle change, root by the standing leg change, lowered only for reach")
    rg.add_argument("shot")
    rg.add_argument("pass_name", metavar="pass", help="the pass to retarget (p1, p2, ...)")
    rg.add_argument("--from", dest="from_", required=True,
                    help="the old character: its character.json (a backup) or a character's name")
    rg.add_argument("--to", help="the character to play it on (default: the pass's own character, read fresh)")
    rg.add_argument("--out", required=True, help="the new pass (out_<out> must not exist)")
    rg.add_argument("--keep", choices=("knees", "standing-height"), default="knees",
                    help="knees (default): each key's root keeps the source's knee bends, smoothed; standing-height: "
                         "the root moves only by the change in standing leg height")
    rg.set_defaults(fn=_cmd_retarget)
    rv = sub.add_parser("review", help="open the local review page: watch the shot in four views, before and after, "
                                       "and accept it, send it back with a note and drawings, or reject it; with no "
                                       "shot, list the shots waiting for a sign-off")
    rv.add_argument("shot", nargs="?", help="the shot folder (default: list the waiting shots under this folder)")
    src = rv.add_mutually_exclusive_group()
    src.add_argument("--lesson", help="a shared lesson bundle folder to review (maintainers)")
    src.add_argument("--pr", type=int, help="a pull request with a lesson bundle, checked out with gh (maintainers)")
    rv.add_argument("--port", type=int, default=0, help="the local port (default: any free port)")
    rv.add_argument("--no-browser", action="store_true", help="print the address and do not open a browser")
    rv.add_argument("--size", type=int, default=360, help="pixels per view (default 360)")
    rv.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    rv.set_defaults(fn=_cmd_review)
    se = sub.add_parser("settings", help="show every setting with its meaning; set, unset, add-critic, remove-critic "
                                         "change kei.toml safely (checked before it is saved, comments kept)")
    se.add_argument("args", nargs="*", metavar="ARG",
                    help="nothing: every setting; <key>: one; set <key> <value>; unset <key>; add-critic <name>; "
                         "remove-critic <name>")
    se.add_argument("--preset", choices=("claude", "codex"), help="add-critic: the seat to copy (default claude)")
    se.add_argument("--config", help="kei.toml (default: ./kei.toml; shown from kei.example.toml when there is none)")
    se.set_defaults(fn=_cmd_settings)
    sh_ = sub.add_parser("shots", help="look after a folder of shots")
    shsub = sh_.add_subparsers(dest="shots_command", required=True)
    td = shsub.add_parser("tidy", help="list the moves that put each shot under a folder named after its character "
                                       "(a character folder); nothing moves without --apply")
    td.add_argument("folder", nargs="?", default=".", help="the folder of shots (default: here)")
    td.add_argument("--dry-run", action="store_true", help="only list the moves (the default)")
    td.add_argument("--apply", action="store_true", help="make the moves; a running shot is never moved")
    td.set_defaults(fn=_cmd_shots_tidy)
    ini = sub.add_parser("init", help="write kei.toml here from the example, so this folder is ready for kei run")
    ini.add_argument("--web", choices=("on", "off"), help="answer the web access question in advance "
                     "(the seats may search the web for references); without it, kei init asks")
    ini.set_defaults(fn=_cmd_init)
    cs = sub.add_parser("characters", help="list the characters a shot can use, built in and imported")
    cs.set_defaults(fn=_cmd_characters)
    my = sub.add_parser("maya", help="animate in Maya: set a shot up, key a pass on the controls")
    msub = my.add_subparsers(dest="maya_command", required=True)
    ms = msub.add_parser("setup", help="the shot's Maya scene: Kei's character with its control rig, or a copy of "
                                       "your scene (your file is never written)")
    ms.add_argument("shot")
    ms.add_argument("--character", help=", ".join(CHARACTERS) + ", or one made with kei import (default: the shot's "
                                        "Character line in PLAN.md, else kei)")
    ms.add_argument("--scene", help="your own Maya scene (.ma or .mb) to copy into the shot")
    ms.add_argument("--fps", type=float, default=24)
    ms.set_defaults(fn=_cmd_maya_setup)
    mk = msub.add_parser("key", help="key out_<pass>/shot.json on the controls in Maya, save the pass's scene and "
                                     "read the joints back for the checks")
    mk.add_argument("shot")
    mk.add_argument("pass_name", metavar="pass", help="blocking, p1, p2, ...")
    mk.add_argument("--mode", choices=MODES, help="default: step for blocking, spline after")
    mk.set_defaults(fn=_cmd_maya_key)
    mf = msub.add_parser("feedback", help="read the corrections an animator posed on a layer named feedback, show "
                                          "them before and after, and record your reason as the shot's note "
                                          "(your layer and your file are never changed)")
    mf.add_argument("shot")
    mf.add_argument("--text", help="the reason, in one sentence, kept word for word (asked when not given)")
    mf.add_argument("--every-shot", action="store_true",
                    help="the reason is a rule for every shot, not only this one (default: this shot), as kei note --every-shot")
    mf.add_argument("--stage", default="passes", help="the stage the shot goes back to (default: passes)")
    mf.add_argument("--scene", help="the saved scene that holds the feedback layer (default: the open Maya the shot "
                                    "works in, else the pass's scene); it is copied, never written")
    mf.add_argument("--no-render", action="store_true", help="skip the before and after previews")
    mf.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    mf.set_defaults(fn=_cmd_maya_feedback)
    msh = msub.add_parser("shelf", help="write the Kei host files for your open Maya and print how to install "
                                          "them; Kei installs nothing by itself")
    msh.add_argument("--out", default="maya_setup", help="the folder to write them in (default: maya_setup)")
    msh.set_defaults(fn=_cmd_maya_shelf)
    un = sub.add_parser("unreal", help="animate in your open Unreal Editor, through Claireon: setup steps, key a pass")
    usub = un.add_subparsers(dest="unreal_command", required=True)
    us = usub.add_parser("setup", help="the one-time steps: Claireon, the Python plugin, the ignore line, kei.toml")
    us.set_defaults(fn=_cmd_unreal_setup)
    uck = usub.add_parser("check", help="check the project for Kei: engine version, Claireon, the Python plugin, the "
                                        "port and the open editor, against the tested combinations")
    uck.add_argument("--project", help="the folder with the .uproject file (default: kei.toml [apps.unreal] project)")
    uck.add_argument("--url", help="the Claireon URL, http://127.0.0.1:<port>/mcp (default: kei.toml, else the port "
                                   "the editor wrote)")
    uck.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    uck.set_defaults(fn=_cmd_unreal_check)
    ut = usub.add_parser("tidy", help="file Kei's sequences for a delivered shot under Production/<phase> in its "
                                      "Unreal folder, keeping the delivered sequence on top (kei approve does it)")
    ut.add_argument("shot")
    ut.set_defaults(fn=_cmd_unreal_tidy)
    uk = usub.add_parser("key", help="key out_<pass>/shot.json on the character's controls in Kei's own sequence in "
                                     "the open editor, and read the joints back for the checks")
    uk.add_argument("shot")
    uk.add_argument("pass_name", metavar="pass", help="blocking, p1, p2, ...")
    uk.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    uk.set_defaults(fn=_cmd_unreal_key)
    usw = usub.add_parser("switch", help="a matched IK/FK switch of one limb at a frame, measured in the open editor: "
                                          "the frame before keeps the old mode, the frame keys the new one on the same pose")
    usw.add_argument("shot")
    usw.add_argument("pass_name", metavar="pass", help="p1, p2, ... (keyed in Unreal already)")
    usw.add_argument("--limb", required=True, choices=("arm_l", "arm_r", "leg_l", "leg_r"))
    usw.add_argument("--to", required=True, choices=("ik", "fk"))
    usw.add_argument("--frame", required=True, type=int)
    usw.set_defaults(fn=_cmd_unreal_switch)
    uc = usub.add_parser("capture-test", help="a test: have the editor draw one frame of a keyed pass from the front, "
                                             "the side and the three quarter view (the real mesh), into out_<pass>/mesh_test/")
    uc.add_argument("shot")
    uc.add_argument("pass_name", metavar="pass", help="blocking, p1, p2, ...")
    uc.add_argument("--frame", type=int, help="the frame to draw (default: the middle key frame)")
    uc.set_defaults(fn=_cmd_unreal_capture_test)
    us = usub.add_parser("style", help="the character's style range from their own clips in the project: how far each "
                                       "soft body check goes in them (rig/style.json); flags inside it become notes")
    us.add_argument("shot")
    us.add_argument("--anim", action="append", required=True,
                    help="a clip of this character, by asset path; repeat for more. Pick clips like this shot")
    us.add_argument("--fps", type=float, default=30.0, help="the clips' frame rate (default 30)")
    us.add_argument("--character", help="the character (default: the shot's)")
    us.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    us.set_defaults(fn=_cmd_unreal_style)
    up = usub.add_parser("pose", help="put a frame of an animation already in the project onto the character's "
                                      "Control Rig and write its control values as keys (rig/pose_<anim>_f<n>.json)")
    up.add_argument("shot")
    up.add_argument("--anim", required=True, help="the animation's asset path, such as /Game/Char/Anim/as_idle")
    up.add_argument("--frame", type=int, default=0, help="the animation's frame (default 0)")
    up.set_defaults(fn=_cmd_unreal_pose)
    _group_help(ap, sub)
    a = ap.parse_args(argv)
    try:
        return _in_working_layout(a)
    except (BookError, ConfigError, StateError, NoCriticError, SheetError, ShotError, PoseError, CharacterError,
            CheckError, PoseRecordError, ProbeError, AnswersError, KeysError, SkillError, TrailsError, CurvesError, BenchError, PackError, BundleError, SoundError, MocapError, ModelError, RetargetError, MayaError, UnrealError, SignOffError, SettingError) as e:
        print(f"kei: {e}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
