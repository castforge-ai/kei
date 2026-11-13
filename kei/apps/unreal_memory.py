"""How much memory the Unreal Editor holds after each step of a shot, so a climb shows up in numbers.

editor_memory(url) -> {"pid", "private_gb", "working_set_gb"} for the process listening on the Claireon port of url
  (Windows only; None when it cannot be read). record(shot_dir, url, label) adds one row to unreal/memory.json:
  {"at", "label", "pid", "private_gb", "working_set_gb"}. A shot that climbs by about the same amount at every pass
  keeps its sequences; one that jumps at a bake keeps the baked animations. Reading it never stops a shot.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FILE = "memory.json"
_SCRIPT = ("$c = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction Stop | Select-Object -First 1; "
           "$p = Get-Process -Id $c.OwningProcess -ErrorAction Stop; "
           "'{{0}} {{1}} {{2}}' -f $p.Id, $p.PrivateMemorySize64, $p.WorkingSet64")


def editor_memory(url: str) -> dict | None:
    m = re.search(r":(\d+)(?:/|$)", url or "")
    if not m or sys.platform != "win32":
        return None
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", _SCRIPT.format(port=int(m.group(1)))],
                             capture_output=True, text=True, timeout=15)
        pid, private, working = out.stdout.split()[:3]
        return {"pid": int(pid), "private_gb": round(int(private) / 2**30, 2),
                "working_set_gb": round(int(working) / 2**30, 2)}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def record(shot_dir: Path, url: str, label: str, reader=editor_memory) -> dict | None:
    """Add a row for this moment; returns it, or None when the memory could not be read."""
    got = reader(url)
    if got is None:
        return None
    path = Path(shot_dir) / "unreal" / FILE
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "label": label, **got}
    rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return row
