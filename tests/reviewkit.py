"""Test helpers for the review page: fake rounds on disk and a client that logs in like the page does."""
import hashlib
import http.client
import json
from pathlib import Path
from urllib.parse import urlsplit

from kei.state import ShotState, save_state

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def fake_round(root, round_id, pass_name="p1", frames=5, fps=24, loop=False, size=24):
    """A round as make_round leaves it, with stand-in PNGs: the page tests are about the routes, not the pictures."""
    d = Path(root) / "review" / round_id
    (d / "frames").mkdir(parents=True, exist_ok=True)
    src = Path(root) / f"out_{pass_name}" / "shot.json"     # the pass the round shows, as make_round leaves it
    if not src.is_file():
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(json.dumps({"rig": "v4", "frames": frames - 1, "fps": fps}), encoding="utf-8")
    for f in range(frames):
        (d / "frames" / f"f{f:04d}.png").write_bytes(PNG)
    meta = {"round": round_id, "pass": pass_name, "fps": fps, "frames": frames, "loop": loop,
            "made_at": "2026-11-03T00:00:00+00:00", "shot_sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "character": "kei", "mode": "spline",
            "size": size, "views": ["side", "three quarter", "front", "back"]}
    (d / "round.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def waiting_shot(tmp_path, status="needs_approval", sign_off=()):
    root = Path(tmp_path) / "shots" / "walk"
    root.mkdir(parents=True)
    save_state(root, ShotState(stage="deliver", status=status, request="a walk", sign_off=list(sign_off)))
    return root


def state_hash(root) -> str:
    return hashlib.sha256((Path(root) / ".kei" / "state.json").read_bytes()).hexdigest()


class PageClient:
    """Logs in with the token URL, then sends the cookie, the token header and the Origin, as the page does."""

    def __init__(self, url):
        u = urlsplit(url)
        self.port = u.port
        self.token = dict(p.split("=", 1) for p in u.query.split("&"))["t"]
        self.host = f"127.0.0.1:{self.port}"
        r, _ = self._send("GET", f"/?t={self.token}", None, {})
        self.cookie = r.getheader("Set-Cookie").split(";")[0]

    def _send(self, method, path, body, headers):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        data = None if body is None else json.dumps(body).encode("utf-8")
        h = dict(headers)
        if data is not None:
            h.update({"Content-Type": "application/json", "Content-Length": str(len(data))})
        c.request(method, path, body=data, headers=h)
        r = c.getresponse()
        out = r.read()
        c.close()
        return r, out

    def get(self, path):
        r, out = self._send("GET", path, None, {"Cookie": self.cookie})
        return r.status, (json.loads(out) if r.getheader("Content-Type", "").startswith("application/json")
                          else out)

    def post(self, path, body):
        r, out = self._send("POST", path, body, {"Cookie": self.cookie, "X-Kei-Token": self.token,
                                                 "Origin": f"http://{self.host}"})
        return r.status, json.loads(out)
