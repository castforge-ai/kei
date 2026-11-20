"""The conductor's Unreal steps: at the start of an Unreal shot, where to animate (asked, because Kei never animates in an
open editor in silence) and the character's Control Rig; after a seat's run, a lost editor stops the shot with
paused_machine and a user asset Kei made dirty stops it with needs_human. The stages do not change.

A shot is an Unreal shot when kei.toml says [apps] app = "unreal", or when its folder has an unreal/ folder (kei run
--app unreal makes it). The choice is kept in unreal/target.json: "open" (an editor, by URL and project) or "kei"
(Kei's own rig, no Unreal).

The animator seat never talks to Claireon. It writes out_<pass>/shot.json and runs kei unreal key <shot> <pass>,
which is key_pass here: keys in Kei's own sequence, reads the motion back from the rig, and writes joints.json for the checks. A
fault in key_pass leaves a file for the conductor (stop_for_machine, stop_for_human), which stops the shot after the
seat's run. kei run resumes at the same pass: it probes the target again first.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Callable

from kei.apps.unreal import Claireon, NeedsHuman, UnrealError
from kei.apps import unreal_memory
from kei.apps.unreal_keys import apply_keys
from kei.apps.unreal_readback import read_back
from kei.apps.unreal_rig import load_rig, read_rig, release_memory
from kei.apps.unreal_session import (Question, candidate_urls, choose_target, find_editors, load_target, locate,
                                     pick_character, probe_editor, save_target)
from kei.characters import shot_character
from kei.sample import ShotError, read_json

WAIT_S = 300.0     # how long Kei waits for a busy editor (shaders compiling, assets loading) before it pauses the shot
STEP_S = 15.0      # and how often it asks again


def patience() -> float:
    """Seconds to wait for the editor: KEI_UNREAL_WAIT_S when set (0 pauses at once), else WAIT_S."""
    try:
        return max(0.0, float(os.environ.get("KEI_UNREAL_WAIT_S", WAIT_S)))
    except ValueError:
        return WAIT_S


def _say_waiting(what: str, wait: float) -> None:
    print(f"kei: {what}; it may be busy (compiling shaders or loading). Asking again every {STEP_S:g} s for up to "
          f"{wait / 60:g} minutes before pausing the shot.", file=sys.stderr, flush=True)


def locate_waiting(target: dict, probe: Callable[[str], dict | None], sleep=time.sleep):
    """locate, asked again every STEP_S while the editor does not answer, for up to patience() seconds."""
    wait, waited = patience(), 0.0
    while True:
        editor = locate(target, probe)
        if (editor is not None and editor.level) or waited >= wait:
            return editor
        if waited == 0:
            _say_waiting(f"the Unreal Editor does not answer at {target.get('url')}" if editor is None
                         else "the Unreal Editor has no level loaded yet", wait)
        sleep(STEP_S)
        waited += STEP_S


def connect_waiting(url: str, sleep=time.sleep) -> Claireon:
    """_connect, tried again every STEP_S while the editor times out, for up to patience() seconds."""
    wait, waited = patience(), 0.0
    while True:
        try:
            return _connect(url)
        except UnrealError:
            if waited >= wait:
                raise
            if waited == 0:
                _say_waiting("the Unreal Editor did not answer a call", wait)
            sleep(STEP_S)
            waited += STEP_S


PAUSED_FILE = "PAUSED.md"
HUMAN_FILE = "NEEDS_HUMAN.md"


def unreal_dir(shot_dir: Path) -> Path:
    return Path(shot_dir) / "unreal"


def wants_unreal(shot_dir: Path, app: str) -> bool:
    return app == "unreal" or unreal_dir(shot_dir).is_dir()


def is_unreal_shot(shot_dir: Path) -> bool:
    t = load_target(Path(shot_dir))
    return bool(t and t.get("kind") == "open")


def stop_for_machine(shot_dir: Path, why: str) -> None:
    """Leave the reason for the conductor: the shot stops with paused_machine, not in silence."""
    unreal_dir(shot_dir).mkdir(parents=True, exist_ok=True)
    (unreal_dir(shot_dir) / PAUSED_FILE).write_text(why, encoding="utf-8")


def stop_for_human(shot_dir: Path, why: str) -> None:
    unreal_dir(shot_dir).mkdir(parents=True, exist_ok=True)
    (unreal_dir(shot_dir) / HUMAN_FILE).write_text(why, encoding="utf-8")


def _take(shot_dir: Path, name: str, default: str) -> str | None:
    p = unreal_dir(shot_dir) / name
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8").strip()
    p.unlink()
    return text or default


def take_pause(shot_dir: Path) -> str | None:
    return _take(shot_dir, PAUSED_FILE, "the Unreal Editor stopped answering")


def take_human(shot_dir: Path) -> str | None:
    return _take(shot_dir, HUMAN_FILE, "a person has to act in the Unreal Editor")


def _connect(url: str) -> Claireon:
    client = Claireon(url)
    client.initialize()
    return client


def prepare(shot_dir: Path, config, probe: Callable[[str], dict | None] = probe_editor) -> dict | None:
    """Make the shot ready to animate in Unreal. Returns None when it is ready, {"question", "choices"} when the
    author must choose where, {"pause": reason} when the editor cannot do it now, or {"human": reason} when a person
    must act. Each run probes the chosen editor again, so a shot resumes only when its editor is back."""
    shot_dir = Path(shot_dir)
    target = load_target(shot_dir)
    if target is None:
        editors = find_editors(candidate_urls(config.unreal_url, config.unreal_project), probe)
        choice = choose_target(editors, config.unreal_session)
        if isinstance(choice, Question):
            return {"question": choice.text, "choices": choice.choices}
        target = {"kind": "open", "url": choice.session.url, "project": choice.session.project}
        save_target(shot_dir, target)
    if target["kind"] != "open":
        return None
    editor = locate_waiting(target, probe)
    if editor is None:
        return {"pause": f"the Unreal Editor for project {target.get('project') or 'unnamed'} does not answer at "
                         f"{target.get('url')}: open it with Claireon's server on (kei unreal setup lists the "
                         "steps), then run the shot again; or delete unreal/target.json to choose again"}
    if load_rig(shot_dir) is not None:
        return None
    try:
        character = pick_character(editor, config.unreal_mesh, config.unreal_control_rig)
        read_rig(connect_waiting(editor.url), shot_dir, character)
    except ValueError as e:
        return {"human": str(e)}
    except NeedsHuman as e:
        return {"human": str(e)}
    except UnrealError as e:
        return {"pause": str(e)}
    return None


def capture_test(shot_dir: Path, pass_name: str, frame: int | None = None,
                 probe: Callable[[str], dict | None] = probe_editor) -> dict:
    """kei unreal capture-test: one frame of a keyed pass drawn by the editor from three views (kei.apps.unreal_capture)."""
    from kei.apps.unreal_capture import capture_test as shoot
    shot_dir = Path(shot_dir)
    target = load_target(shot_dir)
    if not target or target.get("kind") != "open":
        raise ShotError(f"{shot_dir} was not animated in Unreal: there is no character in an editor to draw")
    editor = locate_waiting(target, probe)
    if editor is None:
        raise UnrealError(f"the Unreal Editor for project {target.get('project') or 'unnamed'} does not answer: open "
                          "it with Claireon's server on, then run the test again")
    return shoot(connect_waiting(editor.url), shot_dir, pass_name, frame)


def render_mesh(shot_dir: Path, pass_name: str, timeout: float | None = None, force: bool = False,
                probe: Callable[[str], dict | None] = probe_editor) -> dict:
    """kei unreal render-mesh, and the conductor before a review: the pass rendered on the real mesh by the editor the
    shot is animated in (kei.apps.unreal_mesh)."""
    from kei.apps.unreal_mesh import TIMEOUT_S, render_mesh as draw
    shot_dir = Path(shot_dir)
    target = load_target(shot_dir)
    if not target or target.get("kind") != "open":
        raise ShotError(f"{shot_dir} was not animated in Unreal: there is no character in an editor to render")
    editor = locate_waiting(target, probe)
    if editor is None:
        raise UnrealError(f"the Unreal Editor for project {target.get('project') or 'unnamed'} does not answer: open "
                          "it with Claireon's server on, then render again")
    return draw(connect_waiting(editor.url), shot_dir, pass_name, TIMEOUT_S if timeout is None else timeout,
                force=force)


def bake(shot_dir: Path, pass_name: str, probe: Callable[[str], dict | None] = probe_editor) -> dict:
    """kei export --to unreal: the bake of an approved shot, in the editor the shot was animated in."""
    from kei.apps.unreal_bake import bake_shot
    shot_dir = Path(shot_dir)
    target = load_target(shot_dir)
    if not target or target.get("kind") != "open":
        raise ShotError(f"{shot_dir} was not animated in Unreal: there is nothing to bake there")
    editor = locate(target, probe)
    if editor is None:
        raise UnrealError(f"the Unreal Editor for project {target.get('project') or 'unnamed'} does not answer: open "
                          "it with Claireon's server on, then run kei export again")
    unreal_memory.record(shot_dir, editor.url, f"{pass_name}: before the bake")
    out = bake_shot(_connect(editor.url), shot_dir, pass_name)
    unreal_memory.record(shot_dir, editor.url, f"{pass_name}: after the bake")
    return out


def tidy_shot(shot_dir: Path, probe: Callable[[str], dict | None] = probe_editor) -> dict:
    """kei approve and kei unreal tidy: Kei's folder for the shot in the editor, filed by phase (kei.apps.unreal_tidy)."""
    from kei.apps.unreal_tidy import tidy
    shot_dir = Path(shot_dir)
    target = load_target(shot_dir)
    if not target or target.get("kind") != "open":
        raise ShotError(f"{shot_dir} was not animated in Unreal: there is no Unreal folder to tidy")
    editor = locate(target, probe)
    if editor is None:
        raise UnrealError(f"the Unreal Editor for project {target.get('project') or 'unnamed'} does not answer: open "
                          f"it with Claireon's server on, then run kei unreal tidy {shot_dir}")
    return tidy(_connect(editor.url), shot_dir)


