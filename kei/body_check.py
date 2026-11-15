"""kei check: the body checks of one pass, measured on Kei's own rig, written to out_<pass>/body_check/body_check.json.

What is measured, frame by frame, on the pass's shot.json baked on the shot's character:
  contacts      when each foot touches the ground: a sole point (heel, ball or toe tip) at or under CONTACT_H.
  hover         a planted foot that stays above the ground: while the foot's lowest sole point is still (it moves less
                than SLIDE a frame) and the foot is at its lowest (within CONTACT_H of its lowest in the shot), that
                point stays higher than HOVER. A foot raised off the ground everywhere (a re-imported model with a
                shorter ankle) is never in contact, so the contacts check alone cannot see it.
  foot_slide    how far a sole point that stays in contact moves along the ground from one frame to the next.
  balance       the centre of mass, dropped to the ground, against the support: the outline of the sole points in
                contact. A frame with no contact is airborne and is not judged.
  joint_ranges  knee and elbow bend against their limits, a knee that bends backward, and a foot target the leg
                cannot reach.
  knee_snap     a knee whose bend drops (or jumps) by more than KNEE_SNAP from both neighbour frames and comes back:
                a one-frame pop, such as a contact key snapping the leg straight.
  arcs          the paths of the head, the pelvis, the hand tips and the toe tips: a sharp change of direction while
                the part is moving (a kink) breaks the arc.

An in-place loop (shot.json "in_place": {"speed_mps": v}, Kei's default for a loop) is measured as it plays in the
game: the ground under it moves back at v, so each frame's joints move forward by v x f / fps along the character's
forward axis (z) before anything is measured. A planted foot that slides back by exactly that amount is planted.

Every threshold is a documented constant below. Distances scale with the character's height (CHARACTER_BASE m is
1), so a smaller character is held to the same proportion. Each flag names its frames and says what was found, and
the report records every threshold with its source, so the reader can judge a flag or declare it.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from kei.rig import over_reach
from kei.sample import bake, check_shot, cycle_travel, normalize_keys, read_json

CHARACTER_BASE = 1.71        # m: the height the distance constants are written for
CONTACT_H = 0.02             # m: a sole point this high or lower touches the ground
PENETRATION = 0.01           # m: a sole point this far under the ground goes through it
HOVER = 0.01                 # m: a planted foot whose lowest sole point stays this far above the ground hovers
SLIDE = 0.005                # m per frame: a planted sole point moving more than this slides
BALANCE_TOL = 0.03           # m: the centre of mass may sit this far outside the support before it counts as out
BALANCE_RUN = 3              # frames: a shorter time outside the support is a fall caught by the next step
BEHIND_TOL = 0.03            # m: the centre of mass may sit this far behind the support, against the travel; a fall
                             # backward is never caught by the next step, so even one frame past it counts
LEAN_BACK = 1.0              # deg: a trunk (pelvis to neck) leaning back past this against the travel falls behind;
                             # a walk's trunk tips forward about 6 deg (book LOC1, LOC16)
TRAVEL_MIN = 0.05            # m: a shot whose pelvis travels less than this has no travel direction to judge against
KNEE_MAX, ELBOW_MAX = 150.0, 150.0      # degrees of bend
KNEE_BACK = 0.01             # m: a knee this far behind its hip-to-ankle line, against the foot, bends backward
KNEE_SNAP = 8.0              # degrees: a knee bend this far below (or above) both neighbour frames pops for a frame
REACH = 0.005                # m: a foot target farther than this beyond the leg's reach is not reached
ARC_KINK = 60.0              # degrees: a turn sharper than this between two frames of motion breaks the arc
ARC_MOVING = 0.003           # m per frame: below this speed a part is at rest and its direction is not judged
ARC_PARTS = ("head", "pelvis", "hand_l_tip", "hand_r_tip", "ball_l_tip", "ball_r_tip")
SOLE = ("heel_{s}", "ball_{s}", "ball_{s}_tip")


class CheckError(ValueError):
    """The pass cannot be checked. The message names the file."""


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _len(v) -> float:
    return math.sqrt(sum(x * x for x in v))


def _angle(a, b) -> float:
    la, lb = _len(a), _len(b)
    if la == 0 or lb == 0:
        return 0.0
    c = sum(x * y for x, y in zip(a, b)) / (la * lb)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _hull(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The convex outline of points on the ground (x, z), counter-clockwise."""
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _seg_dist(p, a, b) -> float:
    ab = _sub(b, a)
    t = 0.0 if _len(ab) == 0 else max(0.0, min(1.0, sum(x * y for x, y in zip(_sub(p, a), ab)) / _len(ab) ** 2))
    return _len(_sub(p, (a[0] + ab[0] * t, a[1] + ab[1] * t)))


