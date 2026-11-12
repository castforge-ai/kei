"""The silhouettes against the design sheets: the run widths of the figure, row by row, match the sheet's.

The sheets' profiles are recorded numbers (tests/fixtures/characters/<name>_sheet_profile.json, written by
uv run python -m kei.characters.profile), so these tests need no sheet image. When the sheet image is present, the
recorded numbers are also checked against it.
"""
import struct
import zlib

import pytest

from kei.characters import CHARACTERS, load_character
from kei.characters.profile import (ENDS, FINE, HANDS, ROOT, SHEETS, STEP, TOLERANCE, character_profile, compare,
                                    decode_png, load_fixture, mask_profile, sheet_profile)


def side_skip():
    """In the side view the hand hangs over the thigh on both, at a different depth: those rows are not compared."""
    rows = [f"{k * STEP:.3f}" for k in range(round(1 / STEP) + 1)]
    return set(ENDS) | {t for t in rows if HANDS[0] <= float(t) <= HANDS[1]}


@pytest.fixture(scope="module", params=CHARACTERS)
def name(request):
    return request.param


@pytest.fixture(scope="module")
def profiles(name):
    ch = load_character(name)
    return {v: character_profile(ch, v) for v in ("front", "side")}


def test_the_front_silhouette_matches_the_sheet(name, profiles):
    sheet = load_fixture(name)["views"]["front"]
    assert compare(profiles["front"], sheet) == []


def test_the_side_silhouette_matches_the_sheet(name, profiles):
    sheet = load_fixture(name)["views"]["side"]
    assert compare(profiles["side"], sheet, skip=side_skip()) == []


def test_the_recorded_sheet_profile_is_the_sheet(name):
    path = ROOT / SHEETS[name]["source"]
    if not path.is_file():
        pytest.skip("the sheet image is not in this checkout; the recorded numbers stand")
    png = path.read_bytes()
    fixture = load_fixture(name)
    for view in ("front", "side"):
        assert sheet_profile(png, SHEETS[name][view]) == fixture["views"][view]


def test_the_fixture_holds_every_row_and_numbers_only(name):
    fixture = load_fixture(name)
    for view in ("front", "side"):
        rows = fixture["views"][view]["rows"]
        assert list(rows) == [f"{k * STEP:.3f}" for k in range(round(1 / STEP) + 1)]
        for runs in rows.values():
            assert all(isinstance(x, float) or isinstance(x, int) for r in runs for x in r)
        assert len(fixture["views"][view]["fine_counts"]) == round(1 / FINE) + 1


# The comparison itself, on made-up masks.

def bar(w: int, spans) -> list[bool]:
    return [any(a <= x < b for a, b in spans) for x in range(w)]


def figure(rows) -> list[list[bool]]:
    """A 100-row figure, 200 px wide: rows is [(from row, to row, spans)]."""
    return [next((bar(200, s) for a, b, s in rows if a <= y < b), bar(200, [])) for y in range(101)]


def test_a_narrow_run_fails_beyond_the_tolerance_and_passes_within_it():
    sheet = mask_profile(figure([(0, 101, [(80, 120)])]), 0, 0, 100)
    close = mask_profile(figure([(0, 101, [(81, 120)])]), 0, 0, 100)
    thin = mask_profile(figure([(0, 101, [(83, 117)])]), 0, 0, 100)
    assert compare(close, {"rows": sheet}, skip=()) == []
    out = compare(thin, {"rows": sheet}, skip=())
    assert out and "the sheet 0.400" in out[0]
    assert TOLERANCE == 0.015


def test_a_missing_gap_fails_as_a_run_count():
    """The crotch: the sheet splits into two legs where ours is one block."""
    legs = mask_profile(figure([(0, 101, [(60, 98), (102, 140)])]), 0, 0, 100)
    block = mask_profile(figure([(0, 101, [(60, 140)])]), 0, 0, 100)
    out = compare(block, {"rows": legs}, skip=())
    assert out and "1 runs, the sheet has 2" in out[0]


def test_a_floating_head_fails_as_an_empty_row():
    sheet = mask_profile(figure([(0, 101, [(90, 110)])]), 0, 0, 100)
    gap = mask_profile(figure([(0, 40, [(90, 110)]), (50, 101, [(90, 110)])]), 0, 0, 100)
    assert any("0 runs, the sheet has 1" in line for line in compare(gap, {"rows": sheet}, skip=()))


def test_a_boundary_may_sit_up_to_the_shift_away():
    """The legs split at row 50 on the sheet and at row 51 on ours: the count matches a nearby row of the sheet."""
    def split_at(r):
        return figure([(0, r, [(60, 140)]), (r, 101, [(60, 98), (102, 140)])])
    sheet = {"rows": mask_profile(split_at(50), 0, 0, 100), "fine_step": FINE,
             "fine_counts": {t: len(v) for t, v in mask_profile(split_at(50), 0, 0, 100, FINE).items()}}
    assert compare(mask_profile(split_at(51), 0, 0, 100), sheet, skip=()) == []
    assert compare(mask_profile(split_at(56), 0, 0, 100), sheet, skip=())


def test_an_outline_line_is_not_a_gap():
    sheet = mask_profile(figure([(0, 101, [(80, 120)])]), 0, 0, 100)
    lined = mask_profile(figure([(0, 101, [(80, 100), (100 + 0, 120)])]), 0, 0, 100)
    assert compare(lined, {"rows": sheet}, skip=()) == []


def png(w, h, rows, filt):
    """An RGB PNG with one filter type on every row, encoded the long way (for the decoder's test)."""
    def paeth(a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        return a if pa <= pb and pa <= pc else b if pb <= pc else c
    raw, prev = b"", bytes(w * 3)
    for r in rows:
        cur = bytes(v for px in r for v in px)
        out = bytearray()
        for i, v in enumerate(cur):
            a = cur[i - 3] if i >= 3 else 0
            b = prev[i]
            c = prev[i - 3] if i >= 3 else 0
            pred = (0, a, b, (a + b) // 2, paeth(a, b, c))[filt]
            out.append((v - pred) & 255)
        raw += bytes([filt]) + bytes(out)
        prev = cur

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.mark.parametrize("filt", range(5))
def test_the_png_reader_undoes_every_filter(filt):
    rows = [[((x * 37 + y * 11) % 256, (x * y) % 256, (200 - x * 5 + y) % 256) for x in range(7)] for y in range(5)]
    w, h, got = decode_png(png(7, 5, rows, filt))
    assert (w, h) == (7, 5)
    assert got == rows
