"""Blender, in the background: find it and run one of Kei's jobs in it (kei.apps.blender_side.kei_blender).

find_blender(given) -> (path, how found): KEI_BLENDER, else kei.toml [apps.blender] path, else the newest install in
the usual folder (Windows: Program Files/Blender Foundation/Blender <version>; macOS: /Applications/Blender.app;
Linux: blender on the PATH).
run_job(blender, job) runs `blender -b --factory-startup --python kei_blender.py -- job.json result.json` and returns
the result, or raises BlenderError with Blender's own message. --factory-startup keeps the user's add-ons and
preferences out of Kei's jobs, and Kei's jobs out of them.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SIDE = Path(__file__).resolve().parent / "blender_side" / "kei_blender.py"
TESTED = ("5.2",)        # Blender versions Kei's jobs were run in


class BlenderError(RuntimeError):
    pass


def _installs() -> list[Path]:
    if sys.platform == "win32":
        root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
        return [p / "blender.exe" for p in root.glob("Blender*")]
    if sys.platform == "darwin":
        return [Path("/Applications/Blender.app/Contents/MacOS/Blender")]
    found = shutil.which("blender")
    return [Path(found)] if found else []


def _version_key(path: Path) -> tuple:
    m = re.search(r"(\d+)\.(\d+)", str(path))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def find_blender(given: str | None = None) -> tuple[Path, str]:
    """Blender's executable and how Kei found it. Raises BlenderError naming where to set it."""
    env = os.environ.get("KEI_BLENDER")
    if env or given:
        p = Path(env or given)
        if not p.is_file():
            raise BlenderError(f"Blender not found at {p} (from {'KEI_BLENDER' if env else 'kei.toml [apps.blender] path'})")
        return p, "KEI_BLENDER" if env else "kei.toml"
    found = sorted((p for p in _installs() if p.is_file()), key=_version_key)
    if not found:
        raise BlenderError("Blender is not installed where Kei looks: install Blender 4.2 or later, or set "
                           "KEI_BLENDER (or kei.toml [apps.blender] path) to its executable")
    return found[-1], "installed"


def run_job(blender: Path, job: dict, timeout: float = 900) -> dict:
    """Run one job in a background Blender and return its result (ok is true). Raises BlenderError."""
    with tempfile.TemporaryDirectory(prefix="kei-blender-") as tmp:
        job_path, result_path = Path(tmp) / "job.json", Path(tmp) / "result.json"
        job_path.write_text(json.dumps(job), encoding="utf-8")
        cmd = [str(blender), "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(SIDE), "--",
               str(job_path), str(result_path)]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
        except subprocess.TimeoutExpired:
            raise BlenderError(f"Blender's {job.get('tool')} job ran past {timeout:.0f} s") from None
        if not result_path.is_file():
            tail = (r.stderr or r.stdout or "").strip()[-1500:]
            raise BlenderError(f"Blender's {job.get('tool')} job wrote no result (exit {r.returncode}): {tail}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
    if not result.get("ok"):
        raise BlenderError(f"Blender's {job.get('tool')} job failed: {result.get('error')}\n{result.get('trace', '')}")
    return result
