"""Process facts with the standard library only, for the Kei host and Kei's session finder: when a process started,
and the Maya processes running. Windows reads them through ctypes; other systems through /proc or ps."""
from __future__ import annotations

import csv
import io
import os
import subprocess
import sys

STILL_ACTIVE = 259
MAYA_NAMES = ("maya.exe", "maya", "maya.bin")


def start_time(pid: int) -> float | None:
    """The process's start time (seconds since 1970), or None when it is not running (or not ours to read). On
    Windows an exited process still answers while a handle to it is open, so its exit code must say STILL_ACTIVE."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        h = k.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            code = wintypes.DWORD()
            if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != STILL_ACTIVE:
                return None
            c, e, kt, u = (wintypes.FILETIME() for _ in range(4))
            if not k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(u)):
                return None
            return ((c.dwHighDateTime << 32) | c.dwLowDateTime) / 1e7 - 11644473600.0
        finally:
            k.CloseHandle(h)
    stat = f"/proc/{int(pid)}/stat"
    if os.path.exists(stat):
        try:
            with open(stat) as f:
                ticks = int(f.read().rsplit(")", 1)[1].split()[19])
            with open("/proc/stat") as f:
                boot = next(int(line.split()[1]) for line in f if line.startswith("btime"))
            return boot + ticks / os.sysconf("SC_CLK_TCK")
        except (OSError, ValueError, StopIteration):
            return None
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(int(pid))], capture_output=True, text=True).stdout
    except OSError:
        return None
    if not out.strip():
        return None
    import time
    try:
        return time.mktime(time.strptime(out.strip(), "%a %b %d %H:%M:%S %Y"))
    except ValueError:
        return None


def maya_pids() -> list[int]:
    """The Maya windows running (maya.exe on Windows, Maya or maya.bin elsewhere); batch mayapy is not one."""
    if sys.platform == "win32":
        try:
            out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True).stdout
        except OSError:
            return []
        return [int(r[1]) for r in csv.reader(io.StringIO(out)) if r and r[0].lower() in MAYA_NAMES]
    try:
        out = subprocess.run(["ps", "-axo", "pid=,comm="], capture_output=True, text=True).stdout
    except OSError:
        return []
    pids = []
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and os.path.basename(parts[1]).lower() in ("maya", "maya.bin"):
            pids.append(int(parts[0]))
    return pids
