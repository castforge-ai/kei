"""kei review: the command that renders the round, starts the local page and prints its address."""
import json
import re
import shutil
from pathlib import Path

import pytest

from kei.cli import main
from kei.state import ShotState, save_state
from reviewkit import PageClient, fake_round

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "stepped_walk"


@pytest.fixture
def served(monkeypatch):
    """Replace the wait for Ctrl+C: the test talks to the running server, then closes it from the page."""
    seen = {}

    def serve(server):
        seen["client"] = c = PageClient(seen["url"]())
        seen["mode"] = c.get("/api/mode")
        seen["shot"] = c.get("/api/shot") if seen["mode"][1].get("mode") == "shot" else None
        seen["close"] = c.post("/api/close", {})
        server.closed.wait(5)
        seen["stopped"] = server.closed.is_set()

    import kei.review.app as app
    monkeypatch.setattr(app, "serve", serve)
    monkeypatch.setattr(app.webbrowser, "open", lambda url: seen.setdefault("browser", url))
    return seen


def url_from(capsys_text):
    return re.search(r"http://127\.0\.0\.1:\d+/\?t=[\w-]+", capsys_text).group(0)


def test_no_browser_prints_a_127_url_with_a_token_and_the_server_answers(tmp_path, capsys, served):
    root = tmp_path / "walk"
    shutil.copytree(EXAMPLE / "out_blocking", root / "out_blocking", ignore=shutil.ignore_patterns("frames", "*.png"))
    save_state(root, ShotState(stage="deliver", status="needs_approval", request="a walk"))
    served["url"] = lambda: url_from(capsys.readouterr().out)
    assert main(["review", str(root), "--no-browser", "--size", "16"]) == 0
    assert "browser" not in served
    status, data = served["shot"]
    assert status == 200 and data["after"]["round"] == "r1" and data["actions"] == ["accept", "needs_work", "reject"]
    assert served["close"][0] == 200 and served["stopped"]
    assert (root / "review" / "r1" / "round.json").is_file()


def test_the_browser_opens_unless_no_browser(tmp_path, capsys, served):
    root = tmp_path / "walk"
    root.mkdir()
    save_state(root, ShotState(stage="deliver", status="needs_approval", request="a walk"))
    (root / "out_blocking").mkdir()
    shutil.copy(EXAMPLE / "out_blocking" / "shot.json", root / "out_blocking" / "shot.json")
    fake_round(root, "r1", "blocking")
    import hashlib
    meta = json.loads((root / "review/r1/round.json").read_text(encoding="utf-8"))
    meta["shot_sha256"] = hashlib.sha256((root / "out_blocking" / "shot.json").read_bytes()).hexdigest()
    (root / "review/r1/round.json").write_text(json.dumps(meta), encoding="utf-8")   # reused: no render
    served["url"] = lambda: served["browser"]
    assert main(["review", str(root)]) == 0
    assert served["browser"].startswith("http://127.0.0.1:") and "?t=" in served["browser"]


def test_a_shot_folder_with_no_state_is_one_line_and_exit_1(tmp_path, capsys):
    assert main(["review", str(tmp_path), "--no-browser"]) == 1
    out = "".join(capsys.readouterr())
    assert len(out.strip().splitlines()) == 1 and "Traceback" not in out and "state" in out


def test_the_list_mode_finds_two_waiting_shots_and_skips_a_done_one(tmp_path, capsys, monkeypatch, served):
    for name, status in (("a", "needs_approval"), ("b", "done"), ("c", "needs_approval")):
        save_state(tmp_path / name, ShotState(stage="deliver", status=status, request="x"))
    (tmp_path / "lessons" / "incoming" / "2026-11-03-heel").mkdir(parents=True)
    (tmp_path / "lessons" / "incoming" / "2026-11-03-heel" / "bundle.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    served["url"] = lambda: url_from(capsys.readouterr().out)
    assert main(["review", "--no-browser"]) == 0
    status, mode = served["mode"]
    assert status == 200 and mode["mode"] == "list"
    assert [s["shot"] for s in mode["shots"]] == ["a", "c"]
    assert [b["name"] for b in mode["lessons"]] == ["2026-11-03-heel"]
    assert "kei review a" in mode["shots"][0]["command"].replace("\\", "/")


def test_list_mode_prints_the_waiting_shots_too(tmp_path, capsys, monkeypatch, served):
    save_state(tmp_path / "a", ShotState(stage="deliver", status="needs_approval", request="x"))
    monkeypatch.chdir(tmp_path)
    out = []
    served["url"] = lambda: (out.append(capsys.readouterr().out), url_from(out[-1]))[1]
    assert main(["review", "--no-browser"]) == 0
    assert "a" in out[0] and "waiting" in out[0]
