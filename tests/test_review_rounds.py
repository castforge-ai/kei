"""A review round: the latest pass rendered in the four post views, one PNG per frame, and the round seen last."""
import json
import shutil
from pathlib import Path

import pytest

from kei.state import ShotState, load_state, save_state

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "stepped_walk"
SIZE = 24   # pixels per view: these tests are about the files, not the picture


@pytest.fixture
def walk(tmp_path):
    root = tmp_path / "stepped_walk"
    shutil.copytree(EXAMPLE / "out_blocking", root / "out_blocking", ignore=shutil.ignore_patterns("frames", "*.png"))
    save_state(root, ShotState(stage="deliver", status="needs_approval", request="a walk"))
    return root


def add_pass(root, name, change=0.0):
    data = json.loads((root / "out_blocking" / "shot.json").read_text(encoding="utf-8"))
    data["note"] = f"pass {name} {change}"
    (root / f"out_{name}").mkdir(exist_ok=True)
    (root / f"out_{name}" / "shot.json").write_text(json.dumps(data), encoding="utf-8")


def test_review_views_are_the_post_views():
    from kei.render import POST_VIEWS
    from kei.review.rounds import REVIEW_VIEWS
    assert REVIEW_VIEWS == POST_VIEWS == ("side", "three quarter", "front", "back")


def test_latest_pass_is_the_highest_numbered_pass(walk):
    from kei.review.rounds import latest_pass
    assert latest_pass(walk) == "blocking"
    add_pass(walk, "p2")
    add_pass(walk, "p10")
    assert latest_pass(walk) == "p10"


def test_a_round_has_one_png_per_frame_and_the_shots_fps(walk):
    from kei.review.rounds import make_round
    d = make_round(walk, size=SIZE)
    assert d == walk / "review" / "r1"
    meta = json.loads((d / "round.json").read_text(encoding="utf-8"))
    shot = json.loads((walk / "out_blocking" / "shot.json").read_text(encoding="utf-8"))
    pngs = sorted((d / "frames").glob("f*.png"))
    assert len(pngs) == shot["frames"] + 1 == meta["frames"]
    assert meta["round"] == "r1" and meta["pass"] == "blocking" and meta["fps"] == shot.get("fps", 24)
    assert meta["loop"] is bool(shot.get("loop")) and meta["shot_sha256"] and meta["made_at"]
    assert pngs[0].read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_second_call_with_no_change_reuses_the_round_and_a_change_makes_r2(walk):
    from kei.review.rounds import make_round
    first = make_round(walk, size=SIZE)
    stamp = (first / "round.json").stat().st_mtime_ns
    assert make_round(walk, size=SIZE) == first
    assert (first / "round.json").stat().st_mtime_ns == stamp
    add_pass(walk, "p1")
    second = make_round(walk, size=SIZE)
    assert second.name == "r2"
    assert json.loads((second / "round.json").read_text(encoding="utf-8"))["pass"] == "p1"


def test_before_is_blocking_first_then_the_round_seen_last(walk):
    from kei.review.rounds import before_round, make_round, mark_seen
    add_pass(walk, "p1")
    r1 = make_round(walk, size=SIZE).name
    before = before_round(walk, r1)
    assert before["pass"] == "blocking" and before["round"] == "blocking"
    mark_seen(walk, r1, loops=10)
    h = load_state(walk).history[-1]
    assert (h["result"], h["round"], h["loops"]) == ("seen", "r1", 10)
    add_pass(walk, "p2")
    r2 = make_round(walk, size=SIZE).name
    assert before_round(walk, r2)["round"] == "r1"


def test_before_of_a_blocking_round_with_nothing_seen_is_none(walk):
    from kei.review.rounds import before_round, make_round
    assert before_round(walk, make_round(walk, size=SIZE).name) is None


def test_a_shot_with_no_pass_is_refused_in_plain_words(tmp_path):
    from kei.review.rounds import ReviewError, make_round
    with pytest.raises(ReviewError, match="no pass"):
        make_round(tmp_path, size=SIZE)


def test_a_seen_mark_does_not_change_what_the_next_try_reads():
    from kei.conductor import carried_notes
    s = ShotState(stage="deliver", history=[{"stage": "deliver", "result": "seen", "round": "r1", "misses": []}])
    assert carried_notes(s) == {"gate": [], "critics": [], "author": [], "animator": []}
