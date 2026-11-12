"""Helpers for the tests that need Maya: run a check script in mayapy (no window, Kei's own Maya preferences folder)
and read back its JSON. Without Maya the test is skipped and says why."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from kei.apps.maya import MayaError, find_mayapy, run_job

SCRIPTS = Path(__file__).resolve().parent / "maya"
REPO = Path(__file__).resolve().parents[1]
_CACHE: dict = {}


def mayapy() -> Path:
    try:
        return find_mayapy()[0]
    except MayaError as e:
        pytest.skip(f"needs Maya: {e}")


def run_script(name: str, **args) -> dict:
    """Run tests/maya/<name> in mayapy with args as its job; the script's result dict comes back. Cached per run."""
    key = (name, tuple(sorted(args.items())))
    if key not in _CACHE:
        py = mayapy()
        os.environ.setdefault("KEI_MAYA_APP_DIR", str(Path(tempfile.gettempdir()) / "kei_test_maya_app"))
        _CACHE[key] = run_job(py, {"args": args}, timeout=900, script=SCRIPTS / name)["data"]
    return _CACHE[key]
