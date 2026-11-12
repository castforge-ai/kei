"""The conductor's Maya steps: at the start of a Maya shot, where to animate (asked when Maya is open) and the shot's
scene and rig; after a seat's run, a lost open session stops the shot with paused_machine.

A shot is a Maya shot when kei.toml says [apps] app = "maya", or when its folder has a maya/ folder (kei run --app
maya makes it; --scene also records the user's scene to copy). The stages do not change.
"""
from __future__ import annotations

import json
from pathlib import Path

from kei.apps.maya import MayaError
from kei.apps.maya_session import (HostError, Question, call_host, choose_target, find_sessions, load_target, locate,
                                   save_target)
from kei.apps.maya_shot import setup_shot
from kei.characters import shot_character

PAUSED_FILE = "PAUSED.md"


def maya_dir(shot_dir: Path) -> Path:
    return Path(shot_dir) / "maya"


def wants_maya(shot_dir: Path, app: str) -> bool:
    return app == "maya" or maya_dir(shot_dir).is_dir()


def source_scene(shot_dir: Path) -> Path | None:
    p = maya_dir(shot_dir) / "source.json"
    return Path(json.loads(p.read_text(encoding="utf-8"))["scene"]) if p.is_file() else None


def record_source(shot_dir: Path, scene: Path | None) -> None:
    maya_dir(shot_dir).mkdir(parents=True, exist_ok=True)
    if scene is not None:
        (maya_dir(shot_dir) / "source.json").write_text(json.dumps({"scene": str(Path(scene).resolve())}),
                                                        encoding="utf-8")


def stop_for_machine(shot_dir: Path, why: str) -> None:
    """Leave the reason for the conductor: the shot stops with paused_machine, not in silence."""
    maya_dir(shot_dir).mkdir(parents=True, exist_ok=True)
    (maya_dir(shot_dir) / PAUSED_FILE).write_text(why, encoding="utf-8")


def take_pause(shot_dir: Path) -> str | None:
    p = maya_dir(shot_dir) / PAUSED_FILE
    if not p.is_file():
        return None
    text = p.read_text(encoding="utf-8").strip()
    p.unlink()
    return text or "Maya stopped answering"


def pick_rig(rigs: list[dict], character: str | None) -> dict:
    """The Kei rig to animate in an open scene: the only one, or the one whose character attribute is the shot's
    character. Several that fit (or none) is a question for the author, never a guess."""
    if not rigs:
        raise ValueError("the open scene has no Kei rig: set one up with kei maya setup, or key the rig's own "
                         "controls")
    if len(rigs) == 1:
        return rigs[0]
    fit = [r for r in rigs if r.get("character") == character]
    if len(fit) == 1:
        return fit[0]
    names = ", ".join(f"{r['namespace']} ({r.get('character')})" for r in rigs)
    raise ValueError(f"the open scene has several Kei rigs: {names}; keep the one to animate, or name its "
                     "character in kei.toml [shot] character, then run the shot again")


def open_rig(shot_dir: Path, session, mayapy: Path | None = None, character: str | None = None) -> None:
    """The rig in the open scene: rig/maya_rig.json, and the control map of a Kei rig. read_rig nudges every channel
    to see what it moves, so it runs in the background on a copy of the open scene, never in the user's session (the
    nudges would land in the user's undo queue and unsaved state)."""
    from kei.apps.maya import find_mayapy, run_job
    copy = maya_dir(shot_dir) / "open_scene_copy.ma"
    call_host(session.port, session.token, "save_temp_copy", {"path": str(copy.resolve()).replace("\\", "/")})
    info = call_host(session.port, session.token, "scene_info", {})
    rig = run_job(mayapy or find_mayapy()[0], {"scene": str(copy.resolve()).replace("\\", "/"),
                                               "calls": [{"tool": "read_rig", "inputs": {}}]})["results"][0]
    (Path(shot_dir) / "rig").mkdir(parents=True, exist_ok=True)
    (Path(shot_dir) / "rig" / "maya_rig.json").write_text(json.dumps(rig, indent=1), encoding="utf-8")
    kei = [c for c in rig["controls"] if c["role"] not in ("joint", "control")]
    if kei and rig.get("kei_rigs"):
        chosen = pick_rig(rig["kei_rigs"], character)
        ns = chosen["namespace"]
        ctl = {"character": chosen["character"], "namespace": ns, "unit_per_m": rig["unit_per_m"],
               "units": rig["units"], "up": rig["up"],
               "controls": [c for c in kei if c["name"].rpartition(":")[0] == ns]}
        (Path(shot_dir) / "rig" / "maya_controls.json").write_text(json.dumps(ctl, indent=1), encoding="utf-8")


def prepare(shot_dir: Path, config) -> dict | None:
    """Make the shot ready to animate in Maya. Returns None when it is ready, {"question": text, "choices"} when the
    author must choose where, or {"pause": reason} when Maya cannot do it now."""
    shot_dir = Path(shot_dir)
    target = load_target(shot_dir)
    if target is None:
        sessions, hostless = find_sessions()
        choice = choose_target(sessions, hostless, config.maya_session)
        if isinstance(choice, Question):
            return {"question": choice.text, "choices": choice.choices}
        target = {"kind": choice.kind}
        if choice.session:
            target.update(pid=choice.session.pid, start_time=choice.session.start_time)
        save_target(shot_dir, target)
    try:
        if target["kind"] == "background":
            if not (maya_dir(shot_dir) / "scene.ma").is_file():
                scene = source_scene(shot_dir)
                who = None if scene else shot_character(shot_dir, None, config.character)   # PLAN.md, else config
                setup_shot(shot_dir, character=who, scene=scene,
                           mayapy=Path(config.mayapy) if config.mayapy else None)
        elif not (shot_dir / "rig" / "maya_rig.json").is_file():
            session = locate(target)
            if session is None:
                return {"pause": f"the open Maya (session {target.get('pid')}) is closed or its Kei host does not "
                                 "answer: open it again with the host, or delete maya/target.json to choose again"}
            open_rig(shot_dir, session, Path(config.mayapy) if config.mayapy else None, config.character)
    except (MayaError, HostError, ValueError) as e:
        return {"pause": str(e)}
    return None

