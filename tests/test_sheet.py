import json
import struct
import zlib

import pytest

from kei.sheet import COLS, PANEL, SheetError, draw_sheet, write_sheet

LABEL = 16   # the label strip at the top of each panel


def key(f, function="pose", drawing=True):
    k = {"f": f, "function": function, "kind": "key"}
    if drawing:
        k["drawing"] = {"lines": [[0, 0, 1, 1], [1, 1, 2, 0]], "action": [[0, 0], [2, 1]], "com": [1, 0.5]}
    return k


def plan(n=2, **kw):
    return {"keys": [key(i * 5, **kw) for i in range(n)], "arcs": {"corner": [[0, 0, 0], [5, 1, 1], [10, 2, 0]]}}


def decode(png):
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, w, h = 8, b"", 0, 0
    while pos < len(png):
        n, kind = struct.unpack(">I4s", png[pos:pos + 8])
        body = png[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    rows = [raw[y * (w * 3 + 1) + 1:(y + 1) * (w * 3 + 1)] for y in range(h)]
    return w, h, lambda x, y: tuple(rows[y][x * 3:x * 3 + 3])


def dark(px):
    return max(px) < 100


def test_png_signature_and_size():
    w, h, _ = decode(draw_sheet(plan(2)))
    assert (w, h) == (3 * PANEL, PANEL)


def test_rows_wrap_at_cols():
    w, h, _ = decode(draw_sheet(plan(5)))
    assert (w, h) == (COLS * PANEL, 2 * PANEL)


def test_drawing_is_not_blank():
    w, h, px = decode(draw_sheet(plan(2)))
    first = [px(x, y) for x in range(PANEL) for y in range(LABEL, PANEL)]
    assert any(dark(p) for p in first)
    arcs = [px(x, y) for x in range(2 * PANEL, 3 * PANEL) for y in range(LABEL, PANEL)]
    assert any(max(p) - min(p) > 80 for p in arcs)


def test_key_without_drawing_is_refused():
    p = {"keys": [key(0), key(10, drawing=False)]}
    with pytest.raises(SheetError, match="f 10"):
        draw_sheet(p)


@pytest.mark.parametrize("line", [[0, 0, "a", 1], [0, 0, 1]])
def test_bad_line_is_refused(line):
    p = {"keys": [{"f": 3, "function": "x", "kind": "key", "drawing": {"lines": [line]}}]}
    with pytest.raises(SheetError, match="f 3"):
        draw_sheet(p)


def test_zero_extent_draws():
    p = {"keys": [{"f": 0, "function": "x", "kind": "key",
                   "drawing": {"lines": [[1, 1, 1, 1]], "com": [1, 1], "action": [[1, 1], [1, 1]]}}]}
    w, h, _ = decode(draw_sheet(p))
    assert (w, h) == (2 * PANEL, PANEL)


def test_long_label_stays_in_its_panel():
    p = {"keys": [key(0, function="a" * 80), key(5)]}
    w, h, px = decode(draw_sheet(p))
    # the first panel's label must not spill into the second panel's label strip (the second label starts at x+4)
    second_label_start = [px(x, y) for x in range(PANEL, PANEL + 3) for y in range(LABEL)]
    assert not any(dark(q) for q in second_label_start)


def test_write_sheet_writes_the_file(tmp_path):
    (tmp_path / "plan").mkdir()
    (tmp_path / "plan" / "plan.json").write_text(json.dumps(plan(2)), encoding="utf-8")
    out = write_sheet(tmp_path)
    assert out == tmp_path / "plan" / "plan_sheet.png"
    assert out.read_bytes()[:4] == b"\x89PNG"


def test_write_sheet_without_a_plan(tmp_path):
    with pytest.raises(SheetError):
        write_sheet(tmp_path)


def colour_pixels(px, x0, x1, y0, y1, colour, tol=6):
    return [(x, y) for x in range(x0, x1) for y in range(y0, y1)
            if all(abs(a - b) <= tol for a, b in zip(px(x, y), colour))]


def standing(f, height=1.7):
    return {"f": f, "function": "up", "kind": "key",
            "drawing": {"lines": [[0, 0, 0, height], [0, height * 0.8, 0.3, height * 0.6]], "com": [0, 1.0]}}


def test_the_figure_is_at_least_twice_the_old_size():
    p = {"keys": [standing(0), standing(5)], "arcs": {"head": [[0, 0, 1.7], [5, 0.2, 1.68]]}}
    w, h, px = decode(draw_sheet(p))
    rows = [y for y in range(LABEL, PANEL) if any(dark(px(x, y)) for x in range(PANEL))]
    assert max(rows) - min(rows) >= 300      # was about 150 px in a 240 px panel


def test_key_panels_carry_no_stray_arcs_only_the_arc_point_at_their_frame():
    from kei.sheet import ARC_COLOURS
    p = {"keys": [standing(0), standing(5)], "arcs": {"hand": [[0, -0.5, 0.5], [3, 0.0, 0.3], [5, 0.5, 0.5]]}}
    w, h, px = decode(draw_sheet(p))
    faint = tuple(255 - (255 - v) // 3 for v in ARC_COLOURS[0])
    assert colour_pixels(px, 0, 2 * PANEL, LABEL, PANEL, faint) == []
    marks = colour_pixels(px, 0, PANEL, LABEL, PANEL, ARC_COLOURS[0])
    assert marks and max(x for x, _ in marks) - min(x for x, _ in marks) < 16   # one point, not a path


def test_the_arcs_panel_names_every_arc_in_its_colour():
    from kei.sheet import ARC_COLOURS
    names = ["pelvis", "head", "hand_r", "hand_l", "ankle_r", "toe_r"]
    p = {"keys": [standing(0)], "arcs": {n: [[0, 0.1 * i, 0.2 * i], [5, 0.1 * i + 0.1, 0.2 * i]]
                                         for i, n in enumerate(names)}}
    w, h, px = decode(draw_sheet(p))
    for i in range(len(names)):
        c = ARC_COLOURS[i % len(ARC_COLOURS)]
        legend = colour_pixels(px, PANEL + 4, PANEL + PANEL // 2, LABEL, LABEL + 20 * len(names), c, tol=0)
        assert legend, names[i]


def with_views(f, *views):
    k = standing(f)
    k["views"] = {v: {"lines": [[-0.2, 0, -0.2, 1.7], [0.2, 0, 0.2, 1.7]], "com": [0, 1.0]} for v in views}
    return k


def test_front_and_top_views_sit_beside_the_side_view_of_their_key():
    p = {"keys": [with_views(0, "front", "top"), with_views(5, "front", "top"), standing(9)]}
    w, h, px = decode(draw_sheet(p))
    cols = max(1, COLS // 3)
    assert w == cols * 3 * PANEL
    for sub in (1, 2):   # the front and top panels of the first key are drawn
        assert any(dark(px(x, y)) for x in range(sub * PANEL, (sub + 1) * PANEL) for y in range(LABEL, PANEL, 2))


def test_a_key_without_a_front_view_still_draws_its_side():
    p = {"keys": [with_views(0, "front"), standing(5)]}
    w, h, px = decode(draw_sheet(p))
    second_side = [px(x, y) for x in range(2 * PANEL, 3 * PANEL) for y in range(LABEL, PANEL, 2)] if w > 2 * PANEL \
        else [px(x, y) for x in range(0, PANEL) for y in range(PANEL + LABEL, 2 * PANEL, 2)]
    assert any(dark(q) for q in second_side)


def test_an_unknown_view_is_refused_with_its_key():
    k = standing(3)
    k["views"] = {"back": {"lines": [[0, 0, 0, 1]]}}
    with pytest.raises(SheetError, match="f 3"):
        draw_sheet({"keys": [k]})


def test_a_bad_front_drawing_is_refused_with_its_key_and_view():
    k = standing(3)
    k["views"] = {"front": {"lines": [[0, 0, "a", 1]]}}
    with pytest.raises(SheetError, match="f 3 views.front"):
        draw_sheet({"keys": [k]})
