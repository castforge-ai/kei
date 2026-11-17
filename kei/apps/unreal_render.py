"""Views and playback of an Unreal pass, drawn by Kei's own renderer on the joints Unreal gave back.

render_pass(shot_dir, pass_name, size) -> dict
  The same files as a pass on Kei's own rig: out_<pass>/frames/f0000.png ..., a still per key (key_f0000.png), the key
  sheet (keys.png), the playback (<name>.mp4, or .gif without ffmpeg) and, for a loop, the ten loops (<name>_x10.mp4).
  The pass records the renderer in out_<pass>/unreal_report.json under "views": "renderer": "kei". A second performer
  (joints.json "performers") is drawn in the same views, behind the character, in one lighter colour.
Capture from the editor (Claireon frame capture of a camera Kei places) is NOT part of this version: the live spike
did not prove it, so Kei never claims it. A request for it is refused in plain words and never falls back in silence.
"""
from __future__ import annotations

import json
from pathlib import Path

from kei import render as R
from kei.sample import ShotError, read_json

RENDERER = "kei"
CAPTURE_ENABLED = False


def render_pass(shot_dir: Path, pass_name: str, size: int = 360, renderer: str = RENDERER) -> dict:
    if renderer != RENDERER:
        raise ShotError("Kei draws an Unreal pass with its own renderer on the joints Unreal gave back; drawing "
                        "frames from the editor itself is not built yet (it needs a live test)")
    shot_dir = Path(shot_dir)
    out = shot_dir / f"out_{pass_name}"
    src = out / "joints.json"
    if not src.is_file():
        raise ShotError(f"no {src}: key the pass in Unreal first (kei unreal key {shot_dir} {pass_name})")
    data = read_json(src, "joints")
    shot = read_json(out / "shot.json", "shot")
    frames = [{"f": fr["f"], "joints": {**{n: tuple(p) for n, p in fr["joints"].items()},
                                        **{f"{who}/{n}": tuple(p) for who, js in (fr.get("performers") or {}).items()
                                           for n, p in js.items()}}} for fr in data["frames"]]
    if not frames:
        raise ShotError(f"{src} has no frames")
    bounds = R.fit([fr["joints"] for fr in frames])
    key_fs = sorted({int(k["f"]) for k in shot.get("keys", []) if isinstance(k, dict) and float(k["f"]).is_integer()
                     and 0 <= k["f"] < len(frames)}) or [0]
    name = "blocking" if pass_name == "blocking" else "playback"
    frames_dir = out / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("f*.png"):
        old.unlink()
    canvases, paths = [], []
    for i, fr in enumerate(frames):
        tag = "key" if fr["f"] in key_fs else ""
        cv = R._Canvas(2 * size, 2 * size)
        R._views_on(cv, 0, 0, fr["joints"], size, bounds[i], f"F{fr['f']} {tag}".strip())
        p = frames_dir / f"f{fr['f']:04d}.png"
        p.write_bytes(cv.png())
        canvases.append(cv)
        paths.append(p)
    for old in out.glob("key_f*.png"):
        old.unlink()
    stills = []
    for f in key_fs:
        stills.append(out / f"key_f{f:04d}.png")
        stills[-1].write_bytes(paths[f].read_bytes())
    keys = out / "keys.png"
    keys.write_bytes(R._key_sheet(frames, key_fs, bounds, size // 2))
    fps = data.get("fps") or shot.get("fps") or 24
    for old in (f"{name}.mp4", f"{name}.gif", f"{name}_x{R.LOOPS}.mp4"):
        (out / old).unlink(missing_ok=True)
    played = canvases[:-1] if shot.get("loop") and len(canvases) > 1 else canvases
    loops = None
    if R._mp4(frames_dir, fps, out / f"{name}.mp4", len(played)):
        playback, kind = out / f"{name}.mp4", "mp4"
        if shot.get("loop"):
            loops = R._repeat(playback, R.LOOPS, out / f"{name}_x{R.LOOPS}.mp4")
    else:
        playback, kind = R.write_gif(played, fps, out / f"{name}.gif"), "gif"
    rep_path = out / "unreal_report.json"
    rep = json.loads(rep_path.read_text(encoding="utf-8")) if rep_path.is_file() else {}
    rep["views"] = {"renderer": RENDERER, "frames": len(frames), "size": size}
    rep_path.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return {"frames": paths, "stills": stills, "keys": keys, "playback": playback, "kind": kind, "loops": loops,
            "renderer": RENDERER}
