"""The Kei config file (kei.toml): which agent animates, which agents critique, the rule book and the limits."""
from __future__ import annotations

import re
import tomllib
from urllib.parse import urlparse
from dataclasses import dataclass, field
from pathlib import Path

from kei.book import BUNDLED_BOOK
from kei.characters import known_characters
from kei.characters import DEFAULT as DEFAULT_CHARACTER

SHARE_MODES = ("ask", "always", "never", "auto")
SHARE_REPO = "castforge-ai/kei"     # where shared lessons go unless share.repo names another GitHub repository
_REPO = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/(?!\.\.?$)[A-Za-z0-9._-]{1,100}")
APPS = ("kei", "maya", "unreal")
MAYA_SESSIONS = ("ask", "open", "background")
UNREAL_SESSIONS = ("ask", "open")


LIVE_SWITCH = ("on", "off")
WEB_SWITCH = ("on", "off")
SEND_BACK_POLICIES = ("stop", "retry", "advance")   # limits.on_send_back_limit
RETRY_NOTE = ("Automatic retry after the send-back limit. The critics' last notes are fixable at the keys: apply "
              "each one, or declare it in GATES.md with a reason if you judge it wrong, and continue.")


class ConfigError(ValueError):
    """A config value is missing or wrong. The message names the key."""


@dataclass(frozen=True)
class SeatSpec:
    name: str
    cmd: list[str]
    timeout_s: int = 1800
    fallback_cmd: tuple = ()   # a critic's stand-in seat: it answers when this one hits a usage limit


@dataclass(frozen=True)
class Config:
    animator: SeatSpec
    critics: list[SeatSpec] = field(default_factory=list)
    max_attempts: int = 3
    max_send_backs: int = 3
    on_send_back_limit: str = "stop"     # stop | retry | advance (kei.conductor._limit_reached)
    auto_retries: int = 2
    retry_note: str = RETRY_NOTE
    share: str = "ask"
    share_repo: str = SHARE_REPO          # owner/name of the GitHub repository lessons are shared to
    share_sign_off: str = "off"           # "on": a shared lesson's commit carries the user's Signed-off-by line
    book: Path = BUNDLED_BOOK
    lessons: Path = Path("lessons.local.md")
    max_rule_chars: int = 450000
    character: str = DEFAULT_CHARACTER    # the shot's character when neither shot.json nor PLAN.md names one
    app: str = "kei"                     # where the keys live: Kei's own rig, or Maya
    maya_session: str = "ask"            # a Maya shot with Maya open: ask, the open session, or the background
    mayapy: str | None = None            # Maya's Python, when Kei should not look for it
    unreal_url: str | None = None        # the Claireon server of the open Unreal Editor (127.0.0.1 only)
    unreal_project: str | None = None    # the Unreal project folder, where Claireon writes its port
    unreal_session: str = "ask"          # an Unreal shot: ask, or the one open editor when exactly one answers
    unreal_mesh: str | None = None       # the character's skeletal mesh asset, when the project has several
    unreal_control_rig: str | None = None   # its Control Rig asset
    banned_names: Path | None = None     # the author's private list of names no shot file may hold (gates/sources.py)
    live_page: str = "on"                # kei run starts the shot's live page (kei live); "off" does not
    live_open: str = "on"                # the browser opens the live page when its server starts
    refs_library: Path | None = None     # a folder of footage the seats may measure (kei/refs.py)
    web: str = "on"                      # the seats may search the web for references (seats.web)
    web_asked: bool = False              # kei.toml holds the answer; when False, Kei asks once and saves it
    stage_limits: dict = field(default_factory=dict)   # [limits.<stage>]: max_attempts, max_send_backs per stage
    primary_critic: str | None = None    # when two critics ask opposite things, this one's note stands
    stage_timeouts: dict = field(default_factory=dict)   # [timeouts]: a stage's own seat time limit, seconds

    def attempts_for(self, stage_id: str) -> int:
        return self.stage_limits.get(stage_id, {}).get("max_attempts", self.max_attempts)

    def send_backs_for(self, stage_id: str) -> int:
        return self.stage_limits.get(stage_id, {}).get("max_send_backs", self.max_send_backs)


