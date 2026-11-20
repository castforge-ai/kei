"""kei doctor: check the setup before a run, and say how to fix each problem.

Each line is ok, warn (Kei runs, with less) or fail (a run will not start or will stop). Checked: Python, the config,
the rule book, each seat's program and its version, the web setting, ffmpeg and ffprobe (videos; without them Kei writes
GIFs), gh (sharing lessons), and mayapy when the config's app is Maya. A seat's login cannot be checked without
spending a call: the first run shows it.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

OK, WARN, FAIL = "ok", "warn", "fail"


def _version(cmd: str) -> str | None:
    exe = shutil.which(cmd)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (out.stdout or out.stderr or "").strip().splitlines()[0] if (out.stdout or out.stderr) else ""


def checks(config_path: Path) -> list[tuple[str, str, str, str]]:
    """(status, what, found, fix) per check."""
    from kei.config import ConfigError, load_config
    rows = []
    py = sys.version_info
    rows.append((OK if py >= (3, 12) else FAIL, "Python", f"{py.major}.{py.minor}.{py.micro}",
                 "" if py >= (3, 12) else "install Python 3.12 or newer"))
    try:
        config = load_config(config_path)
        rows.append((OK, "config", str(config_path), ""))
    except ConfigError as e:
        rows.append((FAIL, "config", str(e), "fix kei.toml, or run kei init for a fresh one"))
        return rows
    try:
        from kei.book import load_topics
        n = sum(len(t.rules) for t in load_topics(config.book))
        rows.append((OK, "rule book", f"{n} rules in {config.book}", ""))
    except Exception as e:   # noqa: BLE001 - any failure to read the book is the finding
        rows.append((FAIL, "rule book", str(e), "point book.path in kei.toml at a folder of topic files"))
    for role, seat in [("animator", config.animator)] + [(f"critic {c.name}", c) for c in config.critics]:
        prog = seat.cmd[0] if seat.cmd else ""
        v = _version(prog) if prog else None
        if v is None:
            rows.append((FAIL, f"{role} seat", f"{prog or '(no command)'} is not on the PATH",
                         f"install {prog}, or change the seat with kei settings"))
        else:
            rows.append((OK, f"{role} seat", f"{prog} {v}".strip(), ""))
    rows.append((OK, "web access", config.web, "" if config.web_asked else "kei init asks once"))
    for prog, why in (("ffmpeg", "videos (without it Kei writes GIFs)"), ("ffprobe", "video checks")):
        rows.append((OK, prog, _version(prog) or "", "") if shutil.which(prog) else
                    (WARN, prog, "not found", f"install ffmpeg for {why}"))
    rows.append((OK, "gh", _version("gh") or "", "") if shutil.which("gh") else
                (WARN, "gh", "not found", "install the GitHub CLI to share lessons (kei share)"))
    if getattr(config, "app", "kei") == "maya":
        try:
            from kei.apps.maya import find_mayapy
            path, how = find_mayapy()
            rows.append((OK, "mayapy", f"{path} ({how})", ""))
        except Exception as e:   # noqa: BLE001
            rows.append((FAIL, "mayapy", str(e), "install Maya, or set apps.maya.mayapy in kei.toml"))
    if getattr(config, "app", "kei") == "blender":
        try:
            from kei.apps.blender import find_blender
            path, how = find_blender(getattr(config, "blender", None))
            rows.append((OK, "blender", f"{path} ({how})", ""))
        except Exception as e:   # noqa: BLE001
            rows.append((FAIL, "blender", str(e), "install Blender, or set apps.blender.path in kei.toml"))
    return rows


def report(rows) -> tuple[str, int]:
    lines = []
    for status, what, found, fix in rows:
        lines.append(f"{status:4}  {what}: {found}" + (f"  -> {fix}" if fix else ""))
    fails = sum(1 for r in rows if r[0] == FAIL)
    warns = sum(1 for r in rows if r[0] == WARN)
    lines.append(f"{fails} to fix, {warns} warning(s)" if fails or warns else "everything Kei needs is here")
    return "\n".join(lines), fails
