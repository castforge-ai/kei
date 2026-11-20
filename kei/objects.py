"""Objects in a shot: a crate, a ball, a bucket the character handles.

A pass's shot.json may list objects:

  "objects": [{"name": "crate", "shape": "box", "size": [0.4, 0.4, 0.4], "rest": [0.0, 0.2, 0.5],
               "mass_kg": 35, "colour": "#9a7448", "yaw_deg": 0, "turn": "hands",
               "attach": [{"f": 71, "to": "hands"}, {"f": 143, "to": "floor"}]}]

  shape    box (size: width x, height y, depth z), cylinder (size: diameter, height; upright) or sphere (size:
           diameter). Metres.
  yaw_deg  its heading about the vertical, in degrees (default 0).
  turn     "none" (default): it keeps its heading. "hands": while both hands hold it, it turns with the line between
           the palms, as a crate turns when the arms swing it, and keeps the last heading when let go.
  rest     the centre on frame 0.
  attach   from frame f the object is held by "hand_l", "hand_r" or "hands" (both), or let go ("floor"). A hand
           holds it at the offset it had from the palm on the attach frame, so the object moves with the hand and
           never jumps. Let go, it stays where it is. The agent writes no track: Kei computes the centre of every frame.

The palm is the point between the hand joint and its tip; "hands" holds at the middle of both palms.

Kei draws each object in every render of the character and checks it (object_flags), all hard rules:
  under the ground   the object's bottom is more than PENETRATION under the ground.
  nothing holds it   let go (or never held), its bottom stays more than HOVER above the ground: it floats. Objects
                     rest on the ground only.
  grab from a distance  on a hand's attach frame, that palm is more than GRAB outside the object's surface: the hand
                     takes the object without touching it.
Distances scale with the character's height, as in kei check.
"""
from __future__ import annotations

import math

SHAPES = ("box", "cylinder", "sphere")
SIZES = {"box": 3, "cylinder": 2, "sphere": 1}
HOLDERS = {"hand_l": ("l",), "hand_r": ("r",), "hands": ("l", "r")}
LET_GO = ("floor",)
PENETRATION = 0.01   # m: as kei check's foot rule
HOVER = 0.01         # m: a let-go object this high above the ground floats
GRAB = 0.05          # m: a palm this far outside the object on its attach frame grabs from a distance
COLOUR = "#9a7448"   # unpainted wood, when an object names no colour
SIDE = {"l": "left", "r": "right"}
TURNS = ("none", "hands")   # hands: held by both hands, the object turns with the line between the palms


