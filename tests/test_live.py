"""The live page: what it reads from the shot, the server's checks, the switch, and kei run starting it."""
import http.client
import json
import sys
from pathlib import Path

import pytest

from kei.cli import main
from kei.config import ConfigError, load_config_text
from kei.live import serve as live_serve
from kei.live.snapshot import files, keep_plan, refs_table, snapshot
from kei.settings import current
from kei.state import ShotState, save_state
from reviewkit import PNG, PageClient

PAGE = Path(__file__).resolve().parents[1] / "kei" / "live" / "page"
SEAT = json.dumps([sys.executable, "-c", "pass"])
BASE = f'[animator]\ncmd = {SEAT}\n[[critics]]\nname = "c"\ncmd = {SEAT}\n'

REFS = """# REFS
| Ref | Tier | What it gives | Our checks | Verdict |
|---|---|---|---|---|
| 1. A gait study, 2010 | R | Knee about **5 deg** at contact. | Matches the build. | keep: the order of events |
| 2. A pose display, 2004 | R | A static pose. | Not a gait. | reject: for amounts |
"""


def plan(note="first"):
    return {"fps": 30, "frames": 34, "loop": {"closing_frame": 34}, "root": {"keys": [[0, 0.0], [34, 1.5867]]},
            "keys": [
        {"f": 0, "function": "passing", "kind": "key", "note": note,
         "drawing": {"lines": [[0, 0.9, 0, 1.6]], "action": [[0, 0], [0, 1.7]], "com": [0, 1.0]}},
        {"f": 7, "function": "contact", "kind": "key", "note": "",
         "drawing": {"lines": [[0, 0.9, 0.2, 0]]}}]}


def passed(stage, at):
    return {"stage": stage, "attempt": 1, "result": "pass", "at": at, "misses": []}


@pytest.fixture
def shot(tmp_path):
    root = tmp_path / "shots" / "walk"
    (root / "plan").mkdir(parents=True)
    hist = [passed("brief", "2026-11-11T10:00:00+00:00"), passed("rig", "2026-11-11T10:05:00+00:00"),
            passed("weight", "2026-11-11T10:09:00+00:00"), passed("understanding", "2026-11-11T10:10:00+00:00"),
            passed("references", "2026-11-11T10:14:00+00:00"), passed("study", "2026-11-11T10:17:00+00:00"),
            {"stage": "plan", "attempt": 1, "result": "send_back", "at": "2026-11-11T11:00:00+00:00",
             "misses": ["critic c: Frames 9-13 and 26-30: the mass stays behind the support foot."]}]
    save_state(root, ShotState(stage="plan", status="running", request="a relaxed walk", history=hist))
    (root / "plan" / "plan.json").write_text(json.dumps(plan()), encoding="utf-8")
    (root / "plan" / "plan_sheet.png").write_bytes(PNG)
    (root / "REFS.md").write_text(REFS, encoding="utf-8")
    (root / "PLAN.md").write_text("Idea sentence: an at-ease walk.\n", encoding="utf-8")
    (root / "out_blocking" / "frames").mkdir(parents=True)
    (root / "out_blocking" / "frames" / "f0000.png").write_bytes(PNG)
    (root / "out_blocking" / "blocking.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    return root


def test_the_snapshot_reads_the_stages_the_plan_and_the_references(shot):
    s = snapshot(shot)
    states = {x["id"]: x["state"] for x in s["stages"]}
    assert [states[k] for k in ("brief", "study", "plan", "blocking", "deliver")] == \
        ["done", "done", "working", "todo", "todo"]
    assert s["request"] == "a relaxed walk" and s["plan"]["frames"] == 34
    assert [k["function"] for k in s["plan"]["keys"]] == ["passing", "contact"]
    assert [r["call"] for r in s["refs"]] == ["keep", "reject"] and "**" not in s["refs"][0]["gives"]
    assert s["facts"] == {"Idea sentence": "an at-ease walk."}
    assert [p["name"] for p in s["passes"]] == ["blocking"]
    assert len(s["passes"][0]["frames"]) == 1 and s["passes"][0]["videos"][0]["name"] == "blocking.mp4"
    assert [i["name"] for i in s["images"]] == ["plan_sheet"]      # pass frames are in the pass, not the sheets


def test_a_waiting_shot_carries_its_question(shot):
    save_state(shot, ShotState(stage="references", status="needs_answer", request="a relaxed walk"))
    (shot / "QUESTIONS.md").write_text("# Questions\n1. Which reference?", encoding="utf-8")
    s = snapshot(shot)
    assert s["pending"].startswith("# Questions")
    assert {x["id"]: x["state"] for x in s["stages"]}["references"] == "waiting"


def test_each_new_plan_is_kept_once_so_the_page_can_show_the_tries(shot):
    assert keep_plan(shot) is True
    assert keep_plan(shot) is False                       # the same content is not kept twice
    (shot / "plan" / "plan.json").write_text(json.dumps(plan("second")), encoding="utf-8")
    assert keep_plan(shot) is True
    v = snapshot(shot)["plan_versions"]
    assert [x["n"] for x in v] == [1, 2] and [x["keys"][0]["note"] for x in v] == ["first", "second"]


def test_files_are_named_by_ids_never_by_paths_and_hidden_folders_stay_out(shot):
    (shot / ".kei" / "secret.png").write_bytes(PNG)
    ids = files(shot)
    assert all("/" not in i and "\\" not in i and ".." not in i for i in ids)
    assert {p.name for p in ids.values()} == {"plan_sheet.png", "f0000.png", "blocking.mp4"}


def test_refs_rows_without_a_numbered_ref_are_left_out():
    assert refs_table("| Ref | Tier | a | b | c |\n| x | R | a | b | keep: y |") == []


def test_the_server_refuses_without_the_link_then_serves_the_snapshot_and_the_files(shot):
    server, live, url = live_serve.start(shot)
    try:
        c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
        c.request("GET", "/api/live", headers={"Host": f"127.0.0.1:{server.port}"})
        assert c.getresponse().status == 401
        c.close()
        page = PageClient(url)
        status, data = page.get("/api/live")
        assert status == 200 and data["shot"] == "walk" and data["version"] == live.version
        assert page.get(f"/api/live?v={live.version}") == (200, {"version": live.version, "same": True})
        sheet = data["images"][0]["id"]
        assert page.get(f"/file/{sheet}") == (200, PNG)
        assert page.get("/file/..%2F..%2Fkei.toml")[0] == 404
        assert page.get("/live.js")[0] == 200
        assert page.post("/api/live", {})[0] == 404        # read only: no POST route
    finally:
        server.stop()


def test_the_page_loads_nothing_from_the_network_and_has_no_inline_code():
    html = (PAGE / "index.html").read_text(encoding="utf-8")
    assert "<script>" not in html and "<style>" not in html and ' style="' not in html
    for name in ("index.html", "live.js", "live.css"):
        text = (PAGE / name).read_text(encoding="utf-8")
        assert "http://" not in text and "https://" not in text, name
        assert chr(0x2014) not in text, name                  # no em dashes in what the author reads
    assert ' style="' not in (PAGE / "live.js").read_text(encoding="utf-8")


def test_answering_knows_its_own_shot(shot, tmp_path):
    server, live, url = live_serve.start(shot)
    try:
        f = live_serve.server_file(shot)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"pid": 1, "port": server.port, "url": url}), encoding="utf-8")
        assert live_serve.answering(shot) == url
        other = tmp_path / "other"
        live_serve.server_file(other).parent.mkdir(parents=True)
        live_serve.server_file(other).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        assert live_serve.answering(other) is None          # a port that answers for another shot is not ours
    finally:
        server.stop()


