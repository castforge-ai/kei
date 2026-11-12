"""Plan 3d, task 5: the validation set for Kei and Keira, written to examples/validation/ (build output, not tracked).

  uv run python tools/validate_characters.py [--size 240] [--only kei|keira] [--clips hands,spine,...]
  uv run python tools/validate_characters.py --motion [--only kei|keira] [--height 480] [--fps 24]

--motion writes only the README clips: docs/characters/web/<name>-motion.gif, a looping gesture sequence (a wave, a
point, a palm-up offer, a twist and look back, then rest) in the front and three quarter views, framed once for the
whole clip, on a light background with no labels. It needs ffmpeg (palettegen and paletteuse keep the GIF small).

For each character it writes:
  turnaround.png           the rest views: front, side, back, three quarter, top
  turnaround_overlay.png   the same with the left side tinted, to read left from right
  <clip>/out_p1/shot.json  a motion clip keyed on the character's own rest pose, and its render (frames, key stills,
                           keys.png, playback.mp4 or .gif) from kei.render.render_shot
  closeups/<clip>_<key>.png  each key pose zoomed on the part the clip is about (the right hand, the torso, the
                           feet), front, side and three quarter, to read joints and contacts by eye
and, for the pair, silhouettes.png: the two black silhouettes side by side, front and side.

The clips: hands (the six presets on both hands, forearms raised so the fingers face the viewer), spine (forward, back
and both sides), weight (a shift from foot to foot), step (heel strike, flat, ball, toe-off on each foot) and gestures
(a wave, a point, an offering palm up, a head turn and a twist) and motion (the README loop: the gestures
with a second wave, a point to the side and a hold on each, from rest back to rest).
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kei import hands                                                   # noqa: E402
from kei.characters import CHARACTERS, load_character, rest_pose        # noqa: E402
from kei.characters.mesh import pose_mesh                               # noqa: E402
from kei.characters.profile import decode_png                           # noqa: E402
from kei.render import (_composite, _raster, _view, draw_character_views, draw_silhouette,    # noqa: E402
                        render_shot)
from kei.rig import skeleton                                            # noqa: E402
from kei.sample import bake                                             # noqa: E402
from kei.sheet import _Canvas                                           # noqa: E402

OUT = ROOT / "examples" / "validation"
FPS = 24


def _key(rest: dict, f: int, name: str, **channels) -> dict:
    """A full key: the character's rest pose with some channels changed (a key that leaves a channel out would take the
    rig4 stand, not the character's rest)."""
    k = {**json.loads(json.dumps(rest)), **channels}
    return {"f": f, "name": name, **k}


def _add(v, d):
    return [a + b for a, b in zip(v, d)] + list(v[len(d):])


def clip_hands(rest: dict) -> list[dict]:
    up = {"armL": [0.25, 0.25, 0], "armR": [0.25, 0.25, 0], "elbowL": [1.9, 0.2], "elbowR": [1.9, 0.2]}
    keys, f = [], 0
    for name in hands.PRESETS:
        pose = {**up, **hands.hand_pose(name)}
        if name == "palm-up":
            pose.update(elbowL=[1.4, -1.4], elbowR=[1.4, -1.4])
        keys.append(_key(rest, f, name, **pose))
        f += 10
    keys.append(_key(rest, f, "relaxed again", **up, **hands.hand_pose("relaxed")))
    return keys


def clip_spine(rest: dict) -> list[dict]:
    seq = [("rest", [0, 0, 0]), ("forward", [0.9, 0, 0]), ("rest", [0, 0, 0]), ("back", [-0.45, 0, 0]),
           ("rest", [0, 0, 0]), ("side right", [0, 0.45, 0]), ("side left", [0, -0.45, 0]), ("rest", [0, 0, 0])]
    return [_key(rest, i * 12, n, spine=s, neck=[s[0] * 0.3, s[1] * 0.3, 0]) for i, (n, s) in enumerate(seq)]


def clip_weight(rest: dict) -> list[dict]:
    r = rest["root"]
    out = []
    for i, (name, dx, side) in enumerate((("centre", 0, 0), ("over the right foot", 0.085, -0.1), ("centre", 0, 0),
                                          ("over the left foot", -0.085, 0.1), ("centre", 0, 0))):
        out.append(_key(rest, i * 14, name, root=[r[0] + dx, r[1] - 0.015 * (dx != 0), r[2]], pelvis=[0, side],
                        spine=[0, -side * 0.6, 0]))
    return out