def outside(p, hull) -> float:
    """How far (m) a ground point lies outside the support outline; 0 inside it."""
    if len(hull) == 1:
        return _len(_sub(p, hull[0]))
    if len(hull) == 2:
        return _seg_dist(p, hull[0], hull[1])
    inside = all((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0
                 for a, b in zip(hull, hull[1:] + hull[:1]))
    if inside:
        return 0.0
    return min(_seg_dist(p, a, b) for a, b in zip(hull, hull[1:] + hull[:1]))


def _runs(frames: list[int]) -> list[list[int]]:
    """Consecutive frames as [first, last] runs."""
    out = []
    for f in frames:
        if out and f == out[-1][1] + 1:
            out[-1][1] = f
        else:
            out.append([f, f])
    return out


def _hovers(frames: list[dict], s: str, contact_h: float, slide: float, hover: float) -> list[tuple]:
    """The runs [first, last, lowest height, highest height] where the s foot is planted and hovers: its lowest sole
    point stays still from one frame to the next (moves less than slide), the foot is at its lowest (within contact_h
    of its lowest point in the shot), and that point is higher than hover on every frame of the run."""
    def low(fr):
        return min((fr["joints"][p.format(s=s)][1], p.format(s=s)) for p in SOLE)
    lows = [low(fr) for fr in frames]
    floor = min(y for y, _ in lows)
    planted = set()
    for i in range(len(frames) - 1):
        (y, n) = lows[i]
        a, b = frames[i]["joints"][n], frames[i + 1]["joints"][n]
        if _len(_sub(b, a)) <= slide and y <= floor + contact_h and lows[i + 1][0] <= floor + contact_h:
            planted |= {frames[i]["f"], frames[i + 1]["f"]}
    height = {fr["f"]: y for fr, (y, _) in zip(frames, lows)}
    out = []
    for a, b in _runs(sorted(f for f in planted if height[f] > hover)):
        if b > a:                      # one still frame pair at least: the foot stays
            hs = [height[f] for f in range(a, b + 1)]
            out.append((a, b, min(hs), max(hs)))
    return out


def knee_snaps(bend: list[float], frames: list[int], loop: bool = False,
               limit: float = KNEE_SNAP) -> list[tuple[int, float, str, float]]:
    """The frames where a knee bend (degrees, one per frame) pops: lower (a dip) or higher (a spike) than both
    neighbour frames by more than limit. Each is (frame, size: the smaller of the two steps, "dip" or "spike", the bend
    there). On a loop whose last frame repeats the first, frame 0's neighbours are the last but one and frame 1."""
    out = []
    n = len(bend)
    idx = range(n) if loop and n > 3 else range(1, n - 1)
    for i in idx:
        if loop and i == n - 1:
            continue                      # the repeat of frame 0
        a = bend[i - 1] if i > 0 else bend[n - 2]
        b, c = bend[i], bend[i + 1]
        for kind, d1, d2 in (("dip", a - b, c - b), ("spike", b - a, b - c)):
            if d1 > limit and d2 > limit:
                out.append((frames[i], min(d1, d2), kind, b))
    return out


def _frames(shot: dict, mode: str, proportions: dict) -> list[dict]:
    """Frames 0..n, each {"f", "pose", "joints"}. On a travelling loop the last frame is frame 0 moved on by one
    cycle, so the seam is measured as the motion plays, not as a jump back."""
    props = shot.get("props") if isinstance(shot.get("props"), dict) else {}
    shot = {**shot, "props": {**props, "proportions": proportions}}
    frames = bake(shot, mode)
    if shot.get("loop") and len(frames) > 1:
        d = cycle_travel(shot, normalize_keys(shot))
        f0 = frames[0]
        moved = {n: (p[0] + d[0], p[1], p[2] + d[2]) for n, p in f0["joints"].items()}
        frames[-1] = {"f": frames[-1]["f"], "pose": f0["pose"], "joints": moved}
    return frames


def in_place_speed(shot: dict) -> float:
    """The treadmill speed of an in-place loop, in m/s; 0 for a shot that travels or stands still."""
    ip = shot.get("in_place")
    if not isinstance(ip, dict):
        return 0.0
    try:
        return max(0.0, float(ip.get("speed_mps") or 0))
    except (TypeError, ValueError):
        return 0.0


def _treadmill(frames: list[dict], speed: float, fps: float) -> list[dict]:
    """The frames as they travel: each joint moved forward (+z) by speed x f / fps."""
    out = []
    for fr in frames:
        dz = speed * fr["f"] / fps
        out.append({**fr, "joints": {n: (p[0], p[1], p[2] + dz) for n, p in fr["joints"].items()}})
    return out


def measure(shot: dict, mode: str, proportions: dict, height: float, frames: list[dict] | None = None) -> dict:
    """The report of one pass (see the module docstring). frames: joints from elsewhere (Maya), in place of the
    shot baked on Kei's own rig; they have no pose, so the reach check (a foot target past the leg) is not run."""
    k = height / CHARACTER_BASE
    contact_h, penetration, slide, tol = CONTACT_H * k, PENETRATION * k, SLIDE * k, BALANCE_TOL * k
    hover = HOVER * k
    frames = frames if frames is not None else _frames(shot, mode, proportions)
    speed = in_place_speed(shot)
    if speed:
        frames = _treadmill(frames, speed, float(shot.get("fps") or 24))
    flags: list[dict] = []
    thresholds = {
        "contact_h_m": {"value": round(contact_h, 4), "source": f"CONTACT_H {CONTACT_H} m x height {height} / 1.71"},
        "penetration_m": {"value": round(penetration, 4), "source": f"PENETRATION {PENETRATION} m x height / 1.71"},
        "hover_m": {"value": round(hover, 4), "source": f"HOVER {HOVER} m x height / 1.71"},
        "slide_m_per_frame": {"value": round(slide, 4), "source": f"SLIDE {SLIDE} m x height / 1.71"},
        "balance_tol_m": {"value": round(tol, 4), "source": f"BALANCE_TOL {BALANCE_TOL} m x height / 1.71"},
        "balance_run_frames": {"value": BALANCE_RUN, "source": "BALANCE_RUN"},
        "behind_tol_m": {"value": round(BEHIND_TOL * k, 4), "source": f"BEHIND_TOL {BEHIND_TOL} m x height / 1.71"},
        "lean_back_deg": {"value": LEAN_BACK, "source": "LEAN_BACK (book LOC1, LOC16: a walk leans forward)"},
        "knee_max_deg": {"value": KNEE_MAX, "source": "KNEE_MAX"},
        "elbow_max_deg": {"value": ELBOW_MAX, "source": "ELBOW_MAX"},
        "reach_m": {"value": REACH, "source": "REACH"},
        "knee_snap_deg": {"value": KNEE_SNAP, "source": "KNEE_SNAP (a one-frame dip or spike of the knee bend)"},
        "arc_kink_deg": {"value": ARC_KINK, "source": "ARC_KINK"},
        "arc_moving_m_per_frame": {"value": round(ARC_MOVING * k, 4),
                                   "source": f"ARC_MOVING {ARC_MOVING} m x height / 1.71"},
    }

    # contacts and foot slide
    contacts, slides, max_slide = {}, {}, {}
    sole_in = []   # per frame: the sole points in contact, (x, z)
    for fr in frames:
        sole_in.append([(fr["joints"][p.format(s=s)][0], fr["joints"][p.format(s=s)][2])
                        for s in "lr" for p in SOLE if fr["joints"][p.format(s=s)][1] <= contact_h])
    for s in "lr":
        on = [fr["f"] for fr in frames if any(fr["joints"][p.format(s=s)][1] <= contact_h for p in SOLE)]
        contacts[s] = _runs(on)
        low = [fr["f"] for fr in frames if min(fr["joints"][p.format(s=s)][1] for p in SOLE) < -penetration]
        for a, b in _runs(low):
            flags.append({"check": "contacts", "side": s, "frames": [a, b],
                          "what": f"the {s} foot goes under the ground by more than {penetration:.3f} m"})
        for a, b, lo, hi in _hovers(frames, s, contact_h, slide, hover):
            flags.append({"check": "hover", "side": s, "frames": [a, b],
                          "what": f"the planted {s} foot hovers: its sole's lowest point stays {lo:.3f} to {hi:.3f} m "
                                  f"above the ground, over {hover:.3f}. Lower the foot target, and the root with it "
                                  f"to keep the knee"})
        bad, top = [], 0.0
        for f0, f1 in zip(frames, frames[1:]):
            for p in SOLE:
                n = p.format(s=s)
                a, b = f0["joints"][n], f1["joints"][n]
                if a[1] <= contact_h and b[1] <= contact_h:
                    d = math.hypot(b[0] - a[0], b[2] - a[2])
                    top = max(top, d)
                    if d > slide:
                        bad += [f0["f"], f1["f"]]
        max_slide[s] = round(top, 4)
        slides[s] = _runs(sorted(set(bad)))
        for a, b in slides[s]:
            flags.append({"check": "foot_slide", "side": s, "frames": [a, b],
                          "what": f"the planted {s} foot slides along the ground (up to {top:.3f} m a frame, "
                                  f"over {slide:.3f})"})

    # balance
    out_frames, airborne, worst = [], [], {}
    for fr, pts in zip(frames, sole_in):
        if not pts:
            airborne.append(fr["f"])
            continue
        c = fr["joints"]["com"]
        d = outside((c[0], c[2]), _hull(pts))
        if d > tol:
            out_frames.append(fr["f"])
            worst[fr["f"]] = d
    for a, b in _runs(out_frames):
        if b - a + 1 >= BALANCE_RUN:
            far = max(worst[f] for f in range(a, b + 1))
            flags.append({"check": "balance", "frames": [a, b],
                          "what": f"the centre of mass stays outside the support for {b - a + 1} frames "
                                  f"(up to {far:.3f} m out): fix the pose or declare it as a fall"})
    # balance against the travel: behind the support's back edge, and the trunk's lean, both along the direction the
    # pelvis travels (none for a shot that stays in place)
    p0, p1 = frames[0]["joints"]["pelvis"], frames[-1]["joints"]["pelvis"]
    run = math.hypot(p1[0] - p0[0], p1[2] - p0[2])
    fwd = ((p1[0] - p0[0]) / run, (p1[2] - p0[2]) / run) if run >= TRAVEL_MIN * k else None
    behind, max_behind, leans, lean_back = [], {}, [], {}
    if fwd:
        along = lambda x, z: x * fwd[0] + z * fwd[1]  # noqa: E731
        for fr, pts in zip(frames, sole_in):
            j = fr["joints"]
            if pts:
                d = min(along(*p) for p in pts) - along(j["com"][0], j["com"][2])
                if d > BEHIND_TOL * k:
                    behind.append(fr["f"])
                    max_behind[fr["f"]] = d
            v = _sub(j["neck_01"], j["pelvis"])
            lean = math.degrees(math.atan2(along(v[0], v[2]), v[1]))
            leans.append(lean)
            if lean < -LEAN_BACK:
                lean_back[fr["f"]] = -lean
        for a, b in _runs(behind):
            far = max(max_behind[f] for f in range(a, b + 1))
            flags.append({"check": "balance", "frames": [a, b],
                          "what": f"the centre of mass is up to {far:.3f} m behind the support, against the travel: "
                                  f"the body falls backward, and no next step catches a fall backward. Move the mass "
                                  f"over the support before the rear foot leaves, or shorten the reach of the front "
                                  f"foot"})
        for a, b in _runs(sorted(lean_back)):
            far = max(lean_back[f] for f in range(a, b + 1))
            flags.append({"check": "trunk_lean", "frames": [a, b],
                          "what": f"the trunk (pelvis to neck) leans back up to {far:.1f} deg against the travel: "
                                  f"on the side view the body reads as falling behind. A walk tips forward about "
                                  f"6 deg (LOC16)"})
    balance = {"frames_outside_support": out_frames, "airborne_frames": airborne,
               "max_outside_m": round(max(worst.values(), default=0.0), 4),
               "frames_behind_support": behind, "max_behind_m": round(max(max_behind.values(), default=0.0), 4),
               "trunk_lean_deg": ({"min": round(min(leans), 1), "max": round(max(leans), 1)} if leans else None)}

    # joint ranges
    knee_bend, elbow_bend = {"l": [], "r": []}, {"l": [], "r": []}
    found: dict[tuple, dict[int, float]] = {}   # (what, side) -> {frame: value}: grouped into runs below

    def hit(what: str, side: str, f: int, value: float) -> None:
        found.setdefault((what, side), {})[f] = value
    for fr in frames:
        j = fr["joints"]
        for s in "lr":
            kb = 180.0 - _angle(_sub(j[f"thigh_{s}"], j[f"calf_{s}"]), _sub(j[f"foot_{s}"], j[f"calf_{s}"]))
            eb = 180.0 - _angle(_sub(j[f"upperarm_{s}"], j[f"lowerarm_{s}"]),
                                _sub(j[f"hand_{s}"], j[f"lowerarm_{s}"]))
            knee_bend[s].append(kb)
            elbow_bend[s].append(eb)
            # the knee against the hip-to-ankle line, measured along the foot's forward direction
            hip, knee, ankle = j[f"thigh_{s}"], j[f"calf_{s}"], j[f"foot_{s}"]
            fwd = _sub(j[f"ball_{s}"], j[f"heel_{s}"])
            fwd = (fwd[0], 0.0, fwd[2])
            line = _sub(ankle, hip)
            t = sum(x * y for x, y in zip(_sub(knee, hip), line)) / (_len(line) ** 2 or 1.0)
            off = _sub(knee, tuple(h + v * t for h, v in zip(hip, line)))
            ahead = sum(x * y for x, y in zip(off, fwd)) / (_len(fwd) or 1.0)
            if ahead < -KNEE_BACK:
                hit("knee_back", s, fr["f"], -ahead)
            if kb > KNEE_MAX:
                hit("knee_max", s, fr["f"], kb)
            if eb > ELBOW_MAX:
                hit("elbow_max", s, fr["f"], eb)
        r = over_reach(fr["pose"], proportions) if "pose" in fr else 0.0
        if r > REACH:
            hit("reach", "", fr["f"], r)
    words = {"knee_back": "the {s} knee bends backward (up to {v:.3f} m behind its hip-to-ankle line)",
             "knee_max": "the {s} knee bends up to {v:.0f} deg, past " + f"{KNEE_MAX:.0f}",
             "elbow_max": "the {s} elbow bends up to {v:.0f} deg, past " + f"{ELBOW_MAX:.0f}",
             "reach": "a foot target is up to {v:.3f} m beyond the leg's reach: the leg cannot get there"}
    for (what, s), by_frame in found.items():
        for a, b in _runs(sorted(by_frame)):
            v = max(by_frame[f] for f in range(a, b + 1))
            flags.append({"check": "joint_ranges", **({"side": s} if s else {}), "frames": [a, b],
                          "what": words[what].format(s=s, v=v)})
    for s in "lr":
        for f, size, kind, b in knee_snaps(knee_bend[s], [fr["f"] for fr in frames], bool(shot.get("loop"))):
            move = "drops to" if kind == "dip" else "jumps to"
            flags.append({"check": "knee_snap", "side": s, "frames": [f, f],
                          "what": f"the {s} knee snaps at f{f}: its bend {move} {b:.1f} deg, {size:.1f} deg off both "
                                  f"neighbour frames, and comes back: a one-frame pop"
                                  + (" (the leg snaps straight)" if kind == "dip" and b < 5.0 else "")})
    joint_ranges = {f"{part}_{s}": {"min_deg": round(min(v), 1), "max_deg": round(max(v), 1)}
                    for part, table in (("knee", knee_bend), ("elbow", elbow_bend)) for s, v in table.items()}

    # basic posing: the signs of a bad pose a line drawing hides (kei.posing_check)
    from kei.posing_check import posing_flags
    pose_flags, pose_thresholds = posing_flags(frames, knee_bend, elbow_bend, k, contact_h)
    flags += pose_flags
    thresholds.update(pose_thresholds)

    # arcs: on the distinct positions of each part, so stepped holds are not read as stops mid-path. A stepped pass
    # jumps from key to key: its kinks are listed for the reader but not flagged; judge arcs on the spline pass.
    moving = ARC_MOVING * k
    arcs = {}
    for part in ARC_PARTS:
        path = []
        for fr in frames:
            p = fr["joints"][part]
            if not path or _len(_sub(p, path[-1][1])) > 1e-9:
                path.append((fr["f"], p))
        kinks = []
        for (fa, a), (fb, b), (fc, c) in zip(path, path[1:], path[2:]):
            u, v = _sub(b, a), _sub(c, b)
            if _len(u) > moving and _len(v) > moving:
                turn = _angle(u, v)
                if turn > ARC_KINK:
                    kinks.append((fb, turn))
        arcs[part] = {"kinks": [[f, round(t, 1)] for f, t in kinks]}
        for f, t in (kinks if mode != "step" else []):
            flags.append({"check": "arcs", "part": part, "frames": [f, f],
                          "what": f"the {part} path turns {t:.0f} deg at once while moving: the arc breaks"})

    flags.sort(key=lambda fl: (fl["frames"][0], fl["check"]))
    return {"contacts": contacts, "foot_slide": {"slides": slides, "max_m_per_frame": max_slide},
            "balance": balance, "joint_ranges": joint_ranges, "arcs": arcs, "thresholds": thresholds,
            "flags": flags}


def check_pass(shot_dir: Path, pass_name: str, character: str, mode: str | None = None) -> Path:
    """Measure out_<pass>/shot.json on the character and write out_<pass>/body_check/body_check.json."""
    from kei.characters import load_character, on_character
    out = Path(shot_dir) / f"out_{pass_name}"
    src = out / "shot.json"
    if not src.is_file():
        raise CheckError(f"no {src}: write the pass's keys there first")
    shot = read_json(src, "shot")
    maya = out / "joints.json"
    frames = None
    if maya.is_file() and read_json(maya, "joints").get("source") in ("maya", "unreal"):
        data = read_json(maya, "joints")     # the joints Maya or Unreal gave back: measured as they play there
        frames = [{"f": fr["f"], "joints": {n: tuple(p) for n, p in fr["joints"].items()}} for fr in data["frames"]]
        mode = data.get("mode") or mode
    else:
        check_shot(shot)
    ch = load_character(character)
    shot = on_character(shot, ch)        # a walk made for another character rides at this one's hip height
    mode = mode or ("step" if pass_name == "blocking" else "spline")
    report = {"tool": "kei check", "pass": pass_name, "mode": mode, "character": ch.name,
              "fps": shot.get("fps") or 24, "frames": shot.get("frames") or len(frames or []) - 1,
              "loop": bool(shot.get("loop")), **({"in_place_speed_mps": in_place_speed(shot)} if in_place_speed(shot) else {}), **({"joints_from": data.get("source")} if frames else {}),
              **measure(shot, mode, ch.proportions, ch.height, frames)}
    report["summary"] = (f"{len(report['flags'])} flag(s): fix each at a key, or declare it with a reason"
                         if report["flags"] else "no flag")
    dst = out / "body_check" / "body_check.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(report, indent=1), encoding="utf-8")
    from kei.principles import check_principles   # the twelve principles, on the same frames
    joints = frames if frames is not None else _frames(shot, mode, ch.proportions)
    speed = in_place_speed(shot)
    if speed:
        joints = _treadmill(joints, speed, float(shot.get("fps") or 24))
    check_principles(Path(shot_dir), pass_name, joints, float(shot.get("fps") or 24), ch.height)
    return dst
