"""The review happens in the chat (design Amendment 4, plan 4d): open shots, notes from the chat and their undo,
fixed answers, drop, park and the sign-off words."""
import json
import os
from datetime import date
from pathlib import Path

import pytest

from kei.cli import main
from kei.state import ShotState, load_state, save_state

BASE = '[animator]\ncmd = ["x"]\n'


@pytest.fixture
def here(tmp_path, monkeypatch):
    (tmp_path / "kei.toml").write_text(BASE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def make_pass(root, name="p1", body=None):
    p = Path(root) / f"out_{name}" / "shot.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(body or {"rig": "v4", "frames": 4, "fps": 24, "pass": name}), encoding="utf-8")
    return p


def make_shot(folder, name, status="needs_approval", stage="deliver", passes=("p1",)):
    root = Path(folder) / name
    save_state(root, ShotState(stage=stage, status=status, request="a walk"))
    for p in passes:
        make_pass(root, p)
    return root


def chat_note(root, text, *more):
    return main(["note", str(root), "--text", text, "--from", "chat", *more])


def open_json(capsys, *args):
    capsys.readouterr()
    assert main(["status", "--open", *args, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def names(data):
    return [s["shot"] for s in data["shots"]]


# -- Task 1: kei status --open ----------------------------------------------------------------------------------------

def test_status_open_lists_every_shot_not_done_or_rejected(here, capsys):
    make_shot(here, "walk")
    make_shot(here, "jump", status="running", stage="passes")
    make_shot(here, "run", status="done")
    make_shot(here, "sit", status="rejected")
    (here / "notes").mkdir()                       # a folder with no shot is not a shot
    data = open_json(capsys)
    assert names(data) == ["jump", "walk"]
    walk = data["shots"][1]
    assert (walk["status"], walk["stage"]) == ("needs_approval", "deliver")
    assert walk["last_pass"]["name"] == "p1" and walk["last_pass"]["date"] == date.today().isoformat()


def test_status_open_reads_the_folder_itself_when_it_is_a_shot(here, capsys):
    root = make_shot(here, "walk")
    assert names(open_json(capsys, str(root))) == ["walk"]


def test_status_open_lists_the_open_notes_with_their_words_unchanged(here, capsys):
    root = make_shot(here, "walk")
    words = 'the "left" hand\'s arc is off at 13 to 18\nand the héel slides: 左手'
    assert chat_note(root, words) == 0
    [shot] = open_json(capsys)["shots"]
    [n] = shot["notes"]
    assert (n["n"], n["words"], n["scope"], n["from"]) == (1, words, "this shot", "chat")
    assert n["lesson"] == "local.1"


def test_status_open_hides_a_shot_asked_today_unless_all(here, capsys):
    make_shot(here, "walk")
    make_shot(here, "jump")
    capsys.readouterr()
    assert main(["status", "--open", "--json", "--mark-asked"]) == 0
    assert names(json.loads(capsys.readouterr().out)) == ["jump", "walk"]   # listed, then stamped
    assert names(open_json(capsys)) == []
    assert names(open_json(capsys, "--all")) == ["jump", "walk"]


def test_an_ask_from_another_day_does_not_hide_the_shot(here, capsys):
    root = make_shot(here, "walk")
    (root / ".kei" / "chat.json").write_text(json.dumps({"asked": "2026-01-01"}), encoding="utf-8")
    assert names(open_json(capsys)) == ["walk"]


def test_a_parked_shot_is_hidden_until_a_new_pass_exists(here, capsys):
    root = make_shot(here, "walk", status="running", stage="passes")
    assert main(["park", str(root)]) == 0
    assert names(open_json(capsys)) == []
    assert names(open_json(capsys, "--all")) == ["walk"]
    make_pass(root, "p2")
    assert names(open_json(capsys)) == ["walk"]


def test_a_parked_shot_shows_again_when_its_pass_is_rewritten(here, capsys):
    root = make_shot(here, "walk", status="running", stage="passes")
    assert main(["park", str(root)]) == 0
    make_pass(root, "p1", {"rig": "v4", "frames": 5, "fps": 24})
    assert names(open_json(capsys)) == ["walk"]


def test_status_open_reads_a_moved_shot_from_disk(here, capsys):
    root = make_shot(here, "walk")
    assert chat_note(root, "the arm swings late") == 0
    assert names(open_json(capsys)) == ["walk"]
    os.replace(root, here / "walk_v2")
    data = open_json(capsys)
    assert names(data) == ["walk_v2"] and data["shots"][0]["notes"][0]["words"] == "the arm swings late"
    assert Path(data["shots"][0]["path"]) == (here / "walk_v2").resolve()


def test_status_open_in_text_names_the_shot_its_status_and_its_notes(here, capsys):
    root = make_shot(here, "walk")
    assert chat_note(root, "the arm swings late") == 0
    capsys.readouterr()
    assert main(["status", "--open"]) == 0
    out = capsys.readouterr().out
    assert "walk" in out and "running" in out and "1. the arm swings late (this shot)" in out
    assert chr(0x2014) not in out


def test_status_without_a_shot_or_open_says_what_to_give(here, capsys):
    assert main(["status"]) == 1
    assert "kei status <shot>" in capsys.readouterr().out


# -- Task 2: notes from the chat, and undo ----------------------------------------------------------------------------

def files_of(root, here):
    lessons = here / "lessons.local.md"
    return (root / ".kei" / "state.json").read_bytes(), lessons.read_bytes() if lessons.exists() else None


def test_a_chat_note_records_its_source_and_says_it_in_one_line(here, capsys):
    root = make_shot(here, "walk")
    capsys.readouterr()
    assert chat_note(root, "the arm swings late") == 0
    out = capsys.readouterr().out
    assert "noted for this shot: the arm swings late" in out
    assert f"kei note {root} --undo local.1" in out
    entry = load_state(root).history[-1]
    assert entry["from"] == "chat" and entry["misses"] == ["the arm swings late"] and entry["pass"] == "p1"


@pytest.mark.parametrize("lessons_before", [None, "one"])
def test_undo_after_a_chat_note_restores_state_and_lessons_byte_for_byte(here, capsys, lessons_before):
    root = make_shot(here, "walk")
    if lessons_before:
        from kei.lessons import add_lesson
        add_lesson(here / "lessons.local.md", "keep the heel down", "passes", scope="every")
    before = files_of(root, here)
    assert chat_note(root, "the arm swings late", "--every-shot") == 0
    assert files_of(root, here) != before and load_state(root).status == "running"
    assert main(["note", str(root), "--undo"]) == 0
    assert files_of(root, here) == before
    assert "removed note local" in capsys.readouterr().out


def test_undo_after_a_note_on_a_signed_off_shot_puts_the_approval_back(here):
    root = make_shot(here, "walk", status="done")
    before = files_of(root, here)
    assert chat_note(root, "the arm swings late") == 0
    assert load_state(root).status == "running"
    assert main(["note", str(root), "--undo", "local.1"]) == 0
    assert files_of(root, here) == before and load_state(root).status == "done"


def test_undo_refuses_after_a_new_pass(here, capsys):
    root = make_shot(here, "walk")
    assert chat_note(root, "the arm swings late") == 0
    make_pass(root, "p2")
    state = (root / ".kei" / "state.json").read_bytes()
    capsys.readouterr()
    assert main(["note", str(root), "--undo"]) == 1
    assert "new pass" in capsys.readouterr().out
    assert (root / ".kei" / "state.json").read_bytes() == state


def test_undo_refuses_after_kei_worked_on_the_shot(here, capsys):
    root = make_shot(here, "walk")
    assert chat_note(root, "the arm swings late") == 0
    s = load_state(root)
    s.history.append({"stage": "passes", "attempt": 1, "result": "fail", "misses": ["x"], "at": "t"})
    save_state(root, s)
    capsys.readouterr()
    assert main(["note", str(root), "--undo"]) == 1
    assert "cannot be undone" in capsys.readouterr().out


def test_undo_refuses_a_note_given_with_kei_note_or_on_the_review_page(here, capsys):
    from kei.signoff import note_shot
    root = make_shot(here, "walk")
    assert main(["note", str(root), "--text", "the arm swings late"]) == 0
    capsys.readouterr()
    assert main(["note", str(root), "--undo"]) == 1
    assert "chat" in capsys.readouterr().out and load_state(root).history[-1]["result"] == "note"
    root2 = make_shot(here, "jump")
    note_shot(root2, "from the page", "passes", here / "lessons.local.md", round_id=None)
    assert main(["note", str(root2), "--undo"]) == 1
    assert main(["note", str(root2), "--undo", "local.2"]) == 1


def test_undo_with_nothing_to_undo_or_an_unknown_note_says_so(here, capsys):
    root = make_shot(here, "walk")
    assert main(["note", str(root), "--undo"]) == 1
    assert main(["note", str(root), "--undo", "local.9"]) == 1
    out = capsys.readouterr().out
    assert "no note" in out and "local.9" in out


def test_two_chats_each_undo_only_their_own_note(here):
    root = make_shot(here, "walk")
    before = files_of(root, here)
    assert chat_note(root, "chat A: the arm swings late") == 0     # local.1
    assert chat_note(root, "chat B: the head bobs") == 0           # local.2
    assert main(["note", str(root), "--undo", "local.1"]) == 0
    [left] = [h for h in load_state(root).history if h.get("result") == "note"]
    assert left["lesson"] == "local.2" and left["misses"] == ["chat B: the head bobs"]
    text = (here / "lessons.local.md").read_text(encoding="utf-8")
    assert "chat A" not in text and "chat B: the head bobs" in text
    assert main(["note", str(root), "--undo", "local.2"]) == 0
    assert files_of(root, here) == before


def test_words_with_quotes_newlines_and_other_languages_are_kept_verbatim(here, capsys):
    root = make_shot(here, "walk")
    words = 'il dit "trop tôt"\nthe heel\'s contact; 13 à 18 -- 左の手 «arc»'
    capsys.readouterr()
    assert chat_note(root, words) == 0
    assert f"noted for this shot: {words}" in capsys.readouterr().out
    assert load_state(root).history[-1]["misses"] == [words]
    assert words in (here / "lessons.local.md").read_text(encoding="utf-8")


def test_a_chat_note_on_a_shot_waiting_for_an_answer_keeps_the_question(here, capsys):
    root = Path(here) / "walk"
    save_state(root, ShotState(stage="blocking", status="needs_answer", request="a walk",
                               questions=[{"from": "animator", "stage": "blocking", "text": "which foot?"}]))
    capsys.readouterr()
    assert chat_note(root, "the arm swings late") == 0
    s = load_state(root)
    assert (s.status, s.stage, s.questions[0]["text"]) == ("needs_answer", "blocking", "which foot?")
    assert s.history[-1]["stage"] == "blocking"                      # read by the next try of blocking
    assert "next try of blocking" in capsys.readouterr().out
    from kei.conductor import carried_notes
    assert carried_notes(s)["author"] == ["the arm swings late"]


def test_a_note_given_during_a_run_is_kept_for_the_next_try(tmp_path):
    from kei.signoff import note_shot
    from kei.seats import FakeSeat
    from test_conductor import CFG, Recorder, run_shot, shot, stage_of
    root = shot(tmp_path)
    lessons = tmp_path / "lessons.local.md"
    given = []

    def fault(sid, n, r):
        if sid == "checks" and n == 1:      # the author speaks in another chat while the run is at the checks
            note_shot(r, "the arm swings late", "passes", lessons, source="chat")
            given.append(1)
        return False

    rec = Recorder(fault)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec))
    assert given and state.status == "needs_approval"
    notes = [h for h in state.history if h.get("result") == "note"]
    assert [n["misses"] for n in notes] == [["the arm swings late"]] and notes[0]["stage"] == "passes"
    passes = [p for p in rec.prompts if stage_of(p) == "Breakdowns, spline and polish"]
    assert len(passes) == 2 and "the arm swings late" in passes[1]
    assert load_state(root).history == state.history


# -- Task 3: kei fixed -----------------------------------------------------------------------------------------------

def rule_of(root, lesson):
    from kei.share import rule_status
    return next(r for r in rule_status(root) if r["lesson"] == lesson)


def noted(here, *notes):
    """A shot waiting for the sign-off on p1, with chat notes given on p1, then a new pass p2 shown."""
    root = make_shot(here, "walk")
    for words, every in notes:
        assert chat_note(root, words, *(["--every-shot"] if every else [])) == 0
    make_pass(root, "p2")
    return root


def test_fixed_all_confirms_an_every_shot_rule_and_it_is_shareable(here, capsys):
    from kei.share import shareable
    root = noted(here, ("keep the heel down at the contact", True))
    assert shareable(root) == []
    assert main(["fixed", str(root), "--all"]) == 0
    r = rule_of(root, "local.1")
    assert r["confirmed"] and r["how"] == "yes"
    assert shareable(root) == ["local.1"]
    from kei.signoff import open_notes
    assert open_notes(root) == []
    assert "fixed: 1. keep the heel down at the contact" in capsys.readouterr().out


def test_fixed_not_2_leaves_note_2_open_and_unconfirmed_even_when_the_words_read_alike(here, capsys):
    from kei.share import shareable
    from kei.signoff import open_notes
    root = noted(here, ("keep the heel down at the contact", True), ("the heel pops up at the contact", True))
    assert main(["fixed", str(root), "--not", "2"]) == 0
    assert rule_of(root, "local.1")["confirmed"] and not rule_of(root, "local.2")["confirmed"]
    assert shareable(root) == ["local.1"]
    [left] = open_notes(root)
    assert (left["n"], left["lesson"], left["words"]) == (1, "local.2", "the heel pops up at the contact")
    assert "still open: 2. the heel pops up at the contact" in capsys.readouterr().out


def test_a_fixed_this_shot_note_closes_and_never_becomes_shareable(here):
    from kei.share import shareable
    from kei.signoff import open_notes
    root = noted(here, ("this walk is too fast", False))
    assert main(["fixed", str(root), "--all"]) == 0
    assert open_notes(root) == [] and shareable(root) == []


def test_fixed_refuses_when_no_new_pass_was_shown(here, capsys):
    root = make_shot(here, "walk")
    assert chat_note(root, "the arm swings late") == 0
    state = (root / ".kei" / "state.json").read_bytes()
    capsys.readouterr()
    assert main(["fixed", str(root), "--all"]) == 1
    assert "show the new pass first" in capsys.readouterr().out
    assert (root / ".kei" / "state.json").read_bytes() == state


def test_fixed_refuses_numbers_that_do_not_exist_and_lists_the_real_ones(here, capsys):
    root = noted(here, ("the arm swings late", False), ("the head bobs", False))
    state = (root / ".kei" / "state.json").read_bytes()
    capsys.readouterr()
    assert main(["fixed", str(root), "--not", "2,5"]) == 1
    out = capsys.readouterr().out
    assert "5" in out and "1. the arm swings late" in out and "2. the head bobs" in out
    assert (root / ".kei" / "state.json").read_bytes() == state
    assert main(["fixed", str(root), "--not", "x"]) == 1


def test_fixed_leaves_a_note_given_after_the_new_pass_open(here, capsys):
    from kei.signoff import open_notes
    root = noted(here, ("the arm swings late", False))
    assert chat_note(root, "now the head bobs") == 0          # given on p2
    assert main(["fixed", str(root), "--all"]) == 0
    assert [n["words"] for n in open_notes(root)] == ["now the head bobs"]


def test_fixed_needs_all_or_not(here, capsys):
    root = noted(here, ("the arm swings late", False))
    with pytest.raises(SystemExit):
        main(["fixed", str(root)])
    with pytest.raises(SystemExit):
        main(["fixed", str(root), "--all", "--not", "1"])


def test_fixed_with_no_open_note_says_so(here, capsys):
    root = make_shot(here, "walk")
    assert main(["fixed", str(root), "--all"]) == 1
    assert "no open note" in capsys.readouterr().out


# -- Task 4: drop, park, and the sign-off words ------------------------------------------------------------------------

WORDS = 'ok "ship it"\nc\'est bon, 良い'


def test_approve_keeps_the_authors_words_verbatim(here):
    root = make_shot(here, "walk")
    assert main(["approve", str(root), "--words", WORDS]) == 0
    entry = load_state(root).history[-1]
    assert entry["result"] == "approved" and entry["words"] == WORDS


def test_approve_with_no_words_records_none(here):
    root = make_shot(here, "walk")
    assert main(["approve", str(root)]) == 0
    assert "words" not in load_state(root).history[-1]


@pytest.mark.parametrize("status,stage", [("needs_approval", "deliver"), ("running", "passes"),
                                          ("needs_answer", "blocking")])
def test_drop_rejects_the_shot_with_the_authors_words(here, capsys, status, stage):
    from kei.signoff import rejection
    root = make_shot(here, "walk", status=status, stage=stage)
    assert main(["drop", str(root), "--words", WORDS]) == 0
    s = load_state(root)
    entry = s.history[-1]
    assert s.status == "rejected" and rejection(s) == "dropped by the author"
    assert entry["result"] == "rejected" and entry["words"] == WORDS and entry.get("dropped") is True
    assert "lesson" not in entry                       # a drop is not a craft lesson
    assert "dropped" in capsys.readouterr().out


def test_drop_refuses_a_closed_shot_and_empty_words(here, capsys):
    root = make_shot(here, "walk", status="done")
    assert main(["drop", str(root), "--words", "no"]) == 1
    root2 = make_shot(here, "jump")
    assert main(["drop", str(root2), "--words", "  "]) == 1
    assert load_state(root2).status == "needs_approval"
    assert "Traceback" not in capsys.readouterr().out


def test_park_refuses_a_closed_shot(here, capsys):
    root = make_shot(here, "walk", status="rejected")
    assert main(["park", str(root)]) == 1
    assert "closed" in capsys.readouterr().out


def test_drop_in_auto_mode_shares_only_the_confirmed_rules(here, monkeypatch, capsys):
    import kei.review.app as app
    from kei.share import Sharer
    from test_share_auto import PR_URL, PrRunner, log_of
    from test_share_bundle import seat_writing, sliding, walk
    from test_share_flow import ACCOUNT, GhReader
    (here / "kei.toml").write_text(BASE + '[share]\nmode = "auto"\nrepo = "my-studio/kei-lessons"\n',
                                   encoding="utf-8")
    root = noted(here, ("keep the heel down at the contact", True), ("the heel pops up at the contact", True),
                 ("this walk is too fast", False))
    assert main(["fixed", str(root), "--not", "2"]) == 0
    lessons = here / "lessons.local.md"
    runner = PrRunner()

    def sharer(shot, config):
        return Sharer(shot, lessons, config.share, seat=lambda: seat_writing(sliding(walk()), walk()),
                      runner=lambda b, w, i: runner, gh_found=True, size=0, reader=GhReader(ACCOUNT),
                      repo=config.share_repo)
    monkeypatch.setattr(app, "_sharer", sharer)
    capsys.readouterr()
    assert main(["drop", str(root), "--words", "drop it, wrong brief"]) == 0
    out = capsys.readouterr().out
    assert f"lesson local.1: sent to my-studio/kei-lessons: {PR_URL}" in out
    log = {e["lesson"]: e for e in log_of(lessons)}
    assert log["local.1"]["result"] == "sent"
    assert log["local.2"]["result"] == "kept" and log["local.2"]["reason"] == "fix not confirmed"
    assert "local.3" not in log
    assert load_state(root).status == "rejected"


def test_drop_in_ask_mode_points_to_the_review_page_for_a_confirmed_rule(here, capsys):
    root = noted(here, ("keep the heel down at the contact", True))
    assert main(["fixed", str(root), "--all"]) == 0
    capsys.readouterr()
    assert main(["drop", str(root), "--words", "drop it"]) == 0
    assert f"kei review {root}" in capsys.readouterr().out
