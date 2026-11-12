"""Kei's side of the Unreal adapter: an MCP client for Claireon, the Unreal Editor plugin that runs an MCP server.

Claireon(url).initialize() -> {"protocol_version", "server", "tools"}
  The handshake. Kei offers protocol 2025-11-25; Claireon 2.2.0 answers 2025-03-26, and Kei accepts the answer and
  records it. A tool the adapter needs that the server does not list stops with an UnrealError that names it.
Claireon(url).call(tool, args) -> the tool result
  Only tools in ALLOWED_TOOLS are called; any other name is refused before a request is made. The URL must be
  127.0.0.1 or localhost: Kei sends nothing to any other address.
run_script(client, name, inputs) -> dict
  The only way Kei changes or reads the editor. It sends one of Kei's own scripts from kei/apps/unreal_side/ through
  python_execute, checked against its SHA-256 (kei.apps.unreal_side.hashes), with the inputs as one JSON literal.
  Claireon 2.2.0 reports a Python exception as a success with the traceback in the logs, so each script prints one
  line, KEI_RESULT <json>; no such line is an UnrealError that carries the traceback.
server_url(project_dir) -> the URL Claireon wrote in <project>/Saved/Claireon/MCPServer.json.
An UnrealError means the machine could not do the job: no editor answers, Claireon stops answering, a script failed.
The conductor stops the shot with paused_machine on it; Kei never falls back to its own rig in silence.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

CLIENT_PROTOCOL = "2025-11-25"
ALLOWED_TOOLS: frozenset[str] = frozenset({"python_execute"})
NEEDED_TOOLS: tuple[str, ...] = ("python_execute",)
LOCAL_HOSTS = ("127.0.0.1", "localhost")
START_STEP = ("start the editor with -StartMCPServer, or click the Claireon button in the editor toolbar "
              "(kei unreal setup lists the steps)")
RESULT_PREFIX = "KEI_RESULT "
RESULT_TOKEN = re.compile(r"[0-9a-f]{32}")
RESULT_FILE_MAX = 64 * 1024 * 1024     # a large result is joints for a long shot, never this big
UNREAL_SIDE = Path(__file__).resolve().parent / "unreal_side"
TICK_SECONDS = 0.4      # the editor needs one tick between opening a sequence and keying it, and between a scrub
                        # and a read: those are separate python_execute calls with this pause between them


class UnrealError(RuntimeError):
    """Unreal or Claireon could not do a job. The message says what to do, in plain words, on one line."""


class NeedsHuman(UnrealError):
    """A person has to act before the shot can go on (a user asset Kei made dirty, a rig the probe left changed). The
    conductor stops the shot with needs_human and the message names the asset or the control."""


def tick() -> None:
    time.sleep(TICK_SECONDS)


def one_line(text: object, limit: int = 600) -> str:
    return " ".join(str(text).split())[:limit]


def _local(url: str) -> str:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or p.hostname not in LOCAL_HOSTS:
        raise UnrealError(f"Kei talks to Claireon on 127.0.0.1 only, not to {one_line(url, 80)}: set "
                          "[apps.unreal] url to http://127.0.0.1:<port>/mcp")
    return url


class Claireon:
    def __init__(self, url: str, timeout: float = 60):
        self.url = _local(url)
        self.timeout = timeout
        self.info: dict = {}
        self._id = 0
        # Kei's own folder for large results: Kei names it, the editor writes <token>.json there, and Kei joins the
        # token to this folder itself, so no path the editor sends ever reaches the file system.
        self.results_dir = Path(tempfile.gettempdir()) / "kei-unreal-results"

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}).encode()
        req = urllib.request.Request(self.url, body, {"Content-Type": "application/json",
                                                      "Accept": "application/json, text/event-stream"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                text = r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            raise UnrealError(f"Claireon refused {method}: HTTP {e.code}") from e
        except (socket.timeout, TimeoutError) as e:
            raise UnrealError(f"Claireon did not answer {method} in {self.timeout:g} s: the editor may be busy "
                              "(a dialog, a compile or a load); wait for it, then run the shot again") from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise UnrealError(f"Claireon did not answer {method} in {self.timeout:g} s: the editor may be busy "
                                  "(a dialog, a compile or a load); wait for it, then run the shot again") from e
            raise UnrealError(f"no editor answers at {self.url}: {START_STEP}") from e
        except (OSError, ValueError) as e:      # a closed connection, a reset, a bad status line
            raise UnrealError(f"Claireon did not answer {method} ({one_line(e, 120)}): the editor may have closed or "
                              "stopped its server; open it again, then run the shot again") from e
        try:
            start = text.index("{")
            data = json.loads(text[start:])
        except ValueError as e:
            raise UnrealError(f"Claireon answered {method} with something Kei cannot read") from e
        if "error" in data:
            err = data["error"]
            raise UnrealError(f"Claireon refused {method}: {one_line(err.get('message', err) if isinstance(err, dict) else err)}")
        return data.get("result") or {}

    def initialize(self) -> dict:
        res = self._rpc("initialize", {"protocolVersion": CLIENT_PROTOCOL, "capabilities": {},
                                       "clientInfo": {"name": "kei", "version": "0"}})
        tools = [t.get("name") for t in self._rpc("tools/list").get("tools", [])]
        for need in NEEDED_TOOLS:
            if need not in tools:
                raise UnrealError(f"this Claireon does not list the tool {need}, which Kei needs: update Claireon "
                                  "(https://github.com/believer-oss/claireon)")
        s = res.get("serverInfo") or {}
        self.info = {"protocol_version": res.get("protocolVersion"),
                     "server": f"{s.get('name', 'unknown')} {s.get('version', '')}".strip(), "tools": tools}
        return self.info

    def call(self, tool: str, args: dict) -> dict:
        if tool not in ALLOWED_TOOLS:
            raise UnrealError(f"Kei does not call the Claireon tool {one_line(tool, 80)}: it calls only "
                              f"{', '.join(sorted(ALLOWED_TOOLS))}")
        return self._rpc("tools/call", {"name": tool, "arguments": args})


def server_url(project_dir: Path) -> str | None:
    """The URL of the Claireon server a project's editor wrote (its port is set per project), or None."""
    f = Path(project_dir) / "Saved" / "Claireon" / "MCPServer.json"
    try:
        port = int(json.loads(f.read_text(encoding="utf-8"))["port"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return f"http://127.0.0.1:{port}/mcp"


def _read_script(name: str) -> str:
    """A script of Kei's, with LF line ends so its hash is the same on every checkout."""
    from kei.apps.unreal_side.hashes import UNREAL_SIDE_HASHES
    if not re.fullmatch(r"[a-z0-9_]+\.py", name or "") or name not in UNREAL_SIDE_HASHES:
        raise UnrealError(f"{one_line(name, 80)} is not one of Kei's editor scripts: Kei sends no other code to "
                          "the editor")
    path = UNREAL_SIDE / name
    try:
        text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    except OSError as e:
        raise UnrealError(f"Kei's editor script {name} cannot be read: {e}") from e
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != UNREAL_SIDE_HASHES[name]:
        raise UnrealError(f"Kei's editor script {name} does not match its recorded hash, so Kei will not send it: "
                          "reinstall Kei, or run tools/update_unreal_hashes.py if you changed the script")
    return text


def logs_of(result: dict) -> str:
    """The script's stdout from a python_execute result."""
    text = "".join(b.get("text", "") for b in (result.get("content") or []) if isinstance(b, dict))
    m = re.search(r"<logs>(.*?)</logs>", text, re.S)
    return (m.group(1) if m else text).replace("\r\n", "\n").strip()


def _read_result_file(name: str, token: object, folder: Path) -> dict:
    """A large result: the editor wrote it to <Kei's results folder>/<token>.json. Kei accepts only a bare 32-hex
    token, joins it to its own folder, reads the file once, then removes it."""
    if not isinstance(token, str) or not RESULT_TOKEN.fullmatch(token):
        raise UnrealError(f"the editor script {name} sent a result token Kei does not accept: {one_line(token, 80)}")
    p = Path(folder) / (token + ".json")
    try:
        if p.is_symlink() or not p.is_file():
            raise UnrealError(f"the editor script {name} sent a result token with no result file")
        if p.stat().st_size > RESULT_FILE_MAX:
            raise UnrealError(f"the editor script {name} wrote a result file larger than Kei reads")
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise UnrealError(f"the editor script {name} wrote a result file Kei cannot read") from e
    finally:
        try:
            if not p.is_symlink() and p.is_file():
                p.unlink()
        except OSError:
            pass


def run_script(client: Claireon, name: str, inputs: dict | None = None) -> dict:
    """Run one of Kei's editor scripts with a JSON input and return the dict it printed on its KEI_RESULT line."""
    body = _read_script(name)
    helpers = _read_script("kei_ue.py") if name != "kei_ue.py" else ""
    literal = json.dumps(inputs or {})
    folder = Path(client.results_dir)
    folder.mkdir(parents=True, exist_ok=True)
    code = (f"import json\nKEI_INPUT = json.loads({literal!r})\nKEI_RESULTS_DIR = {str(folder)!r}\n"
            f"{helpers}\n{body}")
    res = client.call("python_execute", {"code": code})
    logs = logs_of(res)
    if res.get("isError"):
        raise UnrealError(f"the editor refused the script {name}: {one_line(logs)}")
    for line in reversed(logs.splitlines()):
        if line.startswith(RESULT_PREFIX):
            try:
                out = json.loads(line[len(RESULT_PREFIX):])
            except ValueError as e:
                raise UnrealError(f"the editor script {name} printed a result Kei cannot read") from e
            if isinstance(out, dict) and set(out) == {"result_token"}:
                out = _read_result_file(name, out["result_token"], client.results_dir)
            if not isinstance(out, dict):
                raise UnrealError(f"the editor script {name} printed a result that is not an object")
            if out.get("error"):
                raise UnrealError(f"the editor script {name} stopped: {one_line(out['error'])}")
            return out
    raise UnrealError(f"the editor script {name} gave no result; the editor said: {one_line(logs[-900:]) or 'nothing'}")
