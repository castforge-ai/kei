"""Seats: any agent CLI that reads a prompt on stdin and works in the shot folder."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Protocol

from kei.config import SeatSpec


@dataclass(frozen=True)
class SeatResult:
    exit_code: int
    output: str
    stderr: str = ""            # the seat's warnings and errors, kept apart from its answer
    usage: dict | None = None   # tokens, when the CLI reports them (Claude Code JSON, Codex --json)
    session: str = ""           # the session id the CLI gave (Codex --json), for the next try to resume


TOKEN_KEYS = {"input_tokens": "input", "output_tokens": "output", "cache_read_input_tokens": "cache_read",
              "cache_creation_input_tokens": "cache_write"}


def unwrap_json(stdout: str) -> tuple[str, dict | None]:
    """Claude Code's --output-format json answer: the reply text and the token use. Any other output is returned
    as it is, with no usage."""
    text = (stdout or "").strip()
    if not text.startswith("{"):
        return stdout, None
    try:
        data = json.loads(text)
    except ValueError:
        return codex_events(stdout)[:2]
    if not isinstance(data, dict) or not isinstance(data.get("result"), str):
        return stdout, None
    raw = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    usage = {k: int(raw[src]) for src, k in TOKEN_KEYS.items() if isinstance(raw.get(src), (int, float))}
    return data["result"], (usage or None)


CODEX_TOKENS = {"input_tokens": "input", "output_tokens": "output", "cached_input_tokens": "cache_read",
                "cache_write_input_tokens": "cache_write"}


def codex_events(stdout: str) -> tuple[str, dict | None, str]:
    """Codex's --json event lines: the agent's messages as the reply, the token use of its turns and the thread id.
    Output that is not Codex events comes back as it is."""
    texts, usage, thread, seen = [], {}, "", False
    for line in (stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict) or not isinstance(ev.get("type"), str):
            continue
        seen = True
        if ev["type"] == "thread.started" and isinstance(ev.get("thread_id"), str):
            thread = ev["thread_id"]
        item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
        if ev["type"] == "item.completed" and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            texts.append(item["text"])
        if ev["type"] == "turn.completed" and isinstance(ev.get("usage"), dict):
            for src, k in CODEX_TOKENS.items():
                if isinstance(ev["usage"].get(src), (int, float)):
                    usage[k] = usage.get(k, 0) + int(ev["usage"][src])
    if not seen:
        return stdout, None, ""
    return "\n\n".join(texts), (usage or None), thread


# A seat that stops for one of these reasons did no craft work: the stage pauses and the try is not counted.
USAGE = re.compile(r"hit your [^\n]{0,40}limit|usage limit|rate[ _-]?limit|(?:status|error|code|http)\W{0,3}429\b"
                   r"|too many requests|quota exceeded", re.I)   # a bare 429 elsewhere in a failed run is no limit
LAUNCH_CODES = {3221225794, -1073741502}   # 0xC0000142: Windows could not start the process (no desktop heap, etc.)
COULD_NOT_START = 126


def pause_kind(result: SeatResult) -> str | None:
    """"usage" when the seat hit a usage or rate limit, "machine" when its process could not start, else None."""
    if result.exit_code == 0:
        return None
    if result.exit_code in LAUNCH_CODES or result.exit_code == COULD_NOT_START:
        return "machine"
    if USAGE.search(result.output or ""):
        return "usage"
    return None


class SeatPaused(Exception):
    """A seat stopped for a usage limit or a machine fault. kind is "usage" or "machine"."""

    def __init__(self, kind: str, seat: str, output: str):
        super().__init__(f"{seat}: {output}")
        self.kind, self.seat, self.output = kind, seat, output


class Seat(Protocol):
    name: str

    def run(self, prompt: str, workdir: Path) -> SeatResult: ...


def _kill_tree(proc: subprocess.Popen) -> None:
    """Agent CLIs start child processes; stop the whole tree, not only the parent."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        proc.kill()
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _user_scripts() -> str | None:
    """The per-user scripts folder, when Kei was installed there (pip install --user): its kei command lives there,
    and that folder is often not on PATH."""
    try:
        d = sysconfig.get_path("scripts", f"{os.name}_user")
    except KeyError:
        return None
    exe = "kei.exe" if os.name == "nt" else "kei"
    return d if d and os.path.isfile(os.path.join(d, exe)) else None


