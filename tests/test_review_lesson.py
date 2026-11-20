"""A maintainer reviews a shared lesson on the same page: the bundle is checked first, both cases are drawn on the
reference character, Kei's own numbers sit beside the bundle's, and the verdict goes into the lesson folder."""
import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from kei.book import BUNDLED_BOOK, load_topics
from kei.cli import main
from kei.lessons import add_lesson
from reviewkit import PageClient
from test_share_bundle import seat_writing, sliding, walk


class Runner:
    def __init__(self):
        self.cmds = []

    def __call__(self, cmd):
        self.cmds.append(list(cmd))
        return 0


def make_bundle(tmp_path, text="the planted foot hovers over the floor at contact; keep the sole on the ground"):
    from kei.share import build_bundle
    lessons = tmp_path / "contrib" / "lessons.local.md"
    add_lesson(lessons, text, "passes")
    return build_bundle("local.1", lessons, tmp_path / "clone" / "lessons" / "incoming" / "2026-11-03-hover",
                        seat_writing(sliding(walk()), walk()))


SMALL_BOOK = """# A one-file test book

### K1. Plan before the first key
stages: plan, blocking

No key goes into the shot before the plan exists.

### K2. Judge by eye
stages: all

Numbers point where to look; the eye decides.

### K99. Planted foot stays on the ground
stages: passes

A planted foot never hovers over the floor at contact.
"""


def book_copy(tmp_path):
    b = tmp_path / "clone" / "book" / "rules.md"
    b.parent.mkdir(parents=True, exist_ok=True)
    b.write_text(SMALL_BOOK, encoding="utf-8")
    return b


@pytest.fixture
def lesson(tmp_path):
    from kei.review.lesson_routes import LessonRoutes
    from kei.review.server import ReviewServer
    bundle = make_bundle(tmp_path)
    book = book_copy(tmp_path)
    runner = Runner()
    routes = LessonRoutes(bundle, book, tmp_path / "renders", runner=runner, author="octo", size=16)
    server = ReviewServer(routes.routes, routes.files)
    yield bundle, book, runner, PageClient(server.start())
    server.stop()


def test_a_good_bundle_opens(lesson):
    bundle, _, _, c = lesson
    assert c.get("/api/mode")[1] == {"mode": "lesson"}
    status, data = c.get("/api/lesson")
    assert status == 200
    assert "planted foot hovers" in data["text"] and data["stage"] == "passes" and data["author"] == "octo"
    assert data["rounds"]["fails"]["character"] == "kei" and data["rounds"]["passes"]["frames"] >= 1
    assert c.get(f"/file/{data['rounds']['fails']['round']}/f0000")[0] == 200
    assert data["check"] == "hover" and data["measured"] is True
    assert all(row["differs"] is False for row in data["numbers"])
    assert data["verdict"] is None


def test_a_bad_bundle_is_refused_with_the_reason(tmp_path):
    from kei.review.lesson_routes import LessonRoutes
    from kei.share import BundleError
    bundle = make_bundle(tmp_path)
    (bundle / "evil.sh").write_text("rm -rf /", encoding="utf-8")
    with pytest.raises(BundleError, match="evil.sh"):
        LessonRoutes(bundle, book_copy(tmp_path), tmp_path / "renders", runner=Runner(), size=16)


def test_kei_review_lesson_on_a_bad_bundle_is_one_line_and_exit_1(tmp_path, capsys):
    bundle = make_bundle(tmp_path)
    (bundle / "lesson.md").write_text("changed", encoding="utf-8")
    assert main(["review", "--lesson", str(bundle), "--no-browser"]) == 1
    out = "".join(capsys.readouterr())
    assert len(out.strip().splitlines()) == 1 and "lesson.md" in out and "Traceback" not in out


def test_number_mismatch_is_flagged(tmp_path):
    from kei.review.lesson_routes import LessonRoutes
    bundle = make_bundle(tmp_path)
    numbers = json.loads((bundle / "numbers.json").read_text(encoding="utf-8"))
    numbers["fails"]["counts"]["hover"] = 99
    numbers["fails"]["count"] = 99
    (bundle / "numbers.json").write_text(json.dumps(numbers), encoding="utf-8")
    meta = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    meta["files"]["numbers.json"] = hashlib.sha256((bundle / "numbers.json").read_bytes()).hexdigest()
    (bundle / "bundle.json").write_text(json.dumps(meta), encoding="utf-8")
    data = LessonRoutes(bundle, book_copy(tmp_path), tmp_path / "renders", runner=Runner(), size=16).lesson()
    row = next(r for r in data["numbers"] if r["case"] == "fails" and r["check"] == "hover")
    assert row["bundle"] == 99 and row["kei"] != 99 and row["differs"] is True
    assert data["any_differs"] is True


def test_the_overlap_list_names_book_rules_of_the_stage_that_share_words(lesson):
    _, _, _, c = lesson
    overlap = c.get("/api/lesson")[1]["overlap"]
    assert any(o["id"] == "K99" for o in overlap)
    assert all(set(o["words"]) for o in overlap)


