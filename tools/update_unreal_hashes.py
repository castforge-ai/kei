"""Write kei/apps/unreal_side/hashes.py: the SHA-256 of each of Kei's editor scripts.

Run it after any change to a file in kei/apps/unreal_side/ (python tools/update_unreal_hashes.py). Kei refuses to send
a script whose hash is not in the table, and tests/test_unreal_side_hashes.py fails when the table is out of date.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kei.apps.unreal_side import FOLDER, file_hash, script_files   # noqa: E402


def table_text() -> str:
    lines = ['"""SHA-256 of each editor script Kei may send to Unreal (LF line ends). Written by',
             'tools/update_unreal_hashes.py: do not edit by hand."""', "", "UNREAL_SIDE_HASHES = {"]
    lines += [f'    "{p.name}": "{file_hash(p)}",' for p in script_files()]
    lines += ["}", ""]
    return "\n".join(lines)


def main() -> int:
    out = FOLDER / "hashes.py"
    out.write_text(table_text(), encoding="utf-8", newline="\n")
    print(f"{len(script_files())} scripts hashed into {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
