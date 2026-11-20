"""Kei's settings: one table lists every key of kei.toml with its type, default and meaning. kei settings and the
Settings tab on the review page both read it, and both save through apply_change(), which validates the new file the
way a shot would read it before anything is written."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from kei.config import (APPS as APP_CHOICES, example_config, LIVE_SWITCH, WEB_SWITCH, SEND_BACK_POLICIES, RETRY_NOTE, MAYA_SESSIONS as MAYA_SESSION_CHOICES, UNREAL_SESSIONS as UNREAL_SESSION_CHOICES,
                        Config, ConfigError, load_config_text)
from kei.toml_edit import TomlEditError, add_table, format_value, remove_array_table, set_value, unset_value

EXAMPLE = example_config()
Which = Callable[[str], "str | None"]
CREDENTIAL = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}|[A-Z0-9_]*API_KEY\s*=|\bghp_[A-Za-z0-9]{20,}")
BOM = b"\xef\xbb\xbf"

KINDS = ("int", "text", "choice", "path", "command")
SHARE_CHOICES = ("ask", "always", "never", "auto")
BUNDLED = "the book that ships with Kei"


class SettingError(ValueError):
    """A setting cannot be read or saved. The message names the key, the value and the reason."""


@dataclass(frozen=True)
class Setting:
    key: str
    kind: str
    default: object
    meaning: str
    help: str = ""
    choices: tuple = ()


SETTINGS: tuple[Setting, ...] = (
    Setting("animator.cmd", "command", None, "the command line of the agent that animates",
            "Kei sends each stage's prompt on its standard input. The first word must be a program on your PATH."),
    Setting("animator.timeout_s", "int", 1800, "seconds a stage may run before Kei stops the animating agent"),
    Setting("critics[<name>].cmd", "command", None, "the command line of a critic, a reviewer that never edits",
            "Any agent command line. A run needs at least one critic: the agent that animates never reviews its own "
            "work."),
    Setting("critics[<name>].timeout_s", "int", 1800, "seconds a critic may take for one review"),
    Setting("animator.model", "text", None, "the animating agent's model (claude or codex seats)",
            "Added to its command line as the CLI's own flag (--model, or -m for codex)."),
    Setting("animator.effort", "text", None, "the animating agent's effort level (claude or codex seats)",
            "Added to its command line: --effort for claude, model_reasoning_effort for codex."),
    Setting("critics[<name>].model", "text", None, "a critic's model (claude or codex seats)"),
    Setting("critics[<name>].effort", "text", None, "a critic's effort level (claude or codex seats)"),
    Setting("timeouts.<stage>", "int", None, "seconds the animating agent may take on one stage, over animator.timeout_s",
            "A [timeouts] table: blocking = 5400 gives the blocking stage its own limit. A try that runs out of time "
            "keeps its work and is not counted, twice per stage."),
    Setting("limits.primary_critic", "text", None, "when two critics ask opposite things, this critic's note stands",
            "Without it, opposite notes on the same frames and part become one question for you."),
    Setting("limits.<stage>.max_attempts", "int", None, "tries for one stage, over limits.max_attempts",
            "A [limits.plan] or [limits.passes] table sets the limits of that stage only."),
    Setting("limits.<stage>.max_send_backs", "int", None, "send-backs for one stage, over limits.max_send_backs"),
    Setting("critics[<name>].fallback_cmd", "command", None, "a stand-in critic for a usage limit",
            "When this critic hits a usage limit, this command line reviews in its place, so the stage goes on."),
    Setting("limits.max_attempts", "int", 3, "tries per stage before the shot stops for a person"),
    Setting("limits.max_send_backs", "int", 3, "critic send-backs per stage before the shot stops for a person"),
    Setting("limits.on_send_back_limit", "choice", "stop", "what Kei does when a stage reaches its send-back limit",
            "stop: the shot waits for a person (kei retry). retry: the stage runs again from attempt 1 with "
            "limits.retry_note for the animator, up to limits.auto_retries times, then stops. advance: the critics' "
            "open notes go to your sign-off checklist and the shot goes on to the next stage.", SEND_BACK_POLICIES),
    Setting("limits.auto_retries", "int", 2, "automatic retries per stage when on_send_back_limit is retry"),
    Setting("limits.retry_note", "text", RETRY_NOTE, "what the animator reads on an automatic retry"),
    Setting("share.mode", "choice", "ask", "what Kei does with new lessons when you accept a shot",
            "ask: the review page offers to share them and runs nothing until you press Send; always: at Accept, "
            "Kei forks the project and pushes each new lesson folder to a branch of your fork, which is public, "
            "then opens GitHub's pull request form (the pull request opens only at GitHub's button); never: Kei "
            "shares nothing; auto: at Accept and at Reject, with no dialog, Kei checks each lesson that is ready "
            "to share and opens its pull request on share.repo itself (set auto with kei settings or in kei.toml, "
            "never from the page).", SHARE_CHOICES),
    Setting("share.repo", "text", "castforge-ai/kei", "the GitHub repository your lessons are shared to",
            "Written owner/name. The default is the public Kei project; a studio can name its own repository, "
            "private or public, and pass the good lessons on from there."),
    Setting("share.sign_off", "choice", "off", "add your Signed-off-by line to every lesson you share",
            "on: each shared lesson's commit carries Signed-off-by with your GitHub account, which says you agree "
            "to the Developer Certificate of Origin in CONTRIBUTING.md. off: add it yourself to the pull request.",
            ("on", "off")),
    Setting("book.path", "path", BUNDLED, "the rule book: a folder of topic files, or one file",
            "A path next to kei.toml. Leave it unset to use the book that ships with Kei."),
    Setting("book.lessons", "path", "lessons.local.md", "the file of your local lessons (kei note writes them)",
            "A path next to kei.toml. It may not exist yet: the first note makes it."),
    Setting("book.banned_names", "path", "kei.banned.txt", "your private list of names no shot file may hold",
            "One pattern per line (a regular expression, any case), # for comments. "
            "A stage whose files name one fails, and the miss gives the file and the "
            "line, never the name. Kei ships no list; kei.banned.txt next to kei.toml is read when it exists."),
    Setting("refs.library", "path", "kei-refs", "a folder of footage Kei may measure for its references",
            "Public-domain and openly licensed clips and photo sequences, with an INDEX.md and a SOURCE.md per "
            "item (creator, year, licence, frame rate, view). Kei's seats may read it and take the short look "
            "there; nothing in it is copied into a shot. Kei ships no library; kei-refs next to kei.toml is read "
            "when it exists."),
    Setting("book.max_chars", "int", 450000, "the most rule text one stage may get; over it, the shot stops"),
    Setting("shot.character", "choice", "kei", "who Kei animates when the brief names nobody",
            "A built-in character (kei, keira) or one you imported with kei import (see kei characters)."),
    Setting("apps.app", "choice", "kei", "where the keys live: Kei's own rig, Maya, Unreal or Blender",
            "kei: Kei keys its own rig. maya: Kei keys the control rig in Maya (also kei run --app maya). unreal: "
            "Kei keys the control rig in your open Unreal Editor, through Claireon (also kei run --app unreal). "
            "blender: Kei keys its character in a background Blender (also kei run --app blender).",
            APP_CHOICES),
    Setting("apps.maya.session", "choice", "ask", "with Maya open, where a Maya shot animates",
            "ask: Kei asks each time; open: the open Maya, through the Kei host; background: Maya with no "
            "window, on a copy in the shot folder.", MAYA_SESSION_CHOICES),
    Setting("apps.maya.mayapy", "path", None, "Maya's Python, when Kei should not look for it",
            "Leave it unset: Kei uses KEI_MAYAPY, else the newest Maya it finds."),
    Setting("apps.blender.path", "path", None, "Blender's executable, when Kei should not look for it",
            "Leave it unset: Kei uses KEI_BLENDER, else the newest Blender it finds."),
    Setting("apps.unreal.session", "choice", "ask", "with Unreal open, where an Unreal shot animates",
            "ask: Kei asks each time, listing every open editor; open: the one open editor, when exactly one "
            "answers.", UNREAL_SESSION_CHOICES),
    Setting("apps.unreal.url", "text", None, "the Claireon server of your open Unreal Editor",
            "Written http://127.0.0.1:<port>/mcp, on this machine only. Leave it unset when apps.unreal.project is "
            "set: Kei reads the port Claireon wrote in the project."),
    Setting("apps.unreal.project", "path", None, "your Unreal project folder (the one with the .uproject file)",
            "Kei reads Saved/Claireon/MCPServer.json there to find the editor's port."),
    Setting("apps.unreal.mesh", "text", None, "the character's skeletal mesh asset, when the project has several",
            "An asset path such as /Game/Characters/Mannequins/Meshes/SKM_Manny_Simple. Leave it unset when the "
            "project has one character with a Control Rig."),
    Setting("apps.unreal.control_rig", "text", None, "the character's Control Rig asset, when the mesh has several",
            "An asset path such as /Game/Characters/Mannequins/Rigs/CR_Mannequin_Body."),
    Setting("live.page", "choice", "on", "the live page: watch the shot's stages, poses and notes as Kei works",
            "on: kei run starts the shot's live page on 127.0.0.1 and prints its link; the page shows the stage, "
            "the key poses of each try, the critics' notes on their frames, the references and the renders, and "
            "updates every second. off: no page (kei live <shot> still opens one by hand).", LIVE_SWITCH),
    Setting("seats.web", "choice", "on", "web access for Kei's agents, to look for references",
            "on: the animator and the critics may search the web and read pages (papers, and clips to look at; "
            "linked at a timestamp, never downloaded). A Claude Code seat gets WebSearch and WebFetch, a Codex seat "
            "gets --search. off: no web; the seats use the book and your kei-refs library only. kei init asks once.",
            WEB_SWITCH),
    Setting("live.open", "choice", "on", "open the live page in your browser when it starts",
            "on: the browser opens once, when the shot's live page starts; off: Kei only prints the link.",
            LIVE_SWITCH),
)

_CRITIC = re.compile(r"critics\[([^\]]+)\]\.(\w+)")


def setting(key: str) -> Setting:
    """The table row of a key; critics[<any name>].cmd finds the critics row."""
    m = _CRITIC.fullmatch(key)
    lookup = f"critics[<name>].{m.group(2)}" if m else key
    for s in SETTINGS:
        if s.key == lookup:
            return s
    raise SettingError(f"{key} is not a Kei setting: run kei settings to list them")


def choices(s: Setting) -> tuple:
    if s.key == "shot.character":
        from kei.characters import known_characters
        return tuple(known_characters())
    return s.choices


def _read(config_path: Path | None) -> dict:
    if config_path is None or not Path(config_path).is_file():
        return {}
    try:
        return tomllib.loads(Path(config_path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise SettingError(f"{config_path} is not valid TOML: {e}") from e


def critic_names(data: dict) -> list[str]:
    crit = data.get("critics", [])
    return [c.get("name", f"critic{i + 1}") for i, c in enumerate(crit if isinstance(crit, list) else [])
            if isinstance(c, dict)]


def lookup(data: dict, key: str):
    """The raw value of key in parsed TOML, or a KeyError."""
    m = _CRITIC.fullmatch(key)
    if m:
        names = critic_names(data)
        if m.group(1) not in names:
            raise KeyError(key)
        return data["critics"][names.index(m.group(1))][m.group(2)]
    value = data
    for part in key.split("."):     # apps.maya.session is data["apps"]["maya"]["session"]
        value = value[part]
    return value


def current(config_path: Path | None) -> list[dict]:
    """Every setting with its value and where it came from: kei.toml, or the default."""
    data = _read(config_path)
    rows = []
    for s in SETTINGS:
        keys = [s.key.replace("<name>", n) for n in critic_names(data)] if "<name>" in s.key else [s.key]
        for key in keys:
            try:
                value, source = lookup(data, key), "kei.toml"
            except (KeyError, TypeError, IndexError):
                value, source = s.default, "default"
            rows.append({"key": key, "value": value, "default": s.default, "source": source, "meaning": s.meaning,
                         "help": s.help, "kind": s.kind, "choices": list(choices(s))})
    return rows


def parse_cli_value(s: Setting, raw: str):
    """A value typed on the command line, read as a TOML value (3, "ask", ["claude", "-p"]). A bare word for a text,
    choice or path setting is taken as text, so kei settings set share.mode always works."""
    try:
        return tomllib.loads("v = " + raw)["v"]
    except tomllib.TOMLDecodeError:
        if s.kind in ("text", "choice", "path"):
            return raw
        raise SettingError(f"{s.key}: {raw!r} is not a value of this kind ({s.kind}); "
                           + ('write a list such as ["claude", "-p"]' if s.kind == "command"
                              else "write a whole number")) from None


# -- saving ---------------------------------------------------------------------------------------------------------

def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def validate_text(text: str, config_path: Path, which: Which | None = None) -> Config:
    """Refuse a config a shot could not run with: not TOML, refused by load_config (the same parser a shot uses), an
    agent program not on PATH, no critic, a book path that does not exist, or a value that looks like a key."""
    which = which or shutil.which
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise SettingError(f"the new kei.toml would not be valid TOML: {e}") from e
    for value in _strings(data):
        if CREDENTIAL.search(value):
            raise SettingError("a value looks like an API key or a token: Kei never writes a credential into "
                               "kei.toml; set it in an environment variable instead")
    try:
        config = load_config_text(text, Path(config_path))
    except ConfigError as e:
        raise SettingError(str(e)) from e
    if not config.critics:
        raise SettingError("a run with no critic does not start: keep at least one [[critics]] seat")
    for label, seat in (("animator", config.animator), *((f"critic {c.name}", c) for c in config.critics)):
        if which(seat.cmd[0]) is None:
            key = "animator.cmd" if label == "animator" else f"critics[{seat.name}].cmd"
            raise SettingError(f"{label}: the program {seat.cmd[0]} is not on PATH; install it, or change {key}")
    book_t = data.get("book", {}) if isinstance(data.get("book"), dict) else {}
    if "path" in book_t and not config.book.exists():
        raise SettingError(f"book.path {book_t['path']!r}: {config.book} does not exist")
    if not config.lessons.parent.is_dir():
        raise SettingError(f"book.lessons {book_t.get('lessons')!r}: the folder {config.lessons.parent} does not "
                           "exist")
    return config


def file_sha256(config_path: Path) -> str | None:
    p = Path(config_path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def _locate(data: dict, key: str) -> tuple[str, str, int | None]:
    """(table, key, index) of a setting key in the file: critics[codex].cmd is ("critics", "cmd", 1)."""
    setting(key)
    m = _CRITIC.fullmatch(key)
    if m:
        names = critic_names(data)
        if m.group(1) not in names:
            raise SettingError(f"{key}: there is no critic named {m.group(1)!r}; the critics are "
                               f"{', '.join(names) or 'none'}")
        return "critics", m.group(2), names.index(m.group(1))
    table, leaf = key.rsplit(".", 1)      # apps.unreal.url is the key url in the table [apps.unreal]
    return table, leaf, None


def _save(config_path: Path, transform: Callable[[str, dict], str], expect_sha256: str | None, which: Which | None,
          notes: list | None) -> tuple[dict, dict]:
    """Read (or start from the example), transform, validate, back up, replace atomically. Returns (old, new) data."""
    config_path = Path(config_path)
    if config_path.is_file():
        raw = config_path.read_bytes()
        if expect_sha256 is not None and hashlib.sha256(raw).hexdigest() != expect_sha256:
            raise SettingError("kei.toml changed since you opened it: reload")
    else:
        raw = EXAMPLE.read_bytes()
        if notes is not None:
            notes.append(f"no kei.toml yet: copied kei.example.toml, with its comments, to {config_path}")
    bom = raw.startswith(BOM)
    text = raw.decode("utf-8-sig")
    old = tomllib.loads(text)
    try:
        new_text = transform(text, old)
    except TomlEditError as e:
        raise SettingError(str(e)) from e
    validate_text(new_text, config_path, which)
    if config_path.is_file():
        config_path.with_name(config_path.name + ".bak").write_bytes(raw)
    tmp = config_path.with_name(config_path.name + ".tmp")
    tmp.write_bytes((BOM if bom else b"") + new_text.encode("utf-8"))
    os.replace(tmp, config_path)
    return old, tomllib.loads(new_text)


def _value_or_default(data: dict, key: str):
    try:
        return lookup(data, key)
    except (KeyError, TypeError, IndexError):
        return setting(key).default


def apply_change(config_path: Path, changes: dict, expect_sha256: str | None = None, which: Which | None = None,
                 notes: list | None = None) -> list[tuple[str, object, object]]:
    """Set each key to its value (None unsets it, so the default applies), validate the whole new file, then write
    kei.toml.bak and replace kei.toml. Returns (key, old, new) per change. Nothing is written when anything fails."""
    def transform(text: str, data: dict) -> str:
        for key, value in changes.items():
            table, leaf, index = _locate(data, key)
            text = (unset_value(text, table, leaf, index) if value is None
                    else set_value(text, table, leaf, format_value(value), index))
        return text
    old, new = _save(config_path, transform, expect_sha256, which, notes)
    return [(k, _value_or_default(old, k), _value_or_default(new, k)) for k in changes]


PRESETS = ("claude", "codex")


def _preset_block(name: str, preset: str) -> str:
    """A [[critics]] table copied from the example config's critic of that kind, under a new name."""
    if preset not in PRESETS:
        raise SettingError(f"--preset {preset!r}: use one of {', '.join(PRESETS)}")
    data = tomllib.loads(EXAMPLE.read_text(encoding="utf-8"))
    cmd = next(c["cmd"] for c in data["critics"] if c["cmd"][0] == preset)
    return f"[[critics]]\nname = {format_value(name)}\ncmd = {format_value(cmd)}\n"


def add_critic(config_path: Path, name: str, preset: str, expect_sha256: str | None = None,
               which: Which | None = None, notes: list | None = None) -> None:
    def transform(text: str, data: dict) -> str:
        if name in critic_names(data):
            raise SettingError(f"there is a critic named {name!r} already")
        return add_table(text, _preset_block(name, preset))
    _save(config_path, transform, expect_sha256, which, notes)


def remove_critic(config_path: Path, name: str, expect_sha256: str | None = None, which: Which | None = None,
                  notes: list | None = None) -> None:
    def transform(text: str, data: dict) -> str:
        names = critic_names(data)
        if name not in names:
            raise SettingError(f"there is no critic named {name!r}; the critics are {', '.join(names) or 'none'}")
        if len(names) == 1:
            raise SettingError("a run with no critic does not start: this is the last critic")
        return remove_array_table(text, "critics", names.index(name))
    _save(config_path, transform, expect_sha256, which, notes)


def show(value) -> str:
    """A value as kei settings prints it: TOML, so it can be typed back."""
    return "(none)" if value is None else format_value(value)
