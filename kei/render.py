"""Views and playback: Kei draws the rig in four views and joins the frames into a video, with no image library.

draw_views(joints) gives one PNG with four panels: front, side, top and three quarter. Each view keeps one scale for
the whole shot, framed on the figure's own extent; where the figure travels the view follows the root and ground ticks
every 0.5 m show the travel. The ground line is drawn, the left side is drawn in a second colour and the centre of
mass is marked.
render_shot(shot.json, out_dir, mode) writes frames/f0000.png..., keys.png (the key frames) and playback.mp4 (when
ffmpeg is installed) or playback.gif (a stdlib encoder), and a still per key.

Cameras: by default each view frames the whole shot and holds still where it can ("fixed"). camera="follow" rides
the shot's even travel (the straight line from the first root to the last, one cycle on a loop), so a walk stays in
place and the ground ticks scroll under it, spaced to repeat exactly over one cycle so the loop has no jump at the
seam. A Camera (Camera.from_plan, from the "camera" in plan/plan.json) is the shot's locked delivery camera: one
panel at its aspect, orthographic or with a lens, following the travel when the plan says so.

The look is provisional: the colours and the bone list are constants, and draw_figure is the one function that
draws the figure, so a later design can replace it.
"""
from __future__ import annotations

import json
import math
import shutil
import struct
import subprocess
from pathlib import Path

from dataclasses import dataclass, replace

from kei.sample import ShotError, bake, check_shot, cycle_travel, normalize_keys, read_shot
from kei.sheet import _Canvas

LABEL = 16           # the label strip at the top of a panel
MARGIN = 0.12        # the share of the panel left empty around the figure

BORDER, TEXT = (205, 205, 205), (20, 20, 20)
RIGHT, LEFT, CENTRE = (40, 40, 40), (30, 120, 220), (110, 110, 110)
COM, GROUND = (220, 40, 40), (170, 150, 120)
PERFORMER = (200, 120, 210)     # a second performer ("<name>/<joint>" in the joints), drawn lighter, in one colour

SPINE = ("spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02", "head", "head_top")
SIDE_CHAINS = (("clavicle_{s}", "upperarm_{s}", "lowerarm_{s}", "hand_{s}", "hand_{s}_tip"),
               ("thigh_{s}", "calf_{s}", "foot_{s}", "ball_{s}", "ball_{s}_tip"),
               ("foot_{s}", "heel_{s}", "ball_{s}"))
CENTRE_LINES = (("thigh_l", "thigh_r"), ("head", "nose"))

VIEWS = ("front", "side", "top", "three quarter")
_Q = math.radians(45)
_E = math.radians(20)   # the three quarter camera looks down this much: the feet, the step width and the line they
                        # land on show, while the camera stays low enough that the bob and the balance still read


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


SENSOR = (36.0, 20.25)   # mm: a full-frame sensor cropped to 16:9, when the plan's camera names no sensor
CAMERA_KEYS = ("yaw_deg", "pitch_deg", "target_m", "span_m", "lens_mm", "distance_m", "sensor_mm", "aspect", "follow")


@dataclass(frozen=True)
class Camera:
    """A locked camera. yaw 0 looks at the character's right side (forward is screen right); +yaw swings the camera
    toward the character's front (90 is the front view). +pitch raises the camera to look down. With distance (m)
    and a lens the projection has perspective, scaled so the target plane keeps true size; without, it is
    orthographic. span is the frame's height (m) at the target."""
    cam: tuple
    right: tuple
    up: tuple
    target: tuple
    span: float
    aspect: float = 16 / 9
    distance: float | None = None
    follow: bool = False

    def __str__(self) -> str:
        return "delivery"

    def project(self, p) -> tuple[float, float]:
        rel = tuple(p[i] - self.target[i] for i in range(3))
        h = sum(rel[i] * self.right[i] for i in range(3))
        v = sum(rel[i] * self.up[i] for i in range(3))
        if self.distance:
            depth = self.distance - sum(rel[i] * self.cam[i] for i in range(3))
            k = self.distance / max(depth, 1e-6)
            h, v = h * k, v * k
        th = sum(self.target[i] * self.right[i] for i in range(3))
        tv = sum(self.target[i] * self.up[i] for i in range(3))
        return th + h, tv + v

    def moved(self, dx: float, dz: float) -> "Camera":
        return replace(self, target=(self.target[0] + dx, self.target[1], self.target[2] + dz))

    @staticmethod
    def from_plan(d) -> "Camera":
        """The "camera" of plan/plan.json: {"yaw_deg", "pitch_deg", "target_m": [x, y, z], "span_m" or "lens_mm" with
        "distance_m" (and "sensor_mm": [w, h]), "aspect": "16:9", "follow": true}. A wrong or unknown key is a ShotError,
        so a setting Kei does not have (a roll, say) is never silently ignored."""
        def bad(key, what):
            return ShotError(f'plan/plan.json "camera": {key} {what}')
        if not isinstance(d, dict):
            raise bad("", "must be an object")
        unknown = [k for k in d if k not in CAMERA_KEYS and k != "name" and not k.endswith("note")]
        if unknown:
            raise bad(", ".join(unknown), "not a camera setting, so it would be ignored; the settings are "
                      f"{', '.join(CAMERA_KEYS)} (a \"name\" or a key ending in \"note\" may hold words)")
        yaw, pitch = d.get("yaw_deg", 0), d.get("pitch_deg", 0)
        for key, v in (("yaw_deg", yaw), ("pitch_deg", pitch)):
            if not _num(v):
                raise bad(key, f"must be a number of degrees, not {v!r}")
        target = d.get("target_m", [0, 0.95, 0])
        if not (isinstance(target, list) and len(target) == 3 and all(map(_num, target))):
            raise bad("target_m", "must be [x, y, z] in metres")
        lens, dist = d.get("lens_mm"), d.get("distance_m")
        sensor = d.get("sensor_mm", list(SENSOR))
        if (lens is None) != (dist is None):
            raise bad("lens_mm", "and distance_m go together")
        if lens is not None:
            if not (_num(lens) and lens > 0 and _num(dist) and dist > 0):
                raise bad("lens_mm", "and distance_m must be numbers above 0")
            if not (isinstance(sensor, list) and len(sensor) == 2 and all(_num(s) and s > 0 for s in sensor)):
                raise bad("sensor_mm", "must be [width, height] in mm")
            span = dist * sensor[1] / lens
        else:
            span = d.get("span_m")
            if not (_num(span) and span > 0):
                raise bad("span_m", "(the frame's height in metres) is needed without lens_mm and distance_m")
        aspect = d.get("aspect", "16:9")
        if isinstance(aspect, str) and ":" in aspect:
            try:
                a, b = (float(x) for x in aspect.split(":"))
                aspect = a / b
            except (ValueError, ZeroDivisionError):
                raise bad("aspect", f"must look like 16:9, not {aspect!r}") from None
        if not (_num(aspect) and aspect > 0):
            raise bad("aspect", f"must look like 16:9, not {aspect!r}")
        follow = d.get("follow", False)
        if not isinstance(follow, bool):
            raise bad("follow", "must be true or false")
        y, p = math.radians(yaw), math.radians(pitch)
        cam = (math.cos(p) * math.cos(y), math.sin(p), math.cos(p) * math.sin(y))
        right = (-math.sin(y), 0.0, math.cos(y))
        up = (right[1] * cam[2] - right[2] * cam[1], right[2] * cam[0] - right[0] * cam[2],
              right[0] * cam[1] - right[1] * cam[0])
        return Camera(cam, right, up, tuple(float(t) for t in target), float(span), float(aspect),
                      float(dist) if dist else None, follow)


