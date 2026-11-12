"""The local review server: 127.0.0.1 only, a token, a cookie, and Host and Origin checks on every request."""
import http.client
import json
import socket
from urllib.parse import urlsplit

import pytest


class Client:
    """Raw requests with every header under the test's control."""

    def __init__(self, url):
        u = urlsplit(url)
        self.port = u.port
        self.token = dict(p.split("=", 1) for p in u.query.split("&"))["t"]
        self.host = f"127.0.0.1:{self.port}"
        self.cookie = None

    def request(self, method, path, body=None, host=None, headers=None, cookie=True, raw=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or self.host}
        if cookie and self.cookie:
            h["Cookie"] = self.cookie
        if body is not None:
            body = json.dumps(body).encode()
            h["Content-Type"] = "application/json"
            h["Content-Length"] = str(len(body))
        h.update(headers or {})
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in h.items():
            c.putheader(k, v)
        c.endheaders(body if raw is None else raw)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r, data

    def login(self):
        r, _ = self.request("GET", f"/?t={self.token}", cookie=False)
        self.cookie = r.getheader("Set-Cookie").split(";")[0]
        return r

    def post(self, path, body, **kw):
        headers = {"X-Kei-Token": self.token, "Origin": f"http://{self.host}", **kw.pop("headers", {})}
        return self.request("POST", path, body, headers=headers, **kw)


@pytest.fixture
def server(tmp_path):
    from kei.review.server import ReviewServer
    calls = []
    secret = tmp_path / "kei.toml"
    secret.write_text("secret", encoding="utf-8")
    frame = tmp_path / "f0000.png"
    frame.write_bytes(b"\x89PNG\r\n\x1a\nxx")

    def echo(req):
        calls.append(req)
        return 200, {"got": req["body"]}

    s = ReviewServer({"POST /api/echo": echo, "GET /api/hello": lambda req: (200, {"hello": 1})},
                     lambda: {"r1-side-0": frame})
    url = s.start()
    yield s, url, calls
    s.stop()


def test_start_returns_a_127_url_with_a_token(server):
    _, url, _ = server
    u = urlsplit(url)
    assert u.scheme == "http" and u.hostname == "127.0.0.1" and u.port and len(Client(url).token) >= 40


def test_no_cookie_gives_401(server):
    c = Client(server[1])
    assert c.request("GET", "/api/hello")[0].status == 401
    assert c.request("GET", "/")[0].status == 401


def test_the_token_url_sets_the_cookie_and_redirects(server):
    c = Client(server[1])
    r = c.login()
    assert r.status in (302, 303) and r.getheader("Location") == "/"
    cookie = r.getheader("Set-Cookie")
    assert cookie.startswith(f"kei_review_{c.port}=") and "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert "Path=/" in cookie
    r, data = c.request("GET", "/api/hello")
    assert r.status == 200 and json.loads(data) == {"hello": 1}


def test_a_wrong_token_gives_401(server):
    c = Client(server[1])
    r, _ = c.request("GET", "/?t=" + "x" * 43, cookie=False)
    assert r.status == 401 and r.getheader("Set-Cookie") is None


def test_a_wrong_cookie_gives_401(server):
    c = Client(server[1])
    c.cookie = f"kei_review_{c.port}=" + "y" * 43
    assert c.request("GET", "/api/hello")[0].status == 401


def test_a_wrong_host_gives_401(server):
    c = Client(server[1])
    c.login()
    assert c.request("GET", "/api/hello", host=f"evil.example:{c.port}")[0].status == 401
    assert c.request("GET", "/api/hello", host=f"localhost:{c.port}")[0].status == 401
    assert c.request("GET", f"/?t={c.token}", host=f"evil.example:{c.port}", cookie=False)[0].status == 401


def test_post_without_token_header_is_refused(server):
    _, url, calls = server
    c = Client(url)
    c.login()
    r, _ = c.request("POST", "/api/echo", {"a": 1}, headers={"Origin": f"http://{c.host}"})
    assert r.status == 401 and calls == []
    r, _ = c.post("/api/echo", {"a": 1}, headers={"X-Kei-Token": "nope"})
    assert r.status == 401 and calls == []


def test_wrong_origin_is_refused(server):
    _, url, calls = server
    c = Client(url)
    c.login()
    r, _ = c.post("/api/echo", {"a": 1}, headers={"Origin": "http://evil.example"})
    assert r.status == 401 and calls == []
    r, _ = c.request("POST", "/api/echo", {"a": 1}, headers={"X-Kei-Token": c.token})   # no Origin at all
    assert r.status == 401 and calls == []


