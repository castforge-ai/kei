"""Silhouette profiles: the figure's pixel runs, row by row, as fractions of its height, to compare a character with
its design sheet.

A profile is read on a mask (True = figure) between the figure's top row and its sole row. At each height t (0 = the
top of the head, 1 = the sole), every STEP of the height, it holds the runs of figure pixels on that row as
[start, end] in fractions of the figure height, measured from the figure's centre line. Three corrections keep the
reading about the body and not the pixels: a gap narrower than MIN_GAP joins its two runs (an outline line is not a
gap in the silhouette); a run narrower than MIN_RUN is dropped (a stray pixel, a soft shadow's edge); and in the
hands' rows (HANDS) a run whose middle is farther than HAND_ZONE from the centre line is a hand and is dropped: the
turn of the hands and the curl of the fingers are the rest pose, not the build, and the sheets turn the palms toward
the viewer while the rest pose (the export's bind pose) turns them toward the thighs.

sheet_profile(png, box) reads a design sheet inside the view's box, between the head top and the sole, so the floor
line under the sole and the logo above the head are outside it; a figure pixel is one that the background, flood
filled from the box's edges, does not reach (see sheet_mask). character_profile(ch, view) renders the character's black
silhouette at rest and reads it the same way. compare(ours, sheet) lists every row where the two differ: a run count
that differs, or a run whose width differs by more than TOLERANCE of the height. The rows in ENDS are not compared:
the head's very top row and the sole row, where one pixel of height changes the width completely and the sheet's
contact shadow joins the sole.

Run as a script, it writes the sheets' profiles to tests/fixtures/characters/<name>_sheet_profile.json, so the tests
need only the numbers: uv run python -m kei.characters.profile
"""
from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

STEP = 0.025            # the profile's rows, as a share of the figure height
FINE = 0.005            # the sheet's rows near each profile row, for the vertical tolerance
SHIFT = 0.01            # a run count may match the sheet at a row up to this share of the height above or below
# The largest width difference allowed for one run, as a share of the height: 0.015 is 2.6 cm on a 1.71 m figure and
# about 12 px on a sheet. A painted sheet is not exact to less: its soft shading and outline move an edge by 2 to 3 px
# a side, the same part differs left to right by up to 0.004, and the head top and sole rows are placed by eye to
# about 4 px. A real proportion fault is larger (the neck and waist faults this check was made for were 0.03 to 0.07).
TOLERANCE = 0.015
MIN_GAP = 0.006         # a gap narrower than this (share of the height) joins its two runs
HANDS = (0.52, 0.66)    # the rows from just under the wrist ring to below the fingertips, on both sheets
HAND_ZONE = 0.15        # in those rows, a run whose middle is farther than this from the centre line is a hand
MIN_RUN = 0.004         # a run narrower than this is dropped
ENDS = ("0.000", "1.000")   # the rows not compared (the module's note says why)
SHEET_DISTANCE = 40     # a sheet pixel is figure when its colour is farther than this from the background
RENDER_SIZE = 900       # the silhouette's panel size in pixels: about 680 px of figure (the sheets have about 820)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "characters"

# Per character and view: the sheet, the view's box (x0, x1) and the figure's head top and sole rows (y).
SHEETS = {
    "kei": {"source": "docs/characters/kei-castforge-character-v2.png",
            "front": {"x": [50, 510], "y": [104, 925]},
            "side": {"x": [525, 720], "y": [104, 925]}},
    "keira": {"source": "docs/characters/keira-castforge-character-v1.png",
              "front": {"x": [90, 480], "y": [104, 922]},
              "side": {"x": [525, 720], "y": [104, 922]}},
}