SEAT_KEYS = ("ANTHROPIC_", "CLAUDE_", "OPENAI_", "CODEX_", "KEI_")   # the seats' own credentials and Kei's settings
SECRET = re.compile(r"TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE_KEY|API_KEY|ACCESS_KEY|_PAT$|DATABASE_URL|"
                    r"^AWS_|^AZURE_|^GOOGLE_APPLICATION|^GCP_|^STRIPE_|^SUPABASE_|^VERCEL_|^NPM_|^GH_|^GITHUB_", re.I)


def secret_name(name: str) -> bool:
    """A variable a seat does not get: a credential for another service (GitHub, cloud, payments, databases). The
    seats' own credentials (Anthropic, OpenAI, Claude, Codex) and Kei's settings pass."""
    if name.upper().startswith(SEAT_KEYS):
        return False
    return bool(SECRET.search(name))


def seat_env() -> dict[str, str]:
    """The seat's environment: Kei's own scripts folder (where the kei command and Kei's python live) first on PATH,
    so a seat that runs `kei render` or `python` gets this Kei, even from a shell that never activated it. Other
    services' credentials stay out (secret_name): a seat that runs python could otherwise read and send them."""
    env = {k: v for k, v in os.environ.items() if not secret_name(k)}
    first = []
    for d in (sysconfig.get_path("scripts"), _user_scripts(), os.path.dirname(sys.executable)):
        if d and os.path.normcase(d) not in map(os.path.normcase, first):
            first.append(d)
    rest = [p for p in env.get("PATH", "").split(os.pathsep)
            if p and os.path.normcase(p.rstrip(r"\/")) not in {os.path.normcase(d) for d in first}]
    env["PATH"] = os.pathsep.join(first + rest)
    return env


def with_dirs(spec: SeatSpec, dirs) -> SeatSpec:
    """The seat with read access to more folders: a Claude Code seat gets one --add-dir per folder. Another agent
    CLI is left as it is: its own flags decide what it may read (Codex's read-only sandbox reads any file)."""
    dirs = [str(Path(d).resolve()) for d in dirs if d]
    if not dirs or Path(spec.cmd[0]).stem.lower() != "claude":
        return spec
    extra = [x for d in dirs if d not in spec.cmd for x in ("--add-dir", d)]
    return replace(spec, cmd=[spec.cmd[0], *extra, *spec.cmd[1:]])


def is_codex_exec(spec: SeatSpec) -> bool:
    return len(spec.cmd) >= 2 and Path(spec.cmd[0]).stem.lower() == "codex" and spec.cmd[1] == "exec" \
        and (len(spec.cmd) < 3 or spec.cmd[2] != "resume")


_CODEX_KEEP_VALUE = {"-m", "--model", "-c", "--config", "--enable", "--disable", "-i", "--image"}
_CODEX_KEEP_FLAG = {"--skip-git-repo-check", "--ignore-user-config", "--ignore-rules", "--ephemeral", "--json",
                    "--strict-config", "--dangerously-bypass-approvals-and-sandbox"}


def codex_resume_cmd(cmd: list[str], session: str) -> list[str]:
    """codex exec <flags> - as codex exec resume <flags> <session> -. resume takes no --sandbox and no --add-dir, so
    they go in as the config keys they set (sandbox_mode, sandbox_workspace_write.writable_roots)."""
    out, roots, i = [], [], 2
    while i < len(cmd):
        a = cmd[i]
        if a in _CODEX_KEEP_VALUE and i + 1 < len(cmd):
            out += [a, cmd[i + 1]]
            i += 2
        elif a in ("-s", "--sandbox") and i + 1 < len(cmd):
            out += ["-c", f'sandbox_mode="{cmd[i + 1]}"']
            i += 2
        elif a == "--add-dir" and i + 1 < len(cmd):
            roots.append(cmd[i + 1])
            i += 2
        elif a in _CODEX_KEEP_FLAG:
            out.append(a)
            i += 1
        else:
            i += 1        # "-" (the prompt from stdin) and flags resume does not take
    if roots:
        out += ["-c", "sandbox_workspace_write.writable_roots=[" + ", ".join(json.dumps(r) for r in roots) + "]"]
    if "--json" not in out:
        out.append("--json")
    return [cmd[0], "exec", "resume", *out, session, "-"]