class ObjectError(ValueError):
    pass


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def read_objects(shot: dict) -> list[dict]:
    """The shot's objects, checked; [] when it has none. Raises ObjectError naming the object and the fault."""
    objs = shot.get("objects")
    if objs is None:
        return []
    if not isinstance(objs, list):
        raise ObjectError('"objects" must be a list')
    last = shot.get("frames")
    seen, out = set(), []
    for i, o in enumerate(objs):
        where = f"objects[{i}]"
        if not isinstance(o, dict):
            raise ObjectError(f"{where} must be an object")
        name = o.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ObjectError(f"{where}: give it a name")
        where = f'object "{name}"'
        if name in seen:
            raise ObjectError(f"{where} is named twice")
        seen.add(name)
        shape = o.get("shape")
        if shape not in SHAPES:
            raise ObjectError(f"{where}: shape must be one of {', '.join(SHAPES)}, not {shape!r}")
        size = o.get("size")
        if not (isinstance(size, list) and len(size) == SIZES[shape] and all(_num(v) and v > 0 for v in size)):
            raise ObjectError(f"{where}: a {shape}'s size is {SIZES[shape]} number(s) above 0, in metres")
        rest = o.get("rest")
        if not (isinstance(rest, list) and len(rest) == 3 and all(_num(v) for v in rest)):
            raise ObjectError(f"{where}: rest is its centre on frame 0, [x, y, z] in metres")
        attach = o.get("attach", [])
        if not isinstance(attach, list):
            raise ObjectError(f"{where}: attach must be a list")
        events = []
        for e in attach:
            if not (isinstance(e, dict) and isinstance(e.get("f"), int) and not isinstance(e.get("f"), bool)):
                raise ObjectError(f"{where}: each attach event is {{\"f\": frame, \"to\": ...}}")
            if e["f"] < 0 or (isinstance(last, int) and e["f"] > last):
                raise ObjectError(f"{where}: attach frame {e['f']} is outside the shot")
            if e.get("to") not in (*HOLDERS, *LET_GO):
                raise ObjectError(f"{where}: attach to must be one of {', '.join((*HOLDERS, *LET_GO))}, "
                                  f"not {e.get('to')!r}")
            events.append({"f": e["f"], "to": e["to"]})
        if len({e["f"] for e in events}) != len(events):
            raise ObjectError(f"{where}: two attach events on one frame")
        yaw = o.get("yaw_deg", 0.0)
        if not _num(yaw):
            raise ObjectError(f"{where}: yaw_deg is its heading in degrees about the vertical, a number")
        turn = o.get("turn", "none")
        if turn not in TURNS:
            raise ObjectError(f"{where}: turn is one of {', '.join(TURNS)}, not {turn!r}")
        colour = o.get("colour", COLOUR)
        if not (isinstance(colour, str) and len(colour) == 7 and colour.startswith("#")):
            raise ObjectError(f"{where}: colour is #rrggbb")
        path = o.get("path")
        if path is not None:
            if not (isinstance(path, list) and path and all(isinstance(k, dict) and isinstance(k.get("f"), int)
                                                              and isinstance(k.get("pos"), list) and len(k["pos"]) == 3
                                                              and all(_num(v) for v in k["pos"]) for k in path)):
                raise ObjectError(f"{where}: path is a list of keys {{\"f\": frame, \"pos\": [x, y, z], "
                                  f"\"yaw_deg\": heading}}")
            path = sorted(({"f": k["f"], "pos": [float(v) for v in k["pos"]],
                            "yaw_deg": float(k.get("yaw_deg", 0.0))} for k in path), key=lambda k: k["f"])
        grip = o.get("grip")
        if grip is not None:
            if not (isinstance(grip, dict) and grip and set(grip) <= {"l", "r"}
                    and all(isinstance(v, list) and len(v) == 3 and all(_num(x) for x in v) for v in grip.values())):
                raise ObjectError(f"{where}: grip gives each hand's point on the object, {{\"l\": [x, y, z], "
                                  f"\"r\": [x, y, z]}} in the object's own axes")
        out.append({"name": name, "shape": shape, "size": [float(v) for v in size], "path": path, "grip": grip,
                    "rest": tuple(float(v) for v in rest), "mass_kg": o.get("mass_kg"), "colour": colour,
                    "attach": sorted(events, key=lambda e: e["f"]), "yaw_deg": float(yaw), "turn": turn})
    return out


def half_extents(o: dict) -> tuple[float, float, float]:
    s = o["size"]
    if o["shape"] == "box":
        return s[0] / 2, s[1] / 2, s[2] / 2
    if o["shape"] == "cylinder":
        return s[0] / 2, s[1] / 2, s[0] / 2
    return (s[0] / 2,) * 3


def palm(joints: dict, side: str) -> tuple[float, float, float]:
    a, b = joints[f"hand_{side}"], joints.get(f"hand_{side}_tip", joints[f"hand_{side}"])
    return tuple((a[i] + b[i]) / 2 for i in range(3))


def _anchor(joints: dict, holder: str) -> tuple[float, float, float]:
    ps = [palm(joints, s) for s in HOLDERS[holder]]
    return tuple(sum(p[i] for p in ps) / len(ps) for i in range(3))


def _palm_line_yaw(joints: dict) -> float:
    """The heading (radians about the vertical) of the line from the left palm to the right one."""
    a, b = palm(joints, "l"), palm(joints, "r")
    return math.atan2(-(b[2] - a[2]), b[0] - a[0])


def _turn(v, a: float):
    """v turned by a radians about the vertical (positive turns x toward -z, as _palm_line_yaw measures)."""
    ca, sa = math.cos(a), math.sin(a)
    return (v[0] * ca + v[2] * sa, v[1], -v[0] * sa + v[2] * ca)


def path_at(o: dict, f: float) -> tuple[tuple[float, float, float], float]:
    """An object with a path: its centre and heading (radians) on frame f, easing in and out between keys, as a heavy
    mass does."""
    ks = o["path"]
    if f <= ks[0]["f"]:
        k = ks[0]
        return tuple(k["pos"]), math.radians(k["yaw_deg"])
    for a, b in zip(ks, ks[1:]):
        if f <= b["f"]:
            u = (f - a["f"]) / max(1e-9, b["f"] - a["f"])
            s = u * u * (3 - 2 * u)
            pos = tuple(a["pos"][i] + (b["pos"][i] - a["pos"][i]) * s for i in range(3))
            return pos, math.radians(a["yaw_deg"] + (b["yaw_deg"] - a["yaw_deg"]) * s)
    k = ks[-1]
    return tuple(k["pos"]), math.radians(k["yaw_deg"])


