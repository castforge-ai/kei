"""A signature on each chat note, so a note a seat writes into the shot's state file is not taken for the author's.

While kei run works on a shot, it merges the chat notes another process (kei note --from chat) wrote to
.kei/state.json. A seat works in the shot folder and can write that file too. kei note signs each chat note with a key
kept outside the shot (in KEI_HOME, default ~/.kei), and kei run merges only notes whose signature holds.

The limit, stated plainly: a seat allowed to run any command can read the key as the user can. The signature stops a
seat that edits the state file, not one set on forging it; the seats' tool limits are the other half of that line.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

FIELDS = ("stage", "lesson", "misses", "at", "scope", "from")


def key_path() -> Path:
    home = os.environ.get("KEI_HOME")
    return (Path(home) if home else Path.home() / ".kei") / "note.key"


def _key() -> bytes:
    path = key_path()
    try:
        return bytes.fromhex(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secrets.token_hex(32), encoding="utf-8")
    return bytes.fromhex(path.read_text(encoding="utf-8").strip())


def _body(entry: dict) -> bytes:
    return json.dumps({k: entry.get(k) for k in FIELDS}, sort_keys=True, ensure_ascii=False).encode("utf-8")


def sign(entry: dict) -> str:
    return hmac.new(_key(), _body(entry), hashlib.sha256).hexdigest()


def signed(entry: dict) -> bool:
    sig = entry.get("sig")
    return isinstance(sig, str) and hmac.compare_digest(sig, sign(entry))
