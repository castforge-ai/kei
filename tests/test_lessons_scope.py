"""A "this shot" lesson reaches only its own shot, and a note the lessons file already holds is not written twice."""
from dataclasses import replace

from kei.book import load_rules, lessons_for_shot
from kei.cli import main
from kei.lessons import add_lesson
from kei.seats import FakeSeat
from kei.state import ShotState, load_state, save_state
from test_chat_review import chat_note, here, make_shot  # noqa: F401  (here is a fixture)
from test_conductor import CFG, Recorder, run_shot
from test_signoff import note


def waiting_at(tmp_path, name):
    root = tmp_path / "shots" / name
    root.mkdir(parents=True)
    save_state(root, ShotState(stage="deliver", status="needs_approval", request="a box falls",
                               approved_plan={"plan/plan.json": "abc"}))
    return root


def test_a_this_shot_lesson_names_its_shot_and_reaches_no_other_shot(tmp_path):
    a, b = waiting_at(tmp_path, "box_a"), waiting_at(tmp_path, "box_b")
    assert note(tmp_path, a, "the feet slide on contact") == 0
    lessons = load_rules([tmp_path / "lessons.local.md"])
    assert [(r.scope, r.shot) for r in lessons] == [("this shot", a.resolve().as_posix())]
    assert lessons_for_shot(lessons, a) == lessons and lessons_for_shot(lessons, b) == []
    config = replace(CFG, lessons=tmp_path / "lessons.local.md")
    save_state(b, ShotState(stage="passes", status="running", request="a box falls",
                            approved_plan={"plan/plan.json": "abc"}))
    rec = Recorder()
    run_shot(b, "a box falls", config, animator=FakeSeat("fake", rec))
    assert rec.prompts and all("the feet slide on contact" not in p for p in rec.prompts)


def test_an_every_shot_lesson_and_an_older_lesson_with_no_shot_reach_every_shot(tmp_path):
    path = tmp_path / "lessons.local.md"
    add_lesson(path, "keep the heel down", "passes", scope="every", shot=tmp_path / "x")
    add_lesson(path, "an old note", "passes", scope="shot")     # written before lessons named their shot
    lessons = load_rules([path])
    assert [r.shot for r in lessons] == ["", ""]
    assert lessons_for_shot(lessons, tmp_path / "y") == lessons


def test_the_same_note_twice_is_one_lesson_whatever_its_case_or_spacing(tmp_path):
    root = waiting_at(tmp_path, "box_a")
    assert note(tmp_path, root, "the feet slide on contact") == 0
    save_state(root, replace(load_state(root), stage="deliver", status="needs_approval"))
    assert note(tmp_path, root, "  The feet   slide on contact ") == 0
    assert [r.id for r in load_rules([tmp_path / "lessons.local.md"])] == ["local.1"]
    assert [h["lesson"] for h in load_state(root).history if h["result"] == "note"] == ["local.1", "local.1"]


def test_the_same_words_for_another_shot_or_stage_are_a_new_lesson(tmp_path):
    path = tmp_path / "lessons.local.md"
    assert add_lesson(path, "the feet slide", "passes", shot=tmp_path / "a") == "local.1"
    assert add_lesson(path, "the feet slide", "passes", shot=tmp_path / "b") == "local.2"
    assert add_lesson(path, "the feet slide", "plan", shot=tmp_path / "a") == "local.3"
    assert add_lesson(path, "the feet slide", "passes", shot=tmp_path / "a") == "local.1"


def test_undo_of_a_repeated_note_keeps_the_lesson_the_first_note_wrote(here):  # noqa: F811
    root = make_shot(here, "walk")
    assert chat_note(root, "the arm swings late") == 0
    lessons = here / "lessons.local.md"
    once = lessons.read_bytes()
    assert chat_note(root, "the arm swings late") == 0
    assert lessons.read_bytes() == once
    assert main(["note", str(root), "--undo"]) == 0
    assert lessons.read_bytes() == once      # the first note's lesson stays
    assert [h["lesson"] for h in load_state(root).history if h["result"] == "note"] == ["local.1"]