def _positive_int(value, key: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ConfigError(f"{key} must be a whole number of 1 or more, not {value!r}")
    return value


def _model_flags(cmd: list[str], table: dict, key: str) -> list[str]:
    """model and effort, written as fields of a seat instead of inside its command: the flags its CLI takes."""
    model, effort = table.get("model"), table.get("effort")
    for name, v in (("model", model), ("effort", effort)):
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise ConfigError(f"{key}.{name} must be a name, such as opus or high")
    if model is None and effort is None:
        return []
    cli = Path(cmd[0]).stem.lower()
    if cli == "claude":
        return (["--model", model] if model else []) + (["--effort", effort] if effort else [])
    if cli == "codex":
        return (["-m", model] if model else []) + (["-c", f'model_reasoning_effort="{effort}"'] if effort else [])
    raise ConfigError(f"{key}: model and effort are known for claude and codex seats; for {cmd[0]}, put them in "
                      f"its cmd")


def _seat(table, key: str, default_name: str) -> SeatSpec:
    if not isinstance(table, dict):
        raise ConfigError(f"{key} must be a table")
    cmd = table.get("cmd")
    if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) and c for c in cmd):
        raise ConfigError(f"{key}.cmd must be a non-empty list of strings")
    timeout = _positive_int(table.get("timeout_s", 1800), f"{key}.timeout_s")
    name = table.get("name", default_name)
    if not isinstance(name, str) or not name:
        raise ConfigError(f"{key}.name must be a non-empty string")
    flags = _model_flags(cmd, table, key)
    at = 2 if Path(cmd[0]).stem.lower() == "codex" and len(cmd) > 1 and cmd[1] == "exec" else 1
    cmd = list(cmd[:at]) + flags + list(cmd[at:])      # right after the program (and codex's exec)
    fallback = table.get("fallback_cmd", [])
    if not isinstance(fallback, list) or not all(isinstance(c, str) and c for c in fallback):
        raise ConfigError(f"{key}.fallback_cmd must be a list of strings (the stand-in seat's command)")
    return SeatSpec(name=name, cmd=list(cmd), timeout_s=timeout, fallback_cmd=tuple(fallback))


def _path(value, base: Path, key: str) -> Path | None:
    """A path from the config, relative to the config file's folder."""
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{key} must be a path, not {value!r}")
    return base / value


def example_config() -> Path:
    """The example kei.toml that ships with Kei: inside the package when installed, beside it in a repository clone."""
    here = Path(__file__).resolve().parent
    inside = here / "kei.example.toml"
    return inside if inside.is_file() else here.parent / "kei.example.toml"


def _is_example(path: Path) -> bool:
    """True when path is the example kei.toml that ships with Kei."""
    try:
        return Path(path).resolve() == example_config().resolve()
    except OSError:
        return False


def load_config(path: Path) -> Config:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"cannot read the config {path}: {e}") from e
    return load_config_text(text, path)


