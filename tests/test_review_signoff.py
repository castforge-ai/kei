"""The sign-off page's routes, through the real server with the cookie and the token, as the page calls them."""
import time

import pytest

from kei.book import load_rules
from kei.state import load_state
from reviewkit import PageClient, fake_round, state_hash, waiting_shot

CHECKS = [{"stage": "passes", "from": "critic a", "check": "watch the seam at 24 fps"},
          {"stage": "passes", "from": "critic b", "check": "the heel drop at f12"}]


@pytest.fixture
def page(tmp_path):
    from kei.review.server import ReviewServer
    from kei.review.signoff_routes import SignOffRoutes
    root = waiting_shot(tmp_path, sign_off=CHECKS)
    fake_round(root, "r1", "p1")
    app = SignOffRoutes(root, tmp_path / "lessons.local.md", "r1", None)
    server = ReviewServer(app.routes, app.files)
    client = PageClient(server.start())
    yield root, app, client
    server.stop()


def test_get_shot_shows_the_rounds_the_checklist_and_the_actions(page):
    root, _, c = page
    status, data = c.get("/api/shot")
    assert status == 200
    assert data["shot"] == "walk" and data["status"] == "needs_approval"
    assert data["after"]["round"] == "r1" and data["after"]["pass"] == "p1" and data["before"] is None
    assert [i["checks"] for i in data["checklist"]] == [[i["check"]] for i in CHECKS]
    assert data["checklist_hidden"] == 0
    assert data["actions"] == ["accept", "needs_work", "reject"]
    assert "passes" in data["stages"] and data["default_stage"] == "passes"


def test_the_round_frames_are_served_and_nothing_else(page):
    _, _, c = page
    assert c.get("/file/r1/f0000")[0] == 200
    assert c.get("/file/r1/f0004")[0] == 200
    assert c.get("/file/r1/f0005")[0] == 404
    assert c.get("/file/r1/round.json")[0] == 404


def test_accept_with_every_item_ticked_closes_the_shot(page):
    root, _, c = page
    status, data = c.post("/api/accept", {"round": "r1", "ticked": [i["check"] for i in CHECKS]})
    assert status == 200 and data["status"] == "done"
    s = load_state(root)
    assert s.status == "done" and s.history[-1]["result"] == "approved" and s.history[-1]["round"] == "r1"


def test_accept_with_an_unticked_checklist_item_is_refused(page):
    root, _, c = page
    before = state_hash(root)
    status, data = c.post("/api/accept", {"round": "r1", "ticked": [CHECKS[0]["check"]]})
    assert status == 409 and "heel drop at f12" in data["error"]
    assert state_hash(root) == before


def test_accept_of_an_old_round_is_refused(page):
    root, _, c = page
    fake_round(root, "r2", "p2")          # the shot ran again: a newer round exists
    before = state_hash(root)
    status, data = c.post("/api/accept", {"round": "r1", "ticked": [i["check"] for i in CHECKS]})
    assert status == 409 and "reload" in data["error"]
    assert state_hash(root) == before


def test_accept_with_no_round_named_is_refused(page):
    root, _, c = page
    before = state_hash(root)
    status, _ = c.post("/api/accept", {"ticked": [i["check"] for i in CHECKS]})
    assert status == 400
    assert state_hash(root) == before


def test_needs_work_takes_the_words_and_the_stage(page):
    root, _, c = page
    status, data = c.post("/api/needs-work", {"round": "r1", "text": "les pieds glissent\nà f12", "stage": "passes",
                                              "drawings": []})
    assert status == 200 and data["lesson"] == "local.1"
    s = load_state(root)
    assert (s.stage, s.status) == ("passes", "running")
    assert s.history[-1]["misses"] == ["les pieds glissent\nà f12"]


def test_reject_keeps_the_reason(page, tmp_path):
    root, _, c = page
    status, data = c.post("/api/reject", {"round": "r1", "reason": "wrong brief", "keep_as_lesson": False})
    assert status == 200 and data["status"] == "rejected"
    assert load_state(root).history[-1]["reason"] == "wrong brief"
    assert not (tmp_path / "lessons.local.md").exists()


