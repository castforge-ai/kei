"""The pen: strokes and flattened PNGs kept in the shot, the note's words byte for byte, the next prompt names them."""
import base64
import json
from dataclasses import replace

import pytest

from kei.book import load_rules
from kei.seats import FakeSeat
from kei.state import load_state
from reviewkit import PNG, PageClient, fake_round, state_hash, waiting_shot
from test_conductor import CFG, Recorder, run_shot

STROKE = {"frame": 3, "view": "side", "points": [[10, 12], [14, 18.5]], "color": "#ff3b6b", "width": 3}


@pytest.fixture
def shot(tmp_path):
    root = waiting_shot(tmp_path)
    fake_round(root, "r1", frames=8)
    return root


def test_strokes_and_pngs_are_saved_and_returned(shot):
    from kei.review.drawings import save_drawings
    back = {**STROKE, "view": "three quarter", "frame": 5}
    paths = save_drawings(shot, "r1", [STROKE, back], {"f0003_side": PNG, "f0005_three_quarter": PNG})
    assert paths == ["review/r1/drawings/1/f0003_side.png", "review/r1/drawings/1/f0005_three_quarter.png",
                     "review/r1/drawings/1/strokes.json"]
    assert (shot / paths[0]).read_bytes() == PNG
    saved = json.loads((shot / "review/r1/drawings/1/strokes.json").read_text(encoding="utf-8"))
    assert saved == {"round": "r1", "strokes": [STROKE, back]}


@pytest.mark.parametrize("strokes, pngs, why", [
    ([STROKE], {"f0003_side": b"GIF89a" + b"\x00" * 10}, "PNG"),
    ([STROKE], {"f0003_side": b"\x89PNG\r\n\x1a\n" + b"\x00" * (4 * 1024 * 1024)}, "4 MB"),
    ([{**STROKE, "frame": 8}], {"f0008_side": PNG}, "frame 8"),
    ([{**STROKE, "frame": -1}], {}, "frame -1"),
    ([{**STROKE, "view": "top"}], {}, "top"),
    ([{**STROKE, "points": "here"}], {}, "points"),
    ([STROKE], {"f0004_side": PNG}, "f0004_side"),
    ([STROKE], {"../../kei": PNG}, "kei"),
])
def test_each_refusal(shot, strokes, pngs, why):
    from kei.review.drawings import DrawingError, save_drawings
    with pytest.raises(DrawingError, match=why):
        save_drawings(shot, "r1", strokes, pngs)
    assert not (shot / "review" / "r1" / "drawings").exists()


def test_an_unknown_round_is_refused(shot):
    from kei.review.drawings import DrawingError, save_drawings
    with pytest.raises(DrawingError):
        save_drawings(shot, "r9", [STROKE], {"f0003_side": PNG})


@pytest.fixture
def page(tmp_path, shot):
    from kei.review.server import ReviewServer
    from kei.review.signoff_routes import SignOffRoutes
    app = SignOffRoutes(shot, tmp_path / "lessons.local.md", "r1", None)
    server = ReviewServer(app.routes, app.files)
    yield shot, PageClient(server.start())
    server.stop()


def b64(data):
    return base64.b64encode(data).decode()


def test_needs_work_keeps_the_words_byte_for_byte_and_the_drawings(page, tmp_path):
    shot, c = page
    text = "les pieds glissent à f12\r\n### pas un titre\n  et ça tourne\n"
    status, data = c.post("/api/needs-work", {"round": "r1", "text": text, "stage": "passes",
                                              "drawings": {"strokes": [STROKE], "pngs": {"f0003_side": b64(PNG)}}})
    assert status == 200, data
    h = load_state(shot).history[-1]
    assert h["misses"] == [text]
    assert h["drawings"] == ["review/r1/drawings/1/f0003_side.png", "review/r1/drawings/1/strokes.json"]
    rule = load_rules([tmp_path / "lessons.local.md"])[0]
    assert "à f12" in rule.title and "### pas un titre" in rule.text and "et ça tourne" in rule.text


def test_needs_work_with_a_bad_drawing_changes_nothing(page, tmp_path):
    shot, c = page
    before = state_hash(shot)
    status, data = c.post("/api/needs-work", {"round": "r1", "text": "x", "stage": "passes",
                                              "drawings": {"strokes": [STROKE], "pngs": {"f0003_side": b64(b"nope")}}})
    assert status == 409 and "PNG" in data["error"]
    assert state_hash(shot) == before and not (tmp_path / "lessons.local.md").exists()


def test_needs_work_with_base64_that_is_not_base64_is_refused(page):
    shot, c = page
    before = state_hash(shot)
    status, _ = c.post("/api/needs-work", {"round": "r1", "text": "x", "stage": "passes",
                                           "drawings": {"strokes": [STROKE], "pngs": {"f0003_side": "%%%"}}})
    assert status in (400, 409) and state_hash(shot) == before


def test_the_passes_prompt_after_a_note_with_drawings_names_each_file(page, tmp_path):
    shot, c = page
    c.post("/api/needs-work", {"round": "r1", "text": "the heel pops", "stage": "passes",
                               "drawings": {"strokes": [STROKE], "pngs": {"f0003_side": b64(PNG)}}})
    rec = Recorder()
    run_shot(shot, "a walk", replace(CFG, lessons=tmp_path / "lessons.local.md"), animator=FakeSeat("fake", rec))
    first = rec.prompts[0]
    assert "- the heel pops" in first
    assert "Look at: review/r1/drawings/1/f0003_side.png" in first
    assert "Look at: review/r1/drawings/1/strokes.json" in first
    assert "review/r1/frames" not in first     # the round's own frames are Kei's renders, not the stage's files


def test_two_notes_on_one_round_keep_both_sets_of_drawings(page):
    from kei.state import save_state
    shot, c = page
    first = {**STROKE, "frame": 3}
    c.post("/api/needs-work", {"round": "r1", "text": "one", "stage": "passes",
                               "drawings": {"strokes": [first], "pngs": {"f0003_side": b64(PNG)}}})
    s = load_state(shot)
    s.status, s.stage = "needs_approval", "deliver"       # the shot came back on the same round
    save_state(shot, s)
    second = {**STROKE, "frame": 5}
    png2 = PNG + b"2"
    c.post("/api/needs-work", {"round": "r1", "text": "two", "stage": "passes",
                               "drawings": {"strokes": [second], "pngs": {"f0005_side": b64(png2)}}})
    notes = [h for h in load_state(shot).history if h.get("result") == "note"]
    one, two = notes[0]["drawings"], notes[1]["drawings"]
    assert set(one).isdisjoint(two)
    assert all((shot / p).is_file() for p in one + two)
    assert (shot / one[0]).read_bytes() == PNG and (shot / two[0]).read_bytes() == png2
    assert json.loads((shot / one[-1]).read_text(encoding="utf-8"))["strokes"] == [first]
