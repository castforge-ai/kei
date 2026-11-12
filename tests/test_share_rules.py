"""Rules and confirmed fixes (design Amendment 3): a note's scope, this shot or every shot; a rule is shareable once
a later round confirms its fix; shares run at approval and at rejection."""
import json
from pathlib import Path

import pytest

from kei.lessons import add_lesson
from kei.state import ShotState, load_state, save_state
from reviewkit import PageClient, fake_round

BASE = '[animator]\ncmd = ["x"]\n'


# -- the scope of a note ---------------------------------------------------------------------------------------------

def test_a_lesson_keeps_its_scope_on_its_own_line_and_out_of_its_text(tmp_path):
    from kei.book import load_rules
    p = tmp_path / "lessons.local.md"
    add_lesson(p, "the foot slides", "passes")
    add_lesson(p, "keep the heel down at contact", "passes", scope="every")
    text = p.read_text(encoding="utf-8")
    assert "stages: passes\nscope: this shot\n" in text and "stages: passes\nscope: every shot\n" in text
    one, two = load_rules([p])
    assert (one.scope, two.scope) == ("this shot", "every shot")
    assert two.text == "keep the heel down at contact"


def test_an_older_lesson_with_no_scope_line_still_reads(tmp_path):
    from kei.book import parse_book
    [r] = parse_book("### local.1. x (provisional)\nstages: passes\n\nthe words\n", "f")
    assert r.scope == "" and r.text == "the words"


def test_add_lesson_refuses_an_unknown_scope(tmp_path):
    from kei.book import BookError
    with pytest.raises(BookError, match="scope"):
        add_lesson(tmp_path / "l.md", "x", "passes", scope="some shots")


def waiting(tmp_path):
    root = tmp_path / "shots" / "walk"
    save_state(root, ShotState(stage="deliver", status="needs_approval", request="a walk"))
    fake_round(root, "r1")
    return root


def test_a_note_is_this_shot_by_default_and_the_history_says_so(tmp_path):
    from kei.signoff import note_shot
    root = waiting(tmp_path)
    state, lesson = note_shot(root, "the arm swings late", "passes", tmp_path / "l.md")
    entry = state.history[-1]
    assert entry["scope"] == "this shot" and entry["round"] == "r1"


def test_a_note_for_every_shot_is_kept_on_the_lesson_and_the_history(tmp_path):
    from kei.book import load_rules
    from kei.signoff import note_shot
    root = waiting(tmp_path)
    state, lesson = note_shot(root, "the arm swings late", "passes", tmp_path / "l.md", scope="every")
    assert state.history[-1]["scope"] == "every shot"
    assert load_rules([tmp_path / "l.md"])[0].scope == "every shot"