def test_reject_kept_as_a_lesson(page, tmp_path):
    _, _, c = page
    c.post("/api/reject", {"round": "r1", "reason": "the weight never reads", "keep_as_lesson": True})
    assert [r.id for r in load_rules([tmp_path / "lessons.local.md"])] == ["local.1"]


def test_seen_records_the_loops(page):
    root, _, c = page
    status, _ = c.post("/api/seen", {"round": "r1", "loops": 10})
    assert status == 200
    h = load_state(root).history[-1]
    assert (h["result"], h["round"], h["loops"]) == ("seen", "r1", 10)
    assert load_state(root).status == "needs_approval"


def test_a_shot_not_waiting_shows_its_status_and_no_buttons(tmp_path):
    from kei.review.server import ReviewServer
    from kei.review.signoff_routes import SignOffRoutes
    root = waiting_shot(tmp_path, status="running")
    fake_round(root, "r1")
    app = SignOffRoutes(root, tmp_path / "l.md", "r1", None)
    server = ReviewServer(app.routes, app.files)
    try:
        c = PageClient(server.start())
        status, data = c.get("/api/shot")
        assert status == 200 and data["status"] == "running" and data["actions"] == []
        assert c.post("/api/accept", {"round": "r1", "ticked": []})[0] == 409
        assert load_state(root).status == "running"
    finally:
        server.stop()


def test_idle_server_changes_no_state(tmp_path):
    from kei.review.server import ReviewServer
    from kei.review.signoff_routes import SignOffRoutes
    root = waiting_shot(tmp_path, sign_off=CHECKS)
    fake_round(root, "r1")
    before = state_hash(root)
    app = SignOffRoutes(root, tmp_path / "l.md", "r1", None)
    server = ReviewServer(app.routes, app.files)
    c = PageClient(server.start())
    c.get("/")                # the page loads, reads the shot, and nobody presses anything
    c.get("/api/shot")
    time.sleep(1.5)
    server.stop()
    assert state_hash(root) == before
    assert load_state(root).status == "needs_approval"


def test_no_get_and_no_query_string_can_approve(page):
    root, _, c = page
    before = state_hash(root)
    for path in ("/api/accept", "/api/accept?round=r1", "/?accept=1", "/api/shot?accept=1&round=r1"):
        c.get(path)
    assert state_hash(root) == before


def test_the_page_script_has_no_timer_that_posts():
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "kei" / "review" / "page" / "review.js").read_text(encoding="utf-8")
    # every call that names /api/accept sits in a button's handler (Accept on the full page, Approve after the
    # cards), after a confirm, with no timer
    sites = [i for i in range(len(js)) if js.startswith('"/api/accept"', i)]
    assert len(sites) == 2
    for i in sites:
        handler = js[js.rfind("function ", 0, i):i]
        assert "confirm(" in handler and "setTimeout" not in handler and "setInterval" not in handler
    assert js.count("approveFromCards()") == 2          # its definition, and the one deliberate "accept" effect


def test_the_shot_name_of_dot_is_its_folder_name(tmp_path, monkeypatch):
    from kei.review.signoff_routes import SignOffRoutes
    root = waiting_shot(tmp_path)
    fake_round(root, "r1")
    monkeypatch.chdir(root)
    from pathlib import Path
    status, data = SignOffRoutes(Path("."), tmp_path / "l.md", "r1", None).get_shot({})
    assert data["shot"] == "walk"


def test_before_and_after_on_different_characters_is_said(tmp_path):
    from kei.review.signoff_routes import SignOffRoutes
    root = waiting_shot(tmp_path)
    after = fake_round(root, "r1")
    before = {**fake_round(root, "r0"), "character": "keira", "round": "blocking", "pass": "blocking"}
    _, data = SignOffRoutes(root, tmp_path / "l.md", "r1", before).get_shot({})
    assert data["characters_differ"] is True and after["character"] == "kei"
    _, data = SignOffRoutes(root, tmp_path / "l.md", "r1", None).get_shot({})
    assert data["characters_differ"] is False