def load_config_text(text: str, path: Path) -> Config:
    """The config in text, read as if it were the file at path (relative paths start from path's folder). kei
    settings checks a change with this before it saves, so a shot and a save read a config the same way."""
    path = Path(path)
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"the config {path} is not valid TOML: {e}") from e
    if "animator" not in data:
        raise ConfigError(f"{path}: the [animator] table is missing")
    animator = _seat(data["animator"], "animator", "animator")
    critics_raw = data.get("critics", [])
    if not isinstance(critics_raw, list):
        raise ConfigError("critics must be a list of [[critics]] tables")
    critics = [_seat(t, f"critics[{i}]", f"critic{i + 1}") for i, t in enumerate(critics_raw)]
    limits = data.get("limits", {})
    max_attempts = _positive_int(limits.get("max_attempts", 3), "max_attempts")
    max_send_backs = _positive_int(limits.get("max_send_backs", 3), "max_send_backs")
    from kei.stages import STAGES
    stage_ids = {s.id for s in STAGES}
    stage_limits = {}
    for k, v in limits.items():
        if not isinstance(v, dict):
            continue
        if k not in stage_ids:
            raise ConfigError(f"limits.{k}: no stage {k!r}; stages: {', '.join(s.id for s in STAGES)}")
        bad = set(v) - {"max_attempts", "max_send_backs"}
        if bad:
            raise ConfigError(f"limits.{k} takes max_attempts and max_send_backs, not {', '.join(sorted(bad))}")
        stage_limits[k] = {n: _positive_int(x, f"limits.{k}.{n}") for n, x in v.items()}
    timeouts_t = data.get("timeouts", {})
    if not isinstance(timeouts_t, dict):
        raise ConfigError("timeouts must be a table of stage = seconds")
    stage_timeouts = {}
    for k, v in timeouts_t.items():
        if k not in stage_ids:
            raise ConfigError(f"timeouts.{k}: no stage {k!r}")
        stage_timeouts[k] = _positive_int(v, f"timeouts.{k}")
    primary_critic = limits.get("primary_critic")
    if primary_critic is not None and not isinstance(primary_critic, str):
        raise ConfigError("limits.primary_critic must be a critic's name")
    on_limit = limits.get("on_send_back_limit", "stop")
    if on_limit not in SEND_BACK_POLICIES:
        raise ConfigError(f"limits.on_send_back_limit is one of {', '.join(SEND_BACK_POLICIES)}, not {on_limit!r}")
    auto_retries = limits.get("auto_retries", 2)
    if not isinstance(auto_retries, int) or isinstance(auto_retries, bool) or auto_retries < 0:
        raise ConfigError("limits.auto_retries is a whole number, 0 or more")
    retry_note = limits.get("retry_note", RETRY_NOTE)
    if not isinstance(retry_note, str) or not retry_note.strip():
        raise ConfigError("limits.retry_note is the text the animator reads on an automatic retry")
    share_t = data.get("share", {})
    if not isinstance(share_t, dict):
        raise ConfigError("share must be a table")
    share = share_t.get("mode", "ask")
    if share not in SHARE_MODES:
        raise ConfigError(f"share.mode must be one of {', '.join(SHARE_MODES)}, not {share!r}")
    share_repo = share_t.get("repo", SHARE_REPO)
    share_sign_off = share_t.get("sign_off", "off")
    if share_sign_off not in ("on", "off"):
        raise ConfigError(f"share.sign_off must be on or off, not {share_sign_off!r}")
    if not isinstance(share_repo, str) or not _REPO.fullmatch(share_repo):
        raise ConfigError(f"share.repo must be a GitHub repository written owner/name, such as {SHARE_REPO}, "
                          f"not {share_repo!r}")
    book_t = data.get("book", {})
    if not isinstance(book_t, dict):
        raise ConfigError("book must be a table")
    book = _path(book_t.get("path"), path.parent, "book.path") or BUNDLED_BOOK
    # Lessons are the user's own file. With no kei.toml, Kei runs on the example config that ships with
    # it, and a lesson saved next to that file would land in the install folder (or the repository clone),
    # so the user's lessons go to the folder Kei runs in instead.
    lessons_base = Path.cwd() if _is_example(path) else path.parent
    lessons = _path(book_t.get("lessons", "lessons.local.md"), lessons_base, "book.lessons")
    max_rule_chars = _positive_int(book_t.get("max_chars", 450000), "book.max_chars")
    banned_names = _path(book_t.get("banned_names"), path.parent, "book.banned_names")
    if banned_names is None and (path.parent / "kei.banned.txt").is_file():
        banned_names = path.parent / "kei.banned.txt"     # the default place, next to kei.toml
    shot_t = data.get("shot", {})
    if not isinstance(shot_t, dict):
        raise ConfigError("shot must be a table")
    character = shot_t.get("character", DEFAULT_CHARACTER)
    if not isinstance(character, str) or character.strip().lower() not in known_characters():
        raise ConfigError(f"shot.character {character!r} is not a known character; use one of: "
                          f"{', '.join(known_characters())}")
    apps_t = data.get("apps", {})
    if not isinstance(apps_t, dict):
        raise ConfigError("apps must be a table")
    app = apps_t.get("app", "kei")
    if app not in APPS:
        raise ConfigError(f"apps.app must be one of {', '.join(APPS)}, not {app!r}")
    maya_t = apps_t.get("maya", {})
    if not isinstance(maya_t, dict):
        raise ConfigError("apps.maya must be a table")
    session = maya_t.get("session", "ask")
    if session not in MAYA_SESSIONS:
        raise ConfigError(f"apps.maya.session must be one of {', '.join(MAYA_SESSIONS)}, not {session!r}")
    mayapy = maya_t.get("mayapy")
    if mayapy is not None and (not isinstance(mayapy, str) or not mayapy):
        raise ConfigError("apps.maya.mayapy must be a path")
    unreal_t = apps_t.get("unreal", {})
    if not isinstance(unreal_t, dict):
        raise ConfigError("apps.unreal must be a table")
    u_session = unreal_t.get("session", "ask")
    if u_session not in UNREAL_SESSIONS:
        raise ConfigError(f"apps.unreal.session must be one of {', '.join(UNREAL_SESSIONS)}, not {u_session!r}")
    u_url = unreal_t.get("url")
    if u_url is not None and (not isinstance(u_url, str) or urlparse(u_url).hostname not in ("127.0.0.1", "localhost")
                              or urlparse(u_url).scheme not in ("http", "https")):
        raise ConfigError("apps.unreal.url must be a URL on 127.0.0.1, such as http://127.0.0.1:50000/mcp: Kei "
                          "talks to Claireon on this machine only")
    unreal_text = {}
    for k in ("project", "mesh", "control_rig"):
        v = unreal_t.get(k)
        if v is not None and (not isinstance(v, str) or not v):
            raise ConfigError(f"apps.unreal.{k} must be a text, not {v!r}")
        unreal_text[k] = v
    live_t = data.get("live", {})
    if not isinstance(live_t, dict):
        raise ConfigError("live must be a table")
    live = {}
    for k in ("page", "open"):
        v = live_t.get(k, "on")
        if v not in LIVE_SWITCH:
            raise ConfigError(f"live.{k} must be one of {', '.join(LIVE_SWITCH)}, not {v!r}")
        live[k] = v
    refs_t = data.get("refs", {})
    if not isinstance(refs_t, dict):
        raise ConfigError("refs must be a table")
    refs_library = _path(refs_t.get("library"), path.parent, "refs.library")
    if refs_library is None and (path.parent / "kei-refs").is_dir():
        refs_library = path.parent / "kei-refs"     # the default place, next to kei.toml
    elif refs_library is not None and not refs_library.is_dir():
        raise ConfigError(f"refs.library {refs_library} is not a folder: make it, or remove the setting")
    seats_t = data.get("seats", {})
    if not isinstance(seats_t, dict):
        raise ConfigError("seats must be a table")
    web = seats_t.get("web", "on")
    if web not in WEB_SWITCH:
        raise ConfigError(f"seats.web must be one of {', '.join(WEB_SWITCH)}, not {web!r}")
    return Config(animator=animator, critics=critics, max_attempts=max_attempts,
                  max_send_backs=max_send_backs, on_send_back_limit=on_limit, auto_retries=auto_retries,
                  retry_note=retry_note.strip(), share=share, share_repo=share_repo, share_sign_off=share_sign_off, book=book, lessons=lessons,
                  max_rule_chars=max_rule_chars, character=character.strip().lower(), app=app,
                  maya_session=session, mayapy=mayapy, unreal_url=u_url, unreal_project=unreal_text["project"],
                  unreal_session=u_session, unreal_mesh=unreal_text["mesh"],
                  unreal_control_rig=unreal_text["control_rig"], live_page=live["page"], live_open=live["open"],
                  banned_names=banned_names, refs_library=refs_library, web=web, web_asked="web" in seats_t,
                  stage_limits=stage_limits, primary_critic=primary_critic, stage_timeouts=stage_timeouts)
