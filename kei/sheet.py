"""The plan sheet: Kei draws plan/plan_sheet.png from the pose drawings in plan/plan.json, with no image library.

A key pose's drawing is a side view in any unit, y up:
    "drawing": {"lines": [[x1, y1, x2, y2], ...], "action": [[x, y], ...], "com": [x, y]}
"lines" is required; "action" (the line of action) and "com" (the centre of mass) are optional.
A key may also hold "views": {"front": <drawing>, "top": <drawing>}, the same pose seen from the front (x is screen
right) and from above (y is forward). Each such view gets its own panel beside the key's side view.
The plan may also hold "arcs": {"<part>": [[frame, x, y], ...]}, the planned paths of the main parts.

The sheet has one panel per key pose and one panel that overlays the arcs on every pose, with a legend naming each arc
in its colour. A key panel marks where each arc is on that key's frame, and nothing more of the arcs. All panels share
one scale and one origin, so a position in one panel compares with the same position in another.
"""
from __future__ import annotations

import json
import math
import os
import struct
import zlib
from pathlib import Path

PANEL = 480          # pixels per panel side: a standing figure is about 320 px tall, enough to judge arms and chest
COLS = 4             # panels per row
LABEL = 16           # the label strip at the top of a panel
PAD = 8

WHITE, BORDER, INK, TEXT = (250, 250, 250), (205, 205, 205), (40, 40, 40), (20, 20, 20)
ACTION, COM, GHOST = (210, 40, 40), (30, 90, 220), (190, 190, 190)
ARC_COLOURS = [(230, 120, 0), (0, 150, 80), (150, 60, 200), (0, 140, 200), (200, 0, 120), (150, 110, 0),
               (0, 70, 160), (130, 20, 40)]

# A 3x5 font: each glyph is five rows of three pixels.
FONT = {
    "A": "010101111101101", "B": "110101110101110", "C": "011100100100011", "D": "110101101101110",
    "E": "111100110100111", "F": "111100110100100", "G": "011100101101011", "H": "101101111101101",
    "I": "111010010010111", "J": "001001001101010", "K": "101101110101101", "L": "100100100100111",
    "M": "101111111101101", "N": "110101101101101", "O": "010101101101010", "P": "110101110100100",
    "Q": "010101101110011", "R": "110101110101101", "S": "011100010001110", "T": "111010010010010",
    "U": "101101101101111", "V": "101101101101010", "W": "101101111111101", "X": "101101010101101",
    "Y": "101101010010010", "Z": "111001010100111", "0": "111101101101111", "1": "010110010010111",
    "2": "110001010100111", "3": "110001010001110", "4": "101101111001001", "5": "111100110001110",
    "6": "011100111101111", "7": "111001010010010", "8": "111101111101111", "9": "111101111001110",
    "-": "000000111000000", ":": "000010000010000", ".": "000000000000010", ",": "000000000010100",
    "_": "000000000000111", "(": "010100100100010", ")": "010001001001010", "/": "001001010100100",
    "+": "000010111010000",
}
GLYPH_SCALE = 2
ADVANCE = 4 * GLYPH_SCALE


class SheetError(ValueError):
    """The plan cannot be drawn. The message names the key's frame."""


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _points(value, size: int, where: str) -> list[list[float]]:
    if not isinstance(value, list) or not all(isinstance(p, list) and len(p) == size and all(map(_num, p))
                                              for p in value):
        raise SheetError(f"{where}: needs a list of {size}-number lists")
    return value


EXTRA_VIEWS = ("front", "top")   # the optional views of a key, drawn beside its side view, in this order


def _drawing(d, where: str) -> dict:
    lines = _points(d.get("lines"), 4, f"{where}.lines")
    if not lines:
        raise SheetError(f"{where}.lines is empty")
    action = _points(d.get("action", []), 2, f"{where}.action")
    com = d.get("com")
    if com is not None and not (isinstance(com, list) and len(com) == 2 and all(map(_num, com))):
        raise SheetError(f"{where}.com needs two numbers")
    return {"lines": lines, "action": action, "com": com}


