"""kei curves: a curve image per channel, the graph editor's view of a pass.

  kei curves <shot> p6 --channels spine,armL              every frame of the pass
  kei curves <shot> p6 --channels root --frames 140-160   a range

Writes out_<pass>/curves/<channel>.png: one line per number of the channel (x, y, z in their colours) over the
frames, the sampled value on every frame, the keyed frames as larger dots, and the lowest and highest value written
at the left. A curve that dips between two equal keys, an overshoot or a flat run read at a glance, as in a graph
editor. It reads only.
"""
from __future__ import annotations

from pathlib import Path

from kei.sample import bake, check_shot, normalize_keys, read_json
from kei.sheet import _Canvas

W, H, PAD, TOP = 900, 300, 40, 18
COLOURS = [(200, 60, 40), (40, 150, 70), (40, 110, 200), (170, 80, 170)]
GRID, TEXT, KEYMARK = (225, 225, 225), (40, 40, 40), (120, 120, 120)


class CurvesError(ValueError):
    pass


def _range(text: str | None, last: int) -> tuple[int, int]:
    if not text:
        return 0, last
    a, _, b = str(text).partition("-")
    try:
        lo, hi = int(a), int(b or a)
    except ValueError:
        raise CurvesError(f"--frames: a range like 140-160, not {text!r}") from None
    if not 0 <= lo <= hi <= last:
        raise CurvesError(f"--frames {text}: the pass has frames 0 to {last}")
    return lo, hi


def draw_curves(shot_dir: Path, pass_name: str, channels: list[str], frames: str | None = None,
                mode: str | None = None) -> list[Path]:
    src = Path(shot_dir) / f"out_{pass_name}" / "shot.json"
    if not src.is_file():
        raise CurvesError(f"no {src}: write the pass's keys there first")
    shot = read_json(src, "shot")
    check_shot(shot)
    mode = mode or ("step" if pass_name == "blocking" else "spline")
    baked = bake(shot, mode)
    lo, hi = _range(frames, len(baked) - 1)
    pose0 = baked[0]["pose"]
    for c in channels:
        if c not in pose0:
            raise CurvesError(f"no channel {c!r}; channels: {', '.join(pose0)}")
    keyed = {int(k["f"]) for k in normalize_keys(shot) if float(k["f"]).is_integer()}
    out_dir = Path(shot_dir) / f"out_{pass_name}" / "curves"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for c in channels:
        rows = []
        for fr in baked[lo:hi + 1]:
            v = fr["pose"][c]
            rows.append((fr["f"], [float(x) for x in v] if isinstance(v, (list, tuple)) else [float(v)]))
        vals = [x for _, vs in rows for x in vs]
        vmin, vmax = min(vals), max(vals)
        span = (vmax - vmin) or 1.0
        cv = _Canvas(W, H)

        def px(f, v):
            x = PAD + (f - lo) / max(1, hi - lo) * (W - 2 * PAD)
            y = H - PAD - (v - vmin) / span * (H - PAD - TOP - 10)
            return int(round(x)), int(round(y))
        for f in range(lo, hi + 1):
            if f in keyed:
                x, _ = px(f, vmin)
                cv.line(x, TOP, x, H - PAD, GRID, False)
        cv.line(PAD, H - PAD, W - PAD, H - PAD, KEYMARK, False)
        for i in range(len(rows[0][1])):
            colour = COLOURS[i % len(COLOURS)]
            pts = [px(f, vs[i]) for f, vs in rows]
            for a, b in zip(pts, pts[1:]):
                cv.line(*a, *b, colour)
            for (f, _), p in zip(rows, pts):
                cv.disk(*p, 3 if f in keyed else 1, colour)
        cv.text(4, 3, f"{c} {pass_name} f{lo}-{hi}  max {vmax:.3f}  min {vmin:.3f}  keys: grey lines", TEXT, W - 8)
        dst = out_dir / f"{c}.png"
        dst.write_bytes(cv.png())
        written.append(dst)
    return written
