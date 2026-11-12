"""Where Kei animates an Unreal shot: in an open Unreal Editor, through Claireon. Kei never picks in silence: it asks.

candidate_urls(config_url, project_dir) -> the Claireon URLs to try: [apps.unreal] url, and the port the project's
  editor wrote in <project>/Saved/Claireon/MCPServer.json.
find_editors(urls, probe) -> [Editor]
  probe(url) returns {"project", "level", "characters"} (the characters that have a Control Rig) or None. Kei calls
  it again at each question, so an editor opened after Kei started is found.
choose_target(editors, setting) -> Target | Question
  setting is [apps.unreal] session: "ask" (default) or "open". Exactly one editor with a Control Rig character and
  "open" is the only case with no question. Every question lists Kei's own rig as a choice.
answer_choice(choices, text) -> the chosen choice, by its number (the same as the Maya question).
The choice is kept in the shot folder (unreal/target.json: the kind, the URL and the project; never a token).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from kei.apps.maya_session import Question, Target, answer_choice
from kei.apps.unreal import Claireon, UnrealError, run_script, server_url

__all__ = ["Editor", "Question", "Target", "answer_choice", "candidate_urls", "choose_target", "find_editors",
           "load_target", "locate", "pick_character", "probe_editor", "save_target", "SETTINGS"]

SETTINGS = ("ask", "open")
SETUP_STEP = "kei unreal setup lists the steps"


@dataclass
class Editor:
    url: str
    project: str
    level: str = ""
    characters: list = field(default_factory=list)     # [{"name", "mesh", "control_rig"}]


def candidate_urls(config_url: str | None, project_dir: str | None) -> list[str]:
    urls = [config_url] if config_url else []
    if project_dir:
        found = server_url(Path(project_dir))
        if found and found not in urls:
            urls.append(found)
    return urls


def probe_editor(url: str, timeout: float = 10) -> dict | None:
    """The real probe: the project, the open level and the characters with a Control Rig, or None when nothing
    answers (or what answers is not an Unreal Editor with Claireon)."""
    try:
        client = Claireon(url, timeout=timeout)
        client.initialize()
        got = run_script(client, "probe.py", {})
    except UnrealError:
        return None
    return {"project": got.get("project", ""), "level": got.get("level", ""), "characters": got.get("characters", []),
            "server": client.info.get("server", "")}


def find_editors(urls: list[str], probe: Callable[[str], dict | None] = probe_editor) -> list[Editor]:
    editors, seen = [], set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        info = probe(url)
        if info is not None:
            editors.append(Editor(url, str(info.get("project") or ""), str(info.get("level") or ""),
                                  list(info.get("characters") or [])))
    return editors


def _who(c: dict) -> str:
    """A character as the author can tell it apart: one mesh can have several Control Rigs."""
    rig = str(c.get("control_rig") or "").rsplit("/", 1)[-1]
    return f"{c['name']} with {rig}" if rig else str(c["name"])


def _line(e: Editor) -> str:
    who = ", ".join(_who(c) for c in e.characters) or "no character with a Control Rig"
    return f"in the open Unreal Editor, project {e.project or 'unnamed'}, level {e.level or 'unknown'}, characters {who}"


KEI_OWN = "Kei's own rig (no Unreal: Kei keys its own skeleton, and you export a file for Unreal afterwards)"


def choose_target(editors: list[Editor], setting: str = "ask") -> Target | Question:
    if setting not in SETTINGS:
        raise ValueError(f"apps.unreal.session must be one of {', '.join(SETTINGS)}, not {setting!r}")
    if setting == "open" and len(editors) == 1 and editors[0].characters:
        return Target("open", editors[0])
    if not editors:
        choices = [{"n": 1, "kind": "retry", "text": "look again (open your project with Claireon first)"},
                   {"n": 2, "kind": "kei", "text": KEI_OWN}]
        text = ("No Unreal Editor answers. To animate in Unreal: install Claireon in your project, open the "
                f"project and start its server ({SETUP_STEP}). Where should Kei animate this shot?\n"
                + "\n".join(f"{c['n']}. {c['text']}" for c in choices) + "\nAnswer with the number.")
        return Question(text, choices)
    choices = [{"n": i + 1, "kind": "open", "url": e.url, "project": e.project, "text": _line(e)}
               for i, e in enumerate(editors)]
    choices.append({"n": len(choices) + 1, "kind": "kei", "text": KEI_OWN})
    lines = ["Unreal is open. Where should Kei animate this shot? Kei writes only in Content/Kei/ of the project "
             "and never saves your assets."]
    lines += [f"{c['n']}. {c['text']}" for c in choices]
    for e in editors:
        if not e.characters:
            lines.append(f"The editor on project {e.project or 'unnamed'} has no character with a Control Rig, so "
                         "Kei cannot key it: pick another choice, or open a project whose character has one.")
    lines.append("Answer with the number.")
    return Question("\n".join(lines), choices)


def target_path(shot_dir: Path) -> Path:
    return Path(shot_dir) / "unreal" / "target.json"


def save_target(shot_dir: Path, choice: dict) -> Path:
    p = target_path(shot_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    keep = {k: choice[k] for k in ("kind", "url", "project") if k in choice}
    p.write_text(json.dumps(keep, indent=1), encoding="utf-8")
    return p


def load_target(shot_dir: Path) -> dict | None:
    p = target_path(shot_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def locate(target: dict, probe: Callable[[str], dict | None] = probe_editor) -> Editor | None:
    """The open editor a target names, probed again: the same URL, answering for the same project."""
    info = probe(target.get("url") or "")
    if info is None or str(info.get("project") or "") != str(target.get("project") or ""):
        return None
    return Editor(target["url"], str(info.get("project") or ""), str(info.get("level") or ""),
                  list(info.get("characters") or []))


def pick_character(editor: Editor, mesh: str | None, control_rig: str | None) -> dict:
    """The character to animate: the one the config names, else the only one. Several (or none) is the author's
    to settle, never a guess."""
    chars = editor.characters
    if not chars:
        raise ValueError("the open project has no character with a Control Rig: open a project that has one, or "
                         "animate on Kei's own rig")
    if mesh or control_rig:
        fit = [c for c in chars if (not mesh or c.get("mesh") == mesh) and (not control_rig
                                                                           or c.get("control_rig") == control_rig)]
        if len(fit) == 1:
            return fit[0]
        raise ValueError(f"no single character in the open project matches {mesh or control_rig}: it has "
                         + ", ".join(f"{c['mesh']} with {c.get('control_rig')}" for c in chars)
                         + ": set [apps.unreal] control_rig in kei.toml too when one mesh has several rigs")
    if len(chars) == 1:
        return chars[0]
    names = ", ".join(f"{c['mesh']} with {c.get('control_rig')}" for c in chars)
    raise ValueError(f"the open project has several characters with a Control Rig: {names}; set [apps.unreal] mesh "
                     "(and control_rig, when one mesh has several) in kei.toml to the one to animate, then run the shot again")
