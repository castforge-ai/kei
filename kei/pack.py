"""Share a review outside this machine: kei pack writes one file anyone can open, and kei note --from-file brings a
reviewer's notes back.

pack(shot, out, max_mb, videos) -> {"path", "pack", "files", "skipped", "bytes"}
  The live page saved as one HTML file with every image and video it shows inside it (as data URIs), so it needs
  neither the shot folder nor a server nor the network. Only the files the page shows go in, never the rendered
  frame folders. A file that would take the pack over max_mb stays out and is listed. The page carries a notes panel:
  the reviewer writes notes (with frames if they know them) and saves <shot>_notes.json, which they send back.
  Each pack has an id, recorded in <shot>/.kei/packs.json, and the notes file carries it.
read_notes(shot, path) -> {"reviewer", "pack", "notes": [text, ...], "sha"}
  Checks a notes file before anything is written: its format, that it names this shot and a pack made from this
  shot, that it was not brought in before, and the size of each note. Each note becomes the reviewer's words, with
  the frames in front ("f13-18: ..."). A PackError says what is wrong.
mark_imported(shot, got) records the file's hash, so the same file is never brought in twice.
The notes go in as notes for this shot only, never as a rule for every shot: the author decides that later.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from kei.live.report import PAGE, _esc, page_html
from kei.live.snapshot import VIDEOS, files, snapshot

PACKS = ".kei/packs.json"
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".mp4": "video/mp4"}
MAX_NOTES = 200
MAX_NOTE_CHARS = 4000
MAX_FILE = 2 * 1024 * 1024
FRAMES = re.compile(r"^\d{1,5}(\s*-\s*\d{1,5})?(\s*,\s*\d{1,5}(\s*-\s*\d{1,5})?)*$")


class PackError(ValueError):
    """A pack could not be written, or a notes file cannot be brought in. The message says why and what to do."""


def _record(shot: Path) -> dict:
    try:
        data = json.loads((shot / PACKS).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_record(shot: Path, data: dict) -> None:
    p = shot / PACKS
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1), encoding="utf-8")


def _shown(snap: dict, found: dict) -> list[str]:
    """The file ids the page refers to: the snapshot names each file it shows by its id."""
    text = json.dumps(snap)
    return [i for i in found if i in text]


def pack(shot: Path, out: Path | None = None, max_mb: float = 200, videos: bool = True) -> dict:
    shot = Path(shot)
    if not (shot / ".kei" / "state.json").is_file():
        raise PackError(f"{shot} is not a Kei shot (no .kei/state.json)")
    snap = snapshot(shot)
    found = files(shot)
    budget = int(max_mb * 1024 * 1024)
    paths, skipped, used = {}, [], 0
    order = sorted(_shown(snap, found), key=lambda i: (found[i].suffix.lower() in VIDEOS, found[i].stat().st_size))
    for i in order:
        p = found[i]
        rel = p.relative_to(shot).as_posix()
        if p.suffix.lower() in VIDEOS and not videos:
            skipped.append((rel, "videos left out (--no-video)"))
            continue
        size = p.stat().st_size * 4 // 3 + 64
        if used + size > budget:
            skipped.append((rel, f"over the {max_mb:g} MB limit"))
            continue
        paths[i] = f"data:{MIME[p.suffix.lower()]};base64," + base64.b64encode(p.read_bytes()).decode("ascii")
        used += size
    pack_id = secrets.token_hex(8)
    meta = {"shot": shot.name, "pack": pack_id}
    notes = (PAGE / "pack_notes.html").read_text(encoding="utf-8").replace("SHOT", _esc(shot.name))
    extra = ("<script>window.KEI_PACK = " + json.dumps(meta).replace("</", "<" + chr(92) + "/") + ";</script>\n"
             + notes)
    html = page_html(shot, snap, paths, extra)
    dest = Path(out) if out else shot / f"{shot.name}_pack.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")
    rec = _record(shot)
    rec.setdefault("packs", []).append({"pack": pack_id, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                        "path": str(dest), "files": len(paths), "skipped": len(skipped)})
    _save_record(shot, rec)
    return {"path": dest, "pack": pack_id, "files": len(paths), "skipped": skipped, "bytes": dest.stat().st_size}


def read_notes(shot: Path, path: Path) -> dict:
    shot, path = Path(shot), Path(path)
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise PackError(f"cannot read {path}: {e.strerror or e}") from e
    if len(raw) > MAX_FILE:
        raise PackError(f"{path.name} is over 2 MB: a notes file from kei pack is far smaller")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise PackError(f"{path.name} is not a notes file from kei pack (not JSON)") from e
    if not isinstance(data, dict) or data.get("kei_notes") != 1:
        raise PackError(f"{path.name} is not a notes file from kei pack (no kei_notes: 1)")
    if data.get("shot") != shot.name:
        raise PackError(f"{path.name} is for the shot {str(data.get('shot'))[:80]!r}, not {shot.name!r}")
    rec = _record(shot)
    if data.get("pack") not in {p.get("pack") for p in rec.get("packs", [])}:
        raise PackError(f"{path.name} names a pack this shot never made: pack the shot with kei pack and send that file")
    sha = hashlib.sha256(raw).hexdigest()
    if sha in rec.get("imported", []):
        raise PackError(f"{path.name} was already brought in")
    reviewer = data.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 80:
        raise PackError(f"{path.name} has no reviewer name")
    notes = data.get("notes")
    if not isinstance(notes, list) or not notes:
        raise PackError(f"{path.name} holds no notes")
    if len(notes) > MAX_NOTES:
        raise PackError(f"{path.name} holds {len(notes)} notes: at most {MAX_NOTES}")
    texts = []
    for n, note in enumerate(notes, 1):
        if not isinstance(note, dict) or not isinstance(note.get("text"), str) or not note["text"].strip():
            raise PackError(f"note {n} in {path.name} has no words")
        text = note["text"].strip()
        if len(text) > MAX_NOTE_CHARS:
            raise PackError(f"note {n} in {path.name} is over {MAX_NOTE_CHARS} characters")
        frames = note.get("frames") or ""
        if not isinstance(frames, str) or (frames.strip() and not FRAMES.match(frames.strip())):
            raise PackError(f"note {n} in {path.name} has frames Kei cannot read: {str(frames)[:40]!r} (use 13-18)")
        frames = re.sub(r"\s+", "", frames)
        texts.append(f"f{frames}: {text}" if frames else text)
    return {"reviewer": reviewer.strip(), "pack": data["pack"], "notes": texts, "sha": sha}


def mark_imported(shot: Path, got: dict) -> None:
    shot = Path(shot)
    rec = _record(shot)
    rec.setdefault("imported", []).append(got["sha"])
    _save_record(shot, rec)