def _basis(view) -> tuple:
    """(toward the camera, screen right, screen up) of a view, in the world."""
    if isinstance(view, Camera):
        return view.cam, view.right, view.up
    return _CAMERA[view]


def stride_tick(cycle: float) -> float:
    """The ground tick spacing nearest TICK that divides one cycle of travel, so the ticks repeat at the seam."""
    if cycle < 1e-6:
        return TICK
    return cycle / max(1, round(cycle / TICK))


def travel_line(shot: dict, frames: list[dict]) -> list[tuple[float, float, float]]:
    """The shot's even travel on the ground, one point per frame: on a travelling loop, the first root moved on by
    the frame's share of one cycle; otherwise the straight line from the first frame's root to the last one's."""
    def root(fr):
        return fr["joints"].get("pelvis", fr["joints"].get("root", (0.0, 0.0, 0.0)))
    a, n = root(frames[0]), len(frames) - 1
    if shot.get("loop") and n > 0:
        d = cycle_travel(shot, normalize_keys(shot))
        line = [(a[0] + d[0] * f / n, 0.0, a[2] + d[2] * f / n) for f in range(n + 1)]
        line[-1] = line[0]   # the last frame of a loop is frame 0 again
        return line
    b = root(frames[-1])
    return [(a[0] + (b[0] - a[0]) * f / max(n, 1), 0.0, a[2] + (b[2] - a[2]) * f / max(n, 1)) for f in range(n + 1)]


def _cycle(shot: dict, line) -> tuple[float, tuple[float, float]]:
    """(the length of one cycle of travel, the unit direction of travel on the ground)."""
    if shot.get("loop"):
        d = cycle_travel(shot, normalize_keys(shot))
        dx, dz = d[0], d[2]
    else:
        dx, dz = line[-1][0] - line[0][0], line[-1][2] - line[0][2]
    n = math.hypot(dx, dz)
    return n, ((dx / n, dz / n) if n > 1e-9 else (0.0, 1.0))


def _view(view, p) -> tuple[float, float]:
    """A world point on a view's screen plane (right, up), orthographic."""
    if isinstance(view, Camera):
        return view.project(p)
    x, y, z = p
    if view == "front":      # the camera in front of the character: its right is on the screen's left
        return -x, y
    if view == "side":       # the camera on the character's right: forward is to the screen's right
        return z, y
    if view == "top":        # from above: forward is up the screen
        return -x, z
    if view == "back":       # the camera behind the character: its right is on the screen's right
        return x, y
    # three quarter: turned 45 degrees between front and side and raised _E, looking down on the figure
    return (-x * math.cos(_Q) + z * math.sin(_Q),
            y * math.cos(_E) - (x * math.sin(_Q) + z * math.cos(_Q)) * math.sin(_E))