def decode_png(data: bytes):
    """(width, height, rows) of an 8-bit RGB or RGBA PNG, every filter type; rows[y][x] is (r, g, b)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, w, h, kind_c = 8, b"", 0, 0, 2
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h, depth, kind_c = struct.unpack(">IIBB", body[:10])
            if depth != 8 or kind_c not in (2, 6) or body[12] != 0:
                raise ValueError("only 8-bit RGB or RGBA PNGs without interlace")
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    bpp = 3 if kind_c == 2 else 4
    raw = zlib.decompress(idat)
    stride = w * bpp
    prev = bytearray(stride)
    rows = []
    for y in range(h):
        f = raw[y * (stride + 1)]
        cur = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if f == 1:
            for i in range(bpp, stride):
                cur[i] = (cur[i] + cur[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                cur[i] = (cur[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                cur[i] = (cur[i] + ((cur[i - bpp] if i >= bpp else 0) + prev[i]) // 2) & 255
        elif f == 4:
            for i in range(stride):
                a = cur[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                cur[i] = (cur[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append([tuple(cur[x * bpp:x * bpp + 3]) for x in range(w)])
        prev = cur
    return w, h, rows


def _runs(row: list[bool], x0: int, height: float, centre: float, hands: bool = False) -> list[list[float]]:
    """The figure runs of one mask row, joined over small gaps, small runs dropped (and the hands, in the hands'
    rows), in fractions of the height from the centre line."""
    runs, start = [], None
    for x, on in enumerate(row + [False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append([start, x])
            start = None
    joined = []
    for r in runs:
        if joined and (r[0] - joined[-1][1]) / height < MIN_GAP:
            joined[-1][1] = r[1]
        else:
            joined.append(r)
    out = [[round((a + x0 - centre) / height, 4), round((b + x0 - centre) / height, 4)]
           for a, b in joined if (b - a) / height >= MIN_RUN]
    return [r for r in out if not hands or abs(r[0] + r[1]) / 2 <= HAND_ZONE]


def mask_profile(mask: list[list[bool]], x0: int, top: int, sole: int, step: float = STEP) -> dict:
    """The runs at every step of the height from top (t = 0) to sole (t = 1), x from the figure's centre line.

    The centre line is the middle of the figure's widest extent over all rows, so a figure standing symmetric reads
    about 0 either way. Keys are the heights as text with three decimals."""
    height = sole - top
    xs = [x for y in range(top, sole + 1) for x, on in enumerate(mask[y]) if on]
    centre = x0 + (min(xs) + max(xs) + 1) / 2
    out = {}
    n = round(1 / step)
    for k in range(n + 1):
        t = k * step
        y = min(sole, top + round(t * height))
        out[f"{t:.3f}"] = _runs(mask[y], x0, height, centre, HANDS[0] <= t <= HANDS[1])
    return out


def figure_rows(mask: list[list[bool]]) -> tuple[int, int]:
    rows = [y for y, r in enumerate(mask) if any(r)]
    return rows[0], rows[-1]


def sheet_mask(rows, box: dict) -> list[list[bool]]:
    """The figure pixels of a sheet view inside its box: everything that the background cannot reach.

    A pixel is background-coloured when its colour is within SHEET_DISTANCE of the sheet's top left pixel. The lit
    side of the body is that light too, so a plain colour test leaves holes inside the torso; instead the background
    is flood-filled from the edges of the box (the head top row to the sole row), and every pixel it does not reach
    is figure. The gaps between the arms and the body and between the legs open to the box's edge, so they stay
    gaps."""
    bg = rows[0][0]
    x0, x1 = box["x"]
    top, sole = box["y"]
    lim = SHEET_DISTANCE * SHEET_DISTANCE
    w, h = x1 - x0 + 1, sole - top + 1
    light = [[sum((c[i] - bg[i]) ** 2 for i in range(3)) <= lim for c in r[x0:x1 + 1]] for r in rows[top:sole + 1]]
    seen = [[False] * w for _ in range(h)]
    stack = [(x, y) for y in range(h) for x in (0, w - 1)] + [(x, y) for x in range(w) for y in (0, h - 1)]
    while stack:
        x, y = stack.pop()
        if 0 <= x < w and 0 <= y < h and light[y][x] and not seen[y][x]:
            seen[y][x] = True
            stack += [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
    mask = [[False] * w for _ in range(len(rows))]
    for y in range(h):
        mask[top + y] = [not s for s in seen[y]]
    return mask


def sheet_profile(png: bytes, box: dict) -> dict:
    """The profile of one sheet view, at STEP rows, and the run counts at FINE rows for the vertical tolerance."""
    _, _, rows = decode_png(png)
    mask = sheet_mask(rows, box)
    top, sole = box["y"]
    fine = mask_profile(mask, box["x"][0], top, sole, FINE)
    return {"box": box, "step": STEP, "rows": mask_profile(mask, box["x"][0], top, sole, STEP),
            "fine_step": FINE, "fine_counts": {t: len(r) for t, r in fine.items()}}


def character_mask(ch, view: str = "front", size: int = RENDER_SIZE) -> list[list[bool]]:
    from kei.render import draw_silhouette
    _, _, rows = decode_png(draw_silhouette(ch, size=size, view=view))
    return [[c[0] < 128 for c in r] for r in rows]


def character_profile(ch, view: str = "front", size: int = RENDER_SIZE) -> dict:
    """The profile of the character's black silhouette at rest, read like a sheet."""
    mask = character_mask(ch, view, size)
    top, sole = figure_rows(mask)
    return mask_profile(mask, 0, top, sole, STEP)