@pytest.mark.parametrize("verdict", ["needs_work", "reject"])
def test_needs_work_and_reject_write_the_verdict_and_leave_the_book(lesson, verdict):
    bundle, book, runner, c = lesson
    before = book.read_bytes()
    status, data = c.post("/api/lesson/verdict", {"verdict": verdict, "text": "le cas qui passe flotte aussi",
                                                  "drawings": []})
    assert status == 200, data
    v = json.loads((bundle / "verdict.json").read_text(encoding="utf-8"))
    assert v["verdict"] == verdict and v["text"] == "le cas qui passe flotte aussi" and v["at"] and v["kei_version"]
    assert v["drawings"] == [] and "rule" not in v
    assert book.read_bytes() == before
    assert not any(cmd[:2] in (["git", "push"], ["gh", "pr"]) and "merge" in cmd for cmd in runner.cmds)
    assert not any(cmd[:2] == ["git", "push"] for cmd in runner.cmds)


def test_accept_adds_the_rule_with_a_new_id_that_does_not_collide(lesson):
    bundle, book, runner, c = lesson
    old_ids = {r.id for t in load_topics(book) for r in t.rules}
    status, data = c.post("/api/lesson/verdict", {"verdict": "accept", "text": "clear and measured", "drawings": []})
    assert status == 200, data
    v = json.loads((bundle / "verdict.json").read_text(encoding="utf-8"))
    new_id = v["rule"]
    assert new_id not in old_ids and new_id == "K100"
    rules = {r.id: r for t in load_topics(book) for r in t.rules}
    assert "hovers over the floor" in rules[new_id].text and rules[new_id].stages == ("passes",)
    assert "(provisional)" not in rules[new_id].title and "local." not in book.read_text(encoding="utf-8")
    assert not any(cmd[:2] == ["git", "push"] for cmd in runner.cmds)


def test_a_second_accept_does_not_add_the_rule_twice(lesson):
    _, book, _, c = lesson
    c.post("/api/lesson/verdict", {"verdict": "accept", "text": "ok", "drawings": []})
    status, data = c.post("/api/lesson/verdict", {"verdict": "accept", "text": "ok", "drawings": []})
    assert status == 409
    assert book.read_text(encoding="utf-8").count("stages: passes\n\nthe planted foot hovers") == 1


def test_a_verdict_with_drawings_keeps_them_beside_it(lesson):
    import base64
    from reviewkit import PNG
    bundle, _, _, c = lesson
    stroke = {"frame": 1, "view": "side", "points": [[1, 2], [3, 4]], "color": "#ff3b6b", "width": 3}
    status, data = c.post("/api/lesson/verdict", {"verdict": "needs_work", "text": "x", "drawings": {
        "strokes": [stroke], "pngs": {"f0001_side": base64.b64encode(PNG).decode()}}})
    assert status == 200, data
    v = json.loads((bundle / "verdict.json").read_text(encoding="utf-8"))
    assert v["drawings"] == ["verdict_drawings/1/f0001_side.png", "verdict_drawings/1/strokes.json"]
    assert (bundle / "verdict_drawings" / "1" / "f0001_side.png").read_bytes() == PNG


def test_a_reviewed_bundle_still_passes_its_check(lesson):
    from kei.share import check_bundle
    bundle, _, _, c = lesson
    c.post("/api/lesson/verdict", {"verdict": "reject", "text": "x", "drawings": []})
    check_bundle(bundle)


def test_review_pr_checks_out_with_gh_and_never_pushes(tmp_path, monkeypatch):
    from kei.review import app
    bundle = make_bundle(tmp_path)
    runner = Runner()

    def reader(cmd):
        runner.cmds.append(list(cmd))
        return json.dumps({"author": {"login": "octo"},
                           "files": [{"path": f"lessons/incoming/{bundle.name}/lesson.md"}]})
    monkeypatch.chdir(tmp_path / "clone")
    routes = app.pr_routes(12, Path.cwd(), book_copy(tmp_path), runner=runner, reader=reader, size=16)
    assert runner.cmds[0] == ["gh", "pr", "checkout", "12"]
    assert routes.lesson()["author"] == "octo"
    routes.verdict({"body": {"verdict": "accept", "text": "ok", "drawings": []}})
    assert not any(cmd[0] == "git" and "push" in cmd for cmd in runner.cmds)
    assert not any("merge" in cmd for cmd in runner.cmds)


def test_accept_on_the_shipped_book_takes_the_id_prefix_of_the_topic_it_lands_in(tmp_path):
    from kei.review.lesson_routes import LessonRoutes
    bundle = make_bundle(tmp_path)
    book = tmp_path / "clone" / "kei" / "book"
    shutil.copytree(BUNDLED_BOOK, book)
    routes = LessonRoutes(bundle, book, tmp_path / "renders", runner=Runner(), size=16)
    old_ids = {r.id for t in load_topics(book) for r in t.rules}
    status, record = routes.verdict({"body": {"verdict": "accept", "text": "ok", "drawings": []}})
    assert status == 200, record
    landed = {t.name: t for t in load_topics(book)}[Path(record["book"]).stem]
    assert record["rule"] not in old_ids and landed.rules[-1].id == record["rule"]
    prefix = re.fullmatch(r"([A-Za-z]+)\d+", landed.rules[0].id).group(1)
    assert re.fullmatch(prefix + r"\d+", record["rule"]), (record, prefix)
