"""A panel's label fits its panel: on the narrow panels of a key sheet the view name shortens and the last words go,
and every view of a row keeps the same words."""
from kei.render import CHARACTER_VIEWS, panel_label
from kei.sheet import ADVANCE


def fits(s, w):
    return len(s) * ADVANCE <= w


def test_a_wide_panel_keeps_the_whole_label():
    assert panel_label("three quarter", "F12 key kei", 400, CHARACTER_VIEWS) == "three quarter F12 key kei"


def test_a_key_sheet_panel_shortens_the_view_and_keeps_the_frame():
    w = 90 - 8     # a key sheet panel: the 180 px frame halved, less the margin
    got = {v: panel_label(v, "F12 key kei", w, CHARACTER_VIEWS) for v in CHARACTER_VIEWS}
    assert got["three quarter"].startswith("3/4 F12") and got["front"].startswith("front F12")
    assert all(fits(s, w) for s in got.values()), got
    assert len({s.split(" ", 1)[1] for s in got.values()}) == 1, got     # the same words after every view name


def test_a_middle_panel_drops_only_what_does_not_fit():
    w = 17 * ADVANCE
    assert panel_label("three quarter", "F3 key kei", w, CHARACTER_VIEWS) == "3/4 F3 key kei"
    assert panel_label("front", "F3 key kei", w, CHARACTER_VIEWS) == "front F3 key kei"


def test_no_room_leaves_the_short_view_name():
    assert panel_label("three quarter", "F3 key", 3 * ADVANCE) == "3/4"
    assert panel_label("side", "", 400) == "side"
