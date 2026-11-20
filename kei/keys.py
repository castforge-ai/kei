"""kei keys: edit a pass's keys without writing a script.

  kei keys <shot> <pass> set     --frame 40 --channel root --value 0,0.93,0.12
  kei keys <shot> <pass> offset  --frames 40-60 --channel root --by 0,-0.02,0
  kei keys <shot> <pass> insert  --frame 47            (a key at f47, the pose the spline plays there)
  kei keys <shot> <pass> copy    --from 12 --frame 30  (f12's pose keyed again at f30)
  kei keys <shot> <pass> delete  --frame 47
  kei keys <shot> <pass> shift   --from 90 --by 6      (retime: every key at or after f90 moves 6 frames; the shot
                                                        grows by 6, and objects' attach frames move with the keys)
  kei keys <shot> <pass> snap    --by 2 [--frames 0-60] (each key moves to the nearest beat of the shot's sound,
                                                        at most 2 frames away; kei sound adds the sound)
  kei keys <shot> <pass> match   --frame 40 --channel armL --value ik   (a matched IK/FK switch at f40: the frame
                                                        before holds the old mode, f40 keys the new mode on the same
                                                        pose; --channel armL, armR, legL or legR, --value ik or fk)

--to <pass> writes the result as another pass (a new out_<pass>/shot.json); without it the pass is edited in place.
Before every edit Kei keeps the pass as it was in out_<pass>/history/<n>.json, and appends the edit to
out_<pass>/edits.json, so every version is kept and every change is named. A mirror operation is left out on purpose:
mirrored poses (twinning) were the critics' most repeated pose note.
"""
from __future__ import annotations

import copy as _copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from kei.sample import SIZE, ShotError, check_shot, normalize_keys, read_json, sampler

OPS = ("set", "offset", "insert", "copy", "delete", "shift", "snap", "match")


class KeysError(ValueError):
    pass


def _numbers(text: str, n: int, what: str) -> list[float]:
    try:
        vals = [float(x) for x in str(text).split(",")]
    except ValueError:
        raise KeysError(f"{what}: numbers separated by commas, not {text!r}") from None
    if len(vals) != n:
        raise KeysError(f"{what}: this channel takes {n} number(s), got {len(vals)}")
    return vals


