"""The pass on the real mesh: the editor renders the character as the game shows it, so the critics judge the mesh and not
only Kei's line drawings (kei unreal render-mesh, and before every review of an Unreal pass).

render_mesh(client, shot_dir, pass_name, timeout) -> dict
  Makes Kei's render level when it is missing (kei_ue script render_level), opens the pass's sequence, waits one editor
  tick, then has the editor place three cameras off the character's own path and start Movie Render Queue (render_mesh).
  Kei then waits on the disk for out_<pass>/mesh/<view>/f0000.png ... for every frame of every view, draws one contact
  sheet per view, out_<pass>/mesh_<view>.png (out_<pass>/mesh_<view>_2.png ... for a long shot), each frame labelled,
  and writes out_<pass>/mesh_report.json. A pass rendered already from the same joints is not rendered again.
  A failure is an UnrealError in words, recorded in mesh_report.json with "ok": false: Kei never puts its own line
  drawings in the place of the mesh in silence.
mesh_lines(shot_dir, passes) -> the lines the critics read about the mesh frames of those passes.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
import time
import zlib
from pathlib import Path
from typing import Callable

from kei.apps.unreal import Claireon, UnrealError, one_line, run_script, tick
from kei.apps.unreal_rig import kei_folder, sequences
from kei.sample import ShotError, read_json
from kei.sheet import INK, _Canvas

VIEWS = ("side", "three_quarter", "feet")
LEVEL = "/Game/Kei/_render/L_KeiRender"
SIZE = (1280, 720)
TIMEOUT_S = 1200.0     # three views of a few hundred frames, with the render's own warm-up, fit well inside this
POLL_S = 3.0
TILE = (320, 180)
COLUMNS = 6
PAGE = 48              # frames on one sheet: 6 x 8 tiles, about 1920 x 1600 pixels
LABEL_H = 14
HEADER_H = 22
GAP = 6                # white space between two tiles
REPORT = "mesh_report.json"


def mesh_folder(shot_dir: Path, pass_name: str) -> Path:
    return Path(shot_dir) / f"out_{pass_name}" / "mesh"


def report_path(shot_dir: Path, pass_name: str) -> Path:
    return Path(shot_dir) / f"out_{pass_name}" / REPORT


def _frames_of(shot_dir: Path, pass_name: str) -> tuple[list[int], str, list[int]]:
    """The frames joints.json holds, its hash (a new keying gives a new render) and the shot's key frames."""
    out = Path(shot_dir) / f"out_{pass_name}"
    src = out / "joints.json"
    if not src.is_file():
        raise ShotError(f"no {src}: key the pass in Unreal first (kei unreal key {shot_dir} {pass_name})")
    data = read_json(src, "joints")
    frames = sorted({int(fr["f"]) for fr in data.get("frames") or []})
    if not frames:
        raise ShotError(f"{src} has no frames")
    shot = read_json(out / "shot.json", "shot") if (out / "shot.json").is_file() else {}
    keys = sorted({int(k["f"]) for k in shot.get("keys") or [] if isinstance(k, dict) and "f" in k
                   and float(k["f"]).is_integer()})
    return frames, hashlib.sha256(src.read_bytes()).hexdigest(), keys


def frame_file(folder: Path, view: str, f: int) -> Path:
    return folder / view / f"f{f:04d}.png"


def missing_frames(folder: Path, views, frames: list[int]) -> dict[str, list[int]]:
    """For each view, the frames not on the disk yet (empty lists when every frame is there)."""
    return {v: [f for f in frames if not frame_file(folder, v, f).is_file()] for v in views}


