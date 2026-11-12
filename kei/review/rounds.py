"""Review rounds: the latest pass of a shot rendered in the four post views, one PNG per frame, so the review page
plays an exact frame rate with no video decoder. A round lives in <shot>/review/r<n>/; the before round is the round
the author saw last, else the blocking pass."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from kei.characters import DEFAULT as DEFAULT_CHARACTER
from kei.characters import latest_pass as _latest_pass_file
from kei.characters import load_character, shot_character
from kei.render import POST_VIEWS, render_post
from kei.signoff import latest_round, round_ids
from kei.state import load_state, save_state

REVIEW_VIEWS = POST_VIEWS            # side, three quarter, front, back: two by two
BEFORE_BLOCKING = "blocking"         # the folder and id of the before round made from out_blocking


class ReviewError(ValueError):
    """A review round cannot be made. The message says why in plain words."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def latest_pass(shot: Path) -> str:
    """The pass the author reviews: out_p<highest n>, else out_blocking (the pass the next pass starts from)."""
    p = _latest_pass_file(Path(shot))
    if p is None:
        raise ReviewError(f"{shot} has no pass to review: no out_blocking/shot.json or out_p<n>/shot.json")
    return p.parent.name[len("out_"):]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_round(shot: Path, round_id: str) -> dict | None:
    p = Path(shot) / "review" / round_id / "round.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _character(shot: Path, data: dict, character: str | None) -> str:
    """character names the config's default: the pass's own "character", else PLAN.md's line, win over it."""
    default = character or os.environ.get("KEI_CHARACTER") or DEFAULT_CHARACTER
    return shot_character(shot, data, default)


def render_file(src: Path, folder: Path, round_id: str, size: int, character: str, mode: str,
                pass_name: str) -> dict:
    """Render one shot.json to folder/frames/ in the four post views and write folder/round.json last (a render cut
    short is never a round). Returns round.json."""
    src, folder = Path(src), Path(folder)
    data = json.loads(src.read_text(encoding="utf-8"))
    r = render_post(src, folder, mode, load_character(character), height=2 * size, video=False)
    meta = {"round": round_id, "pass": pass_name, "fps": data.get("fps") or 24, "frames": len(r["frames"]),
            "loop": bool(data.get("loop")), "made_at": _now(), "shot_sha256": _sha(src), "character": character,
            "mode": mode, "size": size, "views": list(REVIEW_VIEWS)}
    tmp = folder / "round.json.tmp"
    tmp.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    os.replace(tmp, folder / "round.json")
    return meta


def _render(shot: Path, pass_name: str, folder: Path, round_id: str, size: int, character: str | None) -> Path:
    src = shot / f"out_{pass_name}" / "shot.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    mode = "step" if pass_name == "blocking" else "spline"
    render_file(src, folder, round_id, size, _character(shot, data, character), mode, pass_name)
    return folder


def case_rounds(bundle: Path, out: Path, size: int = 360, prefix: str = "case") -> dict[str, dict]:
    """The two cases of a lesson bundle rendered on the reference character, reused while a case is unchanged.
    Returns {"fails": round.json, "passes": round.json}; each round's id is <prefix>-<case>."""
    rounds = {}
    for case in ("fails", "passes"):
        src = Path(bundle) / "cases" / case / "shot.json"
        folder = Path(out) / case
        meta = None
        try:
            meta = json.loads((folder / "round.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if not meta or meta.get("shot_sha256") != _sha(src) or meta.get("size") != size:
            meta = render_file(src, folder, f"{prefix}-{case}", size, "kei", "spline", case)
        rounds[case] = meta
    return rounds


def make_round(shot: Path, size: int = 360, character: str | None = None) -> Path:
    """Render the latest pass to review/r<n>/frames/f0000.png... (size pixels per view) and write round.json. The
    newest round is reused while the pass's shot.json has not changed. character is the default when neither the
    pass nor PLAN.md names one (as kei render finds it)."""
    shot = Path(shot)
    pass_name = latest_pass(shot)
    sha = _sha(shot / f"out_{pass_name}" / "shot.json")
    last = latest_round(shot)
    if last is not None:
        meta = read_round(shot, last)
        if meta and meta.get("pass") == pass_name and meta.get("shot_sha256") == sha:
            return shot / "review" / last
    n = int(last[1:]) + 1 if last else 1
    round_id = f"r{n}"
    return _render(shot, pass_name, shot / "review" / round_id, round_id, size, character)


def _seen(shot: Path) -> list[str]:
    try:
        history = load_state(shot).history
    except ValueError:
        return []
    return [h["round"] for h in history if h.get("result") == "seen" and h.get("round")]


def before_round(shot: Path, after: str, size: int = 360, character: str | None = None) -> dict | None:
    """The round the author saw last (other than after), else a round of out_blocking, else None."""
    shot = Path(shot)
    ids = set(round_ids(shot))
    for round_id in reversed(_seen(shot)):
        if round_id != after and round_id in ids:
            return read_round(shot, round_id)
    after_meta = read_round(shot, after) or {}
    blocking = shot / "out_blocking" / "shot.json"
    if after_meta.get("pass") == "blocking" or not blocking.is_file():
        return None
    meta = read_round(shot, BEFORE_BLOCKING)
    if meta and meta.get("shot_sha256") == _sha(blocking):
        return meta
    _render(shot, "blocking", shot / "review" / BEFORE_BLOCKING, BEFORE_BLOCKING,
            int(after_meta.get("size") or size), character)
    return read_round(shot, BEFORE_BLOCKING)


def mark_seen(shot: Path, round_id: str, loops: int | None = None) -> None:
    """Record that the author played this round on the page: the next round shows it as before."""
    shot = Path(shot)
    if round_id not in round_ids(shot):
        raise ReviewError(f"there is no review round {round_id} in this shot")
    state = load_state(shot)
    entry = {"stage": state.stage, "attempt": 0, "result": "seen", "round": round_id, "misses": [], "at": _now()}
    if loops is not None:
        entry["loops"] = int(loops)
    state.history.append(entry)
    save_state(shot, state)
