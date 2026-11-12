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

from pathlib import Path
from typing import Callable

from kei.apps.unreal import Claireon, NeedsHuman, UnrealError
from kei.apps.unreal_keys import apply_keys
from kei.apps.unreal_readback import read_back
from kei.apps.unreal_rig import load_rig, read_rig
from kei.apps.unreal_session import (Question, candidate_urls, choose_target, find_editors, load_target, locate,
                                     pick_character, probe_editor, save_target)
from kei.characters import shot_character
from kei.sample import ShotError, read_json

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
    editor = locate(target, probe)
    if editor is None:
        return {"pause": f"the Unreal Editor for project {target.get('project') or 'unnamed'} does not answer at "
                         f"{target.get('url')}: open it with Claireon's server on (kei unreal setup lists the "
                         "steps), then run the shot again; or delete unreal/target.json to choose again"}
    if load_rig(shot_dir) is not None:
        return None
    try:
        character = pick_character(editor, config.unreal_mesh, config.unreal_control_rig)
        read_rig(_connect(editor.url), shot_dir, character)
    except ValueError as e:
        return {"human": str(e)}
    except NeedsHuman as e:
        return {"human": str(e)}
    except UnrealError as e:
        return {"pause": str(e)}
    return None


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
    return bake_shot(_connect(editor.url), shot_dir, pass_name)


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


def key_pass(shot_dir: Path, pass_name: str, config, probe: Callable[[str], dict | None] = probe_editor) -> dict:
    """What kei unreal key does: key the pass in Kei's own sequence, read the motion back into joints.json. A lost
    editor or a user asset made dirty leaves a stop file for the conductor, then raises."""
    shot_dir = Path(shot_dir)
    target = load_target(shot_dir)
    if not target or target.get("kind") != "open":
        raise ShotError(f"{shot_dir} is not an Unreal shot: kei run --app unreal {shot_dir} chooses the editor")
    try:
        editor = locate(target, probe)
        if editor is None:
            raise UnrealError(f"the Unreal Editor for project {target.get('project') or 'unnamed'} stopped "
                              "answering: open it again, then run the shot again")
        client = _connect(editor.url)
        report = apply_keys(client, shot_dir, pass_name)
        shot = read_json(shot_dir / f"out_{pass_name}" / "shot.json", "shot")
        kei = shot_character(shot_dir, shot, config.character)
        report["joints"] = str(read_back(client, shot_dir, pass_name, kei, report["mode"]))
    except NeedsHuman as e:
        stop_for_human(shot_dir, str(e))
        raise
    except UnrealError as e:
        stop_for_machine(shot_dir, f"Unreal stopped answering while keying {pass_name}: {e}")
        raise
    return report
