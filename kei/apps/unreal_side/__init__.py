"""Kei's editor scripts: the only code Kei ever sends to the Unreal Editor, through Claireon's python_execute.

Each file here runs inside Unreal's own Python (Python Editor Script Plugin) and uses the `unreal` module only. Kei
sends a file's text with one JSON input line in front of it (KEI_INPUT) and the helpers of kei_ue.py, after it has
checked the file's SHA-256 against hashes.UNREAL_SIDE_HASHES. tools/update_unreal_hashes.py writes that table. The
hash is taken over the text with LF line ends, so a Windows checkout and a Linux checkout agree.

These files are not imported by Kei: they import `unreal`, which only the editor has.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
NOT_SCRIPTS = ("__init__.py", "hashes.py")


def file_hash(path: Path) -> str:
    """SHA-256 of a script's text, with LF line ends."""
    text = Path(path).read_bytes().decode("utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def script_files() -> list[Path]:
    return sorted(p for p in FOLDER.glob("*.py") if p.name not in NOT_SCRIPTS)