def test_a_good_post_reaches_the_route(server):
    _, url, calls = server
    c = Client(url)
    c.login()
    r, data = c.post("/api/echo", {"a": "é"})
    assert r.status == 200 and json.loads(data) == {"got": {"a": "é"}} and len(calls) == 1


def test_a_post_that_is_not_json_is_refused(server):
    _, url, calls = server
    c = Client(url)
    c.login()
    r, _ = c.request("POST", "/api/echo", None, headers={"X-Kei-Token": c.token, "Origin": f"http://{c.host}",
                                                          "Content-Type": "text/plain", "Content-Length": "3"})
    assert r.status in (400, 415) and calls == []


def test_a_body_over_8_mb_is_refused(server):
    _, url, calls = server
    c = Client(url)
    c.login()
    r, _ = c.request("POST", "/api/echo", None, headers={"X-Kei-Token": c.token, "Origin": f"http://{c.host}",
                                                          "Content-Type": "application/json",
                                                          "Content-Length": str(8 * 1024 * 1024 + 1)})
    assert r.status == 413 and calls == []


def test_files_are_served_only_from_the_allowlist(server):
    c = Client(server[1])
    c.login()
    r, data = c.request("GET", "/file/r1-side-0")
    assert r.status == 200 and data.startswith(b"\x89PNG") and r.getheader("Content-Type") == "image/png"
    for path in ("/file/nope", "/file?p=../../kei.toml", "/file/..%2F..%2Fkei.toml", "/file/../kei.toml",
                 "/file/%2e%2e/kei.toml", "/kei.toml", "/../kei.toml"):
        r, data = c.request("GET", path)
        assert r.status == 404, path
        assert b"secret" not in data


def test_the_content_policy_is_on_every_response(server):
    c = Client(server[1])
    c.login()
    for path in ("/", "/api/hello", "/file/r1-side-0", "/nope"):
        r, _ = c.request("GET", path)
        assert "default-src 'self'" in (r.getheader("Content-Security-Policy") or ""), path
    r, _ = c.request("GET", "/api/hello", cookie=False)
    assert "default-src 'self'" in r.getheader("Content-Security-Policy")


def test_the_page_carries_the_token_for_its_own_posts(server):
    c = Client(server[1])
    c.login()
    r, data = c.request("GET", "/")
    assert r.status == 200 and c.token.encode() in data and b"<script" in data.lower()


def test_the_server_answers_on_127_0_0_1_only(server):
    s, url, _ = server
    port = urlsplit(url).port
    try:
        others = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        others = set()
    others = {a for a in others if not a.startswith("127.")}
    if not others:
        pytest.skip("this machine has no address other than 127.0.0.1")
    for addr in others:
        with pytest.raises(OSError):
            socket.create_connection((addr, port), timeout=2).close()


def test_stop_closes_the_port(server):
    s, url, _ = server
    port = urlsplit(url).port
    s.stop()
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=2).close()


def test_two_servers_keep_two_cookies_so_one_page_does_not_lock_out_the_other(server):
    """Browsers share cookies across ports: each server names its cookie by its own port."""
    from kei.review.server import ReviewServer
    s2 = ReviewServer({"GET /api/hello": lambda req: (200, {"hello": 2})}, lambda: {})
    try:
        a, b = Client(server[1]), Client(s2.start())
        a.login()
        b.login()
        name_a, name_b = a.cookie.split("=")[0], b.cookie.split("=")[0]
        assert name_a != name_b
        jar = f"{a.cookie}; {b.cookie}"            # what the browser sends to either port
        a.cookie = b.cookie = jar
        assert a.request("GET", "/api/hello")[0].status == 200 and b.request("GET", "/api/hello")[0].status == 200
    finally:
        s2.stop()


def test_a_refused_post_reads_its_body_first_so_the_client_always_gets_the_401(server):
    """The server refuses before it reads the body. Closing a socket with unread data resets the connection on
    Windows, and the client then loses the 401 (ConnectionAbortedError 10053). A body larger than any socket buffer
    makes that race certain: the server must drain a bounded body before it answers a refusal."""
    _, url, calls = server
    c = Client(url)
    c.login()
    big = {"pad": "x" * (4 * 1024 * 1024)}
    r, _ = c.request("POST", "/api/echo", big, headers={"Origin": f"http://{c.host}"})          # no token
    assert r.status == 401 and calls == []
    r, _ = c.request("POST", "/api/echo", None, headers={"X-Kei-Token": c.token, "Origin": f"http://{c.host}",
                                                          "Content-Type": "text/plain",
                                                          "Content-Length": str(4 * 1024 * 1024)},
                     raw=b"y" * (4 * 1024 * 1024))
    assert r.status == 415 and calls == []
