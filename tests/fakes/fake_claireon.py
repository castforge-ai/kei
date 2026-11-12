"""A fake Claireon server for the Unreal adapter's tests: a stdlib HTTP server on 127.0.0.1 that speaks the same
JSON-RPC, records every request, and answers python_execute the way Claireon 2.2.0 does (one text block, the script's
stdout in <logs>, CRLF line ends). Kei's own scripts carry a first line "# kei_script: <name>"; the fake finds that
name and the JSON inputs line in the code it receives, and calls the handler a test registered for the name. No Unreal
Editor is involved anywhere."""
from __future__ import annotations

import ast
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOOLS = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "unreal" / "claireon_tools.json")
                   .read_text(encoding="utf-8"))["result"]["tools"]
NAME = re.compile(r"^# kei_script: (\w+)", re.M)
INPUT = re.compile(r"^KEI_INPUT = json\.loads\((.*)\)$", re.M)


def wrap(logs: str, status: str = "success") -> dict:
    """What Claireon returns for python_execute: one text content block."""
    body = logs.replace("\n", "\r\n")
    return {"content": [{"type": "text", "text": f'<execute-result status="{status}">\r\n<logs>\r\n{body}\r\n</logs>\r\n'
                                                 "</execute-result>"}], "isError": False}


class FakeClaireon:
    def __init__(self, handlers: dict | None = None, tools: list | None = None, protocol: str = "2025-03-26",
                 delay: float = 0.0):
        self.handlers = dict(handlers or {})
        self.tools = TOOLS if tools is None else tools
        self.protocol = protocol
        self.delay = delay
        self.requests: list[dict] = []      # every JSON-RPC request body, in order
        self.scripts: list = []             # the script name of each python_execute call, in order
        self.codes: list[str] = []          # the code of each python_execute call
        self.inputs: list[dict] = []        # the JSON inputs of each python_execute call
        self.error: dict | None = None      # a JSON-RPC error to answer to tools/call
        self.plain: str | None = None       # raw logs to answer with, instead of a handler's result
        self.stopped = False                # True: answer nothing at all (a closed connection)
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(n))
                fake.requests.append(req)
                if fake.stopped:
                    self.connection.close()
                    return
                if fake.delay:
                    time.sleep(fake.delay)
                out = fake.answer(req)
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        class Quiet(ThreadingHTTPServer):
            def handle_error(self, request, client_address):     # a client that gave up is not a test failure
                pass

        self.server = Quiet(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/mcp"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()

    def answer(self, req: dict) -> dict:
        m, rid = req.get("method"), req.get("id")
        if m == "initialize":
            return {"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": self.protocol, "capabilities": {},
                                                          "serverInfo": {"name": "claireon-unreal-editor",
                                                                         "version": "1.0.0"}}}
        if m == "tools/list":
            return {"jsonrpc": "2.0", "id": rid, "result": {"tools": self.tools}}
        if m == "tools/call":
            if self.error:
                return {"jsonrpc": "2.0", "id": rid, "error": self.error}
            p = req["params"]
            if p["name"] != "python_execute":
                return {"jsonrpc": "2.0", "id": rid, "result": wrap("")}
            code = p["arguments"]["code"]
            self.codes.append(code)
            names = NAME.findall(code)
            name = names[-1] if names else None
            self.scripts.append(name)
            inputs = {}
            m2 = INPUT.search(code)
            if m2:
                inputs = json.loads(ast.literal_eval(m2.group(1)))
            self.inputs.append(inputs)
            if self.plain is not None:
                return {"jsonrpc": "2.0", "id": rid, "result": wrap(self.plain)}
            h = self.handlers.get(name)
            if h is None:
                return {"jsonrpc": "2.0", "id": rid, "result": wrap(f"Traceback: no handler for {name}")}
            res = h(inputs)
            return {"jsonrpc": "2.0", "id": rid, "result": wrap("KEI_RESULT " + json.dumps(res))}
        return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "no such method"}}
