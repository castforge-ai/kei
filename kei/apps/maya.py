"""Kei's side of the Maya adapter: find Maya's own Python (mayapy) and run one job in it, in the background.

find_mayapy(config) -> (path, version)
  KEI_MAYAPY, then [apps.maya] mayapy in kei.toml, then the newest installed Maya (Windows, macOS, Linux places).
  The version is the install's year as its folder names it; a job's result gives the version Maya itself reports.
run_job(mayapy, job, timeout) -> dict
  One mayapy subprocess with one JSON job, no window and no server: maya_side/run_job.py opens the scene (if any),
  calls each named tool and saves the scene (if asked). Maya's preferences go to a folder of Kei's own
  (KEI_MAYA_APP_DIR, default <LOCALAPPDATA>/Kei/maya_app), never the user's Maya preferences.
A MayaError means the machine could not do the job: no mayapy, a licence that refuses batch, a timeout, a crash.
The conductor stops the shot with paused_machine on it; Kei never falls back to its own rig in silence.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAYA_SIDE = Path(__file__).resolve().parent / "maya_side"
RUNNER = MAYA_SIDE / "run_job.py"
REPO = Path(__file__).resolve().parents[2]


class MayaError(RuntimeError):
    """Maya could not run a job. The message says what to do, in plain words."""


def _installs() -> list[Path]:
    if sys.platform == "win32":
        root = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Autodesk"
        return [p / "bin" / "mayapy.exe" for p in root.glob("Maya[0-9]*")]
    if sys.platform == "darwin":
        return [p / "Maya.app" / "Contents" / "bin" / "mayapy" for p in Path("/Applications/Autodesk").glob("maya[0-9]*")]
    return [p / "bin" / "mayapy" for p in Path("/usr/autodesk").glob("maya[0-9]*")]


def _version(path: Path) -> str:
    m = re.search(r"maya(\d{4})", str(path), re.I)
    return m.group(1) if m else "unknown"


def find_mayapy(config: dict | None = None) -> tuple[Path, str]:
    """mayapy and its version: KEI_MAYAPY, then [apps.maya] mayapy, then the newest install found."""
    given = os.environ.get("KEI_MAYAPY") or ((config or {}).get("mayapy"))
    if given:
        p = Path(given)
        if not p.is_file():
            raise MayaError(f"mayapy not found at {p} (from {'KEI_MAYAPY' if os.environ.get('KEI_MAYAPY') else 'kei.toml [apps.maya] mayapy'})")
        return p, _version(p)
    found = sorted((p for p in _installs() if p.is_file()), key=lambda p: _version(p))
    if not found:
        raise MayaError("Maya was not found on this machine: install Maya, or set KEI_MAYAPY to its mayapy")
    return found[-1], _version(found[-1])


def app_dir() -> Path:
    """Maya's preferences folder for Kei's jobs: Kei's own, so the user's Maya preferences are never written."""
    given = os.environ.get("KEI_MAYA_APP_DIR")
    if given:
        return Path(given)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "state")
    return Path(base) / "Kei" / "maya_app"


# Every Maya process Kei starts runs with Autodesk's crash reporter, its usage programme and its in-product messages
# off, so a crash shows no dialog that could send a report and nothing leaves the machine.
NO_REPORTS = {"MAYA_DISABLE_CER": "1", "MAYA_DISABLE_CIP": "1", "MAYA_DISABLE_CLIC_IPM": "1"}


def maya_env(folder: Path) -> dict:
    """The environment of a Maya process Kei starts: Kei's own preferences folder, Kei's Maya side on the path, and
    no crash reporter, usage programme or in-product messages."""
    env = dict(os.environ, MAYA_APP_DIR=str(folder), PYTHONPATH=os.pathsep.join([str(MAYA_SIDE), str(REPO)]),
               **NO_REPORTS)
    env.pop("PYTHONHOME", None)
    return env


def run_job(mayapy: Path, job: dict, timeout: float = 600, script: Path | None = None) -> dict:
    """Run one job in mayapy and return its result. A failed or stuck job raises MayaError."""
    folder = app_dir()
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kei_maya_") as tmp:
        jpath, rpath = Path(tmp) / "job.json", Path(tmp) / "result.json"
        jpath.write_text(json.dumps(job), encoding="utf-8")
        env = maya_env(folder)
        cmd = [str(mayapy), str(script or RUNNER), str(jpath), str(rpath)]
        try:
            p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout,
                               encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired as e:
            raise MayaError(f"the Maya job did not finish in {timeout:.0f} s: Maya may be waiting on a licence or "
                            "sign-in window; open Maya once by hand, then run the shot again") from e
        except OSError as e:
            raise MayaError(f"cannot start mayapy at {mayapy}: {e}") from e
        if "Fatal Error" in (p.stdout or "") + (p.stderr or ""):
            raise MayaError("Maya crashed during the job (a Maya fatal error); nothing was sent anywhere: "
                            + " | ".join(((p.stdout or "") + (p.stderr or "")).strip().splitlines()[-4:]))
        if not rpath.is_file():
            tail = (p.stderr or p.stdout or "").strip().splitlines()[-6:]
            raise MayaError("the Maya job wrote no result (exit " + str(p.returncode) + "): " + " | ".join(tail))
        try:
            result = json.loads(rpath.read_text(encoding="utf-8"))
        except ValueError as e:
            raise MayaError(f"the Maya job wrote a result Kei cannot read: {e}") from e
    if not result.get("ok"):
        raise MayaError(f"Maya: {result.get('error', 'the job failed')}")
    return result