def pose_shot(shot_dir: Path, anim: str, frame: int = 0,
              probe: Callable[[str], dict | None] = probe_editor) -> dict:
    """What kei unreal pose does: a frame of an animation in the project onto the rig, read back as keys."""
    from kei.apps.unreal_pose import pose_from_anim
    shot_dir = Path(shot_dir)
    target = load_target(shot_dir)
    if not target or target.get("kind") != "open":
        raise ShotError(f"{shot_dir} is not an Unreal shot: kei run --app unreal {shot_dir} chooses the editor")
    editor = locate_waiting(target, probe)
    if editor is None:
        raise UnrealError(f"the Unreal Editor for project {target.get('project') or 'unnamed'} does not answer: open "
                          f"it with Claireon's server on, then run kei unreal pose again")
    return pose_from_anim(connect_waiting(editor.url), shot_dir, anim, frame)


def style(shot_dir: Path, anims: list[str], character, fps: float = 30.0,
          probe: Callable[[str], dict | None] = probe_editor) -> dict:
    """What kei unreal style does: the character's style range from their own clips, into rig/style.json."""
    from kei.apps.unreal_style import style_shot
    shot_dir = Path(shot_dir)
    target = load_target(shot_dir)
    if not target or target.get("kind") != "open":
        raise ShotError(f"{shot_dir} is not an Unreal shot: kei run --app unreal {shot_dir} chooses the editor")
    editor = locate_waiting(target, probe)
    if editor is None:
        raise UnrealError(f"the Unreal Editor for project {target.get('project') or 'unnamed'} does not answer: open "
                          f"it with Claireon's server on, then run kei unreal style again")
    return style_shot(connect_waiting(editor.url), shot_dir, anims, character, fps)