def _width(r) -> float:
    return r[1] - r[0]


def compare(ours: dict, sheet: dict, tolerance: float = TOLERANCE, skip=ENDS) -> list[str]:
    """Every row where our profile and the sheet's differ, as a line of text; empty when they match.

    A row's run count must equal the sheet's, or the sheet's at a fine row up to SHIFT above or below (a boundary
    such as the crotch is placed to SHIFT of the height; such a row is then not compared run by run). When the counts
    are equal the runs pair up in order and each width must be within tolerance. Rows in skip are not compared."""
    out = []
    fine = sheet.get("fine_counts", {})
    fstep = sheet.get("fine_step", FINE)
    reach = round(SHIFT / fstep)
    for t, theirs in sheet["rows"].items():
        if t in skip or t not in ours:
            continue
        mine = ours[t]
        if len(mine) != len(theirs):
            near = {fine.get(f"{float(t) + k * fstep:.3f}") for k in range(-reach, reach + 1)}
            if len(mine) not in near:
                out.append(f"t {t}: {len(mine)} runs, the sheet has {len(theirs)} "
                           f"(ours {[round(_width(r), 3) for r in mine]}, sheet {[round(_width(r), 3) for r in theirs]})")
            continue
        for i, (a, b) in enumerate(zip(mine, theirs)):
            d = _width(a) - _width(b)
            if abs(d) > tolerance:
                out.append(f"t {t}: run {i + 1} of {len(mine)} is {_width(a):.3f} wide, the sheet {_width(b):.3f} "
                           f"({d:+.3f})")
    return out


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}_sheet_profile.json").read_text(encoding="utf-8"))


def write_fixtures(root: Path = ROOT) -> list[Path]:
    """Read each sheet and write its profile, numbers only, to the test fixtures."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, spec in SHEETS.items():
        png = (root / spec["source"]).read_bytes()
        data = {"character": name, "source": spec["source"], "distance": SHEET_DISTANCE, "min_gap": MIN_GAP,
                "min_run": MIN_RUN, "hands": list(HANDS), "hand_zone": HAND_ZONE, "units": "fractions of the figure height; x from the figure's centre line; "
                                             "t = 0 at the head top, 1 at the sole",
                "views": {v: sheet_profile(png, spec[v]) for v in ("front", "side")}}
        path = FIXTURES / f"{name}_sheet_profile.json"
        path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


if __name__ == "__main__":
    for p in write_fixtures():
        print(p)
    sys.exit(0)