def with_session(spec: SeatSpec, session: str, resume: bool) -> SeatSpec:
    """A seat that keeps one session across a stage's tries, so later tries keep what the first one read and wrote.
    Claude Code starts (--session-id) or resumes (--resume) the session Kei names. Codex names its own session: the
    first try runs with --json, Kei reads the thread id from the answer, and later tries run codex exec resume on it.
    Another agent CLI is left as it is."""
    if is_codex_exec(spec):
        if resume and session:
            return replace(spec, cmd=codex_resume_cmd(spec.cmd, session))
        if "--json" in spec.cmd:
            return spec
        return replace(spec, cmd=[spec.cmd[0], "exec", "--json", *spec.cmd[2:]])
    if not spec.cmd or Path(spec.cmd[0]).stem.lower() != "claude" or "--resume" in spec.cmd:
        return spec
    flag = ["--resume", session] if resume else ["--session-id", session]
    return replace(spec, cmd=[spec.cmd[0], *flag, *spec.cmd[1:]])


NO_SESSION = re.compile(r"no conversation found|session[^\n]{0,40}not found|invalid session", re.I)


def keep_run(workdir, label: str, prompt: str, result: "SeatResult", seconds: float) -> dict:
    """Keep one seat run in the shot's .kei/runs/: <label>.prompt.txt and <label>.out.txt, every try, never
    delivered. Returns what the history records of it: the files, the seconds and the prompt's size."""
    runs = Path(workdir) / ".kei" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    n = 1
    while (runs / f"{label}-{n}.prompt.txt").exists():
        n += 1
    base = runs / f"{label}-{n}"
    base.with_suffix(".prompt.txt").write_text(prompt, encoding="utf-8")
    base.with_suffix(".out.txt").write_text(result.output or "", encoding="utf-8")
    if getattr(result, "stderr", ""):
        base.with_suffix(".err.txt").write_text(result.stderr, encoding="utf-8")
    kept = {"run": f".kei/runs/{base.name}", "seconds": round(seconds, 1), "prompt_chars": len(prompt)}
    if getattr(result, "usage", None):
        kept["tokens"] = dict(result.usage)
    with open(runs / USAGE_LOG, "a", encoding="utf-8") as f:   # one line per run: kei status adds them up
        f.write(json.dumps({"label": label, **kept}) + "\n")
    return kept


USAGE_LOG = "usage.jsonl"


def run_totals(shot) -> dict:
    """Every seat run of the shot added up: runs, seconds, and tokens where the CLI reported them."""
    path = Path(shot) / ".kei" / "runs" / USAGE_LOG
    total = {"runs": 0, "seconds": 0.0, "tokens": {}}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return total
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        total["runs"] += 1
        total["seconds"] += float(r.get("seconds") or 0)
        for k, v in (r.get("tokens") or {}).items():
            total["tokens"][k] = total["tokens"].get(k, 0) + int(v)
    total["seconds"] = round(total["seconds"], 1)
    return total


WEB_TOOLS = ("WebSearch", "WebFetch")


def _is(spec: SeatSpec, name: str) -> bool:
    return bool(spec.cmd) and Path(spec.cmd[0]).stem.lower() == name