def clip_step(rest: dict) -> list[dict]:
    r, fl, fr = rest["root"], rest["footL"], rest["footR"]
    y = fl[1]

    def foot(base, z, lift=0.0):
        return [base[0], y + lift, z, 0, 0]
    return [
        _key(rest, 0, "contact, left heel", root=[r[0], r[1] - 0.03, 0.0], footL=foot(fl, 0.3), rollL=[-0.35, 0, 0.6],
             footR=foot(fr, -0.28), rollR=[0.7, 0, 0.6], armL=[-0.35, 0.3, 0], armR=[0.35, 0.3, 0]),
        _key(rest, 4, "down, left flat", root=[r[0], r[1] - 0.06, 0.08], footL=foot(fl, 0.3), rollL=[0, 0, 0.6],
             footR=foot(fr, -0.28), rollR=[1.1, 0, 0.6], armL=[-0.25, 0.3, 0], armR=[0.25, 0.3, 0]),
        _key(rest, 8, "passing", root=[r[0], r[1] - 0.01, 0.2], footL=foot(fl, 0.3), rollL=[0.15, 0, 0.6],
             footR=foot(fr, 0.22, 0.09), rollR=[0, 0, 0.6], armL=[0, 0.3, 0], armR=[0, 0.3, 0]),
        _key(rest, 12, "up, left ball", root=[r[0], r[1] + 0.005, 0.42], footL=foot(fl, 0.3), rollL=[0.5, 0, 0.6],
             footR=foot(fr, 0.62, 0.04), rollR=[-0.2, 0, 0.6], armL=[0.25, 0.3, 0], armR=[-0.25, 0.3, 0]),
        _key(rest, 16, "contact, right heel", root=[r[0], r[1] - 0.03, 0.58], footL=foot(fl, 0.3), rollL=[0.8, 0, 0.6],
             footR=foot(fr, 0.88), rollR=[-0.35, 0, 0.6], armL=[0.35, 0.3, 0], armR=[-0.35, 0.3, 0]),
        _key(rest, 20, "left toe-off", root=[r[0], r[1] - 0.05, 0.68], footL=foot(fl, 0.33, 0.02), rollL=[1.25, 0, 0.6],
             footR=foot(fr, 0.88), rollR=[0, 0, 0.6], armL=[0.25, 0.3, 0], armR=[-0.25, 0.3, 0]),
    ]


def clip_gestures(rest: dict) -> list[dict]:
    wave = {"armR": [0.3, 2.3, 0], "elbowR": [1.6, 0.3], **hands.hand_pose("open", "R")}
    return [
        _key(rest, 0, "rest"),
        _key(rest, 10, "wave out", **wave, handR=[0, 0.3]),
        _key(rest, 16, "wave in", **wave, handR=[0, -0.3], head=[0, 0.1, 0.3]),
        _key(rest, 26, "point", armR=[1.45, 0.25, 0], elbowR=[0.05, 0], **hands.hand_pose("point", "R"),
             head=[0, 0, 0.2]),
        _key(rest, 38, "offer palm up", armL=[0.7, 0.35, 0], elbowL=[0.9, -1.4], **hands.hand_pose("palm-up", "L"),
             head=[0.15, 0, -0.35], spine=[0, 0, -0.25]),
        _key(rest, 50, "twist and look back", spine=[0.05, 0, 0.6], neck=[0, 0, 0.4], head=[0, 0, 0.5],
             armL=[-0.3, 0.3, 0], armR=[0.5, 0.3, 0]),
        _key(rest, 60, "rest"),
    ]


def clip_motion(rest: dict) -> list[dict]:
    """The README loop, 5.5 s at 24 fps: the gestures clip with a second wave and a hold on each gesture, from rest
    back to the same rest so the loop has no seam."""
    wave = {"armR": [-0.1, 2.2, 0], "elbowR": [0.7, 0.3], **hands.hand_pose("open", "R")}
    point = {"armR": [0.45, 1.35, 0], "elbowR": [0.05, 0], **hands.hand_pose("point", "R"), "head": [0, 0, 0.2]}
    offer = {"armL": [0.7, 0.35, 0], "elbowL": [0.9, -1.4], **hands.hand_pose("palm-up", "L"),
             "head": [0.15, 0, -0.35], "spine": [0, 0, -0.25]}
    twist = {"spine": [0.05, 0, 0.6], "neck": [0, 0, 0.4], "head": [0, 0, 0.5], "armL": [-0.3, 0.3, 0],
             "armR": [0.5, 0.3, 0]}
    return [
        _key(rest, 0, "rest"),
        _key(rest, 12, "wave out", **wave, handR=[0, 0.3]),
        _key(rest, 18, "wave in", **wave, handR=[0, -0.3], head=[0, 0.1, 0.3]),
        _key(rest, 24, "wave out", **wave, handR=[0, 0.3], head=[0, 0.1, 0.15]),
        _key(rest, 30, "wave in", **wave, handR=[0, -0.3], head=[0, 0.1, 0.3]),
        _key(rest, 44, "point", **point),
        _key(rest, 54, "point held", **point),
        _key(rest, 70, "offer palm up", **offer),
        _key(rest, 80, "offer held", **offer),
        _key(rest, 98, "twist and look back", **twist),
        _key(rest, 108, "look held", **twist),
        _key(rest, 132, "rest"),
    ]