def holder_at(o: dict, f: float) -> str | None:
    """Who holds the object on frame f, from its attach events."""
    holder = None
    for e in o["attach"]:
        if e["f"] > f:
            break
        holder = None if e["to"] in LET_GO else e["to"]
    return holder


def grip_targets(shot: dict, f: float) -> dict:
    """The arm IK targets that put each hand on its grip point of a held object with a path: {"ikL": [x, y, z, 1]}.
    The hand follows the object, never the other way."""
    out = {}
    for o in read_objects(shot):
        if not o.get("path") or not o.get("grip"):
            continue
        holder = holder_at(o, f)
        if holder is None:
            continue
        c, yaw = path_at(o, f)
        for s, local in o["grip"].items():
            if s in HOLDERS[holder]:
                p = _turn(local, yaw)
                out["ikL" if s == "l" else "ikR"] = [c[0] + p[0], c[1] + p[1], c[2] + p[2], 1.0]
    return out


def yaws(o: dict, frames: list[dict]) -> list[float]:
    """The object's heading on each frame, in radians: yaw_deg, and with turn "hands", the turn of the line between
    the palms since both hands took it, kept after they let go."""
    if o.get("path"):
        return [path_at(o, fr["f"])[1] for fr in frames]
    events = {e["f"]: e["to"] for e in o["attach"]}
    yaw, holder, start, out = math.radians(o.get("yaw_deg", 0.0)), None, None, []
    base = yaw
    for fr in frames:
        to = events.get(fr["f"])
        if holder == "hands" and o.get("turn") == "hands":
            yaw = base + _palm_line_yaw(fr["joints"]) - start
        if to in LET_GO:
            holder = None
        elif to is not None:
            holder = to
            if to == "hands" and o.get("turn") == "hands":
                base, start = yaw, _palm_line_yaw(fr["joints"])
        out.append(yaw)
    return out


def track(o: dict, frames: list[dict]) -> list[tuple[tuple[float, float, float], str | None]]:
    """(centre, holder) on each frame: the holder is "hand_l", "hand_r", "hands" or None (let go). An object that
    turns with the hands keeps its offset from them turned the same way."""
    if o.get("path"):              # the object moves on its own keys; the hands follow it (grip_targets)
        return [(path_at(o, fr["f"])[0], holder_at(o, fr["f"])) for fr in frames]
    events = {e["f"]: e["to"] for e in o["attach"]}
    pos, holder, offset, out = o["rest"], None, None, []
    turning = o.get("turn") == "hands"
    start = 0.0
    for fr in frames:
        to = events.get(fr["f"])
        if holder is not None:            # carried to this frame, the let-go frame included
            a = _anchor(fr["joints"], holder)
            off = offset
            if turning and holder == "hands":
                off = _turn(offset, _palm_line_yaw(fr["joints"]) - start)
            pos = tuple(a[i] + off[i] for i in range(3))
        if to in LET_GO:
            holder = None
        elif to is not None:              # taken where it is: the offset from the new holder's palm
            holder = to
            a = _anchor(fr["joints"], to)
            offset = tuple(pos[i] - a[i] for i in range(3))
            if turning and to == "hands":
                start = _palm_line_yaw(fr["joints"])
        out.append((pos, holder))
    return out


def _mesh(o: dict, c):
    from kei.characters import Shape
    from kei.characters.mesh import _revolve, _weld, shape_mesh
    hx, hy, hz = half_extents(o)
    if o["shape"] == "box":
        return shape_mesh(Shape(bone="object", kind="block", material="object", c=c, r=(hx, hy, hz), power=40))
    if o["shape"] == "sphere":
        return shape_mesh(Shape(bone="object", kind="sphere", material="object", c=c, r=(hx,)))
    prof = [(-hy, 0.0, -1.0, 0.0), (-hy, hx, -1.0, 0.0), (-hy, hx, 0.0, 1.0), (hy, hx, 0.0, 1.0),
            (hy, hx, 1.0, 0.0), (hy, 0.0, 1.0, 0.0)]
    return _weld(*_revolve(prof, tuple(c), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), 32))