def with_web(spec: SeatSpec, web: str) -> SeatSpec:
    """The seat with web access on or off (kei.toml seats.web, asked once by kei init). On: a Claude Code seat's
    --allowedTools gains WebSearch and WebFetch, and a Codex seat gets --search (live search, before exec). Off: a
    Claude Code seat gets --disallowedTools for both, and a Codex seat loses --search. Another agent CLI is left as it
    is: its own flags decide."""
    cmd = list(spec.cmd)
    if _is(spec, "claude"):
        if "--allowedTools" in cmd and cmd.index("--allowedTools") + 1 < len(cmd):
            i = cmd.index("--allowedTools") + 1
            tools = [x for x in cmd[i].split(",") if x]
            tools = ([*tools, *(w for w in WEB_TOOLS if w not in tools)] if web == "on"
                     else [x for x in tools if x not in WEB_TOOLS])
            if tools:
                cmd[i] = ",".join(tools)
            else:
                del cmd[i - 1:i + 1]
        elif web == "on":
            cmd += ["--allowedTools", ",".join(WEB_TOOLS)]
        if web != "on" and "--disallowedTools" not in cmd:
            cmd += ["--disallowedTools", ",".join(WEB_TOOLS)]
    elif _is(spec, "codex"):
        cmd = [c for c in cmd if c != "--search"]
        if web == "on":
            cmd.insert(1, "--search")     # a top-level flag: codex exec refuses it after exec
    return replace(spec, cmd=cmd)


class CliSeat:
    def __init__(self, spec: SeatSpec):
        self.spec = spec
        self.name = spec.name

    def run(self, prompt: str, workdir: Path) -> SeatResult:
        exe = shutil.which(self.spec.cmd[0])   # also finds .cmd shims on Windows
        if exe is None:
            return SeatResult(127, f"command not found: {self.spec.cmd[0]}")
        try:
            proc = subprocess.Popen([exe, *self.spec.cmd[1:]], cwd=str(workdir), stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=seat_env())
        except OSError as e:
            return SeatResult(COULD_NOT_START, f"the seat could not start: {e}")
        try:
            out, err = proc.communicate(input=prompt.encode("utf-8"), timeout=self.spec.timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            return SeatResult(124, f"timeout after {self.spec.timeout_s} s")
        stdout = out.decode("utf-8", errors="replace")
        stderr = (err or b"").decode("utf-8", errors="replace")
        session = ""
        if is_codex_exec(self.spec) or (len(self.spec.cmd) > 2 and self.spec.cmd[2] == "resume"):
            text, usage, session = codex_events(stdout)
        else:
            text, usage = unwrap_json(stdout)
        if proc.returncode != 0 and stderr.strip():
            text = (text.rstrip() + "\n" + stderr).lstrip("\n")   # a failed run's error is part of what it said
        return SeatResult(proc.returncode, text, stderr, usage, session)


class FakeSeat:
    """A seat whose behaviour is a Python function, for tests."""

    def __init__(self, name: str, action: Callable[[str, Path], SeatResult]):
        self.name = name
        self.action = action

    def run(self, prompt: str, workdir: Path) -> SeatResult:
        return self.action(prompt, workdir)


_AT_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{1,2}):(\d{2})")
_IN = re.compile(r"\bin\s+(?:(\d+)\s*(?:h|hr|hrs|hours?))?\s*(?:(\d+)\s*(?:m|min|mins|minutes?))?\b", re.I)
_AT_CLOCK = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)


def reset_at(output: str, now=None):
    """When a usage limit resets, read from the CLI's message ("resets 2026-11-24 10:46", "try again in 2h 30m",
    "resets at 3pm"), as a local naive datetime; None when the message gives no time."""
    from datetime import datetime, timedelta
    now = now or datetime.now()
    text = output or ""
    m = _AT_DATE.search(text)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {int(m.group(2)):02d}:{m.group(3)}", "%Y-%m-%d %H:%M")
        except ValueError:
            pass
    for m in _IN.finditer(text):
        h, mins = m.group(1), m.group(2)
        if h or mins:
            return now + timedelta(hours=int(h or 0), minutes=int(mins or 0))
    m = _AT_CLOCK.search(text)
    if m:
        hour = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
        t = now.replace(hour=hour, minute=int(m.group(2) or 0), second=0, microsecond=0)
        return t if t > now else t + timedelta(days=1)
    return None