def _check(plan: dict) -> tuple[list[dict], dict]:
    keys = plan.get("keys") if isinstance(plan, dict) else None
    if not isinstance(keys, list) or not keys:
        raise SheetError('plan.json has no "keys" list')
    out = []
    for k in keys:
        f = k.get("f") if isinstance(k, dict) else None
        where = f"key f {f}"
        d = k.get("drawing") if isinstance(k, dict) else None
        if not isinstance(d, dict):
            raise SheetError(f'{where} has no "drawing" (lines, action, com)')
        entry = {"label": f"F{f} {k.get('function', '')} {k.get('kind', '')}", **_drawing(d, f"{where} drawing"),
                 "views": {}}
        views = k.get("views", {})
        if not isinstance(views, dict):
            raise SheetError(f'{where} "views" must map front or top to a drawing')
        for name, vd in views.items():
            if name not in EXTRA_VIEWS:
                raise SheetError(f'{where} views: unknown view {name!r}; use {" or ".join(EXTRA_VIEWS)}')
            if not isinstance(vd, dict):
                raise SheetError(f"{where} views.{name} must be a drawing (lines, action, com)")
            entry["views"][name] = _drawing(vd, f"{where} views.{name}")
        out.append(entry)
    arcs = plan.get("arcs", {})
    if not isinstance(arcs, dict):
        raise SheetError('"arcs" must map a part name to a list of [frame, x, y]')
    arcs = {name: _points(pts, 3, f"arc {name}") for name, pts in arcs.items()}
    for k, src in zip(out, keys):
        k["f"] = src.get("f")
    return out, arcs


