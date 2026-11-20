"""Staging checks for the delivery camera, per frame and per camera setup, written beside the delivery render.

framing(shot, mode, character, camera) -> {"frames_out": [...], "setups": [...], "notes": [...]}
  For every frame, the character's mesh (every third vertex) is projected through the
  camera of that frame. A frame where any of them falls outside the picture is "out": a hand or a foot cut by the
  frame edge. Each setup (the stretch between two cuts) reports its frames, its yaw and how much of the picture's
  height the character fills at most. Soft notes, never a gate:
    out of frame       frames where the character leaves the picture, as runs (f12-18).
    short setup        a setup under SHORT_SETUP frames: it reads as a flash.
    crosses the line   a cut that moves the camera from the character's right side to its left (or back), so the
                       screen direction of the action flips.
    small in frame     a setup where the character fills less than SMALL of the picture's height.
"""
from __future__ import annotations

import math

from kei.render import Camera, _character_parts, _load, travel_line
from kei.sample import bake

SHORT_SETUP = 8
STEP = 3          # every third vertex of each part: enough to find the edge of the figure
SMALL = 0.25
SIDE = 0.17      # |cos(yaw)| under this is a front or back view: no side, so no line to cross


def _runs(frames: list[int]) -> list[str]:
    out, start, prev = [], None, None
    for f in frames:
        if start is None:
            start = prev = f
        elif f == prev + 1:
            prev = f
        else:
            out.append(f"f{start}" if start == prev else f"f{start}-{prev}")
            start = prev = f
    if start is not None:
        out.append(f"f{start}" if start == prev else f"f{start}-{prev}")
    return out


def framing(shot: dict, mode: str, character, camera: Camera) -> dict:
    from kei.characters import on_character
    ch = _load(character)
    shot = on_character(shot, ch)
    frames = bake(shot, mode)
    line = travel_line(shot, frames)
    out_frames, heights = [], []
    for f, fr in enumerate(frames):
        c = camera.at(f)
        if camera.follow:
            c = c.moved(line[f][0] - line[0][0], line[f][2] - line[0][2])
        pts = [v for part in _character_parts(ch, fr["pose"]) for v in part.verts[::STEP]]
        cx, cy = c.project(c.target)
        half_h, half_w = c.span / 2, c.span * c.aspect / 2
        hs, vs = [], []
        for q in pts:
            h, v = c.project(q)
            hs.append(h - cx)
            vs.append(v - cy)
        if not hs:
            continue
        if max(map(abs, hs)) > half_w or max(map(abs, vs)) > half_h:
            out_frames.append(f)
        heights.append((f, (max(vs) - min(vs)) / c.span))
    bounds = [0, *camera.cuts(), len(frames)]
    setups, notes = [], []
    for a, b in zip(bounds, bounds[1:]):
        if b <= a:
            continue
        c = camera.at(a)
        fill = max((h for f, h in heights if a <= f < b), default=0.0)
        setups.append({"frames": f"f{a}-{b - 1}", "yaw_deg": round(c.yaw_deg, 1), "fill": round(fill, 2)})
        if b - a < SHORT_SETUP and len(bounds) > 2:
            notes.append(f"short setup: f{a}-{b - 1} is {b - a} frames, under {SHORT_SETUP}; it reads as a flash")
        if fill < SMALL:
            notes.append(f"small in frame: in f{a}-{b - 1} the character fills {fill:.0%} of the picture's height")
    for cut in camera.cuts():
        before, after = camera.at(cut - 1), camera.at(cut)
        cb, ca = math.cos(math.radians(before.yaw_deg)), math.cos(math.radians(after.yaw_deg))
        if abs(cb) > SIDE and abs(ca) > SIDE and (cb > 0) != (ca > 0):
            notes.append(f"crosses the line: the cut at f{cut} moves the camera from the character's "
                         f"{'right' if cb > 0 else 'left'} side to its {'right' if ca > 0 else 'left'}; the screen "
                         "direction of the action flips")
    if out_frames:
        notes.insert(0, f"out of frame: {', '.join(_runs(out_frames))} (a part of the character leaves the picture)")
    return {"frames_out": out_frames, "setups": setups, "notes": notes}
