"""Seats: any agent CLI that reads a prompt on stdin and works in the shot folder."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from kei.config import SeatSpec


@dataclass(frozen=True)
class SeatResult:
    exit_code: int
    output: str


# A seat that stops for one of these reasons did no craft work: the stage pauses and the try is not counted.
USAGE = re.compile(r"hit your [^\n]{0,40}limit|usage limit|rate[ _-]?limit|\b429\b|too many requests|quota exceeded",
                   re.I)
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


def seat_env() -> dict[str, str]:
    """The seat's environment: Kei's own scripts folder (where the kei command and Kei's python live) first on PATH,
    so a seat that runs `kei render` or `python` gets this Kei, even from a shell that never activated it."""
    env = dict(os.environ)
    first = []
    for d in (sysconfig.get_path("scripts"), os.path.dirname(sys.executable)):
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
    return SeatSpec(name=spec.name, cmd=[spec.cmd[0], *extra, *spec.cmd[1:]], timeout_s=spec.timeout_s)


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
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=seat_env())
        except OSError as e:
            return SeatResult(COULD_NOT_START, f"the seat could not start: {e}")
        try:
            out, _ = proc.communicate(input=prompt.encode("utf-8"), timeout=self.spec.timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            return SeatResult(124, f"timeout after {self.spec.timeout_s} s")
        return SeatResult(proc.returncode, out.decode("utf-8", errors="replace"))


class FakeSeat:
    """A seat whose behaviour is a Python function, for tests."""

    def __init__(self, name: str, action: Callable[[str, Path], SeatResult]):
        self.name = name
        self.action = action

    def run(self, prompt: str, workdir: Path) -> SeatResult:
        return self.action(prompt, workdir)
