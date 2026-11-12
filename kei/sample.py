"""Keys to frames: Kei samples a keyed shot into a pose per frame. A port of the kit's animkit.js and rig4.js sampler.

A shot: {"rig": "v4", "fps", "frames", "loop", "keys": [{"f", "tangent", ...channels}]}. A key may leave out any
channel: it carries over from the key before, and the first key's missing channels take the default stand.

Modes: "step" holds each key (blocking), "linear" interpolates straight, "spline" is a Hermite curve with "auto"
tangents (from the neighbour keys) or "flat" ones. A loop wraps its frames. A travelling loop keys its last key on
f = frames with the root and the feet moved forward by one cycle; the auto tangents at the seam take that travel out
of the wrapped neighbours, so the seam is not eased by accident.
"""
from __future__ import annotations

import math

import json
from pathlib import Path
from typing import Callable

from kei.rig import CHANNELS, STAND, PoseError, _number, check_channels, check_proportions, full_pose, solve

SIZE = {c: len(v) if isinstance(v, list) else 1 for c, v in STAND.items()}


def _travel_index() -> dict[int, int]:
    """Flat indices of the world travel numbers (x and z of root, the ankle targets and the IK targets)."""
    out, i = {}, 0
    for c in CHANNELS:
        if c in ("root", "footL", "footR", "ikL", "ikR"):
            out[i], out[i + 2] = 0, 2
        i += SIZE[c]
    return out


TRAVEL_IDX = _travel_index()
MODES = ("step", "linear", "spline")
KEY_FIELDS = ("f", "name", "tangent", "note", "function", "kind")


class ShotError(ValueError):
    """The shot cannot be sampled. The message names the key."""


def read_json(path, what: str = "shot"):
    """A JSON file, or a ShotError of one line that names the file."""
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ShotError(f"cannot read the {what} {path}: {e.strerror or e}") from e
    except ValueError as e:
        raise ShotError(f"{path} is not valid JSON: {e}") from e


def read_shot(path):
    return read_json(path, "shot")


def check_shot(shot: dict) -> None:
    """Refuse a shot Kei's rig cannot play: not v4, no frames, a bad fps, bad proportions, no keys, or a key with no
    finite frame or with an unknown channel."""
    if not isinstance(shot, dict) or shot.get("rig") != "v4":
        raise ShotError('the shot needs "rig": "v4"')
    n = shot.get("frames")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ShotError('the shot needs "frames", a whole number of 1 or more')
    if "fps" in shot and not (_number(shot["fps"]) and shot["fps"] > 0):
        raise ShotError('the shot\'s "fps" must be a number above 0')
    pr = _proportions(shot)
    if pr is not None:
        try:
            check_proportions(pr)
        except PoseError as e:
            raise ShotError(str(e)) from e
    keys = shot.get("keys")
    if not isinstance(keys, list) or not keys:
        raise ShotError('the shot needs a "keys" list')
    for i, k in enumerate(keys):
        f = k.get("f") if isinstance(k, dict) else None
        if not _number(f):
            raise ShotError(f'key {i + 1} needs a frame "f", a finite number')
        if k.get("tangent", "auto") not in ("auto", "flat"):
            raise ShotError(f'key f {f}: tangent is "auto" or "flat"')
        try:
            check_channels(k, f"key f {f}", KEY_FIELDS)
        except PoseError as e:
            raise ShotError(str(e)) from e


def normalize_keys(shot: dict) -> list[dict]:
    """The keys sorted by frame, each with every channel, a name and a tangent ("auto" unless set)."""
    prev = STAND
    out = []
    for k in sorted(shot["keys"], key=lambda k: k["f"]):
        full = {"f": k["f"], "name": k.get("name") or "", "tangent": k.get("tangent") or "auto"}
        full.update(full_pose(k, prev))
        prev = full
        out.append(full)
    return out


def _flat(k: dict) -> list[float]:
    out = []
    for c in CHANNELS:
        out.extend(k[c]) if SIZE[c] > 1 else out.append(k[c])
    return out


def _unflat(vals: list[float]) -> dict:
    p, i = {}, 0
    for c in CHANNELS:
        n = SIZE[c]
        p[c] = vals[i] if n == 1 else list(vals[i:i + n])
        i += n
    return p


def cycle_travel(shot: dict, keys: list[dict]) -> tuple[float, float, float]:
    """One cycle of root travel on a loop whose last key sits on f = frames; zero otherwise."""
    a, b = keys[0], keys[-1]
    if not shot.get("loop") or b["f"] != shot["frames"]:
        return (0, 0, 0)
    return (b["root"][0] - a["root"][0], 0, b["root"][2] - a["root"][2])