def _frames(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", str(text))
    if not m:
        raise KeysError(f"--frames: a frame or a range like 40-60, not {text!r}")
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    return min(a, b), max(a, b)


def _channel(name: str) -> int:
    if name not in SIZE:
        raise KeysError(f"no channel {name!r}; channels: {', '.join(SIZE)}")
    return SIZE[name]


def _key_at(shot: dict, f: int) -> dict | None:
    return next((k for k in shot["keys"] if k.get("f") == f), None)


def _full(shot: dict, f: int) -> dict:
    """The pose the shot plays at frame f, as a key with every channel (what a key there would hold)."""
    pose = sampler(shot, "spline")(f)
    return {"f": f, **{c: (list(v) if isinstance(v, (list, tuple)) else v) for c, v in pose.items()}}


def edit(shot: dict, op: str, frame: int | None = None, frames: str | None = None, channel: str | None = None,
         value: str | None = None, by: str | None = None, src: int | None = None,
         beats: list[int] | None = None) -> tuple[dict, str]:
    """The shot with one edit applied, and a line saying what changed. The input is not changed."""
    if op not in OPS:
        raise KeysError(f"op is one of {', '.join(OPS)}")
    out = _copy.deepcopy(shot)
    last = out["frames"]
    if op == "set":
        if frame is None or channel is None or value is None:
            raise KeysError("set needs --frame, --channel and --value")
        n = _channel(channel)
        vals = _numbers(value, n, "--value")
        k = _key_at(out, frame)
        if k is None:
            k = _full(out, frame)
            out["keys"].append(k)
        k[channel] = vals if n > 1 else vals[0]
        said = f"set {channel} at f{frame} to {value}"
    elif op == "offset":
        if frames is None or channel is None or by is None:
            raise KeysError("offset needs --frames, --channel and --by")
        n = _channel(channel)
        d = _numbers(by, n, "--by")
        a, b = _frames(frames)
        full = {k["f"]: k for k in normalize_keys(out)}
        hit = 0
        for k in out["keys"]:
            if a <= k["f"] <= b:
                base = k.get(channel, full[k["f"]][channel])
                base = list(base) if isinstance(base, (list, tuple)) else [base]
                new = [x + y for x, y in zip(base, d)]
                k[channel] = new if n > 1 else new[0]
                hit += 1
        if not hit:
            raise KeysError(f"no key in f{a}-{b}: insert one first")
        said = f"offset {channel} by {by} on {hit} key(s) in f{a}-{b}"
    elif op == "insert":
        if frame is None:
            raise KeysError("insert needs --frame")
        if _key_at(out, frame) is not None:
            raise KeysError(f"f{frame} already has a key")
        out["keys"].append(_full(out, frame))
        said = f"inserted a key at f{frame}, the pose the spline plays there"
    elif op == "copy":
        if frame is None or src is None:
            raise KeysError("copy needs --from and --frame")
        full = {k["f"]: k for k in normalize_keys(out)}
        if src not in full:
            raise KeysError(f"f{src} has no key to copy")
        new = {c: _copy.deepcopy(v) for c, v in full[src].items() if c not in ("f", "name", "tangent")}
        out["keys"] = [k for k in out["keys"] if k["f"] != frame] + [{"f": frame, **new}]
        said = f"copied the pose of f{src} to f{frame}"
    elif op == "delete":
        if frame is None:
            raise KeysError("delete needs --frame")
        if _key_at(out, frame) is None:
            raise KeysError(f"f{frame} has no key")
        if len(out["keys"]) <= 1:
            raise KeysError("the last key cannot be deleted")
        out["keys"] = [k for k in out["keys"] if k["f"] != frame]
        said = f"deleted the key at f{frame}"
    elif op == "match":
        from kei.ikfk import MatchError, match
        if frame is None or channel is None or value not in ("ik", "fk"):
            raise KeysError("match needs --frame, --channel (armL, armR, legL or legR) and --value ik or fk")
        if frame > 0 and _key_at(out, frame - 1) is None:      # the old mode holds up to the frame before
            out["keys"].append(_full(out, frame - 1))
        k = _key_at(out, frame)
        if k is None:
            k = _full(out, frame)
            out["keys"].append(k)
        pose = {c: v for c, v in _full(out, frame).items() if c != "f"}
        props = (out.get("props") or {}).get("proportions")
        try:
            got, rep = match(pose, props, channel, value)
        except MatchError as e:
            raise KeysError(str(e)) from None
        if not rep["matched"]:
            raise KeysError(f"no {value.upper()} pose of {channel} matches f{frame} within 2 mm (closest "
                            f"{rep['gap_m'] * 1000:.1f} mm): the limb may be out of reach there")
        k.update(got)
        said = f"switched {channel} to {value.upper()} at f{frame}, matched within {rep['gap_m'] * 1000:.2f} mm"
    elif op == "snap":
        from kei.sound import snap
        if beats is None:
            raise KeysError("snap needs the shot's sound: kei sound <shot> <file> first")
        try:
            within = int(str(by)) if by is not None else 2
        except ValueError:
            raise KeysError("snap --by is the most frames a key may move, a whole number") from None
        out, n = snap(out, beats, within, _frames(frames) if frames else None)
        said = f"snapped {n} key(s) to the sound's beats (at most {within} frame(s) each)"
    else:  # shift
        if src is None or by is None:
            raise KeysError("shift needs --from and --by")
        try:
            n = int(str(by))
        except ValueError:
            raise KeysError("shift --by is a whole number of frames") from None
        moved = [k for k in out["keys"] if k["f"] >= src]
        if n < 0:
            before = [k["f"] for k in out["keys"] if k["f"] < src]
            if before and min(k["f"] for k in moved) + n <= max(before):
                raise KeysError(f"that shift would move keys onto or past the keys before f{src}")
        for k in moved:
            k["f"] += n
        out["frames"] = last + n
        for o in out.get("objects", []) or []:
            for e in o.get("attach", []) or []:
                if e.get("f", -1) >= src:
                    e["f"] += n
        said = f"shifted {len(moved)} key(s) from f{src} by {n} frame(s); the shot is now {out['frames']} frames"
    out["keys"].sort(key=lambda k: k["f"])
    if any(not (0 <= k["f"] <= out["frames"]) for k in out["keys"]):
        raise KeysError("a key would fall outside the shot's frames")
    try:
        check_shot(out)
    except ShotError as e:
        raise KeysError(f"the edit makes an invalid shot: {e}") from None
    return out, said


def apply(shot_dir: Path, pass_name: str, op: str, to: str | None = None, **kw) -> tuple[Path, str]:
    """Edit out_<pass>/shot.json (or write it to out_<to>), keeping the old version and the edit log."""
    src = Path(shot_dir) / f"out_{pass_name}" / "shot.json"
    if not src.is_file():
        raise KeysError(f"no {src}")
    shot = read_json(src, "shot")
    if op == "snap":
        from kei.sound import load
        sound = load(Path(shot_dir))
        kw = {**kw, "beats": sound["beats"] if sound else None}
    new, said = edit(shot, op, **kw)
    dst_dir = Path(shot_dir) / f"out_{to or pass_name}"
    dst = dst_dir / "shot.json"
    if to and dst.is_file():
        raise KeysError(f"{dst} exists: edit it in place (kei keys <shot> {to} ...) or name a new pass")
    dst_dir.mkdir(parents=True, exist_ok=True)
    if dst.is_file():
        hist = dst_dir / "history"
        hist.mkdir(exist_ok=True)
        n = len(list(hist.glob("*.json"))) + 1
        (hist / f"{n:03d}.json").write_bytes(dst.read_bytes())
    dst.write_text(json.dumps(new, indent=1), encoding="utf-8")
    log = dst_dir / "edits.json"
    edits = json.loads(log.read_text(encoding="utf-8")) if log.is_file() else []
    edits.append({"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "from": f"out_{pass_name}",
                  "op": op, **{k: v for k, v in kw.items() if v is not None and k != "beats"}, "did": said})
    log.write_text(json.dumps(edits, indent=1), encoding="utf-8")
    return dst, said
