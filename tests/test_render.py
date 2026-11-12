import json
import math
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from kei import render
from kei.render import draw_views, fit, project, render_shot, VIEWS
from kei.rig import DEFAULT_POSE, solve
from kei.sample import bake
from test_sheet import decode

SHOTS = {c["name"]: c["shot"] for c in
         json.loads((Path(__file__).parent / "fixtures" / "rig" / "shots.json").read_text(encoding="utf-8"))["shots"]}
FFMPEG = shutil.which("ffmpeg")   # found before any test empties PATH


def ffmpeg_frames(path, w, h):
    """Decode a video or GIF with ffmpeg (an independent decoder) to raw RGB frames of w by h pixels."""
    r = subprocess.run([FFMPEG, "-loglevel", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-vsync", "0", "-"], capture_output=True, check=True)
    n = w * h * 3
    assert len(r.stdout) % n == 0
    return [r.stdout[i:i + n] for i in range(0, len(r.stdout), n)]


def png_rgb(png):
    w, h, px = decode(png)
    return b"".join(bytes(px(x, y)) for y in range(h) for x in range(w))


def write_shot(tmp_path, shot):
    src = tmp_path / "shot.json"
    src.write_text(json.dumps(shot), encoding="utf-8")
    return src


def no_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    assert shutil.which("ffmpeg") is None


def colours(png):
    w, h, px = decode(png)
    return w, h, {px(x, y) for y in range(h) for x in range(w)}


def test_views_png_signature_and_size():
    png = draw_views(solve(DEFAULT_POSE), size=200)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    w, h, _ = decode(png)
    assert (w, h) == (400, 400)


def test_left_and_right_differ_in_colour():
    _, _, seen = colours(draw_views(solve(DEFAULT_POSE), size=200))
    assert render.LEFT in seen and render.RIGHT in seen and render.LEFT != render.RIGHT
    assert render.COM in seen and render.GROUND in seen


def test_left_side_is_drawn_in_the_left_colour():
    j = solve(DEFAULT_POSE)
    w, h, px = decode(draw_views(j, size=200))
    b = fit([j])[0]
    x, y = project("front", j["calf_l"], b, 200)    # the left knee, front panel at the origin
    near = {px(x + dx, y + dy) for dx in range(-1, 2) for dy in range(-1, 2)}
    assert render.LEFT in near


def test_shared_scale_keeps_a_travelling_shot_in_frame():
    frames = [fr["joints"] for fr in bake(SHOTS["walk"], "spline")]
    size = 160
    for j, b in zip(frames, fit(frames)):
        for view in VIEWS:
            for name, p in j.items():
                x, y = project(view, p, b, size)
                assert 0 <= x < size and render.LABEL <= y < size, (view, name)


def stride_shot(travel, jump=0.0):
    """A shot of 24 frames: the figure moves travel metres forward and rises jump metres at frame 12."""
    def key(f, z, up):
        return {"f": f, "root": [0, 0.96 + up, z], "footL": [-0.1, 0.08 + up, z + 0.15],
                "footR": [0.1, 0.08 + up, z - 0.15]}
    return {"rig": "v4", "fps": 24, "frames": 24, "loop": False,
            "keys": [key(0, 0, 0), key(12, travel / 2, jump), key(24, travel, 0)]}


def front_height(shot, f, size=160):
    frames = [fr["joints"] for fr in bake(shot, "linear")]
    j, b = frames[f], frame_bounds(frames)[f]
    return project("front", j["ball_l"], b, size)[1] - project("front", j["head_top"], b, size)[1]


def test_a_travelling_shot_does_not_shrink_the_figure():
    still = front_height(stride_shot(0), 0)
    assert front_height(stride_shot(8), 0) >= 0.9 * still
    assert front_height(stride_shot(8), 24) >= 0.9 * still


def test_a_jump_does_not_shrink_the_figure():
    still = front_height(stride_shot(0), 12)
    assert front_height(stride_shot(0, jump=1.0), 12) >= 0.8 * still


def test_a_long_travel_stays_in_every_panel():
    frames = [fr["joints"] for fr in bake(stride_shot(8, jump=1.0), "linear")]
    size = 160
    for j, b in zip(frames, frame_bounds(frames)):
        for view in VIEWS:
            for name, p in j.items():
                if name == "root":      # the root's shadow on the ground, not drawn: it stays below a jump
                    continue
                x, y = project(view, p, b, size)
                assert 0 <= x < size and render.LABEL <= y < size, (view, name)


def ticks(png, ox, oy, size):
    """The ground ticks of a panel: ground coloured pixels off the panel's main ground row."""
    w, h, px = decode(png)
    pts = [(x, y) for y in range(oy + render.LABEL, oy + size) for x in range(ox, ox + size)
           if px(x, y) == render.GROUND]
    rows = {}
    for _, y in pts:
        rows[y] = rows.get(y, 0) + 1
    main = max(rows, key=rows.get) if rows else None
    return {x for x, y in pts if y != main}


@pytest.mark.parametrize("view", ["side", "three quarter"])
def test_ground_ticks_show_the_travel(view):
    frames = [fr["joints"] for fr in bake(stride_shot(8), "linear")]
    bs = frame_bounds(frames)
    size = 200
    ox, oy = (0, 0) if view == "front" else ((size, 0) if view == "side" else (size, size))
    a = ticks(draw_views(frames[0], size=size, bounds=bs[0]), ox, oy, size)
    b = ticks(draw_views(frames[5], size=size, bounds=bs[5]), ox, oy, size)
    assert len(a) >= 4 and len(b) >= 4      # a tick every 0.5 m across the panel
    assert a != b                           # the ground slides under the figure as it travels


def test_top_view_ground_marks_move_with_the_travel():
    frames = [fr["joints"] for fr in bake(stride_shot(8), "linear")]
    bs = frame_bounds(frames)
    size = 200

    def marks(i):
        w, h, px = decode(draw_views(frames[i], size=size, bounds=bs[i]))
        return {(x, y) for y in range(size + render.LABEL, 2 * size) for x in range(size)
                if px(x, y) == render.GROUND}
    a, b = marks(0), marks(5)
    assert len(a) >= 8 and a != b


def test_the_top_view_origin_mark_stays_in_its_panel():
    # a figure far from the world origin: the origin mark of the top view falls outside the top panel
    j = solve({**DEFAULT_POSE, "root": [2.0, 0.98, -2.0], "footL": [1.9, 0.08, -2.0], "footR": [2.1, 0.08, -2.0]})
    size = 100
    cv = render._Canvas(3 * size, 3 * size)
    b = fit([j])[0]
    b["top"] = (b["top"][0] + 3.0, b["top"][1] + 3.0, b["top"][2])   # the panel looks away from the origin
    render._panel(cv, size, size, "top", j, b, size, "")
    w, h, px = decode(cv.png())
    ink = [(x, y) for y in range(h) for x in range(w) if px(x, y) != px(0, 0)]
    assert ink
    assert all(size <= x < 2 * size and size <= y < 2 * size for x, y in ink), \
        [p for p in ink if not (size <= p[0] < 2 * size and size <= p[1] < 2 * size)][:5]


def frame_bounds(frames):
    """The bounds of each frame of a shot."""
    return fit(frames)


def metre_px(view, b, size):
    """Pixels for one metre up the screen of a view (forward for the top view), measured over 10 m so the
    rounding of a pixel moves it by 0.1 px at most."""
    up = (0, 0, 10) if view == "top" else (0, 10, 0)
    return math.dist(project(view, (0, 0, 0), b, size), project(view, up, b, size)) / 10


def test_one_scale_per_view_across_the_frames_and_the_figure_fills_its_panel():
    frames = [fr["joints"] for fr in bake(SHOTS["walk"], "spline")]
    size = 160
    bs = frame_bounds(frames)
    for view in VIEWS:
        # a metre is the same number of pixels in every frame: the scale does not breathe
        px = [metre_px(view, b, size) for b in bs]
        assert max(px) - min(px) <= 0.1, view
    for j, b in zip(frames, bs):
        for view in VIEWS:
            for name, p in j.items():
                x, y = project(view, p, b, size)
                assert 0 <= x < size and render.LABEL <= y < size, (view, name)
    # a still figure fills most of the front panel's height: a fit that is too loose fails
    j = solve(DEFAULT_POSE)
    b = frame_bounds([j])[0]
    tall = project("front", j["ball_l"], b, size)[1] - project("front", j["head_top"], b, size)[1]
    assert tall > 0.6 * (size - render.LABEL)


def gif_frames(data):
    assert data[:6] == b"GIF89a"
    w, h, flags = struct.unpack("<HHB", data[6:11])
    pos = 13 + (3 * 2 ** ((flags & 7) + 1) if flags & 0x80 else 0)
    count = 0
    while data[pos] != 0x3B:
        kind = data[pos]
        if kind == 0x21:
            pos += 2
            while data[pos]:
                pos += data[pos] + 1
            pos += 1
        elif kind == 0x2C:
            count += 1
            lflags = data[pos + 9]
            pos += 10 + (3 * 2 ** ((lflags & 7) + 1) if lflags & 0x80 else 0)
            pos += 1   # the LZW minimum code size
            while data[pos]:
                pos += data[pos] + 1
            pos += 1
        else:
            raise AssertionError(f"bad block {kind:#x} at {pos}")
    return (w, h), count


def lzw_decode(codes_bytes, min_size):
    """A plain GIF LZW decoder, to prove the encoder round trips."""
    bits = int.from_bytes(codes_bytes, "little")
    nbits = len(codes_bytes) * 8
    clear, eoi = 1 << min_size, (1 << min_size) + 1
    pos, size, out = 0, min_size + 1, bytearray()
    table, prev = None, None
    while pos + size <= nbits:
        code = (bits >> pos) & ((1 << size) - 1)
        pos += size
        if code == clear:
            table = [bytes([i]) for i in range(clear)] + [b"", b""]
            size, prev = min_size + 1, None
            continue
        if code == eoi:
            break
        if prev is None:
            entry = table[code]
        else:
            entry = table[code] if code < len(table) else prev + prev[:1]
            table.append(prev + entry[:1])
            if len(table) == (1 << size) and size < 12:
                size += 1
        out += entry
        prev = entry
    return bytes(out)


def test_lzw_round_trips():
    import random
    rnd = random.Random(3)
    data = bytes(rnd.choice([0, 0, 0, 1, 2, 7, 200]) for _ in range(60000)) + bytes(range(256)) * 40
    assert lzw_decode(render.lzw_encode(data, 8), 8) == data


def test_gif_playback_when_ffmpeg_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    assert shutil.which("ffmpeg") is None
    shot = {"rig": "v4", "fps": 12, "frames": 6, "loop": False,
            "keys": [{"f": 0}, {"f": 3, "armR": [1.2, 0.2, 0]}, {"f": 6, "root": [0, 0.9, 0.1]}]}
    src = tmp_path / "shot.json"
    src.write_text(json.dumps(shot), encoding="utf-8")
    out = render_shot(src, tmp_path / "out", "step", size=120)
    assert out["playback"].name == "playback.gif"
    assert out["kind"] == "gif"
    (w, h), count = gif_frames(out["playback"].read_bytes())
    assert (w, h) == (240, 240) and count == 7
    assert len(out["frames"]) == 7 and out["frames"][0].name == "f0000.png"
    assert out["keys"].name == "keys.png" and out["keys"].read_bytes()[:4] == b"\x89PNG"
    assert_gif_shows_the_frames(out["playback"], out["frames"], 240, 240)


def assert_gif_shows_the_frames(gif, pngs, w, h):
    """ffmpeg, an independent decoder, reads the GIF back pixel for pixel as the frames written."""
    if FFMPEG is None:
        return
    decoded = ffmpeg_frames(gif, w, h)
    assert len(decoded) == len(pngs)
    for i, (got, p) in enumerate(zip(decoded, pngs)):
        assert got == png_rgb(p.read_bytes()), f"frame {i} differs"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_mp4_playback_with_ffmpeg(tmp_path):
    src = tmp_path / "shot.json"
    src.write_text(json.dumps(SHOTS["sway"]), encoding="utf-8")
    out = render_shot(src, tmp_path / "out", "spline", size=120)
    assert out["kind"] == "mp4" and out["playback"].name == "playback.mp4"
    assert out["playback"].stat().st_size > 1000


def test_a_loop_gif_leaves_out_the_repeated_last_frame(tmp_path, monkeypatch):
    no_ffmpeg(tmp_path, monkeypatch)
    shot = {**SHOTS["sway"], "frames": 8, "keys": [{"f": 0, "yaw": 0.2}, {"f": 4, "yaw": -0.2}, {"f": 8, "yaw": 0.2}]}
    out = render_shot(write_shot(tmp_path, shot), tmp_path / "out", "spline", size=60)
    assert out["kind"] == "gif" and len(out["frames"]) == 9       # every frame is still written
    _, count = gif_frames(out["playback"].read_bytes())
    assert count == 8                                             # frame 8 repeats frame 0: not played
    assert_gif_shows_the_frames(out["playback"], out["frames"][:8], 120, 120)


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_a_loop_mp4_leaves_out_the_repeated_last_frame(tmp_path):
    shot = {**SHOTS["sway"], "frames": 8, "keys": [{"f": 0, "yaw": 0.2}, {"f": 4, "yaw": -0.2}, {"f": 8, "yaw": 0.2}]}
    out = render_shot(write_shot(tmp_path, shot), tmp_path / "out", "spline", size=60)
    assert out["kind"] == "mp4"
    assert len(ffmpeg_frames(out["playback"], 120, 120)) == 8
    still = render_shot(write_shot(tmp_path, {**shot, "loop": False}), tmp_path / "out2", "spline", size=60)
    assert len(ffmpeg_frames(still["playback"], 120, 120)) == 9


def test_the_key_sheet_keeps_the_figure_in_its_smaller_panels(tmp_path):
    src = tmp_path / "shot.json"
    src.write_text(json.dumps(SHOTS["walk"]), encoding="utf-8")
    out = render_shot(src, tmp_path / "out", "step", size=160)
    w, h, px = decode(out["keys"].read_bytes())
    half = 80
    # no figure ink on the label strip of any panel below the first row: the figure stays inside its panel
    for row in range(1, h // half):
        for x in range(w):
            for y in range(row * half + 1, row * half + 3):
                assert px(x, y) not in (render.LEFT, render.RIGHT, render.CENTRE), (x, y)