def sampler(shot: dict, mode: str) -> Callable[[float], dict]:
    """A function from a frame (any number) to a full pose."""
    keys = normalize_keys(shot)
    vals = [_flat(k) for k in keys]
    n, loop = shot["frames"], bool(shot.get("loop"))
    travel = cycle_travel(shot, keys)

    def shift(v, sign):
        return [x + sign * travel[TRAVEL_IDX[j]] if j in TRAVEL_IDX else x for j, x in enumerate(v)]

    tans = []
    for i, k in enumerate(keys):
        if k["tangent"] == "flat":
            tans.append([0.0] * len(vals[i]))
            continue
        if i - 1 >= 0:
            fa, va = keys[i - 1]["f"], vals[i - 1]
        elif loop and len(keys) > 2:
            fa, va = keys[-2]["f"] - n, shift(vals[-2], -1)
        else:
            fa, va = k["f"], vals[i]
        if i + 1 < len(keys):
            fb, vb = keys[i + 1]["f"], vals[i + 1]
        elif loop and len(keys) > 2:
            fb, vb = keys[1]["f"] + n, shift(vals[1], 1)
        else:
            fb, vb = k["f"], vals[i]
        df = fb - fa
        tans.append([(vb[j] - va[j]) / df if df > 0 else 0 for j in range(len(vals[i]))])

    def at(f: float) -> dict:
        if loop:
            f = f % n
        f = max(keys[0]["f"], min(keys[-1]["f"], f))
        i = 0
        while i < len(keys) - 2 and f >= keys[i + 1]["f"]:
            i += 1
        last = i + 1 >= len(keys)
        if mode == "step" or last:
            return _unflat(vals[i + 1] if not last and f >= keys[i + 1]["f"] else vals[i])
        a, b = keys[i], keys[i + 1]
        d = b["f"] - a["f"]
        u = (f - a["f"]) / d if d > 0 else 0
        va, vb = vals[i], vals[i + 1]
        if mode == "linear":
            return _unflat([x + (y - x) * u for x, y in zip(va, vb)])
        h00, h10 = 2 * u ** 3 - 3 * u * u + 1, u ** 3 - 2 * u * u + u
        h01, h11 = -2 * u ** 3 + 3 * u * u, u ** 3 - u * u
        ta, tb = tans[i], tans[i + 1]
        return _unflat([h00 * va[j] + h10 * d * ta[j] + h01 * vb[j] + h11 * d * tb[j] for j in range(len(va))])

    return at


def _proportions(shot: dict) -> dict | None:
    props = shot.get("props")
    return props.get("proportions") if isinstance(props, dict) else None


def _knee_flex(j, side: str) -> float:
    a, b, c = j[f"thigh_{side}"], j[f"calf_{side}"], j[f"foot_{side}"]
    u = [a[k] - b[k] for k in range(3)]
    w = [c[k] - b[k] for k in range(3)]
    d = sum(u[k] * w[k] for k in range(3)) / ((math.hypot(*u) * math.hypot(*w)) or 1.0)
    return math.pi - math.acos(max(-1.0, min(1.0, d)))


def _lift(shot: dict):
    """props.match_knees (the proportions of the character the shot was made for): the shot played on another
    character rides its root higher or lower, frame by frame, so its knees bend as they did on the character it was
    made for (kei.characters.on_character sets it). Only the root's height moves; the feet stay where the shot puts
    them. The height is found by a search within LIFT_RANGE metres."""
    props = shot.get("props")
    author = props.get("match_knees") if isinstance(props, dict) else None
    mine = props.get("proportions") if isinstance(props, dict) else None

    def at_lifted(at):
        def f(t):
            p = at(t)
            if author:
                want = solve(p, author)
                target = (_knee_flex(want, "l"), _knee_flex(want, "r"))

                def err(dy):
                    q = {**p, "root": [p["root"][0], p["root"][1] + dy, p["root"][2]]}
                    j = solve(q, mine)
                    return (_knee_flex(j, "l") - target[0]) ** 2 + (_knee_flex(j, "r") - target[1]) ** 2
                lo, hi = -LIFT_RANGE, LIFT_RANGE
                for _ in range(40):                  # golden section on the root's lift
                    m1, m2 = lo + (hi - lo) * 0.382, lo + (hi - lo) * 0.618
                    if err(m1) < err(m2):
                        hi = m2
                    else:
                        lo = m1
                dy = (lo + hi) / 2
                p["root"] = [p["root"][0], p["root"][1] + dy, p["root"][2]]
            return p
        return f
    return at_lifted


LIFT_RANGE = 0.08


def bake(shot: dict, mode: str = "spline") -> list[dict]:
    """Frames 0..frames: {"f", "pose", "joints"} each."""
    at, pr = _lift(shot)(sampler(shot, mode)), _proportions(shot)
    return [{"f": f, "pose": (p := at(f)), "joints": solve(p, pr)} for f in range(shot["frames"] + 1)]


def bake_continuous(shot: dict) -> list[dict]:
    """bake for measuring: on a travelling loop, frames at and after f = frames move forward by one cycle of
    travel, so speeds across the seam are real. A loop gets one extra frame."""
    keys, at, pr = normalize_keys(shot), _lift(shot)(sampler(shot, "spline")), _proportions(shot)
    n, loop = shot["frames"], bool(shot.get("loop"))
    d = cycle_travel(shot, keys)
    out = []
    for f in range(n + 1 + (1 if loop else 0)):
        p = at(f)
        if loop and f >= n:
            p["root"] = [p["root"][0] + d[0], p["root"][1] + d[1], p["root"][2] + d[2]]
            for c in ("footL", "footR", "ikL", "ikR"):
                p[c] = [p[c][0] + d[0], p[c][1], p[c][2] + d[2]] + p[c][3:]
        out.append({"f": f, "pose": p, "joints": solve(p, pr)})
    return out