def test_the_page_lists_only_the_checks_about_the_round_on_screen_and_accept_needs_only_those(tmp_path):
    from kei.review.server import ReviewServer
    from kei.review.signoff_routes import SignOffRoutes
    stale = {"stage": "blocking", "from": "critic a", "check": "BLK42: watch out_blocking/blocking_x10.mp4 for the seam"}
    now = [{"stage": "passes", "from": "critic a", "check": "HND2: f19-f24, the near hand over the thigh in "
                                                             "out_p1/delivery/playback_x10.mp4"},
           {"stage": "passes", "from": "critic b", "check": "HND30: watch F19-F24 in out_p1/playback_x10.mp4; the "
                                                             "near hand swings free of the thigh"}]
    root = waiting_shot(tmp_path, sign_off=[stale, *now])
    fake_round(root, "r1", "p1")
    app = SignOffRoutes(root, tmp_path / "l.md", "r1", None)
    server = ReviewServer(app.routes, app.files)
    try:
        c = PageClient(server.start())
        data = c.get("/api/shot")[1]
        [item] = data["checklist"]
        assert set(item["from"]) == {"critic a", "critic b"} and set(item["checks"]) == {i["check"] for i in now}
        assert data["checklist_hidden"] == 1 and "out_blocking" not in str(data["checklist"])
        assert c.post("/api/accept", {"round": "r1", "ticked": [now[0]["check"]]})[0] == 409   # half an item
        status, _ = c.post("/api/accept", {"round": "r1", "ticked": [i["check"] for i in now]})
        assert status == 200 and load_state(root).status == "done"
        assert len(load_state(root).sign_off) == 3          # the stale check stays in state.json
    finally:
        server.stop()


def test_the_page_never_ticks_a_box_for_the_author():
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "kei" / "review" / "page" / "review.js").read_text(encoding="utf-8")
    assert "checked: true" not in js and ".checked = true" not in js


def test_needs_work_from_the_cards_keeps_each_answer_in_the_history(page):
    root, _, c = page
    cards = [{"check": CHECKS[0]["check"], "answer": "no", "note": "the seam hitches"},
             {"check": CHECKS[1]["check"], "answer": "yes"}]
    status, data = c.post("/api/needs-work", {"round": "r1", "text": "the seam hitches", "stage": "passes",
                                              "drawings": [], "cards": cards})
    assert status == 200, data
    h = load_state(root).history[-1]
    assert h["misses"] == ["the seam hitches"] and h["cards"] == cards


def test_cards_that_are_not_a_list_of_answers_are_refused(page):
    root, _, c = page
    before = state_hash(root)
    status, _ = c.post("/api/needs-work", {"round": "r1", "text": "x", "stage": "passes", "cards": "yes"})
    assert status == 400 and state_hash(root) == before


def _real_pass(root, name, note="x"):
    import json as _json
    d = root / f"out_{name}"
    d.mkdir(exist_ok=True)
    (d / "shot.json").write_text(_json.dumps({"rig": "v4", "frames": 4, "note": note}), encoding="utf-8")


def test_accept_is_refused_when_a_new_pass_appeared_since_the_round(page):
    root, _, c = page
    _real_pass(root, "p9")                      # kei run in a terminal wrote a newer pass; no round shows it
    status, data = c.post("/api/accept", {"round": "r1", "ticked": [i["check"] for i in CHECKS]})
    assert status == 409 and "restart kei review" in data["error"]
    assert load_state(root).status == "needs_approval"


def test_accept_is_refused_when_the_rounds_pass_changed_since_it_was_drawn(page):
    root, _, c = page
    _real_pass(root, "p1", note="changed after the round was drawn")
    status, data = c.post("/api/accept", {"round": "r1", "ticked": [i["check"] for i in CHECKS]})
    assert status == 409 and "restart kei review" in data["error"]
    assert load_state(root).status == "needs_approval"
