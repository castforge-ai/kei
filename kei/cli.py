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
from kei.export_fbx import export_fbx
from kei.export_gltf import export_glb
from kei.render import CHARACTER_VIEWS, Camera, draw_character_views, draw_silhouette, render_post, render_shot
from kei.rig import PoseError, check_channels, solve
from kei.sample import MODES, ShotError, bake, check_shot, read_json
from kei.sheet import SheetError, write_sheet
from kei.stages import STAGES
from kei.state import PAUSED, StateError, load_state, save_state

EXIT_DONE, EXIT_ERROR, EXIT_NEEDS_HUMAN, EXIT_NEEDS_ANSWER, EXIT_NEEDS_APPROVAL, EXIT_PAUSED = 0, 1, 2, 3, 4, 5
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


def _cmd_run(a) -> int:
    config = load_config(_config_path(a.config))
    shot = Path(a.shot)
    if load_state(shot).status == "rejected":
        print(f"this shot was rejected: {rejection(load_state(shot))}")
        print(REOPEN.format(shot=shot))
        return EXIT_ERROR
    if not a.request and not load_state(shot).request:
        print('kei: a new shot needs --request "what to animate"')
        return EXIT_ERROR
    if a.app == "maya" or a.scene:
        from kei.apps.maya_stage import record_source
        record_source(shot, Path(a.scene) if a.scene else None)
    if a.app == "unreal":
        (shot / "unreal").mkdir(parents=True, exist_ok=True)     # the mark of an Unreal shot: the conductor asks where
    _live_page(shot, config)
    before = len(load_state(shot).history)
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


def _cmd_live(a) -> int:
    from kei.live.serve import serve
    shot = Path(a.shot)
    if not shot.is_dir():
        print(f"kei: no shot folder at {shot}")
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
        print(e)
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
        print("kei: --undo takes no --text, --every-shot or --from: it removes a note given in the chat")
        return EXIT_ERROR
    config = load_config(_config_path(a.config))
    state, removed = undo_note(shot, config.lessons, None if a.undo == "last" else a.undo)
    print(f"removed note {removed['lesson']}: {removed['misses'][0]}")
    print(f"the shot is back to {state.status} at {state.stage}")
    return EXIT_DONE


def _cmd_note(a) -> int:
    shot = Path(a.shot)
    if a.undo:
        return _cmd_note_undo(a, shot)
    if a.text is None:
        print('kei: a note needs words: kei note <shot> --text "..."')
        return EXIT_ERROR
    if not a.from_:
        why = note_refusal(load_state(shot), a.stage)
        if why:
            print(why if why.startswith("this shot") else f"kei: {why}")
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
              f'shot takes it through: kei note {shot} --text "..." --every-shot')
        return EXIT_ERROR
    if feedback is not None and not a.text.strip():
        print("kei: the reason needs words, in one sentence; Kei never writes it for you")
        return EXIT_ERROR
    unreal_q = next((x for x in state.questions if x.get("kind") == "unreal_target"), None)
    if unreal_q is not None:     # where to animate an Unreal shot: the answer is a choice's number
        from kei.apps.unreal_session import answer_choice as unreal_choice, save_target as unreal_save
        try:
            choice = unreal_choice(unreal_q["choices"], a.text)
        except ValueError as e:
            print(f"kei: {e}")
            return EXIT_ERROR
        if choice["kind"] != "retry":      # "look again" keeps nothing: the next run asks again, after a fresh probe
            unreal_save(shot, choice)
    target_q = next((x for x in state.questions if x.get("kind") == "maya_target"), None)
    if target_q is not None:     # where to animate a Maya shot: the answer is a choice's number
        from kei.apps.maya_session import answer_choice, save_target
        try:
            choice = answer_choice(target_q["choices"], a.text)
        except ValueError as e:
            print(f"kei: {e}")
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
    if a.note:
        entry["notes"] = [a.note]
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
    if a.all or a.mark_asked or a.json:
        print("kei: --all, --mark-asked and --json go with --open")
        return EXIT_ERROR
    if not a.shot:
        print("kei: give a shot: kei status <shot>, or list the open shots here: kei status --open")
        return EXIT_ERROR
    state = load_state(Path(a.shot))
    print(f"stage: {state.stage}")
    print(f"attempts: {state.attempts}")
    print(f"send-backs: {state.send_backs}")
    print(f"status: {state.status}")
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
        print(f"kei: no folder {root}")
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


