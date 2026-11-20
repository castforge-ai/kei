"""kei trails: the paths of chosen parts, with a dot per frame, for one pass or several passes overlaid.

  kei trails <shot> p6 --parts hand_l_tip,head                 one pass
  kei trails <shot> p5 p6 --parts hand_l_tip --frames 140-160   two passes overlaid, each in its colour

Writes out_<last pass>/trails/trails.png: a side panel and a front panel. Each part's path is a line with a dot on
every frame, so the gaps between the dots are the spacing chart (wide gaps fast, close ones slow), and the keyed frames
are larger dots. The trails replace the review sheets and A-over-B strips the agents drew themselves.
"""
from __future__ import annotations

from pathlib import Path

from kei.render import _view
from kei.sample import bake, check_shot, normalize_keys, read_json
from kei.sheet import _Canvas

PANEL = 520
PAD = 30
COLOURS = [(200, 60, 40), (40, 110, 200), (40, 150, 70), (170, 80, 170), (200, 140, 20), (20, 150, 160)]
VIEWS = ("side", "front")


class TrailsError(ValueError):
    pass


def _frames_range(text: str | None, last: int) -> tuple[int, int]:
    if not text:
        return 0, last
    a, _, b = str(text).partition("-")
    try:
        lo, hi = int(a), int(b or a)
    except ValueError:
        raise TrailsError(f"--frames: a range like 140-160, not {text!r}") from None
    return max(0, min(lo, hi)), min(last, max(lo, hi))


def draw_trails(shot_dir: Path, passes: list[str], parts: list[str], frames: str | None = None,
                character: str | None = None) -> Path:
    from kei.characters import load_character, on_character, shot_character
    if not passes:
        raise TrailsError("name a pass")
    data = []
    for name in passes:
        src = Path(shot_dir) / f"out_{name}" / "shot.json"
        if not src.is_file():
            raise TrailsError(f"no {src}")
        shot = read_json(src, "shot")
        check_shot(shot)
        ch = load_character(shot_character(shot_dir, shot, character or "kei"))
        shot = on_character(shot, ch)
        baked = bake(shot, "step" if name == "blocking" else "spline")
        keys = {int(k["f"]) for k in normalize_keys(shot) if float(k["f"]).is_integer()}
        data.append((name, baked, keys))
    lo, hi = _frames_range(frames, min(len(d[1]) for d in data) - 1)
    joints = data[0][1][0]["joints"]
    for p in parts:
        if p not in joints:
            raise TrailsError(f"no part {p!r}; for example hand_l_tip, hand_r_tip, head, pelvis, ball_l_tip")
    cv = _Canvas(PANEL * len(VIEWS), PANEL + 40)
    for vi, view in enumerate(VIEWS):
        pts = [_view(view, fr["joints"][p]) for _, baked, _ in data for fr in baked[lo:hi + 1] for p in parts]
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        span = max(max(xs) - min(xs), max(ys) - min(ys), 0.05)
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        scale = (PANEL - 2 * PAD) / span

        def px(q, ox=vi * PANEL):
            return round(ox + PANEL / 2 + (q[0] - cx) * scale), round(PANEL / 2 - (q[1] - cy) * scale)
        cv.box(vi * PANEL, 0, vi * PANEL + PANEL - 1, PANEL - 1, (200, 200, 200))
        cv.text(vi * PANEL + 6, 6, f"{view} f{lo}-{hi}", (20, 20, 20), PANEL - 12)
        for pi, (name, baked, keys) in enumerate(data):
            col = COLOURS[pi % len(COLOURS)]
            for part in parts:
                path = [(fr["f"], px(_view(view, fr["joints"][part]))) for fr in baked[lo:hi + 1]]
                for (_, a), (_, b) in zip(path, path[1:]):
                    cv.line(a[0], a[1], b[0], b[1], col, False)
                for f, a in path:
                    cv.disk(a[0], a[1], 4 if f in keys else 2, col)
    for pi, (name, _, _) in enumerate(data):
        col = COLOURS[pi % len(COLOURS)]
        cv.disk(14 + pi * 150, PANEL + 20, 5, col)
        cv.text(24 + pi * 150, PANEL + 14, f"{name}: {', '.join(parts)}", col, 120)
    out = Path(shot_dir) / f"out_{passes[-1]}" / "trails" / "trails.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(cv.png())
    return out
