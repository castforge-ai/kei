"""The Kei host: a small HTTP server inside the user's open Maya, so Kei can work in that session.

- It answers on 127.0.0.1 only, on a free port, and only to requests that carry the session's token (a random value
  made at start). Any account on the machine can reach a 127.0.0.1 port, so the port alone keeps nobody out.
- POST /call with {"tool", "inputs"} runs one named tool from the tool table (kei_tools.TOOLS), on Maya's main thread
  (maya.cmds is not safe from another thread). A change tool runs in one undo chunk, so one undo removes the call.
  There is no tool that runs code it is sent. Tools that change the scene they run on (playblast, export_fbx) are
  refused here: Kei runs them in the background on a copy.
- The session file, %LOCALAPPDATA%/Kei/maya/<pid>/session.json (elsewhere ~/.local/state/kei/maya/<pid>/), holds the
  pid, the process start time, the port, the token, the Maya version, the scene and whether it has unsaved changes.
  It is refreshed when a scene opens or is saved and on each call, and removed when Maya quits.

In Maya, a line in userSetup.py starts it:  import maya.utils, kei_host; maya.utils.executeDeferred(kei_host.start)
"""
from __future__ import annotations

import contextlib
import hmac
import http.server
import json
import os
import secrets
import shutil
import sys
import threading
from pathlib import Path

try:
    from . import kei_proc, kei_tools
except ImportError:
    import kei_proc
    import kei_tools

ADDRESS = "127.0.0.1"
DRAIN = 64 * 1024                   # what a refused request may have read of its body
MAX_BODY = 64 * 1024 * 1024         # the largest request a session accepts


class _Server(http.server.ThreadingHTTPServer):
    """Closing never waits for a handler: a call in flight may be waiting for the main thread, which is the one
    closing (Maya quitting), and an idle connection must not hold Maya open."""
    daemon_threads = True
    block_on_close = False


def session_root() -> Path:
    """Where Kei hosts write their session files (KEI_MAYA_SESSIONS overrides it, for tests)."""
    if os.environ.get("KEI_MAYA_SESSIONS"):
        return Path(os.environ["KEI_MAYA_SESSIONS"])
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Kei" / "maya"
    return Path.home() / ".local" / "state" / "kei" / "maya"


