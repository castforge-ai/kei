"""One kei run per shot at a time: .kei/run.lock holds the running process's id while it works on the shot.

A lock left behind by a process that is gone (a crash, a closed terminal) is taken over, so a stale lock never blocks
the shot. A lock held by a live process stops the second run before it touches anything.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from pathlib import Path

from kei.state import StateError

LOCK = Path(".kei") / "run.lock"


class RunLockedError(StateError):
    """Another kei run works on this shot now."""


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        h = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5     # access denied: it exists, owned by someone else
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return True
            return code.value == 259                # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)                             # signal 0: a check only, never sent (POSIX)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _holder(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@contextlib.contextmanager
def run_lock(shot_dir: Path):
    """Hold the shot's run lock while the block runs. Raises RunLockedError when a live process holds it."""
    path = Path(shot_dir) / LOCK
    path.parent.mkdir(parents=True, exist_ok=True)
    mine = json.dumps({"pid": os.getpid(), "since": time.strftime("%Y-%m-%dT%H:%M:%S")})
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            held = _holder(path)
            pid = int(held.get("pid") or 0)
            if pid == os.getpid():
                yield                                # the same process again (a nested run): already held
                return
            if _alive(pid):
                raise RunLockedError(f"another kei run (process {pid}, since {held.get('since', '?')}) is working "
                                     f"on {shot_dir}: wait for it, or stop it; a lock left by a closed run is "
                                     f"taken over by itself") from None
            with contextlib.suppress(OSError):
                path.unlink()                        # left by a process that is gone
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(mine)
        break
    else:
        raise RunLockedError(f"cannot take the run lock {path}: another run took it at the same moment")
    try:
        yield
    finally:
        if _holder(path).get("pid") == os.getpid():
            with contextlib.suppress(OSError):
                path.unlink()
