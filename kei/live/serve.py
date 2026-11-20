"""The live page server: one per shot, on 127.0.0.1, with the review server's checks (a token link, a session cookie,
the Host header, a strict Content-Security-Policy). Read only: the page has no POST route.

serve(shot, port=0, open_browser=True) -> serves until the shot is idle (IDLE_SECONDS with no change and no page
  open) or ends; writes <shot>/.kei/live/server.json with its pid, port and link.
ensure(shot, open_browser=True) -> the link of the shot's live page, starting a server in its own process when none
  answers. kei run calls it, unless kei.toml says [live] page = "off" or KEI_NO_LIVE is set.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from kei.live.snapshot import files, keep_plan, signature, snapshot
from kei.review.server import ReviewServer

PAGE_DIR = Path(__file__).resolve().parent / "page"
PAGE_FILES = {"/live.js": ("live.js", "text/javascript; charset=utf-8"),
              "/live.css": ("live.css", "text/css; charset=utf-8")}
IDLE_SECONDS = 2 * 3600       # no file change and no page open for this long: the server stops
ENDED_SECONDS = 15 * 60       # after the shot is approved or rejected, and no page open
POLL_SECONDS = 1.0
ENDED = ("done", "rejected")         # a shot signed off or rejected


def server_file(shot: Path) -> Path:
    return Path(shot) / ".kei" / "live" / "server.json"


def server_name(shot: Path) -> str:
    """The Server header of this shot's live server, so Kei knows a port answers for this shot."""
    return "kei-live-" + hashlib.sha256(str(Path(shot).resolve()).encode("utf-8")).hexdigest()[:12]


class Live:
    def __init__(self, shot: Path):
        self.shot = Path(shot)
        self.version = 0
        self.sig = None
        self.changed_at = time.time()
        self.seen_at = 0.0
        self.lock = threading.Lock()

    def poll(self) -> None:
        sig = signature(self.shot)
        if sig != self.sig:
            keep_plan(self.shot)
            with self.lock:
                self.sig = sig
                self.version += 1
                self.changed_at = time.time()

    def route(self, req) -> tuple:
        self.seen_at = time.time()
        if req["query"].get("v") == str(self.version):
            return 200, {"version": self.version, "same": True}
        return 200, {"version": self.version, **snapshot(self.shot)}

    def idle(self) -> bool:
        now = time.time()
        quiet = now - max(self.changed_at, self.seen_at)
        status = (snapshot_status(self.shot) or "")
        return quiet > IDLE_SECONDS or (status in ENDED and now - self.seen_at > ENDED_SECONDS
                                        and now - self.changed_at > ENDED_SECONDS)


def snapshot_status(shot: Path) -> str | None:
    try:
        return json.loads((Path(shot) / ".kei" / "state.json").read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError):
        return None


def start(shot: Path, port: int = 0) -> tuple[ReviewServer, Live, str]:
    live = Live(shot)
    live.poll()
    server = ReviewServer({"GET /api/live": live.route}, lambda: files(live.shot), port=port, page_dir=PAGE_DIR,
                          page_files=PAGE_FILES, name=server_name(shot))
    url = server.start()
    return server, live, url


def serve(shot: Path, port: int = 0, open_browser: bool = True, announce=print) -> None:
    shot = Path(shot)
    server, live, url = start(shot, port)
    f = server_file(shot)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"pid": os.getpid(), "port": server.port, "url": url}), encoding="utf-8")
    announce(f"Watch the shot live: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        while not server.closed.wait(POLL_SECONDS):
            try:
                live.poll()
            except OSError:
                pass
            if live.idle():
                break
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        try:
            if json.loads(f.read_text(encoding="utf-8")).get("pid") == os.getpid():
                f.unlink()
        except (OSError, ValueError):
            pass


def answering(shot: Path) -> str | None:
    """The link of the shot's live server when one answers for this shot, else None."""
    try:
        info = json.loads(server_file(shot).read_text(encoding="utf-8"))
        port, url = int(info["port"]), str(info["url"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
        c.request("GET", "/favicon.ico", headers={"Host": f"127.0.0.1:{port}"})
        r = c.getresponse()
        r.read()
        c.close()
    except OSError:
        return None
    return url if (r.getheader("Server") or "").startswith(server_name(shot)) else None


def ensure(shot: Path, open_browser: bool = True, wait_s: float = 8.0) -> str | None:
    """Start the shot's live page in its own process if none answers, and return its link (None if it did not
    start: the run goes on without it)."""
    shot = Path(shot)
    url = answering(shot)
    if url:
        return url
    cmd = [sys.executable, "-c", "from kei.cli import main; raise SystemExit(main())", "live", str(shot), "--quiet"]
    if not open_browser:
        cmd.append("--no-open")
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen(cmd, **kw)
    except OSError:
        return None
    end = time.time() + wait_s
    while time.time() < end:
        url = answering(shot)
        if url:
            return url
        time.sleep(0.2)
    return None
