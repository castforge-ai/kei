"""kei try and kei sweep: test a key edit before making it.

  kei try <shot> <pass> set --frame 40 --channel spine --value 0.1,0,0
  kei sweep <shot> <pass> --frame 40 --channel spine --from 0 --to 0.3 --steps 7

kei try applies one kei keys edit to a copy of the pass, runs kei check on the copy before and after, and prints the
flags the edit removes and the ones it adds. kei sweep does the same for a range of values of one channel at one
key (a set edit per value; a channel of several numbers moves only its first number unless --index names another)
and prints a line per value. Neither changes the shot: everything happens in a temporary folder.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from kei.keys import KeysError, _channel, _full, _key_at, edit
from kei.sample import read_json

COPIED_DIRS = ("plan", "rig")


def _copy_shot(shot_dir: Path, pass_name: str, dst: Path) -> None:
    """What kei check reads: the shot's top files, plan/ and rig/, the blocking keys and the pass's own inputs."""
    shot_dir = Path(shot_dir)
    for p in shot_dir.iterdir():
        if p.is_file():
            shutil.copy2(p, dst / p.name)
        elif p.name in COPIED_DIRS:
            shutil.copytree(p, dst / p.name)
    for rel in ("out_blocking/shot.json", f"out_{pass_name}/shot.json", f"out_{pass_name}/hands_toes.json"):
        src = shot_dir / rel
        if src.is_file():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / rel)


def _flags(shot_dir: Path, pass_name: str, character: str) -> dict[str, str]:
    """Every flag kei check raises on the pass, by id, with its text."""
    from kei.body_check import check_pass
    from kei.explain import body_id
    path = check_pass(shot_dir, pass_name, character)
    body = json.loads(path.read_text(encoding="utf-8"))
    out = {body_id(f): f["what"] for f in body.get("flags", []) if not f.get("note") and not f.get("inside_style")}
    pr = path.parent.parent / "principles" / "principles.json"
    if pr.is_file():
        out.update({f["id"]: f["what"] for f in json.loads(pr.read_text(encoding="utf-8")).get("flags", [])})
    return out


def trial(shot_dir: Path, pass_name: str, character: str, edits: list[dict]) -> list[dict]:
    """For each edit (the keyword arguments of kei keys, with "op"), the flags before and after it on a copy of the
    pass: [{"edit", "did", "before", "after", "gone", "new"}]. The first entry's "before" is the pass as it is."""
    src = Path(shot_dir) / f"out_{pass_name}" / "shot.json"
    if not src.is_file():
        raise KeysError(f"no {src}")
    shot = read_json(src, "shot")
    results = []
    with tempfile.TemporaryDirectory(prefix="kei-try-") as tmp:
        tmp = Path(tmp)
        _copy_shot(Path(shot_dir), pass_name, tmp)
        before = _flags(tmp, pass_name, character)
        target = tmp / f"out_{pass_name}" / "shot.json"
        for e in edits:
            kw = {k: v for k, v in e.items() if k != "op"}
            new, did = edit(shot, e["op"], **kw)
            target.write_text(json.dumps(new), encoding="utf-8")
            after = _flags(tmp, pass_name, character)
            results.append({"edit": e, "did": did, "before": len(before), "after": len(after),
                            "gone": sorted(set(before) - set(after)), "new": sorted(set(after) - set(before)),
                            "new_what": {k: after[k] for k in set(after) - set(before)}})
    return results


def sweep_edits(shot: dict, frame: int, channel: str, lo: float, hi: float, steps: int, index: int = 0) -> list[dict]:
    """The set edits of a sweep: the channel's value at the key, its index-th number from lo to hi in steps."""
    n = _channel(channel)
    if steps < 2:
        raise KeysError("--steps: at least 2 values")
    if not 0 <= index < n:
        raise KeysError(f"--index: {channel} has {n} number(s)")
    key = _key_at(shot, frame) or _full(shot, frame)
    base = key.get(channel)
    base = list(base) if isinstance(base, (list, tuple)) else [base if base is not None else 0.0] * n
    out = []
    for i in range(steps):
        v = lo + (hi - lo) * i / (steps - 1)
        vals = list(base)
        vals[index] = round(v, 6)
        out.append({"op": "set", "frame": frame, "channel": channel, "value": ",".join(str(x) for x in vals)})
    return out