class Host:
    def __init__(self, tools: dict, executor, session_dir: Path, undo=None, info=None):
        self.tools, self.executor, self.root = tools, executor, Path(session_dir)
        self.undo = undo or (lambda name: contextlib.nullcontext())
        self.info = info or (lambda: {})
        self.token, self.port, self.server = "", 0, None
        self.address = ADDRESS
        self.state: dict = {}
        self.lock = threading.Lock()

    @property
    def session_file(self) -> Path:
        return self.root / str(os.getpid()) / "session.json"

    def _write(self) -> None:
        """The session file, private to the user: the folder 0o700 and the file 0o600 (on Windows the folder sits in
        the account's own LOCALAPPDATA)."""
        with self.lock:
            folder = self.session_file.parent
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt":
                os.chmod(folder, 0o700)
            tmp = self.session_file.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(self.state, indent=1))
            os.replace(tmp, self.session_file)

    def refresh(self, info: dict | None = None) -> None:
        """Write the scene and its unsaved state again (on a scene event, and after each call)."""
        info = self.info() if info is None else info
        for k in ("maya_version", "scene", "unsaved"):
            if k in info:
                self.state[k] = info[k]
        self._write()

    def start(self) -> dict:
        self.token = secrets.token_urlsafe(32)
        host = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                # the token is checked from the headers before any body is read; a refused body is drained (at
                # most 64 KiB), since a socket closed with unread data is reset on Windows and the caller would see
                # a broken connection instead of the refusal
                length = self.headers.get("Content-Length")
                try:
                    n = int(length) if length is not None else None
                except ValueError:
                    n = -1
                if n is None:
                    self._send(411, {"ok": False, "error": "Content-Length is required"})
                    return
                if n < 0:
                    self._send(400, {"ok": False, "error": "a bad Content-Length"})
                    return
                given = self.headers.get("Authorization", "")
                if not hmac.compare_digest(given.encode(), ("Bearer " + host.token).encode()):
                    self.rfile.read(min(n, DRAIN))
                    self.close_connection = True
                    self._send(401, {"ok": False, "error": "no session token, or a wrong one"})
                    return
                if n > MAX_BODY:
                    self.close_connection = True
                    self._send(413, {"ok": False, "error": f"a request is at most {MAX_BODY} bytes"})
                    return
                raw = self.rfile.read(n)
                if self.path != "/call":
                    self._send(404, {"ok": False, "error": f"no {self.path}"})
                    return
                try:
                    req = json.loads(raw or b"{}")
                except ValueError:
                    self._send(400, {"ok": False, "error": "the request is not JSON"})
                    return
                status, body = host.handle(req.get("tool"), req.get("inputs") or {})
                self._send(status, body)

        Handler.timeout = 10        # an idle or slow connection never holds a handler for long
        self.server = _Server((ADDRESS, 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.state = {"pid": os.getpid(), "start_time": kei_proc.start_time(os.getpid()), "port": self.port,
                      "token": self.token, "maya_version": None, "scene": None, "unsaved": None}
        self.refresh()
        return dict(self.state)

    def handle(self, name, inputs) -> tuple[int, dict]:
        try:
            args = kei_tools.check_inputs(name, inputs, self.tools)
        except kei_tools.ToolError as e:
            return 400, {"ok": False, "error": str(e)}
        if name in kei_tools.BACKGROUND_ONLY:
            return 403, {"ok": False, "error": f"{name} changes the scene it runs on; Kei runs it in the background "
                                                "on a copy of this scene, never in the open session"}
        entry = self.tools[name]

        def run():
            with kei_tools.in_degrees():
                if entry["kind"] == "change":
                    with self.undo("kei_" + name):
                        out = entry["fn"](**args)
                else:
                    out = entry["fn"](**args)
            try:
                info = self.info()          # on the main thread too: maya.cmds is not safe from this one
            except Exception:
                info = None
            return out, info

        try:
            result, info = self.executor(run)
        except Exception as e:
            return 500, {"ok": False, "error": f"{name}: {e}"}
        if info is not None:
            try:
                self.refresh(info)
            except OSError:
                pass
        return 200, {"ok": True, "result": result}

    def stop(self) -> None:
        """Stop serving and remove the session file. In-flight handlers are not waited for."""
        if self.server:
            server, self.server = self.server, None
            server.shutdown()
            server.server_close()
        shutil.rmtree(self.session_file.parent, ignore_errors=True)


HOST: Host | None = None
JOBS: list[int] = []


def _maya_undo(name):
    from maya import cmds

    @contextlib.contextmanager
    def chunk():
        cmds.undoInfo(openChunk=True, chunkName=name)
        try:
            yield
        finally:
            cmds.undoInfo(closeChunk=True)
    return chunk()


def _maya_info() -> dict:
    from maya import cmds
    return {"maya_version": cmds.about(version=True), "scene": cmds.file(q=True, sceneName=True),
            "unsaved": bool(cmds.file(q=True, modified=True))}


def start() -> dict:
    """Start the host in this Maya (from userSetup.py or the Kei shelf button). A second start keeps the first."""
    global HOST
    if HOST is not None:        # already serving: write the session file again (Kei may have taken it for stale)
        HOST.refresh()
        return dict(HOST.state)
    import maya.utils
    from maya import cmds
    HOST = Host(kei_tools.TOOLS, maya.utils.executeInMainThreadWithResult, session_root(), _maya_undo, _maya_info)
    info = HOST.start()
    for event in ("SceneOpened", "NewSceneOpened", "SceneSaved"):
        JOBS.append(cmds.scriptJob(event=[event, lambda: HOST and HOST.refresh()], protected=True))
    JOBS.append(cmds.scriptJob(event=["quitApplication", stop], protected=True))
    print(f"Kei host: 127.0.0.1:{info['port']} (session {os.getpid()})")
    return info


def stop() -> None:
    global HOST
    if HOST is not None:
        HOST.stop()
        HOST = None
    if JOBS:
        from maya import cmds
        for job in JOBS:
            if isinstance(job, int) and cmds.scriptJob(exists=job):    # in batch scriptJob gives no id
                cmds.scriptJob(kill=job, force=True)
        JOBS.clear()