CLIPS = {"hands": clip_hands, "spine": clip_spine, "weight": clip_weight, "step": clip_step,
         "gestures": clip_gestures, "motion": clip_motion}


# Per clip: the bones the close-ups centre on, and the span they show (metres).
FOCUS = {"hands": (("hand_r",), 0.45), "spine": (("spine_03",), 1.1), "weight": (("pelvis", "foot_l", "foot_r"), 1.1),
         "step": (("calf_l", "calf_r"), 1.0), "gestures": (("spine_05", "hand_r"), 1.2),
         "motion": (("spine_05", "hand_r"), 1.2)}
CLOSE_VIEWS = ("front", "side", "three quarter")


def closeups(ch, clip: str, shot: dict, out: Path, size: int) -> list[Path]:
    frames = bake({**shot, "props": {"proportions": ch.proportions}}, "spline")
    bones, span = FOCUS[clip]
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for k in shot["keys"]:
        pose = frames[k["f"]]["pose"]
        B = skeleton(pose, ch.proportions)
        c = [sum(B[b].head[i] for b in bones) / len(bones) for i in range(3)]
        bounds = {v: (*_view(v, c), span) for v in CLOSE_VIEWS}
        p = out / f"{clip}_f{k['f']:03d}_{k['name'].replace(' ', '-').replace(',', '')}.png"
        p.write_bytes(draw_character_views(ch, pose, size=size, views=CLOSE_VIEWS, bounds=bounds,
                                           label=k["name"]))
        paths.append(p)
    return paths


def silhouettes(size: int) -> Path:
    imgs = [decode_png(draw_silhouette(load_character(n), size=size, view=v)) for n in CHARACTERS
            for v in ("front", "side")]
    cv = _Canvas(len(imgs) * size, size)
    for i, (w, h, rows) in enumerate(imgs):
        for y in range(h):
            for x in range(w):
                cv.dot(i * size + x, y, rows[y][x])
    path = OUT / "silhouettes.png"
    path.write_bytes(cv.png())
    return path


MOTION_VIEWS = ("front", "three quarter")
MOTION_BG = (247, 245, 241)       # a light warm grey, close to the README page
MOTION_GROUND = (214, 206, 194)
MOTION_MARGIN = 0.05              # the share of the panel height left empty above and below the figure
MOTION_OUT = ROOT / "docs" / "characters" / "web"


def motion_bounds(parts_per_frame) -> dict:
    """One framing for the whole clip, per view: (centre h, bottom v, width m, height m), from the ground to the
    highest point any frame reaches, so the camera holds still and the loop does not jump."""
    out = {}
    for view in MOTION_VIEWS:
        hs, vs = [], [0.0]
        for parts in parts_per_frame:
            for p in parts:
                for q in p.verts:
                    h, v = _view(view, q)
                    hs.append(h)
                    vs.append(v)
        out[view] = ((max(hs) + min(hs)) / 2, min(vs), max(hs) - min(hs), max(vs) - min(vs))
    return out


def motion_widths(bounds: dict, height: int) -> dict:
    """Each panel as wide as its view's widest frame plus a margin, rounded to an even pixel count."""
    out = {}
    for view, (_, _, wide, tall) in bounds.items():
        s = height * (1 - 2 * MOTION_MARGIN) / tall
        out[view] = 2 * math.ceil((wide * s + height * 2 * MOTION_MARGIN) / 2)
    return out