def material(o: dict) -> str:
    return f"object:{o['name']}"


def materials(shot: dict) -> dict:
    """The colour of each object's material, to add to the character's materials before drawing."""
    return {material(o): o["colour"] for o in read_objects(shot)}


def object_edges(shot: dict, frames: list[dict]) -> list[list[tuple]]:
    """Per frame, each object as 3D line segments ((a, b, colour)), for the stick render: a box's twelve edges, a
    cylinder's two rims and four sides, a sphere's three great circles."""
    out = [[] for _ in frames]
    for o in read_objects(shot):
        colour = tuple(int(o["colour"][i:i + 2], 16) for i in (1, 3, 5))
        hx, hy, hz = half_extents(o)
        if o["shape"] == "box":
            corners = [(sx * hx, sy * hy, sz * hz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
            local = [(corners[i], corners[j]) for i in range(8) for j in range(i + 1, 8)
                     if sum(corners[i][k] != corners[j][k] for k in range(3)) == 1]
        else:
            ring = [(math.cos(2 * math.pi * i / 24), math.sin(2 * math.pi * i / 24)) for i in range(25)]
            if o["shape"] == "cylinder":
                local = [((hx * a[0], y, hx * a[1]), (hx * b[0], y, hx * b[1])) for y in (-hy, hy)
                         for a, b in zip(ring, ring[1:])]
                local += [((hx * x, -hy, hx * z), (hx * x, hy, hx * z)) for x, z in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            else:
                local = [(tuple(hx * v for v in p(a)), tuple(hx * v for v in p(b)))
                         for p in (lambda q: (q[0], q[1], 0.0), lambda q: (q[0], 0.0, q[1]), lambda q: (0.0, q[0], q[1]))
                         for a, b in zip(ring, ring[1:])]
        for i, ((c, _), y) in enumerate(zip(track(o, frames), yaws(o, frames))):
            out[i] += [(tuple(c[k] + v for k, v in enumerate(_turn(a, y))),
                        tuple(c[k] + v for k, v in enumerate(_turn(b, y))), colour) for a, b in local]
    return out


def object_parts(shot: dict, frames: list[dict]) -> list[list]:
    """Per frame, a mesh Part for each object at its place on that frame."""
    from kei.characters.mesh import Part
    out = [[] for _ in frames]
    for o in read_objects(shot):
        ys = yaws(o, frames)
        for i, (c, _) in enumerate(track(o, frames)):
            v, n, t = _mesh(o, c)
            if ys[i]:
                v = [tuple(c[k] + x for k, x in enumerate(_turn([p[k] - c[k] for k in range(3)], ys[i]))) for p in v]
                n = [_turn(q, ys[i]) for q in n]
            out[i].append(Part(f"object:{o['name']}", material(o), v, n, t, -1))
    return out


def surface_gap(o: dict, c, p, yaw: float = 0.0) -> float:
    """How far the point p is outside the object centred at c and turned by yaw (0 inside or on it)."""
    hx, hy, hz = half_extents(o)
    d = list(_turn([p[i] - c[i] for i in range(3)], -yaw))
    if o["shape"] == "box":
        q = [max(0.0, abs(d[0]) - hx), max(0.0, abs(d[1]) - hy), max(0.0, abs(d[2]) - hz)]
        return math.sqrt(sum(v * v for v in q))
    if o["shape"] == "cylinder":
        radial = max(0.0, math.hypot(d[0], d[2]) - hx)
        return math.hypot(radial, max(0.0, abs(d[1]) - hy))
    return max(0.0, math.sqrt(sum(v * v for v in d)) - hx)


def _runs(fs: list[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for f in fs:
        if runs and f == runs[-1][1] + 1:
            runs[-1][1] = f
        else:
            runs.append([f, f])
    return runs


def object_flags(shot: dict, frames: list[dict], k: float = 1.0) -> list[dict]:
    """The hard flags of every object (see the module docstring), in kei check's flag shape. k scales distances."""
    flags = []
    for o in read_objects(shot):
        hy = half_extents(o)[1]
        t = track(o, frames)
        under, floats = [], []
        for fr, (c, holder) in zip(frames, t):
            bottom = c[1] - hy
            if bottom < -PENETRATION * k:
                under.append(fr["f"])
            elif holder is None and bottom > HOVER * k:
                floats.append(fr["f"])
        for a, b in _runs(under):
            flags.append({"check": "objects", "object": o["name"], "frames": [a, b],
                          "what": f"the {o['name']} goes under the ground by more than {PENETRATION * k:.3f} m"})
        for a, b in _runs(floats):
            flags.append({"check": "objects", "object": o["name"], "frames": [a, b],
                          "what": f"nothing holds the {o['name']}: it floats above the ground. Let go of it on "
                                  f"the ground, or hold it"})
        by_f = {fr["f"]: (fr, c) for fr, (c, _) in zip(frames, t)}
        for e in o["attach"]:
            if e["to"] in LET_GO or e["f"] not in by_f:
                continue
            fr, c = by_f[e["f"]]
            for s in HOLDERS[e["to"]]:
                gap = surface_gap(o, c, palm(fr["joints"], s))
                if gap > GRAB * k:
                    flags.append({"check": "objects", "object": o["name"], "frames": [e["f"], e["f"]],
                                  "what": f"the {SIDE[s]} hand takes the {o['name']} from {gap:.3f} m away "
                                          f"(over {GRAB * k:.3f}): bring the palm to its surface on the attach "
                                          f"frame"})
    return flags


def object_report(shot: dict, frames: list[dict]) -> dict:
    """Per object: its holds as [first, last, holder] runs and its lowest and highest centre."""
    out = {}
    for o in read_objects(shot):
        t = track(o, frames)
        holds, cur = [], None
        for fr, (_, h) in zip(frames, t):
            if h is not None and cur and cur[2] == h and cur[1] == fr["f"] - 1:
                cur[1] = fr["f"]
            elif h is not None:
                cur = [fr["f"], fr["f"], h]
                holds.append(cur)
            else:
                cur = None
        ys = [c[1] for c, _ in t]
        out[o["name"]] = {"shape": o["shape"], "size_m": o["size"], "mass_kg": o["mass_kg"], "holds": holds,
                          "centre_y_m": {"min": round(min(ys), 4), "max": round(max(ys), 4)} if ys else None}
    return out


BODY_KG = 70.0          # kg at CHARACTER_BASE height, when CHARACTER.md gives no Mass line


def body_mass(shot_dir, height: float, base: float = 1.71) -> float:
    """The character's body mass: CHARACTER.md's "Mass: <kg> kg" line (the weight stage writes it), else BODY_KG scaled
    by the cube of the height."""
    import re
    from pathlib import Path
    p = Path(shot_dir) / "CHARACTER.md" if shot_dir else None
    if p is not None and p.is_file():
        m = re.search(r"^\s*Mass:\s*([0-9]+(?:\.[0-9]+)?)\s*kg", p.read_text(encoding="utf-8"), re.M | re.I)
        if m:
            return float(m.group(1))
    return BODY_KG * (height / base) ** 3


def with_loads(shot: dict, frames: list[dict], body_kg: float, k: float = 1.0) -> list[dict]:
    """The frames with the objects' weight in the balance: while the hands hold an object that has a mass_kg, the centre
    of mass is the body's and the object's together; while a palm presses on an object resting on the ground (within
    GRAB of it), the object's base joins the support ("support_extra": ground points (x, z)). Frames with neither come
    back unchanged."""
    objs = [o for o in read_objects(shot)]
    if not objs:
        return frames
    tracks = {o["name"]: track(o, frames) for o in objs}
    out = []
    for i, fr in enumerate(frames):
        j = fr["joints"]
        com = j.get("com")
        extra = []
        load_m, load_s = 0.0, [0.0, 0.0, 0.0]
        for o in objs:
            c, holder = tracks[o["name"]][i]
            if holder is not None and isinstance(o.get("mass_kg"), (int, float)) and o["mass_kg"] > 0:
                load_m += o["mass_kg"]
                load_s = [load_s[n] + c[n] * o["mass_kg"] for n in range(3)]
            elif holder is None and c[1] - half_extents(o)[1] <= HOVER * k:
                if any(surface_gap(o, c, palm(j, s)) <= GRAB * k for s in "lr" if f"hand_{s}" in j):
                    hx, _, hz = half_extents(o)
                    extra += [(c[0] + dx, c[2] + dz) for dx in (-hx, hx) for dz in (-hz, hz)]
        if not load_m and not extra:
            out.append(fr)
            continue
        nj = dict(j)
        if load_m and com is not None:
            total = body_kg + load_m
            nj["com"] = tuple((com[n] * body_kg + load_s[n]) / total for n in range(3))
            nj["com_body"] = com
        out.append({**fr, "joints": nj, **({"support_extra": extra} if extra else {})})
    return out


SINK = 0.02   # m: a palm this deep inside the object it holds sinks into it


def surface_depth(o: dict, c, p, yaw: float = 0.0) -> float:
    """How deep the point p is inside the object centred at c and turned by yaw (0 outside or on it)."""
    hx, hy, hz = half_extents(o)
    d = list(_turn([p[i] - c[i] for i in range(3)], -yaw))
    if o["shape"] == "box":
        inside = [h - abs(v) for v, h in zip(d, (hx, hy, hz))]
        return max(0.0, min(inside)) if all(x > 0 for x in inside) else 0.0
    if o["shape"] == "cylinder":
        radial, vertical = hx - math.hypot(d[0], d[2]), hy - abs(d[1])
        return max(0.0, min(radial, vertical)) if radial > 0 and vertical > 0 else 0.0
    return max(0.0, hx - math.sqrt(sum(v * v for v in d)))


def grip_flags(shot: dict, frames: list[dict], k: float = 1.0) -> list[dict]:
    """While both hands hold an object: a palm that drifts off its surface (over GRAB) or sinks into it (over SINK).
    The object follows the middle of the palms, so the palms can still slide apart or press together: the grip changes
    while the hold stays."""
    flags = []
    for o in read_objects(shot):
        t, ys = track(o, frames), yaws(o, frames)
        for side in "lr":
            off, sunk = {}, {}
            for fr, (c, holder), y in zip(frames, t, ys):
                if holder != "hands" or f"hand_{side}" not in fr["joints"]:
                    continue
                p = palm(fr["joints"], side)
                gap, depth = surface_gap(o, c, p, y), surface_depth(o, c, p, y)
                if gap > GRAB * k:
                    off[fr["f"]] = gap
                if depth > SINK * k:
                    sunk[fr["f"]] = depth
            for found, what in ((off, "drifts {v:.3f} m off"), (sunk, "sinks {v:.3f} m into")):
                for a, b in _runs(sorted(found)):
                    v = max(found[f] for f in range(a, b + 1))
                    flags.append({"check": "objects", "object": o["name"], "frames": [a, b],
                                  "what": f"while held, the {SIDE[side]} palm " + what.format(v=v)
                                          + f" the {o['name']}: keep the palm on its surface"})
    return flags


MESH_REACH = 1.2   # m: an object farther than this from the pelvis is not tested against the body's mesh


def mesh_flags(shot: dict, frames: list[dict], ch, k: float = 1.0) -> list[dict]:
    """The body's mesh against each object, on every frame the object is near the body: a body part more than SINK
    inside the object is a flag naming the part, the frames and the depth (a thumb inside a crate). Frames need their
    pose (a baked pass)."""
    from kei.characters.mesh import pose_mesh
    objs = read_objects(shot)
    if not objs or not frames or "pose" not in frames[0]:
        return []
    tracks = {o["name"]: (track(o, frames), yaws(o, frames)) for o in objs}
    deep: dict = {}
    for i, fr in enumerate(frames):
        near = [o for o in objs if math.dist(tracks[o["name"]][0][i][0], fr["joints"]["pelvis"]) <= MESH_REACH * k]
        if not near:
            continue
        parts = [p for p in pose_mesh(ch, fr["pose"]) if not p.bone.startswith("object:")]
        for o in near:
            c, y = tracks[o["name"]][0][i][0], tracks[o["name"]][1][i]
            hx, hy, hz = half_extents(o)
            r = math.sqrt(hx * hx + hy * hy + hz * hz)
            for p in parts:
                d = max((surface_depth(o, c, v, y) for v in p.verts if math.dist(v, c) <= r), default=0.0)
                if d > SINK * k:
                    deep.setdefault((o["name"], p.bone), {})[fr["f"]] = d
    flags = []
    for (name, bone), by_f in sorted(deep.items()):
        for a, b in _runs(sorted(by_f)):
            d = max(by_f[f] for f in range(a, b + 1) if f in by_f)
            flags.append({"check": "objects", "object": name, "part": bone, "frames": [a, b],
                          "measure": "mesh_depth_m", "value": round(d, 4),
                          "what": f"the {bone} goes {d:.3f} m into the {name}: keep the body on its surface"})
    return flags