# Per view: the direction toward the camera, the screen's right and the screen's up, in the world.
_CAMERA = {
    "front": ((0.0, 0.0, 1.0), (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "side": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    "back": ((0.0, 0.0, -1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "top": ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "three quarter": ((math.sin(_Q) * math.cos(_E), math.sin(_E), math.cos(_Q) * math.cos(_E)),
                      (-math.cos(_Q), 0.0, math.sin(_Q)),
                      (-math.sin(_Q) * math.sin(_E), math.cos(_E), -math.cos(_Q) * math.sin(_E))),
}


MIN_SPAN = 1.0       # metres: the smallest span a view is framed to, so the top view keeps some floor around it
TICK = 0.5           # metres between two ground ticks
KEEP = 0.85          # the least share of its own size a figure keeps when a view zooms out for a jump


def _extent(vals: list[float]) -> tuple[float, float]:
    """(centre, size) of a list of numbers."""
    return (max(vals) + min(vals)) / 2, max(vals) - min(vals)


def fit(frames: list[dict], views: tuple[str, ...] = VIEWS, follow: list | None = None,
        tick: float | None = None) -> list[dict[str, tuple[float, float, float]]]:
    """The bounds of each frame: [{view: (centre h, centre v, span in m)}], the span in metres so the same bounds fit
    a panel of any size.

    Each view has one span for the whole shot: the figure's own extent in that view, measured from the root, so a
    travel or a jump does not shrink the figure. On each screen axis of a view the centre stays put when the whole
    shot fits the panel; otherwise it follows the root (a walk in the side view, a jump in every view), and the ground
    ticks show the travel. With follow (a point per frame on the ground, the even travel) the views ride it
    instead: the travel stays centred and only the ground moves. tick replaces the ground tick spacing."""
    roots = follow or [j.get("pelvis", j.get("root", (0.0, 0.0, 0.0))) for j in frames]
    out = [{} for _ in frames]
    for view in views:
        rs = [_view(view, r) for r in roots]
        # a raised camera sees the travel climb the screen too: a follow camera rides that climb, so the points are
        # measured as if the travel stayed level and the climb is added back to each frame's centre below
        lift = [r[1] - rs[0][1] if follow is not None and view != "top" else 0.0 for r in rs]
        # the "root" joint is the root's shadow on the ground, not part of the figure: a jump must not stretch it
        absolute = [[(q[0], q[1] - dl) for q in (_view(view, p) for n, p in j.items() if n != "root")]
                    for j, dl in zip(frames, lift)]
        rel = [(q[0] - r[0], q[1] + dl - r[1]) for pts, r, dl in zip(absolute, rs, lift) for q in pts]
        rel_c, rel_e = zip(*(_extent([q[ax] for q in rel]) for ax in (0, 1)))
        abs_c, abs_e = zip(*(_extent([q[ax] for pts in absolute for q in pts]) for ax in (0, 1)))
        span = max(MIN_SPAN, *rel_e)
        if view != "top":   # a jump may zoom out a little (the figure keeps KEEP of its size) to keep the ground
            span = max(span, min(abs_e[1] / (1 + MARGIN), span / KEEP))
        room = span * (1 + MARGIN)      # the extent a centre may hold still, with half the margin left
        for i, (r, pts) in enumerate(zip(rs, absolute)):
            c = []
            for ax in (0, 1):
                if follow is not None and (ax == 0 or view == "top"):
                    c.append(r[ax] + rel_c[ax])            # the follow camera rides the travel
                elif abs_e[ax] <= room:
                    c.append(abs_c[ax])                     # the whole shot fits: the camera holds still
                elif ax == 1 and view != "top":
                    # up and down: move only as far as the figure needs, so the ground leaves the panel late
                    lo, hi = min(q[1] for q in pts), max(q[1] for q in pts)
                    c.append(min(max(abs_c[1], hi - room / 2), lo + room / 2))
                else:
                    c.append(r[ax] + rel_c[ax])            # along the travel: follow the root
            out[i][view] = (c[0], c[1] + lift[i], span)
    if tick:
        for o in out:
            o["_tick"] = tick
    return out


def _scale(span: float, size: int) -> float:
    return (size - LABEL) * (1 - 2 * MARGIN) / span


def _px(view: str, h: float, v: float, bounds: dict, size: int) -> tuple[int, int]:
    ch, cv, span = bounds[view]
    s, area = _scale(span, size), size - LABEL
    return round(size / 2 + (h - ch) * s), round(LABEL + area / 2 - (v - cv) * s)


def project(view: str, p, bounds: dict, size: int) -> tuple[int, int]:
    """A world point to a pixel in a panel whose top left corner is (0, 0)."""
    return _px(view, *_view(view, p), bounds, size)


def _ticks(view: str, axis: int, bounds: dict, size: int) -> list[float]:
    """The world values, every TICK metres, that the panel shows on one screen axis of a view."""
    ch, cv, span = bounds[view]
    half = (size / 2) / _scale(span, size)
    c = (ch, cv)[axis]
    t = bounds.get("_tick", TICK)
    return [k * t for k in range(math.floor((c - half) / t), math.ceil((c + half) / t) + 1)]


def draw_figure(cv: _Canvas, to_px, joints: dict) -> None:
    """The figure: right side dark, left side in the left colour, the centre of mass as a dot. A second performer's
    joints ("ghost/pelvis" ...) are drawn first, behind it, in one lighter colour."""
    for who in sorted({n.split("/", 1)[0] for n in joints if "/" in n}):
        mine = {n.split("/", 1)[1]: p for n, p in joints.items() if n.startswith(who + "/")}
        _draw_one(cv, to_px, mine, {"right": PERFORMER, "left": PERFORMER, "centre": PERFORMER, "com": None})
    _draw_one(cv, to_px, {n: p for n, p in joints.items() if "/" not in n},
              {"right": RIGHT, "left": LEFT, "centre": CENTRE, "com": COM})


def _draw_one(cv: _Canvas, to_px, joints: dict, colours: dict) -> None:
    def seg(a, b, c):
        if a in joints and b in joints:
            cv.line(*to_px(joints[a]), *to_px(joints[b]), c)
    RIGHT, LEFT, CENTRE, COM = colours["right"], colours["left"], colours["centre"], colours["com"]
    for s, c in (("r", RIGHT), ("l", LEFT)):
        for chain in SIDE_CHAINS:
            names = [n.format(s=s) for n in chain]
            for a, b in zip(names, names[1:]):
                seg(a, b, c)
    for a, b in zip(SPINE, SPINE[1:]):
        seg(a, b, RIGHT)
    for a, b in CENTRE_LINES:
        seg(a, b, CENTRE)
    if "com" in joints and COM is not None:
        cv.disk(*to_px(joints["com"]), 3, COM)


def _panel(cv: _Canvas, ox: int, oy: int, view: str, joints: dict, bounds: dict, size: int, label: str) -> None:
    """One view in the panel at (ox, oy). Nothing drawn here leaves the panel."""
    saved, cv.clip = cv.clip, (ox, oy, ox + size, oy + size)
    try:
        _panel_inside(cv, ox, oy, view, joints, bounds, size, label)
    finally:
        cv.clip = saved


def _panel_inside(cv: _Canvas, ox: int, oy: int, view: str, joints: dict, bounds: dict, size: int,
                  label: str) -> None:
    cv.box(ox, oy, ox + size - 1, oy + size - 1, BORDER)

    def to_px(p):
        x, y = project(view, p, bounds, size)
        return ox + x, oy + y
    if view != "top":
        _, gy = to_px((0.0, 0.0, 0.0))
        cv.line(ox + 1, gy, ox + size - 2, gy, GROUND, False)
        if view != "front":     # ticks every TICK metres along the ground, so a travel stays visible
            for h in _ticks(view, 0, bounds, size):
                tx = ox + _px(view, h, 0.0, bounds, size)[0]
                cv.line(tx, gy + 1, tx, gy + 4, GROUND, False)
        if not oy + LABEL <= gy < oy + size:    # the ground is out of the panel: a height ruler shows how high
            for v in _ticks(view, 1, bounds, size):
                ty = oy + _px(view, 0.0, v, bounds, size)[1]
                if ty >= oy + LABEL:
                    cv.line(ox + 1, ty, ox + 5, ty, GROUND, False)
    else:
        ox0, oy0 = to_px((0.0, 0.0, 0.0))
        cv.line(ox0 - 4, oy0, ox0 + 4, oy0, GROUND, False)
        cv.line(ox0, oy0 - 4, ox0, oy0 + 4, GROUND, False)
        for h in _ticks(view, 0, bounds, size):     # a small cross every TICK metres on the floor
            for v in _ticks(view, 1, bounds, size):
                x, y = _px(view, h, v, bounds, size)
                cv.line(ox + x - 1, oy + y, ox + x + 1, oy + y, GROUND, False)
                cv.line(ox + x, oy + y - 1, ox + x, oy + y + 1, GROUND, False)
    draw_figure(cv, to_px, joints)
    cv.text(ox + 4, oy + 3, f"{view} {label}".strip(), TEXT, size - 8)


def _views_on(cv: _Canvas, ox: int, oy: int, joints: dict, size: int, bounds: dict, label: str) -> None:
    for i, view in enumerate(VIEWS):
        _panel(cv, ox + (i % 2) * size, oy + (i // 2) * size, view, joints, bounds, size, label)


def draw_views(joints: dict, size: int = 360, bounds: dict | None = None, label: str = "") -> bytes:
    """One PNG, two panels by two (front, side / top, three quarter), each size by size pixels."""
    bounds = bounds or fit([joints])[0]
    cv = _Canvas(2 * size, 2 * size)
    _views_on(cv, 0, 0, joints, size, bounds, label)
    return cv.png()


# ---------------- the characters ----------------
CHARACTER_VIEWS = ("front", "side", "back", "three quarter", "top")
SHADOW_SIDE, LIGHT_SIDE = 0.58, 0.47     # half-lambert shading: shade = SHADOW_SIDE + LIGHT_SIDE * (0.5 + 0.5 n.L)
OUTLINE = 0.62                           # an outline pixel's share of its own colour
DEPTH_STEP = 0.004                       # metres: a neighbour this much farther draws an outline
OVERLAY = 0.4                            # how much of the left colour tints the left side, when the overlay is on
GLOW = 0.45                              # the glow's strength around the chest C at emission 1


def _hex(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def _light(view):
    cam, right, up = _basis(view)
    v = tuple(cam[i] * 0.7 + up[i] * 0.55 - right[i] * 0.35 for i in range(3))   # from the front, above, the left
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def character_points(parts) -> dict:
    """A few points of a posed mesh for framing: the extremes on each world axis, plus the pelvis as the root."""
    pts = {}
    for k in range(3):
        for pick, tag in ((min, "lo"), (max, "hi")):
            v = pick((v for p in parts for v in p.verts), key=lambda q: q[k])
            pts[f"{tag}{k}"] = v
    return pts


def _raster(view: str, parts, ch, to_px, w: int, h: int, emission: float, overlay: bool, flat: bool):
    """Depth-buffered triangles of the posed parts in one panel: colour, depth and part id per pixel."""
    cam = _basis(view)[0]
    light = _light(view)
    mats = {k: _hex(v) for k, v in ch.materials.items()}
    from kei.characters.texture import load_texture, sample
    imported = bool(getattr(ch, "parts", None))
    persp = isinstance(view, Camera) and view.distance
    zbuf = [-math.inf] * (w * h)
    cbuf = [None] * (w * h)
    ibuf = [-1] * (w * h)
    for pid, p in enumerate(parts):
        base = mats["body"] if p.material == "emission" else mats[p.material]
        if p.material == "emission":
            # the C: emissive orange at full strength, a slightly darker inset of the body colour when off
            dim = tuple(c * 0.9 for c in base)
            base = tuple(dim[i] + (mats["emission"][i] - dim[i]) * emission for i in range(3))
        elif overlay and p.bone.endswith("_l"):
            base = tuple(base[i] + (LEFT[i] - base[i]) * OVERLAY for i in range(3))
        scr = [to_px(v) for v in p.verts]
        depth = [sum(v[i] * cam[i] for i in range(3)) for v in p.verts]
        if flat or (p.material == "emission" and emission > 0):     # a silhouette, or the glowing C: unlit
            shade = [1.0] * len(p.verts)
        else:
            shade = [min(1.0, SHADOW_SIDE + LIGHT_SIDE * (0.5 + 0.5 * sum(n[i] * light[i] for i in range(3))))
                     for n in p.normals]
        tex = load_texture(ch, getattr(p, "texture", 0)) if imported and p.uvs is not None and not flat else None
        textured = tex is not None
        if textured:
            if persp:   # 1 / distance from the lens per vertex: texture coordinates interpolate perspective-correct
                q = [1.0 / max(0.1, view.distance - sum((v[i] - view.target[i]) * cam[i] for i in range(3)))
                     for v in p.verts]
            else:
                q = [1.0] * len(p.verts)
            tint = (overlay and p.bone.endswith("_l"))
        for ti, t in enumerate(p.tris):
            a, b, c = t
            v0, v1, v2 = p.verts[a], p.verts[b], p.verts[c]
            e1 = (v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2])
            e2 = (v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2])
            nf = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
            if nf[0] * cam[0] + nf[1] * cam[1] + nf[2] * cam[2] <= 0:
                continue                                       # faces away from the camera
            (x0, y0), (x1, y1), (x2, y2) = scr[a], scr[b], scr[c]
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(area) < 1e-12:
                continue
            lo_x, hi_x = max(0, math.floor(min(x0, x1, x2))), min(w - 1, math.ceil(max(x0, x1, x2)))
            lo_y, hi_y = max(0, math.floor(min(y0, y1, y2))), min(h - 1, math.ceil(max(y0, y1, y2)))
            if lo_x > hi_x or lo_y > hi_y:
                continue
            inv = 1.0 / area
            d0, d1, d2 = depth[a], depth[b], depth[c]
            s0, s1, s2 = shade[a], shade[b], shade[c]
            if textured:
                uv = p.uvs[ti]
                q0, q1, q2 = q[a], q[b], q[c]
            for y in range(lo_y, hi_y + 1):
                py = y + 0.5
                row = y * w
                for x in range(lo_x, hi_x + 1):
                    px = x + 0.5
                    w0 = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) * inv
                    w1 = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) * inv
                    w2 = 1.0 - w0 - w1
                    if w0 < 0 or w1 < 0 or w2 < 0:
                        continue
                    z = w0 * d0 + w1 * d1 + w2 * d2
                    i = row + x
                    if z <= zbuf[i]:
                        continue
                    zbuf[i] = z
                    s = w0 * s0 + w1 * s1 + w2 * s2
                    if textured:
                        a0, a1, a2 = w0 * q0, w1 * q1, w2 * q2
                        qs = a0 + a1 + a2
                        col = sample(tex, (a0 * uv[0] + a1 * uv[2] + a2 * uv[4]) / qs,
                                     (a0 * uv[1] + a1 * uv[3] + a2 * uv[5]) / qs)
                        if tint:
                            col = tuple(col[k] + (LEFT[k] - col[k]) * OVERLAY for k in range(3))
                        cbuf[i] = (col[0] * s, col[1] * s, col[2] * s)
                    else:
                        cbuf[i] = (base[0] * s, base[1] * s, base[2] * s)
                    ibuf[i] = pid
    return zbuf, cbuf, ibuf


def _composite(cv: _Canvas, ox: int, oy: int, w: int, h: int, parts, bufs, emission: float, silhouette: bool,
               glow_px: int) -> None:
    """The buffers onto the canvas: outlines where a neighbour is another part farther away or empty, the glow."""
    if silhouette:
        for i, pid in enumerate(bufs[2]):
            if pid >= 0:
                cv.dot(ox + i % w, oy + i // w, (0, 0, 0))
        return
    for i, c in enumerate(_shade(w, h, parts, bufs, emission, glow_px)):
        if c is not None:
            cv.dot(ox + i % w, oy + i // w, c)


def _shade(w: int, h: int, parts, bufs, emission: float, glow_px: int, reach: int = 1) -> list:
    """The colour of every pixel of the buffers (None where no part is): a darker outline where a neighbour up to
    reach pixels away is another part farther away or empty, and the glow around the C."""
    zbuf, cbuf, ibuf = bufs
    out = list(cbuf)
    steps = [(d, 0) for d in range(1, reach + 1)] + [(-d, 0) for d in range(1, reach + 1)] + \
            [(0, d) for d in range(1, reach + 1)] + [(0, -d) for d in range(1, reach + 1)]
    for i, pid in enumerate(ibuf):
        if pid < 0 or (emission > 0 and parts[pid].material == "emission"):    # a light has no dark outline
            continue
        x, y = i % w, i // w
        z = zbuf[i]
        for dx, dy in steps:
            xx, yy = x + dx, y + dy
            j = yy * w + xx if 0 <= xx < w and 0 <= yy < h else -1
            if j < 0 or ibuf[j] < 0 or (ibuf[j] != pid and zbuf[j] < z - DEPTH_STEP):
                c = cbuf[i]
                out[i] = (c[0] * OUTLINE, c[1] * OUTLINE, c[2] * OUTLINE)
                break
    glow = None
    if emission > 0 and glow_px > 0:
        marks = [i for i, pid in enumerate(ibuf) if pid >= 0 and parts[pid].material == "emission"]
        if marks:
            glow = {}
            for i in marks:
                x, y = i % w, i // w
                for dy in range(-glow_px, glow_px + 1):
                    for dx in range(-glow_px, glow_px + 1):
                        xx, yy = x + dx, y + dy
                        d = math.hypot(dx, dy)
                        if 0 < d <= glow_px and 0 <= xx < w and 0 <= yy < h:
                            j = yy * w + xx
                            glow[j] = max(glow.get(j, 0.0), (1 - d / (glow_px + 1)) * GLOW * emission)
            for i in marks:
                glow.pop(i, None)
    for i, c in enumerate(out):
        if c is None:
            continue
        if glow and i in glow:
            g = glow[i]
            c = tuple(c[k] + (EMISSION_GLOW[k] - c[k]) * g for k in range(3))
        out[i] = tuple(max(0, min(255, round(v))) for v in c)
    return out


def _smooth_onto(cv: _Canvas, ox: int, oy: int, w: int, h: int, ss: int, colours: list) -> None:
    """A figure drawn ss times larger, averaged down onto the canvas: each pixel mixes its ss x ss samples, an
    empty sample showing what the canvas already holds there (the page, the ground line), so edges blend."""
    n = ss * ss
    W = w * ss
    for y in range(h):
        for x in range(w):
            r = g = b = 0
            empty = 0
            base = (y * ss) * W + x * ss
            for sy in range(ss):
                row = base + sy * W
                for sx in range(ss):
                    c = colours[row + sx]
                    if c is None:
                        empty += 1
                    else:
                        r += c[0]
                        g += c[1]
                        b += c[2]
            if empty == n:
                continue
            X, Y = ox + x, oy + y
            if empty:
                x0, y0, x1, y1 = cv.clip
                if not (max(0, x0) <= X < min(cv.w, x1) and max(0, y0) <= Y < min(cv.h, y1)):
                    continue
                i = (Y * cv.w + X) * 3
                r += cv.px[i] * empty
                g += cv.px[i + 1] * empty
                b += cv.px[i + 2] * empty
            cv.dot(X, Y, (round(r / n), round(g / n), round(b / n)))


EMISSION_GLOW = (255, 170, 90)
TICKS_EACH_WAY = 40     # ground ticks drawn on each side of the travel's start, enough for any panel
SUPERSAMPLE = 3         # the figure is drawn this many times larger on each axis and averaged down, so its edges
                        # blend instead of stepping; the silhouette stays hard, to compare characters pixel for pixel


def _ground_ticks(cv: _Canvas, ox: int, oy: int, view, bounds: dict, to_px, w: int, size: int) -> None:
    """Marks on the ground along the line of travel, fixed in the world, when the camera follows the travel. Their
    spacing divides one cycle, so a loop's last frame and its first show them in the same place."""
    ticks = bounds.get("_ticks")
    if not ticks or view == "front":
        return
    (x0, z0), (ux, uz), t = ticks
    for k in range(-TICKS_EACH_WAY, TICKS_EACH_WAY + 1):
        p = (x0 + ux * k * t, 0.0, z0 + uz * k * t)
        if isinstance(view, Camera) and view.distance:
            rel = [p[i] - view.target[i] for i in range(3)]
            if view.distance - sum(rel[i] * view.cam[i] for i in range(3)) <= 0.1:
                continue                                    # behind the lens
        x, y = to_px(p)
        x, y = round(x), round(y)
        if 0 <= x < w and LABEL <= y < size:
            cv.line(ox + x, oy + y + 1, ox + x, oy + y + 5, GROUND, False)


SHADOW = (95, 92, 88)        # the contact shadow's colour at full strength
SHADOW_ALPHA = 0.6            # its strength under a planted foot
SHADOW_LIFT = 0.06            # metres: a sole this high casts no shadow


def _contact_shadows(cv: _Canvas, ox: int, oy: int, parts, to_px) -> None:
    """A soft ellipse on the ground under each foot, darkest when the foot is planted and gone when it is
    SHADOW_LIFT above the ground, so a figure seen from above does not float. Drawn before the figure."""
    for side in "lr":
        pts = [v for p in parts if p.bone in (f"foot_{side}", f"ball_{side}") for v in p.verts]
        if not pts:
            continue
        k = 1.0 - min(p[1] for p in pts) / SHADOW_LIFT
        if k <= 0:
            continue
        xs, zs = [p[0] for p in pts], [p[2] for p in pts]
        c = ((min(xs) + max(xs)) / 2, 0.0, (min(zs) + max(zs)) / 2)
        a, bb = max(0.03, (max(zs) - min(zs)) / 2 * 1.1), max(0.025, (max(xs) - min(xs)) / 2 * 1.2)
        c0, cu, cv_ = to_px(c), to_px((c[0], 0.0, c[2] + a)), to_px((c[0] + bb, 0.0, c[2]))
        U = (cu[0] - c0[0], cu[1] - c0[1])
        V = (cv_[0] - c0[0], cv_[1] - c0[1])
        det = U[0] * V[1] - U[1] * V[0]
        if abs(det) < 1e-9:
            continue
        r = abs(U[0]) + abs(U[1]) + abs(V[0]) + abs(V[1])
        x0, x1 = int(c0[0] - r) - 1, int(c0[0] + r) + 2
        y0, y1 = int(c0[1] - r) - 1, int(c0[1] + r) + 2
        for y in range(y0, y1):
            for x in range(x0, x1):
                dx, dy = x - c0[0], y - c0[1]
                su = (dx * V[1] - dy * V[0]) / det
                sv = (U[0] * dy - U[1] * dx) / det
                d2 = su * su + sv * sv
                if d2 >= 1:
                    continue
                X, Y = ox + x, oy + y
                cx0, cy0, cx1, cy1 = cv.clip
                if not (max(0, cx0) <= X < min(cv.w, cx1) and max(0, cy0) <= Y < min(cv.h, cy1)):
                    continue
                t = SHADOW_ALPHA * k * (1 - d2) ** 2
                i = (Y * cv.w + X) * 3
                for ch_ in range(3):
                    cv.px[i + ch_] = round(cv.px[i + ch_] + (SHADOW[ch_] - cv.px[i + ch_]) * t)


def _character_panel(cv: _Canvas, ox: int, oy: int, view, ch, parts, bounds: dict, size: int, label: str,
                     emission: float, overlay: bool, silhouette: bool = False, width: int | None = None,
                     ss: int | None = None, clean: bool = False, joints: dict | None = None) -> None:
    """One view of the character. clean leaves out the review marks (the border, the label, the ground ticks) and
    keeps the ground line, for a video to post. joints draws the skeleton over the body (an imported character's
    fit sheet)."""
    w = width or size
    ss = SUPERSAMPLE if ss is None else max(1, int(ss))
    saved, cv.clip = cv.clip, (ox, oy, ox + w, oy + size)
    try:
        ch_, cv_, span = bounds[view]
        s, area = _scale(span, size), size - LABEL

        def to_px(p):
            h_, v_ = _view(view, p)
            return w / 2 + (h_ - ch_) * s, LABEL + area / 2 - (v_ - cv_) * s
        if not silhouette:
            if not clean:
                cv.box(ox, oy, ox + w - 1, oy + size - 1, BORDER)
            if view == "three quarter":
                # seen from above, the ground is a plane: a review draws the line of travel on it, through the
                # ground under the figure, so the feet read as landing on it; a post shows the figure alone
                if not clean:
                    g = bounds.get("_ground", (0.0, 0.0, 0.0))
                    ux, uz = bounds["_ticks"][1] if bounds.get("_ticks") else (0.0, 1.0)
                    a = to_px((g[0] - ux * 50, 0.0, g[2] - uz * 50))
                    b = to_px((g[0] + ux * 50, 0.0, g[2] + uz * 50))
                    cv.line(ox + round(a[0]), oy + round(a[1]), ox + round(b[0]), oy + round(b[1]), GROUND, False)
                    _ground_ticks(cv, ox, oy, view, bounds, to_px, w, size)
                else:      # a post: soft contact shadows instead, so the feet land on the ground
                    _contact_shadows(cv, ox, oy, parts, to_px)
            elif view != "top":
                gy = round(to_px(bounds.get("_ground", (0.0, 0.0, 0.0)))[1])
                cv.line(ox + 1, oy + gy, ox + w - 2, oy + gy, GROUND, False)
                if not clean:
                    _ground_ticks(cv, ox, oy, view, bounds, to_px, w, size)
        glow_px = max(1, round(size / 110))
        if silhouette or ss <= 1:
            bufs = _raster(view, parts, ch, to_px, w, size, emission, overlay, silhouette)
            _composite(cv, ox, oy, w, size, parts, bufs, emission, silhouette, glow_px)
        else:
            def to_ss(p):
                x, y = to_px(p)
                return x * ss, y * ss
            bufs = _raster(view, parts, ch, to_ss, w * ss, size * ss, emission, overlay, False)
            _smooth_onto(cv, ox, oy, w, size, ss,
                         _shade(w * ss, size * ss, parts, bufs, emission, glow_px * ss, reach=ss))
        if joints:     # the skeleton over the body: the fit sheet of an imported character
            draw_figure(cv, lambda q: (round(ox + to_px(q)[0]), round(oy + to_px(q)[1])), joints)
        if not silhouette and not clean:
            cv.text(ox + 4, oy + 3, f"{view} {label}".strip(), TEXT, w - 8)
    finally:
        cv.clip = saved


def _character_parts(ch, pose: dict):
    from kei.characters.mesh import pose_mesh
    return pose_mesh(ch, pose)


def _load(character):
    if isinstance(character, str):
        from kei.characters import load_character
        return load_character(character)
    return character


def character_bounds(parts, views: tuple[str, ...] = CHARACTER_VIEWS) -> dict:
    return fit([{**character_points(parts), "pelvis": (0.0, 0.0, 0.0)}], views)[0]


def draw_character_views(character, pose: dict, size: int = 360, views: tuple[str, ...] = CHARACTER_VIEWS,
                         emission: float = 1.0, overlay: bool = False, bounds: dict | None = None,
                         label: str = "", supersample: int | None = None) -> bytes:
    """One PNG, a row of panels (front, side, back, three quarter, top by default), the character's shapes drawn
    in ivory and charcoal with soft light, a darker outline and the chest C glowing at emission (0 = off). overlay
    tints the left side, for reviews."""
    ch = _load(character)
    emission = max(0.0, min(1.0, float(emission)))     # as the export clamps it
    parts = _character_parts(ch, pose)
    bounds = bounds or character_bounds(parts, views)
    cv = _Canvas(len(views) * size, size)
    for i, view in enumerate(views):
        _character_panel(cv, i * size, 0, view, ch, parts, bounds, size, label, emission, overlay, ss=supersample)
    return cv.png()


FIT_VIEWS = ("front", "side", "three quarter")


def draw_fit_sheet(character, size: int = 480) -> bytes:
    """An imported character's fit sheet: the body at rest with the fitted skeleton drawn over it, in the front, side
    and three quarter views, the left side tinted, so a person can check every joint sits where the body bends; then
    the side view at a shot's neutral stance (kei.characters.neutral_pose: the trunk stood up, the head stacked), so
    the person approves what a shot will play."""
    from kei.characters import neutral_pose, rest_pose
    from kei.rig import solve
    ch = _load(character)
    pose = rest_pose(ch)
    parts = _character_parts(ch, pose)
    bounds = character_bounds(parts, FIT_VIEWS)
    joints = solve(pose, ch.proportions)
    cv = _Canvas((len(FIT_VIEWS) + 1) * size, size)
    for i, view in enumerate(FIT_VIEWS):
        _character_panel(cv, i * size, 0, view, ch, parts, bounds, size, "fit", 0.0, True, joints=joints)
    neutral = neutral_pose(ch)
    n_parts = _character_parts(ch, neutral)
    _character_panel(cv, len(FIT_VIEWS) * size, 0, "side", ch, n_parts, character_bounds(n_parts, ("side",)), size,
                     "neutral stance", 0.0, True, joints=solve(neutral, ch.proportions))
    return cv.png()


def draw_silhouette(character, pose: dict | None = None, size: int = 360, view: str = "front") -> bytes:
    """The character in black on white, framed on a fixed 1.9 m span centred 0.86 m up, so two characters compare
    pixel for pixel."""
    ch = _load(character)
    if pose is None:
        from kei.characters import rest_pose
        pose = rest_pose(ch)
    cv = _Canvas(size, size)
    bounds = {view: (0.0, 0.86, 1.9 / (1 + MARGIN))}
    _character_panel(cv, 0, 0, view, ch, _character_parts(ch, pose), bounds, size, "", 0.0, False, True)
    return cv.png()


def _key_sheet(frames: list[dict], key_fs: list[int], bounds: list[dict], size: int) -> bytes:
    cols = min(4, len(key_fs))
    rows = -(-len(key_fs) // cols)
    cv = _Canvas(cols * 2 * size, rows * 2 * size)
    for i, f in enumerate(key_fs):
        _views_on(cv, (i % cols) * 2 * size, (i // cols) * 2 * size, frames[f]["joints"], size, bounds[f],
                  f"F{f} key")
    return cv.png()


# ---------------- GIF ----------------
def lzw_encode(data: bytes, min_size: int) -> bytes:
    """GIF LZW: variable code size from min_size + 1 up to 12 bits, a clear code when the table is full."""
    clear, eoi = 1 << min_size, (1 << min_size) + 1
    acc, nacc, out = 0, 0, bytearray()
    size = min_size + 1

    def put(code):
        nonlocal acc, nacc
        acc |= code << nacc
        nacc += size
        while nacc >= 8:
            out.append(acc & 0xFF)
            acc >>= 8
            nacc -= 8

    table, next_code = {}, eoi + 1
    put(clear)
    prefix = None
    for b in data:
        if prefix is None:
            prefix = b
            continue
        code = table.get((prefix, b))
        if code is not None:
            prefix = code
            continue
        put(prefix)
        table[(prefix, b)] = next_code
        next_code += 1
        if next_code - 1 == (1 << size) and size < 12:
            size += 1
        if next_code == 4096:
            put(clear)
            table, next_code, size = {}, eoi + 1, min_size + 1
        prefix = b
    if prefix is not None:
        put(prefix)
        if next_code == (1 << size) and size < 12:
            size += 1
    put(eoi)
    if nacc:
        out.append(acc & 0xFF)
    return bytes(out)


def _palette(frames: list[_Canvas]) -> tuple[list[tuple[int, int, int]], dict]:
    seen = {}
    for cv in frames:
        px = cv.px
        for i in range(0, len(px), 3):
            c = (px[i], px[i + 1], px[i + 2])
            if c not in seen:
                seen[c] = len(seen)
                if len(seen) > 256:
                    raise ValueError("more than 256 colours in a frame")
    pal = list(seen) + [(0, 0, 0)] * (256 - len(seen))
    return pal, seen


def write_gif(frames: list[_Canvas], fps: float, path: Path) -> Path:
    """An animated GIF that loops, one image per canvas."""
    w, h = frames[0].w, frames[0].h
    pal, index = _palette(frames)
    delay = max(2, round(100 / fps))
    out = bytearray(b"GIF89a" + struct.pack("<HHBBB", w, h, 0xF7, 0, 0))
    out += b"".join(bytes(c) for c in pal)
    out += b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00"
    for cv in frames:
        px = cv.px
        idx = bytes(index[(px[i], px[i + 1], px[i + 2])] for i in range(0, len(px), 3))
        out += b"\x21\xF9\x04\x00" + struct.pack("<H", delay) + b"\x00\x00"
        out += b"\x2C" + struct.pack("<HHHHB", 0, 0, w, h, 0) + b"\x08"
        data = lzw_encode(idx, 8)
        for i in range(0, len(data), 255):
            block = data[i:i + 255]
            out += bytes([len(block)]) + block
        out += b"\x00"
    out += b"\x3B"
    path.write_bytes(bytes(out))
    return path


def _mp4(frames_dir: Path, fps: float, path: Path, count: int) -> bool:
    """frames_dir/f0000.png... to an mp4 of the first count frames."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return False
    cmd = [exe, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames_dir / "f%04d.png"),
           "-frames:v", str(count), "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", str(path)]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0 and path.is_file()


LOOPS = 10   # a cycle is watched about ten times in a row at its own frame rate before it passes


def _repeat(video: Path, times: int, path: Path) -> Path | None:
    """The video played times in a row, at its own rate, with no re-encode (so no frame changes)."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    cmd = [exe, "-y", "-loglevel", "error", "-stream_loop", str(times - 1), "-i", str(video), "-c", "copy", str(path)]
    r = subprocess.run(cmd, capture_output=True)
    return path if r.returncode == 0 and path.is_file() else None


def _character_frames(shot: dict, mode: str, character, size: int, emission: float, overlay: bool,
                      camera=None):
    """A shot drawn on a character: its proportions replace the shot's, every frame a row of the character views,
    or, with a Camera, one panel through it."""
    ch = _load(character)
    emission = max(0.0, min(1.0, float(emission)))     # as the export clamps it
    from kei.characters import on_character
    shot = on_character(shot, ch)
    frames = bake(shot, mode)
    parts = [_character_parts(ch, fr["pose"]) for fr in frames]
    line = travel_line(shot, frames)
    cycle, unit = _cycle(shot, line)
    ticks = ((line[0][0], line[0][2]), unit, stride_tick(cycle))
    views = CHARACTER_VIEWS
    if isinstance(camera, Camera):
        views = None
        cams = [camera.moved(p[0] - line[0][0], p[2] - line[0][2]) if camera.follow else camera for p in line]

        def frame_bounds(f: int, panel: int) -> dict:
            c = cams[f]
            h, v = c.project(c.target)
            span = c.span * (panel - LABEL) * (1 - 2 * MARGIN) / panel   # the frame's height is the camera's span
            return {c: (h, v, span), "_ticks": ticks, "_ground": (c.target[0], 0.0, c.target[2])}
    else:
        pts = [{**character_points(p), "pelvis": fr["joints"]["pelvis"]} for p, fr in zip(parts, frames)]
        bounds = fit(pts, CHARACTER_VIEWS, follow=line if camera == "follow" else None)
        if camera == "follow":
            for b in bounds:
                b["_ticks"] = ticks

    def draw(f: int, label: str, panel: int) -> _Canvas:
        text = f"{label} {ch.name}".strip()
        if views is None:
            w = round(panel * camera.aspect)
            cv = _Canvas(w, panel)
            _character_panel(cv, 0, 0, cams[f], ch, parts[f], frame_bounds(f, panel), panel, text, emission, overlay,
                             width=w)
            return cv
        cv = _Canvas(len(views) * panel, panel)
        for i, view in enumerate(views):
            _character_panel(cv, i * panel, 0, view, ch, parts[f], bounds[f], panel, text, emission, overlay)
        return cv
    return frames, draw


def render_shot(shot_path: Path, out_dir: Path, mode: str, size: int = 360, name: str = "playback",
                character=None, emission: float = 1.0, overlay: bool = False, proportions: dict | None = None,
                camera=None) -> dict:
    """Render a shot: the frames, a still per key (key_f0000.png...), the key sheet and a playback named name.mp4
    or name.gif. Returns the paths written and the playback kind. With a character ("kei", "keira" or a loaded
    one) each frame is a row of the character views drawn with its shapes, on its proportions, its name in every
    label. proportions, for the stick figure, replace the shot's own."""
    shot = read_shot(shot_path)
    check_shot(shot)
    if proportions is not None:
        props = shot.get("props") if isinstance(shot.get("props"), dict) else {}
        shot = {**shot, "props": {**props, "proportions": proportions}}
    key_fs = sorted({int(k["f"]) for k in normalize_keys(shot)
                     if float(k["f"]).is_integer() and 0 <= k["f"] <= shot["frames"]})
    if character is None:
        if isinstance(camera, Camera):
            raise ShotError("the delivery camera draws the character: render without --style stick")
        frames = bake(shot, mode)
        line = travel_line(shot, frames) if camera == "follow" else None
        tick = stride_tick(_cycle(shot, line)[0]) if line else None
        bounds = fit([fr["joints"] for fr in frames], follow=line, tick=tick)

        def draw(f: int, label: str) -> _Canvas:
            cv = _Canvas(2 * size, 2 * size)
            _views_on(cv, 0, 0, frames[f]["joints"], size, bounds[f], label)
            return cv

        def key_sheet() -> bytes:
            return _key_sheet(frames, key_fs or [0], bounds, size // 2)
    else:
        frames, draw_c = _character_frames(shot, mode, character, size, emission, overlay, camera)

        def draw(f: int, label: str) -> _Canvas:
            return draw_c(f, label, size)

        def key_sheet() -> bytes:   # one row of views per key
            rows = [draw_c(f, f"F{f} key", size // 2) for f in key_fs or [0]]
            cv = _Canvas(rows[0].w, sum(r.h for r in rows))
            for i, r in enumerate(rows):
                cv.px[i * len(r.px):(i + 1) * len(r.px)] = r.px
            return cv.png()
    out_dir = Path(out_dir)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("f*.png"):
        old.unlink()
    canvases, paths = [], []
    for fr in frames:
        tag = "key" if fr["f"] in key_fs else ""
        cv = draw(fr["f"], f"F{fr['f']} {tag}".strip())
        p = frames_dir / f"f{fr['f']:04d}.png"
        p.write_bytes(cv.png())
        canvases.append(cv)
        paths.append(p)
    stills = []
    for old in out_dir.glob("key_f*.png"):
        old.unlink()
    for f in key_fs:
        stills.append(out_dir / f"key_f{f:04d}.png")
        stills[-1].write_bytes(paths[f].read_bytes())
    keys = out_dir / "keys.png"
    keys.write_bytes(key_sheet())
    fps = shot.get("fps") or 24
    for old in (f"{name}.mp4", f"{name}.gif"):
        (out_dir / old).unlink(missing_ok=True)
    # a loop's last frame repeats frame 0: the playback leaves it out, so the loop has no hitch at the seam
    played = canvases[:-1] if shot.get("loop") and len(canvases) > 1 else canvases
    (out_dir / f"{name}_x{LOOPS}.mp4").unlink(missing_ok=True)
    loops = None
    if _mp4(frames_dir, fps, out_dir / f"{name}.mp4", len(played)):
        playback, kind = out_dir / f"{name}.mp4", "mp4"
        if shot.get("loop"):
            loops = _repeat(playback, LOOPS, out_dir / f"{name}_x{LOOPS}.mp4")
    else:
        playback, kind = write_gif(played, fps, out_dir / f"{name}.gif"), "gif"
    return {"frames": paths, "stills": stills, "keys": keys, "playback": playback, "kind": kind, "loops": loops}


POST_VIEWS = ("side", "three quarter", "front", "back")   # two by two: the side view first, where balance reads


def _encode(frames_dir: Path, fps: float, path: Path, count: int) -> bool:
    """frames_dir/f0000.png... to an H.264 mp4 in yuv420p, quality kept high, ready to post."""
    exe = shutil.which("ffmpeg")
    if not exe:
        return False
    cmd = [exe, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames_dir / "f%04d.png"),
           "-frames:v", str(count), "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(path)]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0 and path.is_file()


def render_post(shot_path: Path, out_dir: Path, mode: str, character, height: int = 1080, name: str = "shot",
                emission: float = 1.0, video: bool = True) -> dict:
    """A clean video of a shot to post: the character in four views (side, three quarter, front, back) two by two,
    height pixels square, drawn smooth, with no label, border or tick; H.264, yuv420p, at the shot's frame rate. A
    loop also gets name_post_x10.mp4. Every view rides the travel, so the figure walks in place, centred, and a loop
    plays with no jump at its seam. Writes out_dir/frames/ and out_dir/name_post.mp4; pelvis_px gives the pelvis's
    place in each panel per frame."""
    shot = read_shot(shot_path)
    check_shot(shot)
    ch = _load(character)
    emission = max(0.0, min(1.0, float(emission)))
    from kei.characters import on_character
    shot = on_character(shot, ch)
    frames = bake(shot, mode)
    parts = [_character_parts(ch, fr["pose"]) for fr in frames]
    pts = [{**character_points(p), "pelvis": fr["joints"]["pelvis"]} for p, fr in zip(parts, frames)]
    # every view rides the even travel, so the figure walks in place, centred, and a loop's last frame flows into
    # its first with no jump back; with no ground mark nothing scrolls
    bounds = fit(pts, POST_VIEWS, follow=travel_line(shot, frames))
    panel = height // 2

    def pelvis_px(view, f):
        ch_, cv_, span = bounds[f][view]
        h_, v_ = _view(view, frames[f]["joints"]["pelvis"])
        sc = _scale(span, panel)
        return (panel / 2 + (h_ - ch_) * sc, LABEL + (panel - LABEL) / 2 - (v_ - cv_) * sc)
    out_dir = Path(out_dir)
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("f*.png"):
        old.unlink()
    paths = []
    for fr, pp in zip(frames, parts):
        cv = _Canvas(2 * panel, 2 * panel)
        for i, view in enumerate(POST_VIEWS):
            _character_panel(cv, (i % 2) * panel, (i // 2) * panel, view, ch, pp, bounds[fr["f"]], panel, "",
                             emission, False, clean=True)
        p = frames_dir / f"f{fr['f']:04d}.png"
        p.write_bytes(cv.png())
        paths.append(p)
    result = {"frames": paths, "video": None, "loops": None,
              "pelvis_px": {v: [pelvis_px(v, i) for i in range(len(frames))] for v in POST_VIEWS}}
    if video:
        fps = shot.get("fps") or 24
        count = len(paths) - 1 if shot.get("loop") and len(paths) > 1 else len(paths)
        dst = out_dir / f"{name}_post.mp4"
        if _encode(frames_dir, fps, dst, count):
            result["video"] = dst
            if shot.get("loop"):
                result["loops"] = _repeat(dst, LOOPS, out_dir / f"{name}_post_x{LOOPS}.mp4")
    return result