def motion_frame(ch, parts, bounds: dict, height: int, widths: dict) -> _Canvas:
    """One frame of the README clip: the views side by side, no border and no label, the ground as a soft line."""
    cv = _Canvas(sum(widths.values()), height)
    cv.px[:] = bytes(MOTION_BG) * (cv.w * cv.h)
    ox = 0
    for view in MOTION_VIEWS:
        w = widths[view]
        ch_, bottom, _, tall = bounds[view]
        s = height * (1 - 2 * MOTION_MARGIN) / tall
        ground = height * (1 - MOTION_MARGIN) + bottom * s

        def to_px(p, view=view, ch_=ch_, s=s, ground=ground, w=w):
            h, v = _view(view, p)
            return w / 2 + (h - ch_) * s, ground - v * s
        gy = round(ground)
        for x in range(ox + round(w * 0.08), ox + round(w * 0.92)):
            cv.dot(x, gy, MOTION_GROUND)
        bufs = _raster(view, parts, ch, to_px, w, height, 1.0, False, False)
        saved, cv.clip = cv.clip, (ox, 0, ox + w, height)
        _composite(cv, ox, 0, w, height, parts, bufs, 1.0, False, max(1, round(height / 160)))
        cv.clip = saved
        ox += w
    return cv


def motion_frames(name: str, height: int):
    """The README clip of one character, baked in spline mode as a loop: the frames as canvases of height pixels.
    The loop's last frame is frame 0 again, so it is left out."""
    ch = load_character(name)
    keys = clip_motion(rest_pose(ch))
    shot = {"rig": "v4", "fps": FPS, "frames": keys[-1]["f"], "loop": True, "keys": keys,
            "props": {"proportions": ch.proportions}}
    parts = [pose_mesh(ch, fr["pose"]) for fr in bake(shot, "spline")[:shot["frames"]]]
    bounds = motion_bounds(parts)
    widths = motion_widths(bounds, height)
    for p in parts:
        yield motion_frame(ch, p, bounds, height, widths)


def write_motion(name: str, height: int = 480, fps: int = FPS, out: Path | None = None,
                 supersample: int = 2) -> Path:
    """The README clip of one character as a looping GIF. The frames are drawn at supersample times the height and
    ffmpeg scales them down (smooth edges), builds one palette for the whole clip and writes the GIF."""
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("ffmpeg is needed for --motion (palettegen and paletteuse)")
    work = OUT / name / "motion"
    work.mkdir(parents=True, exist_ok=True)
    for old in work.glob("f*.png"):
        old.unlink()
    w = 0
    for i, cv in enumerate(motion_frames(name, height * supersample)):
        (work / f"f{i:04d}.png").write_bytes(cv.png())
        w = cv.w
    out = out or MOTION_OUT / f"{name}-motion.gif"
    out.parent.mkdir(parents=True, exist_ok=True)
    scale = f"scale={w // supersample // 2 * 2}:{height}:flags=lanczos"
    if fps != FPS:
        scale = f"fps={fps}," + scale
    graph = (f"[0:v]{scale},split[a][b];[a]palettegen=max_colors=128:stats_mode=full[p];"
             f"[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
    subprocess.run([exe, "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(work / "f%04d.png"),
                    "-filter_complex", graph, "-loop", "0", str(out)], check=True)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--size", type=int, default=240)
    ap.add_argument("--only", choices=CHARACTERS)
    ap.add_argument("--clips", default=",".join(CLIPS))
    ap.add_argument("--motion", action="store_true", help="write only the README clips (needs ffmpeg)")
    ap.add_argument("--height", type=int, default=480, help="the README clip height in pixels")
    ap.add_argument("--fps", type=int, default=FPS, help="the README clip frame rate")
    a = ap.parse_args(argv)
    if a.motion:
        for name in ([a.only] if a.only else CHARACTERS):
            path = write_motion(name, a.height, a.fps)
            print(f"{name} motion: {path} ({path.stat().st_size // 1024} KB)")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"silhouettes: {silhouettes(a.size * 2)}")
    for name in ([a.only] if a.only else CHARACTERS):
        ch = load_character(name)
        rest = rest_pose(ch)
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "turnaround.png").write_bytes(draw_character_views(ch, rest, size=a.size * 2))
        (d / "turnaround_overlay.png").write_bytes(draw_character_views(ch, rest, size=a.size * 2, overlay=True))
        print(f"{name}: {d / 'turnaround.png'}")
        for clip in a.clips.split(","):
            keys = CLIPS[clip](rest)
            shot = {"rig": "v4", "fps": FPS, "frames": keys[-1]["f"], "loop": False, "keys": keys}
            sd = d / clip / "out_p1"
            sd.mkdir(parents=True, exist_ok=True)
            (sd / "shot.json").write_text(json.dumps(shot, indent=1) + "\n", encoding="utf-8")
            r = render_shot(sd / "shot.json", sd, "spline", size=a.size, character=ch)
            closeups(ch, clip, shot, d / "closeups", a.size * 2)
            print(f"{name} {clip}: {r['keys']} {r['playback']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