def test_kei_note_every_shot(tmp_path, monkeypatch, capsys):
    from kei.cli import main
    (tmp_path / "kei.toml").write_text(BASE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    root = waiting(tmp_path)
    assert main(["note", str(root), "--text", "the arm swings late", "--every-shot"]) == 0
    assert load_state(root).history[-1]["scope"] == "every shot"
    assert "every shot" in capsys.readouterr().out
    save_state(root, ShotState(stage="deliver", status="needs_approval", request="a walk"))
    assert main(["note", str(root), "--text", "only here"]) == 0
    assert load_state(root).history[-1]["scope"] == "this shot"


@pytest.fixture
def page(tmp_path):
    from kei.review.server import ReviewServer
    from kei.review.signoff_routes import SignOffRoutes
    root = waiting(tmp_path)
    routes = SignOffRoutes(root, tmp_path / "l.md", "r1", None)
    server = ReviewServer(routes.routes, routes.files)
    yield root, PageClient(server.start())
    server.stop()


def test_the_page_sends_the_scope_of_a_needs_work_note(page):
    root, c = page
    status, data = c.post("/api/needs-work", {"round": "r1", "text": "heel", "stage": "passes", "scope": "every"})
    assert status == 200, data
    assert load_state(root).history[-1]["scope"] == "every shot"


def test_the_page_refuses_an_unknown_scope(page):
    root, c = page
    status, data = c.post("/api/needs-work", {"round": "r1", "text": "heel", "stage": "passes", "scope": "most"})
    assert status == 400 and "scope" in data["error"] and load_state(root).status == "needs_approval"


def test_a_reject_keeps_the_card_answers_given_before_it(page):
    root, c = page
    cards = [{"check": "Frame 3-5: the heel stays down", "answer": "yes"}]
    status, data = c.post("/api/reject", {"round": "r1", "reason": "wrong brief", "cards": cards})
    assert status == 200, data
    entry = load_state(root).history[-1]
    assert entry["result"] == "rejected" and entry["cards"] == cards and entry["round"] == "r1"


JS = Path(__file__).resolve().parent.parent / "kei" / "review" / "page" / "review.js"


def js(expr):
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = f"const k = require({json.dumps(str(JS))}); process.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_key_e_toggles_every_shot_and_y_and_n_are_unchanged():
    assert js('[k.keyCard("e", "BODY", false), k.keyCard("E", "BODY", false), k.keyCard("e", "TEXTAREA", false)]') \
        == ["every", "every", None]
    assert js('[k.keyCard("y", "BODY", false), k.keyCard("n", "BODY", false)]') == ["yes", "no"]


def test_a_no_carries_its_scope_and_the_note_is_every_shot_when_one_no_is():
    st = js('(() => { let s = k.cardStart(2); s = k.cardReducer(s, {type: "no", note: "a", scope: "every"}).state;'
            ' s = k.cardReducer(s, {type: "no", note: "b"}).state; return s; })()')
    assert [a["scope"] for a in st["answers"]] == ["every", "shot"]
    assert js('k.noteScope([{answer: "no", scope: "shot"}, {answer: "yes"}])') == "shot"
    assert js('k.noteScope([{answer: "no", scope: "shot"}, {answer: "no", scope: "every"}])') == "every"


# -- a rule is shareable once a later round confirms its fix ---------------------------------------------------------

CHECK = "Frame 3-5: the left heel lifts early"


def note(lesson, round_id, scope="every shot", no=(CHECK,), yes=()):
    cards = [{"check": c, "answer": "no"} for c in no] + [{"check": c, "answer": "yes"} for c in yes]
    return {"stage": "passes", "attempt": 0, "result": "note", "lesson": lesson, "misses": ["x"], "scope": scope,
            "round": round_id, "cards": cards}


def closed(result, round_id, yes=()):
    e = {"stage": "deliver", "attempt": 0, "result": result, "misses": [], "round": round_id}
    if yes:
        e["cards"] = [{"check": c, "answer": "yes"} for c in yes]
    return e


def rules(tmp_path, history, status="done"):
    from kei.share import rule_status
    root = tmp_path / "shots" / "walk"
    save_state(root, ShotState(stage="deliver", status=status, request="a walk", history=history))
    return {r["lesson"]: r for r in rule_status(root)}


def test_approval_confirms_every_rule_of_the_shot(tmp_path):
    r = rules(tmp_path, [note("local.1", "r1"), closed("approved", "r2")])["local.1"]
    assert r["confirmed"] and (r["fails_round"], r["passes_round"], r["how"]) == ("r1", "r2", "approval")


def test_a_yes_to_the_notes_check_in_a_later_round_confirms_it_without_approval(tmp_path):
    r = rules(tmp_path, [note("local.1", "r1"), closed("rejected", "r2", yes=[CHECK])], "rejected")["local.1"]
    assert r["confirmed"] and (r["fails_round"], r["passes_round"], r["how"]) == ("r1", "r2", "yes")


def test_a_yes_to_the_same_check_reworded_by_the_critics_confirms_it(tmp_path):
    reworded = "Frame 3-6: the left heel lifts too early"
    r = rules(tmp_path, [note("local.1", "r1"), note("local.2", "r2", no=["Frame 20: the head bobs"],
                                                     yes=[reworded])], "running")
    assert r["local.1"]["confirmed"] and r["local.1"]["passes_round"] == "r2"
    assert not r["local.2"]["confirmed"]


def test_a_yes_to_another_check_or_in_the_same_round_confirms_nothing(tmp_path):
    r = rules(tmp_path, [note("local.1", "r1"), closed("rejected", "r2", yes=["Frame 20-24: the head bobs"])],
              "rejected")["local.1"]
    assert not r["confirmed"] and r["passes_round"] is None
    r = rules(tmp_path, [note("local.1", "r1"), closed("rejected", "r1", yes=[CHECK])], "rejected")["local.1"]
    assert not r["confirmed"]


def test_this_shot_notes_and_older_notes_with_no_scope_are_never_rules(tmp_path):
    old = note("local.2", "r1")
    del old["scope"]
    r = rules(tmp_path, [note("local.1", "r1", scope="this shot"), old, closed("approved", "r2")])
    assert r == {}


def test_an_approval_before_the_note_confirms_nothing(tmp_path):
    r = rules(tmp_path, [closed("approved", "r1"), note("local.1", "r1")], "running")["local.1"]
    assert not r["confirmed"]


# -- shares at approval and at rejection, only confirmed rules ----------------------------------------------------

from test_share_auto import PR_URL, PrRunner, log_of      # noqa: E402
from test_share_bundle import seat_writing, sliding, walk      # noqa: E402
from test_share_flow import ACCOUNT, GhReader      # noqa: E402


@pytest.fixture
def shot(tmp_path):
    from kei.review.server import ReviewServer
    from kei.review.signoff_routes import SignOffRoutes
    from kei.share import Sharer
    servers = []

    def build(mode, history):
        lessons = tmp_path / "lessons.local.md"
        add_lesson(lessons, "the left heel lifts early at the contact", "passes", scope="every")
        add_lesson(lessons, "keep the head level through the walk", "passes", scope="every")
        add_lesson(lessons, "this walk is too fast", "passes")
        root = tmp_path / "shots" / "walk"
        save_state(root, ShotState(stage="deliver", status="needs_approval", request="a walk", history=history))
        fake_round(root, "r1")
        fake_round(root, "r2")
        runner = PrRunner()
        sharer = Sharer(root, lessons, mode, seat=lambda: seat_writing(sliding(walk()), walk()),
                        runner=lambda b, w, i: runner, gh_found=True, size=16, reader=GhReader(ACCOUNT))
        routes = SignOffRoutes(root, lessons, "r2", None, sharer=sharer)
        server = ReviewServer(routes.routes, routes.files)
        servers.append(server)
        return PageClient(server.start()), runner, root, lessons

    yield build
    for s in servers:
        s.stop()


HISTORY = [note("local.1", "r1"), note("local.2", "r1", no=["Frame 20-24: the head bobs"]),
           note("local.3", "r1", scope="this shot", no=())]


def test_auto_at_rejection_sends_only_the_rule_whose_fix_was_confirmed(shot):
    c, runner, root, lessons = shot("auto", HISTORY)
    status, data = c.post("/api/reject", {"round": "r2", "reason": "wrong brief",
                                          "cards": [{"check": CHECK, "answer": "yes"}]})
    assert status == 200 and data["status"] == "rejected"
    [result] = data["share"]["results"]
    assert result["lesson"] == "local.1" and result["url"] == PR_URL
    log = {e["lesson"]: e for e in log_of(lessons)}
    assert log["local.1"]["result"] == "sent"
    assert (log["local.1"]["fails_round"], log["local.1"]["passes_round"]) == ("r1", "r2")
    assert log["local.2"]["result"] == "kept" and log["local.2"]["reason"] == "fix not confirmed"
    assert "local.3" not in log                              # a note for this shot never shares
    assert load_state(root).status == "rejected"


def test_auto_at_approval_sends_every_rule_and_never_a_this_shot_note(shot):
    c, runner, root, lessons = shot("auto", HISTORY)
    data = c.post("/api/accept", {"round": "r2", "ticked": []})[1]
    assert sorted(r["lesson"] for r in data["share"]["results"]) == ["local.1", "local.2"]
    assert "local.3" not in {e["lesson"] for e in log_of(lessons)}


def test_ask_at_rejection_offers_the_confirmed_rule_and_says_why_the_other_stays(shot):
    c, runner, root, lessons = shot("ask", HISTORY)
    data = c.post("/api/reject", {"round": "r2", "reason": "wrong brief",
                                  "cards": [{"check": CHECK, "answer": "yes"}]})[1]
    assert data["share"]["lessons"] == ["local.1"] and runner.cmds == []
    assert data["share"]["kept"] == [{"lesson": "local.2", "reason": "fix not confirmed"}]
    assert c.get("/api/shot")[1]["share"]["lessons"] == ["local.1"]
    assert c.post("/api/share/prepare", {"lesson": "local.2"})[0] == 409
    assert c.post("/api/share/prepare", {"lesson": "local.3"})[0] == 409
    status, panel = c.post("/api/share/prepare", {"lesson": "local.1"})
    assert status == 200, panel
    assert c.post("/api/share/send", {"lesson": "local.1"})[0] == 200
    assert runner.cmds[-1][:4] == ["gh", "pr", "create", "--web"]


def test_kei_approve_points_to_the_review_page_only_for_rules(tmp_path, monkeypatch, capsys):
    from kei.cli import main
    (tmp_path / "kei.toml").write_text(BASE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "shots" / "walk"
    save_state(root, ShotState(stage="deliver", status="needs_approval", request="a walk",
                               history=[note("local.1", "r1", scope="this shot")]))
    assert main(["approve", str(root)]) == 0
    assert "share" not in capsys.readouterr().out


def test_the_page_line_for_a_rule_kept_here():
    assert js('k.shareLine({lesson: "local.2", result: "kept", reason: "fix not confirmed"})') == \
        "Lesson local.2: kept here, not shared: fix not confirmed"