def _cmd_render(a) -> int:
    if a.shot is not None and a.pass_name is None:
        raise ShotError("kei render <shot> needs a pass too (blocking, p1, ...)")
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
        r = render_post(src, dst, mode, ch, height=2 * (a.size or POST_PANEL), emission=a.emission,
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
        r = render_shot(src, out, mode, size=a.size or 360, name=name, proportions=ch.proportions, camera=camera)
    else:
        r = render_shot(src, out, mode, size=a.size or CHARACTER_PANEL, name=name, character=ch, emission=a.emission,
                        overlay=a.overlay, camera=camera)
    print(f"character: {ch.name}, style: {a.style}, camera: {a.camera}")
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
        print("kei: the reason needs words, in one sentence; Kei never writes it for you")
        return EXIT_ERROR
    if not in_run:
        why = note_refusal(load_state(shot), a.stage)
        if why:
            print(why if why.startswith("this shot") else f"kei: {why}")
            return EXIT_ERROR
        if a.text is None and not sys.stdin.isatty():
            print('kei: give the reason in one sentence with --text "..." (and --every-shot when it applies to every '
                  "shot); Kei never writes it for you")
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
    return EXIT_DONE


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
    if a.to == "unreal":
        return _export_unreal(a)
    if a.shot and maya_shot.is_maya_shot(Path(a.shot)):
        if (a.format or "fbx") != "fbx" or not a.pass_name:
            raise ShotError("a Maya shot exports FBX from a keyed pass: kei export --shot <shot> --pass <pass> "
                            "--format fbx")
        r = maya_shot.export_pass(Path(a.shot), a.pass_name, Path(a.out or f"{Path(a.shot).name}_{a.pass_name}.fbx"))
        print(f"{r['fbx']} ({r['joints']} joints, baked from the controls)")
        return EXIT_DONE
    if not a.character:
        raise ShotError("kei export needs --character (or --shot on a Maya shot)")
    ch = load_character(a.character)
    shot, mode = None, None
    if a.shot:
        if not a.pass_name:
            raise ShotError("kei export --shot needs --pass (blocking, p1, ...)")
        _, src, mode = _pass_shot(a)
        shot = read_json(src, "shot")
        check_shot(shot)
    suffix = Path(a.out).suffix.lower() if a.out else ""
    fmt = a.format or ("fbx" if suffix == ".fbx" else "gltf")
    if suffix in (".fbx", ".glb") and suffix != (".fbx" if fmt == "fbx" else ".glb"):
        raise ShotError(f"--format {fmt} does not write a {suffix} file")
    write = export_fbx if fmt == "fbx" else export_glb
    path = write(ch, a.out or f"{ch.name}.{'fbx' if fmt == 'fbx' else 'glb'}", a.emission, shot, mode or "spline")
    print(f"{ch.title}: {path}" + (f" (animated, mode {mode})" if shot else " (rest pose)"))
    return EXIT_DONE


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


def _cmd_init(a) -> int:
    """Write ./kei.toml from the example, so a new folder is ready for `kei run`. Never overwrites a kei.toml."""
    dest = Path.cwd() / "kei.toml"
    if dest.exists():
        print(f"kei.toml is already here ({dest}); left as it is. Start a shot with: kei run <shot> --request \"...\"")
        return EXIT_DONE
    dest.write_bytes(EXAMPLE_CONFIG.read_bytes())
    print(f"wrote {dest} from the example: one animator seat and two critic seats, your own agent command lines.")
    seats = load_config(dest)
    missing = sorted({s.cmd[0] for s in [seats.animator, *seats.critics] if s.cmd and not shutil.which(s.cmd[0])})
    if missing:
        print("not found on your PATH: " + ", ".join(missing) + ". Install them, or change the seats with kei settings.")
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
        print(f"- {f['check']} f{f['frames'][0]}-{f['frames'][1]}: {f['what']}")
    print(report["summary"])
    print(f"written: {path}")
    return EXIT_DONE


def _cmd_retarget(a) -> int:
    from kei.retarget import retarget_pass
    dst, r = retarget_pass(Path(a.shot), a.pass_name, a.from_, a.to, a.out, keep=a.keep)
    print(f"retargeted {a.pass_name} -> {a.out}: {dst}")
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
        print(f"kei: {e}")
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


def main(argv: list[str] | None = None) -> int:
    _safe_output()
    ap = argparse.ArgumentParser(prog="kei", description="Kei Animator, by Castforge: run a shot through every stage.")
    ap.add_argument("--version", action="version", version="kei-animator " + _version())
    sub = ap.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run the shot until it is done or needs a person")
    r.add_argument("shot")
    r.add_argument("--request", help="what to animate, in plain words (needed for a new shot only)")
    r.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    r.add_argument("--app", choices=("kei", "maya", "unreal"), help="where the keys live (default: kei.toml [apps] app)")
    r.add_argument("--scene", help="with --app maya: your Maya scene, copied into the shot (never written)")
    r.set_defaults(fn=_cmd_run)
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
    s.add_argument("--json", action="store_true", help="with --open: the same list as JSON")
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
    n.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
    n.set_defaults(fn=_cmd_note)
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
    po = sub.add_parser("pose", help="print the joint positions of one pose (a JSON file of channels)")
    po.add_argument("pose")
    po.set_defaults(fn=_cmd_pose)
    for cmd, fn, text in (("render", _cmd_render, "draw out_<pass>/shot.json: frames, key stills, a key sheet and a "
                                                   "playback (blocking.mp4 for the blocking pass); with --character "
                                                   "and no shot, the character's rest views and silhouette"),
                          ("bake", _cmd_bake, "write out_<pass>/joints.json, the joints of every frame"),
                          ("check", _cmd_check, "measure a pass on the character (contacts, a hovering foot, "
                                                "foot slide, balance, knee snaps, "
                                                "joint ranges, arcs) into out_<pass>/body_check/body_check.json")):
        c = sub.add_parser(cmd, help=text)
        if cmd == "render":
            c.add_argument("shot", nargs="?")
            c.add_argument("pass_name", metavar="pass", nargs="?", help="blocking, p1, p2, ...")
            c.add_argument("--style", choices=("character", "stick"), default="character",
                           help="the character's shapes (default) or the stick figure, a diagnostic")
            c.add_argument("--emission", type=float, default=1.0, help="the chest C's glow, 0 (off) to 1")
            c.add_argument("--overlay", action="store_true", help="tint the left side, for reviews")
            c.add_argument("--size", type=int, default=None,
                           help="pixels per view panel (default 540 for the character, 360 for the stick figure)")
            c.add_argument("--camera", choices=("fixed", "follow", "delivery"), default="fixed",
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
        c.add_argument("--character", help="the character (" + ", ".join(CHARACTERS) + ", or one made with kei import); "
                                           "default: shot.json's "
                                           "\"character\", else PLAN.md's Character line, else the config's")
        c.add_argument("--config", help="kei.toml (default: ./kei.toml, else kei.example.toml)")
        c.add_argument("--mode", choices=MODES, help="default: step for blocking, spline after")
        c.set_defaults(fn=fn)
    ex = sub.add_parser("export", help="write a character as binary glTF (.glb) or FBX (.fbx), at rest or animated")
    ex.add_argument("--character", help=", ".join(CHARACTERS) + ", or one made with kei import (not needed with --shot on a Maya shot)")
    ex.add_argument("--format", choices=("gltf", "fbx"),
                    help="default: fbx when --out ends in .fbx, else gltf")
    ex.add_argument("--out", help="the .glb or .fbx file (default: <character>.glb or .fbx here)")
    ex.add_argument("--emission", type=float, default=1.0, help="the chest C's glow, 0 (off) to 1")
    ex.add_argument("--to", choices=("unreal",), help="with --shot and --pass on an approved Unreal shot: bake Kei's "
                    "sequence to an animation asset in the open editor, in Kei's own folder (/Game/Kei/<shot>/)")
    ex.add_argument("--shot", help="a shot folder: bake out_<pass>/shot.json into an animation")
    ex.add_argument("--pass", dest="pass_name", help="the pass to bake with --shot (blocking, p1, ...)")
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
    rg = sub.add_parser("retarget", help="write a new pass that plays a pass made for a character's old "
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
    uc = usub.add_parser("capture-test", help="a test: have the editor draw one frame of a keyed pass from the front, "
                                             "the side and the three quarter view (the real mesh), into out_<pass>/mesh_test/")
    uc.add_argument("shot")
    uc.add_argument("pass_name", metavar="pass", help="blocking, p1, p2, ...")
    uc.add_argument("--frame", type=int, help="the frame to draw (default: the middle key frame)")
    uc.set_defaults(fn=_cmd_unreal_capture_test)
    up = usub.add_parser("pose", help="put a frame of an animation already in the project onto the character's "
                                      "Control Rig and write its control values as keys (rig/pose_<anim>_f<n>.json)")
    up.add_argument("shot")
    up.add_argument("--anim", required=True, help="the animation's asset path, such as /Game/Char/Anim/as_idle")
    up.add_argument("--frame", type=int, default=0, help="the animation's frame (default 0)")
    up.set_defaults(fn=_cmd_unreal_pose)
    a = ap.parse_args(argv)
    try:
        return _in_working_layout(a)
    except (BookError, ConfigError, StateError, NoCriticError, SheetError, ShotError, PoseError, CharacterError,
            CheckError, ModelError, RetargetError, MayaError, UnrealError, SignOffError, SettingError) as e:
        print(f"kei: {e}")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
