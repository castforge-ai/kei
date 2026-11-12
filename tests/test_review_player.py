"""The page's player clock: the frame on screen comes from the elapsed time and the shot's fps, never from the
browser's timer rate. Runs review.js's pure functions under node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parent.parent / "kei" / "review" / "page" / "review.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed: the player clock runs in node only")


def call(expr):
    script = f"const k = require({json.dumps(str(JS))}); process.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_24_fps_at_1000_ms_is_frame_24():
    assert call("k.frameAt(1000, 24, 100, false)") == 24


def test_frame_zero_at_the_start_and_one_frame_per_tick():
    assert call("[0, 41, 42, 83, 84].map(ms => k.frameAt(ms, 24, 100, false))") == [0, 0, 1, 1, 2]


def test_a_32_frame_loop_wraps():
    # a loop of 32 frames has 33 pictures: the last repeats the first and is not played
    ms = 32 * 1000 / 24
    assert call(f"[k.frameAt({ms} - 1, 24, 33, true), k.frameAt({ms}, 24, 33, true)]") == [31, 0]
    assert call(f"k.loopsAt({ms}, 24, 33, true)") == 1


def test_a_shot_that_is_not_a_loop_plays_every_picture():
    assert call("k.frameAt(12 * 1000 / 24, 24, 13, false)") == 12
    assert call("k.frameAt(13 * 1000 / 24, 24, 13, false)") == 0


def test_ten_loops_end_on_the_last_frame():
    end = 10 * 32 * 1000 / 24
    assert call(f"k.x10Frame({end} - 1, 24, 33, true)") == {"frame": 31, "loops": 9, "done": False}
    assert call(f"k.x10Frame({end}, 24, 33, true)") == {"frame": 31, "loops": 10, "done": True}
    assert call(f"k.x10Frame({end} + 5000, 24, 33, true)") == {"frame": 31, "loops": 10, "done": True}


def test_the_labels_name_the_pass_and_the_round():
    assert call('k.roundLabel("before", {"pass": "blocking", "round": "blocking"})') == "before: blocking"
    assert call('k.roundLabel("after", {"pass": "p3", "round": "r2"})') == "after: p3, r2"


def test_arrow_keys_step_one_frame_and_ignore_typing():
    assert call('k.keyDelta("ArrowRight", "CANVAS", false)') == 1
    assert call('k.keyDelta("ArrowLeft", "BODY", false)') == -1
    assert call('k.keyDelta("ArrowLeft", "TEXTAREA", false)') == 0
    assert call('k.keyDelta("ArrowRight", "INPUT", false)') == 0
    assert call('k.keyDelta("ArrowRight", "SELECT", false)') == 0
    assert call('k.keyDelta("ArrowRight", "DIV", true)') == 0      # contenteditable
    assert call('k.keyDelta("a", "BODY", false)') == 0


def test_a_step_wraps_at_the_seam_of_a_cycle_and_stops_at_the_ends_of_a_shot():
    # a 26-frame cycle has 27 pictures; the last repeats the first and is never shown
    assert call("k.stepFrame(25, 1, 27, true)") == 0
    assert call("k.stepFrame(0, -1, 27, true)") == 25
    assert call("k.stepFrame(12, -1, 13, false)") == 11
    assert call("k.stepFrame(12, 1, 13, false)") == 12
    assert call("k.stepFrame(0, -1, 13, false)") == 0


def run_cards(events, total):
    js = ("let st = k.cardStart(%d); const fx = [];"
          "for (const e of %s) { const r = k.cardReducer(st, e); st = r.state; fx.push(...r.effects); }"
          "[st, fx]" % (total, json.dumps(events)))
    script = f"const k = require({json.dumps(str(JS))}); process.stdout.write(JSON.stringify((() => {{ {js.replace('[st, fx]', 'return [st, fx];')} }})()));"
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_run_of_yes_answers_never_approves():
    st, fx = run_cards([{"type": "yes"}] * 50, 4)
    assert "accept" not in fx and st["i"] == 4
    st, fx = run_cards([{"type": "yes"}] * 4 + [{"type": "approve"}], 4)
    assert fx.count("accept") == 1                     # only the deliberate Approve does


def test_approve_is_refused_before_the_last_card_or_after_a_no():
    _, fx = run_cards([{"type": "yes"}, {"type": "approve"}], 3)
    assert "accept" not in fx and "refused" in fx
    _, fx = run_cards([{"type": "yes"}, {"type": "no", "note": "the heel pops", "drew": False}, {"type": "yes"},
                       {"type": "approve"}], 3)
    assert "accept" not in fx and "refused" in fx


def test_a_no_needs_a_note_or_a_pen_stroke():
    st, fx = run_cards([{"type": "no", "note": "  ", "drew": False}], 2)
    assert fx == ["need-reason"] and st["i"] == 0
    st, fx = run_cards([{"type": "no", "note": "", "drew": True}], 2)
    assert st["i"] == 1 and st["answers"][0]["answer"] == "no"
    st, fx = run_cards([{"type": "no", "note": "le talon saute\n### pas un titre", "drew": False},
                        {"type": "yes"}, {"type": "send"}], 2)
    assert "needs-work" in fx and st["answers"][0]["note"] == "le talon saute\n### pas un titre"


def test_the_note_is_the_authors_words_verbatim():
    cards = [{"text": "Frame 3-5: the heel lands soft"}, {"text": "Frame 9: the head stays level"},
             {"text": "Frame 1-2: the toe drags"}]
    answers = [{"answer": "no", "note": "le talon saute à f4\n  trop tôt", "drew": False}, {"answer": "yes"},
               {"answer": "no", "note": "", "drew": True}]
    note = call(f"k.noteFromCards({json.dumps(cards)}, {json.dumps(answers)})")
    assert note == "le talon saute à f4\n  trop tôt\n\nFrame 1-2: the toe drags (see my drawing)"
    assert call(f"k.summaryLine({json.dumps(answers)})") == "3 checked: 1 yes, 2 no"


def test_y_and_n_answer_but_not_while_typing():
    assert call('k.keyCard("y", "BODY", false)') == "yes"
    assert call('k.keyCard("N", "CANVAS", false)') == "no"
    assert call('k.keyCard("y", "TEXTAREA", false)') is None
    assert call('k.keyCard("n", "INPUT", false)') is None
    assert call('k.keyCard("x", "BODY", false)') is None


def test_the_loop_plays_over_the_frames_the_question_names():
    assert call("[0, 1, 2, 3, 4, 5, 6].map(i => k.rangeFrame(i * 1000 / 24 + 1, 24, [13, 18], 27, true))") == \
        [13, 14, 15, 16, 17, 18, 13]
    assert call("k.rangeFrame(5 * 1000 / 24 + 1, 24, null, 27, true)") == 5
    assert call("k.rangeFrame(1, 24, [20, 40], 27, true)") == 20       # clamped to the round's frames