def key_pass(shot_dir: Path, pass_name: str, config, probe: Callable[[str], dict | None] = probe_editor) -> dict:
    """What kei unreal key does: key the pass in Kei's own sequence, read the motion back into joints.json. A lost
    editor or a user asset made dirty leaves a stop file for the conductor, then raises."""
    shot_dir = Path(shot_dir)
    target = load_target(shot_dir)
    if not target or target.get("kind") != "open":
        raise ShotError(f"{shot_dir} is not an Unreal shot: kei run --app unreal {shot_dir} chooses the editor")
    try:
        editor = locate_waiting(target, probe)
        if editor is None:
            raise UnrealError(f"the Unreal Editor for project {target.get('project') or 'unnamed'} stopped "
                              "answering: open it again, then run the shot again")
        client = connect_waiting(editor.url)
        unreal_memory.record(shot_dir, editor.url, f"{pass_name}: before keying")
        report = apply_keys(client, shot_dir, pass_name)
        shot = read_json(shot_dir / f"out_{pass_name}" / "shot.json", "shot")
        kei = shot_character(shot_dir, shot, config.character)
        report["joints"] = str(read_back(client, shot_dir, pass_name, kei, report["mode"]))
        mem = unreal_memory.record(shot_dir, editor.url, f"{pass_name}: keyed and read back")
        freed = release_memory(client, shot_dir)
        after = unreal_memory.record(shot_dir, editor.url, f"{pass_name}: after releasing memory")
        if mem:
            report["memory"] = {"private_gb": mem["private_gb"], "working_set_gb": mem["working_set_gb"],
                                **({"after_release_gb": after["private_gb"]} if after else {}),
                                **({"release": freed} if freed else {})}
    except NeedsHuman as e:
        stop_for_human(shot_dir, str(e))
        raise
    except UnrealError as e:
        stop_for_machine(shot_dir, f"Unreal stopped answering while keying {pass_name}: {e}")
        raise
    return report


def switch_limb(shot_dir: Path, pass_name: str, limb: str, to: str, frame: int,
                probe: Callable[[str], dict | None] = probe_editor) -> dict:
    """kei unreal switch: a matched IK/FK switch in the editor the shot is animated in (kei.apps.unreal_switch)."""
    from kei.apps.unreal_switch import switch
    shot_dir = Path(shot_dir)
    target = load_target(shot_dir)
    if not target or target.get("kind") != "open":
        raise ShotError(f"{shot_dir} is not animated in Unreal: kei keys <shot> <pass> match switches on Kei's own rig")
    editor = locate_waiting(target, probe)
    if editor is None:
        raise UnrealError(f"the Unreal Editor for project {target.get('project') or 'unnamed'} does not answer: open "
                          "it with Claireon's server on, then run the switch again")
    return switch(connect_waiting(editor.url), shot_dir, pass_name, limb, to, frame)