class _Canvas:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.px = bytearray(bytes(WHITE) * (w * h))
        self.clip = (0, 0, w, h)   # x0, y0, x1, y1 (x1 and y1 excluded): nothing is drawn outside it

    def dot(self, x: int, y: int, c) -> None:
        x0, y0, x1, y1 = self.clip
        if max(0, x0) <= x < min(self.w, x1) and max(0, y0) <= y < min(self.h, y1):
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(c)

    def line(self, x0: int, y0: int, x1: int, y1: int, c, wide: bool = True) -> None:
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.dot(x0, y0, c)
            if wide:
                self.dot(x0 + 1, y0, c)
                self.dot(x0, y0 + 1, c)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def disk(self, cx: int, cy: int, r: int, c) -> None:
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    self.dot(x, y, c)

    def box(self, x0: int, y0: int, x1: int, y1: int, c) -> None:
        self.line(x0, y0, x1, y0, c, False)
        self.line(x1, y0, x1, y1, c, False)
        self.line(x1, y1, x0, y1, c, False)
        self.line(x0, y1, x0, y0, c, False)

    def text(self, x: int, y: int, s: str, c, max_w: int) -> None:
        for ch in s.upper()[:max(0, max_w // ADVANCE)]:
            for i, bit in enumerate(FONT.get(ch, "0" * 15)):
                if bit == "1":
                    gx, gy = x + (i % 3) * GLYPH_SCALE, y + (i // 3) * GLYPH_SCALE
                    for oy in range(GLYPH_SCALE):
                        for ox in range(GLYPH_SCALE):
                            self.dot(gx + ox, gy + oy, c)
            x += ADVANCE

    def png(self) -> bytes:
        stride = self.w * 3
        raw = b"".join(b"\x00" + bytes(self.px[y * stride:(y + 1) * stride]) for y in range(self.h))

        def chunk(kind: bytes, body: bytes) -> bytes:
            return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _drawing_points(ds: list[dict]) -> list[tuple[float, float]]:
    pts = [(l[0], l[1]) for k in ds for l in k["lines"]] + [(l[2], l[3]) for k in ds for l in k["lines"]]
    return pts + [tuple(p) for k in ds for p in k["action"]] + [tuple(k["com"]) for k in ds if k["com"]]


def _transforms(keys: list[dict], arcs: dict) -> dict:
    """{view: to_px}: one scale for every panel of every view (fit to the largest), each view centred on its own
    points, 10 % margin, y up. A position in one panel compares with the same position in another of its view."""
    sets = {"side": _drawing_points(keys) + [tuple(p[1:]) for path in arcs.values() for p in path]}
    for v in EXTRA_VIEWS:
        ds = [k["views"][v] for k in keys if v in k["views"]]
        if ds:
            sets[v] = _drawing_points(ds)
    area = PANEL - LABEL - 2 * PAD
    span = max(max(max(p[i] for p in pts) - min(p[i] for p in pts) for i in (0, 1)) for pts in sets.values()) or 1.0
    scale = area / (span * 1.2)
    out = {}
    for view, pts in sets.items():
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2

        def to_px(ox: int, oy: int, x: float, y: float, cx=cx, cy=cy) -> tuple[int, int]:
            return (round(ox + PAD + area / 2 + (x - cx) * scale),
                    round(oy + LABEL + PAD + area / 2 - (y - cy) * scale))
        out[view] = to_px
    return out


def _pose(cv: _Canvas, P, ox: int, oy: int, k: dict, ink, with_marks: bool) -> None:
    for x0, y0, x1, y1 in k["lines"]:
        cv.line(*P(ox, oy, x0, y0), *P(ox, oy, x1, y1), ink)
    if not with_marks:
        return
    for a, b in zip(k["action"], k["action"][1:]):
        cv.line(*P(ox, oy, *a), *P(ox, oy, *b), ACTION)
    if k["com"]:
        cv.disk(*P(ox, oy, *k["com"]), 4, COM)


def _arcs(cv: _Canvas, P, ox: int, oy: int, arcs: dict) -> None:
    """Every planned path, a dot per planned frame."""
    for i, path in enumerate(arcs.values()):
        c = ARC_COLOURS[i % len(ARC_COLOURS)]
        pts = [p[1:] for p in path]
        for a, b in zip(pts, pts[1:]):
            cv.line(*P(ox, oy, *a), *P(ox, oy, *b), c)
        for p in pts:
            cv.disk(*P(ox, oy, *p), 3, c)


def _arc_marks(cv: _Canvas, P, ox: int, oy: int, arcs: dict, f) -> None:
    """In a key panel: where each arc is on the key's own frame, when the plan gives that frame."""
    for i, path in enumerate(arcs.values()):
        c = ARC_COLOURS[i % len(ARC_COLOURS)]
        for p in path:
            if p[0] == f:
                cv.disk(*P(ox, oy, p[1], p[2]), 4, c)


LEGEND_ROW = 14


def _legend(cv: _Canvas, ox: int, oy: int, arcs: dict) -> None:
    """The arcs panel's label and one line per arc in its own colour, so no name is cut off."""
    cv.text(ox + 4, oy + 3, "ARCS" if arcs else "ARCS: NONE PLANNED", TEXT, PANEL - 8)
    for i, name in enumerate(arcs):
        y = oy + LABEL + 2 + i * LEGEND_ROW
        c = ARC_COLOURS[i % len(ARC_COLOURS)]
        cv.disk(ox + 9, y + 4, 3, c)
        cv.text(ox + 18, y, name, c, PANEL // 2 - 22)


def draw_sheet(plan: dict) -> bytes:
    """The plan sheet as PNG bytes: a cell per key pose (its side view, then its front and top views when the plan
    draws them), then one cell with every arc over every pose."""
    keys, arcs = _check(plan)
    T = _transforms(keys, arcs)
    views = ["side"] + [v for v in EXTRA_VIEWS if v in T]
    cell = len(views) * PANEL
    count = len(keys) + 1
    cols = min(max(1, COLS // len(views)), count)
    rows = -(-count // cols)
    cv = _Canvas(cols * cell, rows * PANEL)
    for i in range(count):
        cx, oy = (i % cols) * cell, (i // cols) * PANEL
        for j, view in enumerate(views):
            ox, P = cx + j * PANEL, T[view]
            cv.box(ox, oy, ox + PANEL - 1, oy + PANEL - 1, BORDER)
            if i < len(keys):
                k = keys[i]
                d = k if view == "side" else k["views"].get(view)
                if d is not None:
                    _pose(cv, P, ox, oy, d, INK, with_marks=True)
                if view == "side":
                    _arc_marks(cv, P, ox, oy, arcs, k["f"])
                    label = k["label"]
                else:
                    label = f"F{k['f']} {view}" + ("" if d is not None else ": not drawn")
                cv.text(ox + 4, oy + 3, label, TEXT, PANEL - 8)
            else:
                for k in keys:
                    d = k if view == "side" else k["views"].get(view)
                    if d is not None:
                        _pose(cv, P, ox, oy, d, GHOST, with_marks=False)
                if view == "side":
                    _arcs(cv, P, ox, oy, arcs)
                    _legend(cv, ox, oy, arcs)
                else:
                    cv.text(ox + 4, oy + 3, f"every key, {view}", TEXT, PANEL - 8)
    return cv.png()


def write_sheet(shot_dir: Path) -> Path:
    """Draw plan/plan_sheet.png from plan/plan.json and return its path. An unchanged sheet is not rewritten."""
    src = Path(shot_dir) / "plan" / "plan.json"
    try:
        plan = json.loads(src.read_text(encoding="utf-8"))
    except OSError as e:
        raise SheetError(f"cannot read {src}: {e}") from e
    except ValueError as e:
        raise SheetError(f"{src} is not valid JSON: {e}") from e
    out = src.with_name("plan_sheet.png")
    data = draw_sheet(plan)
    if out.is_file():
        # A redraw keeps the sheet's time: the order checks ask when the plan was first drawn, not when it last
        # changed. A later plan change is seen by the critics through the plan's hashes instead.
        t = out.stat().st_mtime
        if out.read_bytes() != data:
            out.write_bytes(data)
    else:
        out.write_bytes(data)
        t = src.stat().st_mtime
    os.utime(out, (t, t))
    return out
