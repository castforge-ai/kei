"""The Settings tab: the same rows and the same checks as kei settings, through the real server with the cookie and
the token."""
import hashlib
import shutil
from pathlib import Path

import pytest

from kei.config import load_config
from reviewkit import PageClient

EXAMPLE = Path(__file__).resolve().parent.parent / "kei.example.toml"


class Ran(list):
    printed: list


def which_all(name):
    return f"/usr/bin/{name}"


@pytest.fixture
def tab(tmp_path):
    from kei.review.server import ReviewServer
    from kei.review.settings_routes import SettingsRoutes
    toml = tmp_path / "kei.toml"
    shutil.copy(EXAMPLE, toml)
    ran = Ran()

    def runner(cmd, timeout):
        ran.append((list(cmd), timeout))
        return 0, f"{cmd[0]} 9.9.9"
    printed = []
    routes = SettingsRoutes(toml, which=which_all, runner=runner, announce=printed.append)
    server = ReviewServer(routes.routes, lambda: {})
    ran.printed = printed
    yield toml, PageClient(server.start()), ran
    server.stop()


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_rows_match_kei_settings(tab):
    from kei.settings import current
    toml, c, _ = tab
    status, data = c.get("/api/settings")
    assert status == 200 and data["rows"] == current(toml) and data["sha256"] == sha(toml)


def test_a_good_save_changes_the_file(tab):
    toml, c, _ = tab
    status, data = c.post("/api/settings", {"changes": {"share.mode": "never", "limits.max_attempts": 4},
                                            "sha256": sha(toml), "confirm_commands": False})
    assert status == 200 and data["saved"] is True, data
    cfg = load_config(toml)
    assert (cfg.share, cfg.max_attempts) == ("never", 4) and data["sha256"] == sha(toml)
    assert ["share.mode", "ask", "never"] in data["changes"]


def test_stale_hash_is_refused(tab):
    toml, c, _ = tab
    before = toml.read_bytes()
    status, data = c.post("/api/settings", {"changes": {"share.mode": "never"}, "sha256": "0" * 64})
    assert status == 409 and "reload" in data["error"] and toml.read_bytes() == before


def test_a_refused_save_returns_the_key_and_the_reason_and_changes_nothing(tab):
    toml, c, _ = tab
    before = toml.read_bytes()
    status, data = c.post("/api/settings", {"changes": {"limits.max_attempts": 0}, "sha256": sha(toml)})
    assert status == 409 and data["key"] == "limits.max_attempts" and "max_attempts" in data["error"]
    assert toml.read_bytes() == before


def test_a_command_change_needs_the_code_kei_prints_in_the_terminal(tab):
    import re
    toml, c, ran = tab
    before = toml.read_bytes()
    change = {"critics[codex].cmd": ["codex", "exec", "-"]}
    status, data = c.post("/api/settings", {"changes": change, "sha256": sha(toml), "confirm_commands": True})
    assert status == 200 and data["saved"] is False and data["code_in_terminal"] is True   # the page alone: no
    [item] = data["confirm"]
    assert item["key"] == "critics[codex].cmd" and item["old"][0] == "codex" and item["new"] == ["codex", "exec", "-"]
    assert toml.read_bytes() == before
    code = re.search(r"type (\d{6}) on the page", ran.printed[-1]).group(1)
    assert code not in str(data)                                                  # the code never reaches the page
    status, data = c.post("/api/settings", {"changes": change, "sha256": sha(toml), "confirm_code": "000000"
                                            if code != "000000" else "111111"})
    assert data["saved"] is False and data["wrong_code"] is True and toml.read_bytes() == before
    code = re.search(r"type (\d{6}) on the page", ran.printed[-1]).group(1)       # a wrong code spends it
    status, data = c.post("/api/settings", {"changes": change, "sha256": sha(toml), "confirm_code": code})
    assert status == 200 and data["saved"] is True
    assert load_config(toml).critics[1].cmd == ["codex", "exec", "-"]


def test_test_seat_runs_version_with_a_10_second_limit(tab):
    _, c, ran = tab
    status, data = c.post("/api/settings/test-seat", {"key": "critics[codex].cmd"})
    assert status == 200 and data["ok"] is True and "9.9.9" in data["output"]
    assert ran == [(["codex", "--version"], 10)]


def test_a_settings_post_needs_the_token(tab):
    toml, c, _ = tab
    before = toml.read_bytes()
    import http.client
    import json
    conn = http.client.HTTPConnection("127.0.0.1", c.port, timeout=10)
    body = json.dumps({"changes": {"share.mode": "never"}, "sha256": sha(toml)}).encode()
    conn.request("POST", "/api/settings", body=body, headers={"Cookie": c.cookie, "Content-Type": "application/json",
                                                               "Origin": f"http://{c.host}"})
    assert conn.getresponse().status == 401
    assert toml.read_bytes() == before


def test_every_review_page_carries_the_settings_routes(tmp_path):
    from kei.review import app
    server, _ = app.list_server(tmp_path, settings=tmp_path / "kei.toml")
    assert "GET /api/settings" in server.routes and "POST /api/settings" in server.routes


def test_test_seat_on_a_command_written_as_text_says_how_to_write_it(tab):
    toml, c, ran = tab
    text = toml.read_text(encoding="utf-8")
    start = text.index("cmd = [", text.index("[animator]"))
    end = text.index("]\n", start) + 1
    toml.write_text(text[:start] + 'cmd = "claude -p"' + text[end:], encoding="utf-8")
    status, data = c.post("/api/settings/test-seat", {"key": "animator.cmd"})
    assert status == 409 and "list" in data["error"] and '["claude", "-p"]' in data["error"]
    assert ran == []


def test_a_single_use_link_opens_once_and_its_token_is_not_the_pages(tmp_path):
    import http.client
    from urllib.parse import urlsplit
    from kei.review.server import ReviewServer
    server = ReviewServer({}, lambda: {}, single_use_link=True)
    url = server.start()
    try:
        u = urlsplit(url)
        PageClient(url)                                                  # the first load logs in
        c = http.client.HTTPConnection("127.0.0.1", u.port, timeout=10)
        c.request("GET", f"/?{u.query}", headers={"Host": f"127.0.0.1:{u.port}"})
        r = c.getresponse()
        assert r.status == 410 and b"works once" in r.read()             # a copied link opens nothing
        assert server.link != server.token                               # and it never was the page's POST token
    finally:
        server.stop()