def test_the_switch_is_on_by_default_and_off_is_kept(tmp_path):
    p = tmp_path / "kei.toml"
    c = load_config_text(BASE, p)
    assert (c.live_page, c.live_open) == ("on", "on")
    c = load_config_text(BASE + '[live]\npage = "off"\nopen = "off"\n', p)
    assert (c.live_page, c.live_open) == ("off", "off")
    with pytest.raises(ConfigError, match="live.page"):
        load_config_text(BASE + '[live]\npage = "yes"\n', p)
    p.write_text(BASE, encoding="utf-8")
    rows = {r["key"]: r for r in current(p)}
    assert rows["live.page"]["value"] == "on" and rows["live.page"]["choices"] == ["on", "off"]


@pytest.mark.parametrize("switch, started", [("on", True), ("off", False)])
def test_kei_run_starts_the_live_page_unless_it_is_off(tmp_path, monkeypatch, capsys, switch, started):
    monkeypatch.delenv("KEI_NO_LIVE", raising=False)
    calls = []
    monkeypatch.setattr(live_serve, "ensure",
                        lambda shot, open_browser=True: calls.append(open_browser) or "http://127.0.0.1:1/?t=x")
    cfgp = tmp_path / "kei.toml"
    cfgp.write_text(BASE + f'[limits]\nmax_attempts = 1\n[live]\npage = "{switch}"\nopen = "off"\n',
                    encoding="utf-8")
    main(["run", str(tmp_path / "shot"), "--request", "a box falls", "--config", str(cfgp)])
    assert calls == ([False] if started else [])
    assert ("live page: http://127.0.0.1:1/?t=x" in capsys.readouterr().out) is started


def test_the_snapshot_says_whether_kei_planned_a_loop_and_how_far_the_root_travels(shot):
    p = snapshot(shot)["plan"]
    assert p["loop"] is True and p["travel"] == [[0, 0.0], [34, 1.5867]]
    data = json.loads((shot / "plan" / "plan.json").read_text(encoding="utf-8"))
    data.pop("loop")
    data["root"] = {"keys": [[0, 0.0], [34, 0.0]]}
    (shot / "plan" / "plan.json").write_text(json.dumps(data), encoding="utf-8")
    p = snapshot(shot)["plan"]
    assert p["loop"] is False and p["travel"] == []            # in place, plays once


def test_a_plan_length_written_as_a_range_reaches_the_page_as_one_number(shot):
    data = json.loads((shot / "plan" / "plan.json").read_text(encoding="utf-8"))
    data["frames"] = [0, 150]
    (shot / "plan" / "plan.json").write_text(json.dumps(data), encoding="utf-8")
    assert snapshot(shot)["plan"]["frames"] == 150