def wait_for_frames(folder: Path, views, frames: list[int], timeout: float, sleep: Callable = time.sleep,
                    clock: Callable = time.monotonic) -> None:
    """Wait until every frame of every view is on the disk and the newest files stopped growing. Out of time is an
    UnrealError that says how far the render got."""
    start, sizes = clock(), None
    while True:
        gaps = missing_frames(folder, views, frames)
        if not any(gaps.values()):
            now = {v: frame_file(folder, v, frames[-1]).stat().st_size for v in views}
            if now == sizes and all(now.values()):
                return
            sizes = now
        if clock() - start >= timeout:
            got = ", ".join(f"{v} {len(frames) - len(g)} of {len(frames)}" for v, g in gaps.items())
            raise UnrealError(f"the editor did not render the mesh frames in {timeout:g} s ({got}): look at the Movie "
                              "Render Queue window and the Output Log in the editor, then render again")
        sleep(POLL_S)


# ---- reading the rendered frames back, standard library only ----

def _unfilter(raw: bytes, w: int, h: int, bpp: int) -> bytearray:
    stride = w * bpp
    out = bytearray(h * stride)
    prev = bytearray(stride)
    for y in range(h):
        base = y * (stride + 1)
        kind, line = raw[base], bytearray(raw[base + 1:base + 1 + stride])
        if kind == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif kind == 2:
            line = bytearray((a + b) & 255 for a, b in zip(line, prev))
        elif kind == 3:
            for x in range(stride):
                line[x] = (line[x] + ((line[x - bpp] if x >= bpp else 0) + prev[x]) // 2) & 255
        elif kind == 4:
            for x in range(stride):
                a, b, c = (line[x - bpp] if x >= bpp else 0), prev[x], (prev[x - bpp] if x >= bpp else 0)
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        elif kind != 0:
            raise ValueError(f"PNG filter {kind}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def read_rgb(data: bytes) -> tuple[int, int, bytearray]:
    """An 8-bit RGB or RGBA PNG (what Movie Render Queue and ffmpeg write) as width, height and RGB bytes."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    i, idat, head = 8, [], None
    while i + 8 <= len(data):
        n, kind = struct.unpack(">I", data[i:i + 4])[0], data[i + 4:i + 8]
        if kind == b"IHDR":
            head = struct.unpack(">IIBBBBB", data[i + 8:i + 8 + 13])
        elif kind == b"IDAT":
            idat.append(data[i + 8:i + 8 + n])
        i += 12 + n
    if head is None:
        raise ValueError("no PNG header")
    w, h, depth, colour, _, _, interlace = head
    if depth != 8 or colour not in (2, 6) or interlace:
        raise ValueError(f"a PNG Kei does not read (depth {depth}, colour type {colour}, interlace {interlace})")
    bpp = 3 if colour == 2 else 4
    px = _unfilter(zlib.decompress(b"".join(idat)), w, h, bpp)
    if bpp == 4:
        del px[3::4]
    return w, h, px


def shrink(w: int, h: int, px: bytearray, tw: int, th: int) -> bytearray:
    """Nearest-pixel resize of RGB bytes."""
    out = bytearray(tw * th * 3)
    xs = [min(w - 1, (x * w) // tw) * 3 for x in range(tw)]
    for y in range(th):
        row = min(h - 1, (y * h) // th) * w * 3
        o = y * tw * 3
        for x, sx in enumerate(xs):
            out[o + 3 * x:o + 3 * x + 3] = px[row + sx:row + sx + 3]
    return out


def _ffmpeg_tiles(view_dir: Path, frames: list[int], tmp: Path) -> dict[int, Path] | None:
    """Every frame scaled to a tile by ffmpeg, much faster than Python. None without ffmpeg or on its failure."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    cmd = [exe, "-y", "-loglevel", "error", "-start_number", str(frames[0]), "-i", str(view_dir / "f%04d.png"),
           "-frames:v", str(len(frames)), "-vf", f"scale={TILE[0]}:{TILE[1]}:flags=area", "-pix_fmt", "rgb24",
           "-pred", "none", "-start_number", "0", str(tmp / "t%04d.png")]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        return None
    got = {f: tmp / f"t{i:04d}.png" for i, f in enumerate(frames)}
    if r.returncode != 0 or not all(p.is_file() for p in got.values()):
        return None
    return got


def _tile(path: Path) -> bytearray:
    w, h, px = read_rgb(path.read_bytes())
    return px if (w, h) == TILE else shrink(w, h, px, *TILE)


def _paste(cv: _Canvas, ox: int, oy: int, px: bytearray) -> None:
    tw = TILE[0] * 3
    for y in range(TILE[1]):
        i = ((oy + y) * cv.w + ox) * 3
        cv.px[i:i + tw] = px[y * tw:(y + 1) * tw]


def contact_sheets(shot_dir: Path, pass_name: str, view: str, frames: list[int], keys: list[int]) -> list[Path]:
    """One sheet per PAGE frames of a view, every frame labelled F<n> (and KEY on a key frame)."""
    out = Path(shot_dir) / f"out_{pass_name}"
    view_dir = mesh_folder(shot_dir, pass_name) / view
    pages = [frames[i:i + PAGE] for i in range(0, len(frames), PAGE)]
    paths = []
    with tempfile.TemporaryDirectory(prefix="kei-mesh-") as tmp:
        quick = _ffmpeg_tiles(view_dir, frames, Path(tmp)) if frames == list(range(frames[0], frames[-1] + 1)) else None
        for n, page in enumerate(pages, 1):
            rows = (len(page) + COLUMNS - 1) // COLUMNS
            cv = _Canvas(COLUMNS * (TILE[0] + GAP) - GAP, HEADER_H + rows * (TILE[1] + LABEL_H + GAP) - GAP)
            part = f" ({n} OF {len(pages)})" if len(pages) > 1 else ""
            cv.text(6, 5, f"{pass_name} {view} - real mesh - F{page[0]}-F{page[-1]}{part}", INK, cv.w - 12)
            for i, f in enumerate(page):
                ox, oy = (i % COLUMNS) * (TILE[0] + GAP), HEADER_H + (i // COLUMNS) * (TILE[1] + LABEL_H + GAP)
                cv.text(ox + 4, oy + 2, f"F{f}" + (" KEY" if f in keys else ""), INK, TILE[0] - 8)
                src = quick[f] if quick else frame_file(mesh_folder(shot_dir, pass_name), view, f)
                try:
                    _paste(cv, ox, oy + LABEL_H, _tile(src))
                except (OSError, ValueError, zlib.error) as e:
                    raise UnrealError(f"the mesh frame {frame_file(mesh_folder(shot_dir, pass_name), view, f)} "
                                      f"cannot be read ({one_line(e, 120)}): render again") from e
            p = out / (f"mesh_{view}.png" if n == 1 else f"mesh_{view}_{n}.png")
            p.write_bytes(cv.png())
            paths.append(p)
    return paths


def _clear(shot_dir: Path, pass_name: str, views) -> None:
    out = Path(shot_dir) / f"out_{pass_name}"
    for v in views:
        for old in (mesh_folder(shot_dir, pass_name) / v).glob("f*.png"):
            old.unlink()
    for old in out.glob("mesh_*.png"):
        old.unlink()


def _reusable(shot_dir: Path, pass_name: str, sequence: str, sha: str, views) -> dict | None:
    try:
        rep = json.loads(report_path(shot_dir, pass_name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (rep.get("ok") and rep.get("sequence") == sequence and rep.get("joints_sha") == sha
            and list(rep.get("views") or {}) == list(views)):
        return None
    sheets = [Path(shot_dir) / s for v in rep["views"].values() for s in v.get("sheets") or []]
    return rep if sheets and all(p.is_file() for p in sheets) else None


def _write_report(shot_dir: Path, pass_name: str, rep: dict) -> None:
    report_path(shot_dir, pass_name).write_text(json.dumps(rep, indent=1), encoding="utf-8")


def render_mesh(client: Claireon, shot_dir: Path, pass_name: str, timeout: float = TIMEOUT_S, views=VIEWS,
                force: bool = False, sleep: Callable = time.sleep, clock: Callable = time.monotonic) -> dict:
    shot_dir = Path(shot_dir)
    made = sequences(shot_dir).get(pass_name) or []
    if not made:
        raise ShotError(f"no Unreal sequence for {pass_name} in {shot_dir}: key the pass first (kei unreal key)")
    seq = made[-1]
    frames, sha, keys = _frames_of(shot_dir, pass_name)
    views = list(views)
    if not force:
        held = _reusable(shot_dir, pass_name, seq, sha, views)
        if held is not None:
            return {**held, "reused": True}
    folder = mesh_folder(shot_dir, pass_name)
    rep = {"ok": False, "renderer": "unreal_mrq", "pass": pass_name, "sequence": seq, "joints_sha": sha,
           "frames": [frames[0], frames[-1]], "count": len(frames), "size": list(SIZE)}
    try:
        if frames[0] != 0:
            raise UnrealError(f"joints.json of {pass_name} starts at frame {frames[0]}, not 0: the render writes "
                              "from frame 0, so Kei cannot match the frames; key the pass again")
        _clear(shot_dir, pass_name, views)
        for v in views:
            (folder / v).mkdir(parents=True, exist_ok=True)
        level = run_script(client, "render_level.py", {"level": LEVEL})
        run_script(client, "render_mesh.py", {"stage": "open", "sequence": seq})
        tick()          # the character is bound one editor tick after the sequence opens
        tick()
        started = run_script(client, "render_mesh.py", {
            "stage": "render", "sequence": seq, "out_dir": folder.resolve().as_posix(), "last": frames[-1],
            "views": views, "level": LEVEL, "views_folder": kei_folder(shot_dir) + "/Views", "size": list(SIZE),
            "pelvis": "pelvis"})
        rep.update({"level_made": bool(level.get("made")), "cameras": started.get("views", []),
                    "travel_cm": started.get("travel_cm"), "warnings": started.get("warnings", [])})
        wait_for_frames(folder, views, frames, timeout, sleep, clock)
        rep["views"] = {}
        for v in views:
            sheets = contact_sheets(shot_dir, pass_name, v, frames, keys)
            rep["views"][v] = {"folder": (folder / v).relative_to(shot_dir).as_posix(),
                               "sheets": [p.relative_to(shot_dir).as_posix() for p in sheets]}
    except (UnrealError, ShotError) as e:
        rep["error"] = str(e)
        _write_report(shot_dir, pass_name, rep)
        raise
    rep["ok"] = True
    _write_report(shot_dir, pass_name, rep)
    return rep


def mesh_lines(shot_dir: Path, passes: list[str]) -> list[str]:
    """What the critics read about the real-mesh frames of the passes under review: the sheets to open, or why there
    are none. Empty for a shot that is not animated in Unreal."""
    from kei.apps.unreal_stage import is_unreal_shot
    shot_dir = Path(shot_dir)
    if not passes or not is_unreal_shot(shot_dir):
        return []
    lines = ["The real mesh, rendered in Unreal (judge these frames first; see \"The real mesh\" above):"]
    for p in passes:
        try:
            rep = json.loads(report_path(shot_dir, p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            rep = None
        if rep is None:
            lines.append(f"- {p}: NOT rendered on the mesh. Only Kei's line drawings exist for this pass: say so in "
                         "\"minor\", and judge nothing the line drawings cannot show as fine.")
        elif not rep.get("ok"):
            lines.append(f"- {p}: the mesh render FAILED ({one_line(rep.get('error', 'no reason given'), 300)}). "
                         "Do not pass it on the line drawings alone: ask the author (a question) to render it again "
                         f"with kei unreal render-mesh <shot> {p}, and judge the mesh on the next try.")
        else:
            for v, info in (rep.get("views") or {}).items():
                lines.append(f"- {p} {v}: {', '.join(info.get('sheets') or [])} (every frame, labelled; full size: "
                             f"{info.get('folder')}/f0000.png ...)")
            for w in rep.get("warnings") or []:
                lines.append(f"  note from the render: {w}")
    return lines
