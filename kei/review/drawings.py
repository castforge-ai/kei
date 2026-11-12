"""The author's drawings on a review round: the strokes as vectors and one flattened PNG per drawn frame and view,
kept in the shot under review/<round>/drawings/. The next stage prompt lists them as files to look at."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from kei.review.rounds import REVIEW_VIEWS, read_round

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PNG = 4 * 1024 * 1024
_KEY = re.compile(r"f(\d{4})_([a-z_]+)")


class DrawingError(ValueError):
    """A drawing the page sent cannot be kept. The message says which and why."""


def view_slug(view: str) -> str:
    return view.replace(" ", "_")


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_stroke(s, frames: int) -> tuple[int, str]:
    if not isinstance(s, dict):
        raise DrawingError("a stroke must be an object with frame, view, points, color and width")
    f = s.get("frame")
    if not isinstance(f, int) or isinstance(f, bool) or not 0 <= f < frames:
        raise DrawingError(f"a stroke is on frame {f}, outside the round's frames 0 to {frames - 1}")
    view = s.get("view")
    if view not in REVIEW_VIEWS:
        raise DrawingError(f"a stroke is on an unknown view {view!r}: use one of {', '.join(REVIEW_VIEWS)}")
    pts = s.get("points")
    if not isinstance(pts, list) or not pts or not all(
            isinstance(p, list) and len(p) == 2 and all(_num(c) for c in p) for p in pts):
        raise DrawingError("a stroke's points must be a list of [x, y] pairs")
    if not isinstance(s.get("color", ""), str) or not _num(s.get("width", 1)):
        raise DrawingError("a stroke's color must be text and its width a number")
    return f, view


def write_drawings(out: Path, rel: str, round_id: str, frames: int, strokes: list[dict],
                   pngs: dict[str, bytes]) -> list[str]:
    """Check every stroke and PNG against a round of frames, then write a new numbered set out/<n>/strokes.json and
    f<frame>_<view>.png. Returns the written paths as rel/<n>/<name>, the PNGs first. Nothing is written when
    anything is refused, and an earlier set is never touched."""
    if not isinstance(strokes, list):
        raise DrawingError("strokes must be a list")
    drawn = {(f"f{f:04d}_{view_slug(v)}") for f, v in (_check_stroke(s, frames) for s in strokes)}
    for key, data in pngs.items():
        m = _KEY.fullmatch(key)
        if m is None or key not in drawn:
            raise DrawingError(f"the picture {key!r} names no drawn frame and view")
        if not isinstance(data, bytes) or not data.startswith(PNG_SIGNATURE):
            raise DrawingError(f"the picture {key} is not a PNG")
        if len(data) > MAX_PNG:
            raise DrawingError(f"the picture {key} is over 4 MB")
    base = Path(out)
    taken = [int(d.name) for d in base.iterdir() if d.is_dir() and d.name.isdigit()] if base.is_dir() else []
    n = max(taken, default=0) + 1           # each note keeps its own set; an earlier set is never deleted
    out, rel = base / str(n), f"{rel}/{n}"
    out.mkdir(parents=True)
    written = []
    for key in sorted(pngs):
        (out / f"{key}.png").write_bytes(pngs[key])
        written.append(f"{rel}/{key}.png")
    tmp = out / "strokes.json.tmp"
    tmp.write_text(json.dumps({"round": round_id, "strokes": strokes}, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out / "strokes.json")
    written.append(f"{rel}/strokes.json")
    return written


def save_drawings(shot: Path, round_id: str, strokes: list[dict], pngs: dict[str, bytes]) -> list[str]:
    """The author's drawings on a review round of the shot, under review/<round>/drawings/. Returns the paths
    relative to the shot."""
    shot = Path(shot)
    meta = read_round(shot, round_id) if re.fullmatch(r"r\d+", round_id or "") else None
    if meta is None:
        raise DrawingError(f"there is no review round {round_id} in this shot")
    rel = f"review/{round_id}/drawings"
    return write_drawings(shot / rel, rel, round_id, int(meta["frames"]), strokes, pngs)
