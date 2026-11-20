"""The local review server: standard library only, bound to 127.0.0.1, one token per run, and (for kei review) a link
that works once.

Every request needs the session cookie (set by the first load of the token URL) and the Host 127.0.0.1:<port>, which
blocks DNS rebinding. Every POST also needs the token in the X-Kei-Token header and the page's own Origin, so a web
page in the same browser cannot post to it. Anything else gets 401 and reaches no route. Files are served only from
an allowlist of ids, never from a path in the request. The page loads nothing from the network."""
from __future__ import annotations

import hmac
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

PAGE_DIR = Path(__file__).resolve().parent / "page"
PAGE_FILES = {"/review.js": ("review.js", "text/javascript; charset=utf-8"),
              "/review.css": ("review.css", "text/css; charset=utf-8")}
TOKEN_SLOT = "{{KEI_TOKEN}}"
USED_LINK = ("This review link was already opened, and a link works once. Use the tab it opened, or stop kei review "
             "and run it again for a new link.")
COOKIE = "kei_review"     # the cookie is named kei_review_<port>: browsers share cookies across ports
MAX_BODY = 8 * 1024 * 1024
DRAIN_SECONDS = 1     # how long a refused body may pause before the server stops reading it (loopback never pauses)
CSP = ("default-src 'self'; img-src 'self' data: blob:; frame-ancestors 'none'; base-uri 'none'; "
       "form-action 'none'")
TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".mp4": "video/mp4",
         ".json": "application/json", ".md": "text/plain; charset=utf-8",
         ".txt": "text/plain; charset=utf-8"}

Route = Callable[[dict], tuple]   # request {"method", "path", "query", "body"} -> (status, JSON-able object)


def _same(a: str | None, b: str) -> bool:
    return a is not None and hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class ReviewServer:
    def __init__(self, routes: dict[str, Route], files: Callable[[], dict[str, Path]], port: int = 0,
                 page_dir: Path = PAGE_DIR, page_files: dict | None = None, name: str = "kei-review",
                 single_use_link: bool = False):
        self.routes = dict(routes)
        self.page_dir = Path(page_dir)        # the live page (kei.live) serves its own page with the same checks
        self.page_files = PAGE_FILES if page_files is None else page_files
        self.name = name
        self.files = files
        self.port = port
        self.token = secrets.token_urlsafe(32)
        self.session = secrets.token_urlsafe(32)   # the cookie's value: never the token itself
        # The link's own token. With single_use_link it is not the page's POST token and it works once: a link
        # copied into a transcript or the browser history opens nothing after the first load.
        self.link = secrets.token_urlsafe(32) if single_use_link else self.token
        self.single_use_link = single_use_link
        self.link_used = False
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.closed = threading.Event()

    @property
    def cookie_name(self) -> str:
        return f"{COOKIE}_{self.port}"

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> str:
        server = self

        class Handler(_Handler):
            owner = server
            server_version = server.name
        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="kei-review", daemon=True)
        self.thread.start()
        return f"{self.origin}/?t={self.link}"

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        self.closed.set()

    def wait(self) -> None:
        """Serve until stop() (the page's Close) or Ctrl+C."""
        try:
            while not self.closed.wait(0.5):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


class _Handler(BaseHTTPRequestHandler):
    owner: ReviewServer
    server_version = "kei-review"
    sys_version = ""

    def log_message(self, *args) -> None:   # the terminal stays quiet
        pass

    # -- replies -----------------------------------------------------------------------------------------------
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, obj) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _drain(self) -> None:
        """Read and drop the body of a request about to be refused, up to MAX_BODY. A socket closed with unread data
        resets the connection on Windows, and the client then loses the refusal (ConnectionAbortedError 10053).
        Nothing read here reaches a route."""
        try:
            left = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if not 0 < left <= MAX_BODY:
            return
        try:
            self.connection.settimeout(DRAIN_SECONDS)
            while left > 0:
                chunk = self.rfile.read(min(left, 64 * 1024))
                if not chunk:
                    return
                left -= len(chunk)
        except OSError:      # a slow or closed client: answer anyway
            pass

    def _refuse(self) -> None:
        self._drain()
        self._json(401, {"error": "not allowed: open the page from the address Kei printed"})

    def _missing(self) -> None:
        self._json(404, {"error": "not found"})

    # -- checks --------------------------------------------------------------------------------------------------
    def _host_ok(self) -> bool:
        return self.headers.get("Host") == f"127.0.0.1:{self.owner.port}"

    def _cookie_ok(self) -> bool:
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == self.owner.cookie_name and _same(value, self.owner.session):
                return True
        return False

    def _post_ok(self) -> bool:
        return (_same(self.headers.get("X-Kei-Token"), self.owner.token)
                and self.headers.get("Origin") == self.owner.origin)

    # -- methods -------------------------------------------------------------------------------------------------
    def do_GET(self) -> None:
        if not self._host_ok():
            return self._refuse()
        url = urlsplit(self.path)
        if url.path == "/" and "t" in parse_qs(url.query):
            if not _same(parse_qs(url.query)["t"][0], self.owner.link):
                return self._refuse()
            if self.owner.single_use_link:
                if self.owner.link_used:
                    if self._cookie_ok():        # this browser already holds the session: just show the page
                        return self._send(303, b"", "text/plain", {"Location": "/"})
                    return self._send(410, USED_LINK.encode("utf-8"), "text/plain; charset=utf-8")
                self.owner.link_used = True
            return self._send(303, b"", "text/plain", {
                "Location": "/", "Set-Cookie": f"{self.owner.cookie_name}={self.owner.session}; HttpOnly; SameSite=Strict; Path=/"})
        if not self._cookie_ok():
            return self._refuse()
        if url.path == "/":
            html = (self.owner.page_dir / "index.html").read_text(encoding="utf-8").replace(TOKEN_SLOT, self.owner.token)
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if url.path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if url.path in self.owner.page_files:
            name, ctype = self.owner.page_files[url.path]
            return self._send(200, (self.owner.page_dir / name).read_bytes(), ctype)
        if url.path.startswith("/file/"):
            return self._file(url.path[len("/file/"):])
        self._route("GET", url, None)

    def do_POST(self) -> None:
        if not (self._host_ok() and self._cookie_ok() and self._post_ok()):
            return self._refuse()
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            self._drain()
            return self._json(415, {"error": "the body must be JSON"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "bad Content-Length"})
        if length > MAX_BODY:
            return self._json(413, {"error": "the body is over 8 MB"})
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "null")
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"error": "the body is not valid JSON"})
        self._route("POST", urlsplit(self.path), body)

    def _file(self, file_id: str) -> None:
        path = self.owner.files().get(file_id)    # the raw id: an encoded ../ is just an unknown id
        if path is None or not Path(path).is_file():
            return self._missing()
        p = Path(path)
        self._send(200, p.read_bytes(), TYPES.get(p.suffix.lower(), "application/octet-stream"))

    def _route(self, method: str, url, body) -> None:
        fn = self.owner.routes.get(f"{method} {url.path}")
        if fn is None:
            return self._missing()
        req = {"method": method, "path": url.path, "query": {k: v[0] for k, v in parse_qs(url.query).items()},
               "body": body}
        try:
            status, obj = fn(req)
        except ValueError as e:   # every Kei refusal is a ValueError with a plain message
            status, obj = 409, {"error": str(e)}
        except Exception as e:    # noqa: BLE001 - the page gets a plain line, never a traceback
            status, obj = 500, {"error": f"Kei could not do that: {type(e).__name__}"}
        self._json(status, obj)
