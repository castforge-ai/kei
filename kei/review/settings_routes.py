"""The Settings tab: the same rows as kei settings and the same apply_change(), behind the review page's locks
(127.0.0.1, the token, the cookie, Host and Origin). A change to an agent command is shown in full, old and new,
and saved only after the user confirms it."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from kei import settings as st

TEST_SECONDS = 10
AUTO_OFF_PAGE = ("automatic sharing is switched on and pointed only with kei settings or in kei.toml, which say "
                 "where lessons will go and whether that repository is public: run kei settings set share.mode auto "
                 "(or kei settings set share.repo owner/name) in a terminal")


def _run_version(cmd: list[str], timeout: int) -> tuple[int, str]:
    exe = shutil.which(cmd[0])
    if exe is None:
        return 127, f"{cmd[0]} is not on PATH"
    try:
        r = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"{cmd[0]} did not answer within {timeout} seconds"
    except OSError as e:
        return 126, f"{cmd[0]} could not start: {e}"
    return r.returncode, (r.stdout or r.stderr).strip()[:500]


class SettingsRoutes:
    """target is the kei.toml a save writes (./kei.toml or --config); shown is the file read when target does not
    exist yet (kei.example.toml)."""

    def __init__(self, target: Path, shown: Path | None = None, which=None,
                 runner: Callable[[list[str], int], tuple[int, str]] = _run_version):
        self.target = Path(target)
        self.shown = Path(shown) if shown else st.EXAMPLE
        self.which = which
        self.runner = runner
        self.routes = {"GET /api/settings": self.get,
                       "POST /api/settings": self.save,
                       "POST /api/settings/test-seat": self.test_seat}

    def _file(self) -> Path:
        return self.target if self.target.is_file() else self.shown

    def get(self, req) -> tuple[int, dict]:
        return 200, {"rows": st.current(self._file()), "sha256": st.file_sha256(self.target),
                     "path": str(self.target), "exists": self.target.is_file()}

    def save(self, req) -> tuple[int, dict]:
        body = req["body"] if isinstance(req.get("body"), dict) else {}
        changes = body.get("changes")
        if not isinstance(changes, dict) or not changes:
            return 400, {"error": "changes must name at least one setting"}
        if body.get("sha256") != st.file_sha256(self.target):
            return 409, {"error": "kei.toml changed since you opened it: reload", "key": None}
        try:
            rows = {r["key"]: r for r in st.current(self._file())}
            mode = changes.get("share.mode", rows["share.mode"]["value"]) if "share.mode" in rows else None
            touched = [k for k in ("share.mode", "share.repo") if k in changes]
            if mode == "auto" and touched:      # never from a dialog (design Amendment 2)
                return 409, {"error": AUTO_OFF_PAGE, "key": touched[0]}
            commands = [k for k in changes if st.setting(k).kind == "command"]
            if commands and body.get("confirm_commands") is not True:
                return 200, {"saved": False, "confirm": [
                    {"key": k, "old": rows.get(k, {}).get("value"), "new": changes[k]} for k in commands]}
            notes: list[str] = []
            done = st.apply_change(self.target, changes, expect_sha256=body.get("sha256"), which=self.which,
                                   notes=notes)
        except st.SettingError as e:
            text = str(e)
            key = next((k for k in changes if k in text or k.rsplit(".", 1)[-1] in text), None)
            if key is None and len(changes) == 1:
                key = next(iter(changes))
            return 409, {"error": text, "key": key}
        return 200, {"saved": True, "changes": [list(c) for c in done], "notes": notes,
                     "sha256": st.file_sha256(self.target), "applies": "from the next kei run"}

    def test_seat(self, req) -> tuple[int, dict]:
        key = (req["body"] or {}).get("key") if isinstance(req.get("body"), dict) else None
        if not isinstance(key, str) or st.setting(key).kind != "command":
            return 400, {"error": "name a seat's command, such as animator.cmd"}
        row = next((r for r in st.current(self._file()) if r["key"] == key), None)
        if row is None or not row["value"]:
            return 409, {"error": f"{key} is not set"}
        if not isinstance(row["value"], list) or not all(isinstance(a, str) and a for a in row["value"]):
            return 409, {"error": f"{key} must be a list of words, such as [\"claude\", \"-p\"], not "
                                  f"{row['value']!r}: a shot would refuse it too"}
        code, out = self.runner([row["value"][0], "--version"], TEST_SECONDS)
        return 200, {"ok": code == 0, "code": code, "output": out}
