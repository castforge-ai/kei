"""kei check, part two: the twelve principles of animation, measured on the joints of one pass.

Written to out_<pass>/principles/principles.json, beside body_check.json. Each principle gets a section with its status
("clean", "flags" or "unchecked"), what was measured, and its flags. Every flag has an "id" that stays the same while the
fault stays (principle.kind.part.f<first frame>), so the animator fixes it, or declares it in GATES.md under
"## Declared" with the id and a reason. The gate (P9 and P10) refuses a pass with a flag neither fixed nor declared.

What is measured, on the joint positions only (Kei metres: x the character's right, y up, z forward):
  squash_stretch   the trunk (pelvis to head) and the legs (pelvis height) compress and extend; a trunk that keeps its
                   length, its curve and its height through the moves is rigid (SQS rules: the body is never a stick).
  anticipation     before each main move (a peak of speed of the head, chest, pelvis or a hand), the part first moves
                   the other way, however little (ANT rules: small, never none).
  staging          at each story key (the blocking keys), a hand inside the torso's outline from the front AND the side
                   is hidden in the body (STG rules: read in silhouette).
  pose_to_pose     every extreme of every part on a blocking key, and every stop there too: the passes only splined the
                   blocking (BLK, WFL: breakdowns and offsets are new poses, not in-betweens).
  overlap          per chain, from the trunk out (chest, elbow, wrist, fingertip; pelvis, chest, head): every part
                   stopping on one frame (OVL18), a follower with no lag behind its driver (OVL3, OVL24), an arm riding
                   the chest like a rigid part (OVL4, OVL36), and a stop with no overshoot and settle (OVL9, OVL19).
  slow_in_out      each move's speed: a start or a stop with no ease (the speed jumps), and a stretch of constant speed
                   (SPC rules: spacing changes through a move).
  arcs             the head and the hands: a move that travels on a straight line (ARC rules; kinks stay in
                   body_check).
  secondary        the parts the main action does not drive (each hand against the chest, the fingers): dead for a
                   second or more (OVL33, TIM34: a hold stays alive).
  timing           a dead hold (the whole body still for half a second or more) and blocking keys spaced evenly (TIM
                   rules: rhythm, no two spans alike in a row).
  exaggeration     the size of each move against the character's style range, rig/style.json. With no style range yet
                   it is reported, not judged: "unchecked".
  solid_drawing    twinning: left and right moving in unison (OVL30), or posed as mirror images at a key (PSE rules).
                   Balance and joint ranges are in body_check.json.
  appeal           measured in part: a straight line of action at a key (no C or S curve in front or side view), and
                   the contrast between neighbour keys is reported. The rest needs eyes; the section says so.

Every threshold is a constant below, scaled by the character's height like body_check's, and recorded in the report.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

CHARACTER_BASE = 1.71
REST = 0.0006            # m/frame: slower than this, a part is still
MOVE_MIN = 0.0015        # m/frame: a move must peak at least this fast to be judged
MOVE_FRAMES = 3          # frames: a shorter burst is not a move
DEAD = 0.0002            # m/frame: slower than this for a whole span, a part is dead (not even a breath)
DEAD_PART_S = 3.0        # s: a secondary part dead this long is flagged
DEAD_HOLD_S = 0.5        # s: the whole body dead this long is a dead hold
SAME_STOP = 1            # frames: parts stopping within this of each other stop together
SAME_STOP_PARTS = 4      # parts: this many stopping together, and no moving part left, is one stop for all
RIGID = 0.2              # an arm whose motion against the chest is under this share of its world motion rides rigid
RIGID_MIN = 0.03         # m: the arm must travel this far in the world for the rigid test
OVERSHOOT = 0.003        # m: a follower going this far past where it settles, after its driver stops, overshoots
SETTLE_LOOK = 12         # frames after a driver stops in which a follower may overshoot
EASE_JUMP = 0.6          # a speed change from one frame to the next of this share of the move's peak has no ease
CONSTANT = 0.05          # speeds within this share of their mean ...
CONSTANT_RUN = 8         # ... for this many frames in a row, at move speed, are constant: no spacing
STRAIGHT = 0.01          # a path deviating from its chord by less than this share of its length is straight
STRAIGHT_MIN = 0.04      # m: a path shorter than this is not judged for its arc
ANTIC_LOOK = 15          # frames before a move's peak in which its anticipation is looked for
ANTIC_MIN = 0.001        # m: the counter-move must go at least this far
EXTREME_MIN = 0.005      # m: an extreme must stand out this much from the frames around it
ON_KEY = 1               # frames: an extreme within this of a blocking key is on the key
POSE_TO_POSE = 0.6       # this share of extremes on blocking keys or more: the motion only goes from key to key
UNISON = 0.97            # correlation of the left and right speeds over the frames either moves
UNISON_RATIO = 0.8       # ... and the slower side moves at least this share of the faster
TWIN = 0.02              # m: left and right mirrored within this at a key are twins
LINE_STRAIGHT = 0.02     # share of the body's length: a line of action bending less is straight
SQS_RANGE = 0.004        # share of the height: a trunk length, curve and pelvis height all changing less is rigid
EVEN_SPANS = 3           # blocking spans: this many equal spans in a row are an even rhythm

PRINCIPLES = ("squash_stretch", "anticipation", "staging", "pose_to_pose", "overlap", "slow_in_out", "arcs",
              "secondary", "timing", "exaggeration", "solid_drawing", "appeal")
MAIN = ("head", "spine_03", "pelvis", "hand_l", "hand_r")
STOP_PARTS = ("pelvis", "spine_03", "head", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r")
ARC_PARTS = ("head", "hand_l", "hand_r")


class PrincipleError(ValueError):
    """The pass cannot be measured. The message names the file."""


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _len(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _len(a)
    return _mul(a, 1.0 / n) if n > 1e-9 else (0.0, 0.0, 0.0)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _runs(idx: list[int]) -> list[list[int]]:
    out: list[list[int]] = []
    for i in idx:
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return out


class Motion:
    """The joints of a pass, frame by frame, with the chest frame each part can be read in."""

    def __init__(self, frames: list[dict]):
        self.fs = [int(fr["f"]) for fr in frames]
        self.j = [{n: tuple(p) for n, p in fr["joints"].items()} for fr in frames]
        self.n = len(frames)

    def has(self, part: str) -> bool:
        return all(part in j for j in self.j)

    def pos(self, part: str) -> list[tuple]:
        return [j[part] for j in self.j]

    def chest_axes(self, i: int):
        j = self.j[i]
        right = _unit(_sub(j["clavicle_r"], j["clavicle_l"]))
        up0 = _sub(j["neck_01"], j["spine_03"])
        up = _unit(_sub(up0, _mul(right, _dot(up0, right))))
        return right, up, _cross(right, up)

    def local(self, part: str, base: str = "spine_03") -> list[tuple]:
        """The part in the chest's own frame: what moves against the chest, not with it."""
        out = []
        for i in range(self.n):
            r, u, fw = self.chest_axes(i)
            d = _sub(self.j[i][part], self.j[i][base])
            out.append((_dot(d, r), _dot(d, u), _dot(d, fw)))
        return out


def speeds(path: list[tuple]) -> list[float]:
    """Speed at each frame (m/frame), the first frame taking the second's."""
    s = [_len(_sub(b, a)) for a, b in zip(path, path[1:])]
    return [s[0] if s else 0.0] + s


def moves(sp: list[float], rest: float, move_min: float) -> list[tuple[int, int, int]]:
    """(start, peak, end) indexes of each burst above rest that peaks at move_min or faster."""
    out = []
    for a, b in _runs([i for i, v in enumerate(sp) if v > rest]):
        if b - a + 1 < MOVE_FRAMES:
            continue
        pk = max(range(a, b + 1), key=lambda i: sp[i])
        if sp[pk] >= move_min:
            out.append((a, pk, b))
    return out


def _corr(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va < 1e-12 or vb < 1e-12:
        return 0.0
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def _extremes(path: list[tuple], prominence: float) -> list[int]:
    """Indexes where a coordinate turns back after travelling at least prominence each way (a peak or a trough)."""
    out = set()
    for axis in range(3):
        v = [p[axis] for p in path]
        last_i, last_v, direction = 0, v[0], 0
        for i in range(1, len(v)):
            d = v[i] - last_v
            if direction >= 0 and d < -prominence:
                if direction > 0:
                    out.add(last_i)
                direction, last_i, last_v = -1, i, v[i]
            elif direction <= 0 and d > prominence:
                if direction < 0:
                    out.add(last_i)
                direction, last_i, last_v = 1, i, v[i]
            elif (direction > 0 and v[i] > last_v) or (direction < 0 and v[i] < last_v) or direction == 0:
                if direction == 0 and abs(d) < prominence:
                    continue
                last_i, last_v = i, v[i]
    return sorted(out)


class Report:
    def __init__(self):
        self.sections = {p: {"status": "clean", "measured": {}, "flags": []} for p in PRINCIPLES}

    def flag(self, principle: str, kind: str, part: str, frames: tuple[int, int], what: str, rule: str):
        fid = f"{principle}.{kind}.{part}.f{frames[0]}"
        sec = self.sections[principle]
        if any(f["id"] == fid for f in sec["flags"]):
            return
        sec["flags"].append({"id": fid, "principle": principle, "frames": [frames[0], frames[1]], "part": part,
                             "what": what, "rule": rule})
        sec["status"] = "flags"

    def unchecked(self, principle: str, why: str):
        sec = self.sections[principle]
        sec["unchecked"] = why
        if not sec["flags"]:
            sec["status"] = "unchecked"


def measure(frames: list[dict], fps: float, height: float, blocking_keys: list[int] | None = None,
            hands: dict | None = None, style: dict | None = None, is_blocking: bool = False) -> dict:
    m = Motion(frames)
    if m.n < 4:
        raise PrincipleError("a pass needs four frames or more to be measured")
    k = height / CHARACTER_BASE
    rest, move_min, dead = REST * k, MOVE_MIN * k, DEAD * k
    R = Report()
    F = m.fs
    keys = sorted(set(int(f) for f in (blocking_keys or []) if F[0] <= int(f) <= F[-1]))
    key_i = [F.index(f) for f in keys if f in F]
    chest_ok = all(m.has(p) for p in ("clavicle_l", "clavicle_r", "neck_01", "spine_03"))

    world = {p: m.pos(p) for p in set(MAIN + STOP_PARTS) if m.has(p)}
    sp = {p: speeds(path) for p, path in world.items()}
    mv = {p: moves(s, rest, move_min) for p, s in sp.items()}
    local = {p: m.local(p) for p in ("hand_l", "hand_r", "lowerarm_l", "lowerarm_r", "head") if chest_ok and m.has(p)}
    lsp = {p: speeds(path) for p, path in local.items()}

    # --- overlap ---------------------------------------------------------------------------------------------
    ends: dict[int, list[str]] = {}
    for p in STOP_PARTS:
        for a, pk, b in mv.get(p, []):
            ends.setdefault(b, []).append(p)
    seen = set()
    for e in sorted(ends):
        if e in seen or e >= m.n - 1:
            continue
        near = sorted({p for f in range(e - SAME_STOP, e + SAME_STOP + 1) for p in ends.get(f, [])})
        moving_after = [p for p in sp if p in STOP_PARTS and any(v > rest for v in sp[p][e + SAME_STOP + 1:
                                                                                         e + SAME_STOP + 3])]
        if len(near) >= SAME_STOP_PARTS and not moving_after:
            seen.update(range(e - SAME_STOP, e + SAME_STOP + 1))
            R.flag("overlap", "same_stop", "body", (F[e], F[e]),
                   f"{len(near)} parts ({', '.join(near)}) stop on f{F[e]} and nothing carries on: stagger the stop, "
                   "the trunk first, the head and the arms after, the hands last", "OVL18, OVL19")
    for drv, fol in (("spine_03", "hand_l"), ("spine_03", "hand_r")):
            if drv not in mv or fol not in sp or fol not in local:
                continue
            lags = []
            for a, pk, b in mv[drv]:
                wpath = sum(_len(_sub(world[fol][i + 1], world[fol][i])) for i in range(a, b))
                lpath = sum(_len(_sub(local[fol][i + 1], local[fol][i])) for i in range(a, b))
                if lpath > wpath:          # the hand acts on its own here (a reach): it may lead
                    continue
                w = range(max(0, a - 2), min(m.n, b + 6))
                fpk = max(w, key=lambda i: sp[fol][i])
                if sp[fol][fpk] >= rest:
                    lags.append((F[pk], F[fpk] - F[pk]))
            if lags and all(lag <= 0 for _, lag in lags):
                R.flag("overlap", "no_lag", fol, (lags[0][0], lags[-1][0]),
                       f"the {fol}, carried by the {drv}, peaks with or before it in every move ({', '.join(f'f{f} {l:+d}' for f, l in lags)} "
                       "frames): it should drag a frame or more behind its driver", "OVL3, OVL24")
            R.sections["overlap"]["measured"].setdefault("lag_frames", {})[f"{drv}>{fol}"] = [l for _, l in lags]
    for side in ("l", "r"):
        hand = f"hand_{side}"
        if hand not in local:
            continue
        for a, pk, b in mv.get("spine_03", []):
            wpath = sum(_len(_sub(world[hand][i + 1], world[hand][i])) for i in range(a, b))
            lpath = sum(_len(_sub(local[hand][i + 1], local[hand][i])) for i in range(a, b))
            if wpath >= RIGID_MIN * k and lpath < RIGID * wpath:
                R.flag("overlap", "rigid_arm", hand, (F[a], F[b]),
                       f"the {hand} travels {wpath * 100:.1f} cm with the chest but only {lpath * 100:.1f} cm against it: "
                       "the arm rides the chest like a stick; let it drag behind the turn and catch up after",
                       "OVL4, OVL36, OVL24")
    for drv in ("spine_03", "head"):
        for a, pk, b in mv.get(drv, []):
            if sp[drv][pk] < 2 * move_min or b >= m.n - 2:
                continue
            settled = False
            for fol in ("head", "hand_l", "hand_r"):
                if fol == drv or fol not in local:
                    continue
                q = local[fol]
                end = min(m.n - 1, b + SETTLE_LOOK)
                final = q[end]
                approach = _unit(_sub(q[b], q[max(a, b - 3)]))
                if _len(approach) < 0.5:
                    continue
                past = max(_dot(_sub(q[i], final), approach) for i in range(b, end + 1))
                if past >= OVERSHOOT * k:
                    settled = True
                    break
            if not settled:
                R.flag("overlap", "dead_stop", drv, (F[b], F[min(m.n - 1, b + SETTLE_LOOK)]),
                       f"the {drv} stops on f{F[b]} and no head or hand goes on past it and settles back: the stop is "
                       "dead; let the followers overshoot a little and settle", "OVL9, OVL19, OVL20")

    # --- pose to pose ----------------------------------------------------------------------------------------
    if not keys:
        R.unchecked("pose_to_pose", "no blocking keys to compare with")
    elif not is_blocking:
        ext = []
        for p in ("head", "spine_03", "pelvis", "hand_l", "hand_r", "lowerarm_l", "lowerarm_r"):
            if not m.has(p):
                continue
            path = local[p] if p in local else world[p]
            ext += [(p, i) for i in _extremes(path, EXTREME_MIN * k)]
        on = [e for e in ext if any(abs(F[e[1]] - kf) <= ON_KEY for kf in keys)]
        share = len(on) / len(ext) if ext else 0.0
        R.sections["pose_to_pose"]["measured"] = {"extremes": len(ext), "on_blocking_keys": len(on),
                                                  "share": round(share, 2), "blocking_keys": keys}
        if len(ext) >= 8 and share >= POSE_TO_POSE:
            R.flag("pose_to_pose", "only_keys", "body", (F[0], F[-1]),
                   f"{len(on)} of {len(ext)} extremes sit on the blocking keys: the pass only goes from key to key. "
                   "Offset the parts: each part reaches its extreme on its own frame, before or after the key",
                   "BLK, WFL, OVL38")

    # --- slow in and out, arcs, anticipation ----------------------------------------------------------------
    for p in MAIN:
        if p not in mv:
            continue
        s = sp[p]
        for a, pk, b in mv[p]:
            peak = s[pk]
            for i in (a, a + 1):
                if 0 < i <= b and s[i] - s[i - 1] > EASE_JUMP * peak:
                    R.flag("slow_in_out", "no_ease_out", p, (F[i - 1], F[i]),
                           f"the {p} leaves at once on f{F[i]} ({s[i - 1] * 100:.2f} to {s[i] * 100:.2f} cm/frame): ease "
                           "out of the pose", "SPC")
            for i in (b, b + 1):
                if a < i < m.n and s[i - 1] - s[i] > EASE_JUMP * peak:
                    R.flag("slow_in_out", "no_ease_in", p, (F[i - 1], F[i]),
                           f"the {p} brakes at once on f{F[i]} ({s[i - 1] * 100:.2f} to {s[i] * 100:.2f} cm/frame): "
                           "ease into the pose", "SPC")
            run = 0
            for i in range(a + 1, b + 1):
                same = s[i] >= move_min * 2 and abs(s[i] - s[i - 1]) <= CONSTANT * max(s[i], s[i - 1])
                run = run + 1 if same else 0
                if run + 1 == CONSTANT_RUN:
                    R.flag("slow_in_out", "constant", p, (F[i - CONSTANT_RUN + 1], F[i]),
                           f"the {p} moves at one speed for {CONSTANT_RUN} frames: even spacing, no slow in or out",
                           "SPC, TIM")
            if p in ARC_PARTS:
                path = world[p][a:b + 1]
                chord = _sub(path[-1], path[0])
                length = sum(_len(_sub(y, x)) for x, y in zip(path, path[1:]))
                if length >= STRAIGHT_MIN * k and _len(chord) > 1e-6:
                    u = _unit(chord)
                    dev = max(_len(_sub(_sub(q, path[0]), _mul(u, _dot(_sub(q, path[0]), u)))) for q in path)
                    R.sections["arcs"]["measured"].setdefault(p, []).append([F[a], F[b], round(dev / length, 3)])
                    if dev < STRAIGHT * length:
                        R.flag("arcs", "straight", p, (F[a], F[b]),
                               f"the {p} travels {length * 100:.1f} cm on a straight line (it bows {dev * 100:.1f} cm): "
                               "give the path an arc", "ARC")
            if a > 1 and peak >= 3 * move_min:      # a clear action, not a drift, and not cut by the clip's start
                vdir = _unit(_sub(world[p][min(pk + 1, m.n - 1)], world[p][max(pk - 1, 0)]))
                back = 0.0
                for i in range(max(1, pk - ANTIC_LOOK), pk):
                    step = _dot(_sub(world[p][i], world[p][i - 1]), vdir)
                    if step < 0:
                        back += -step
                R.sections["anticipation"]["measured"].setdefault(p, []).append([F[pk], round(back * 100, 2)])
                if back < ANTIC_MIN * k:
                    R.flag("anticipation", "none", p, (F[max(0, pk - ANTIC_LOOK)], F[pk]),
                           f"the {p}'s move peaking on f{F[pk]} has no counter-move before it: a small move the "
                           "other way first, never none", "ANT")

    # --- secondary --------------------------------------------------------------------------------------------
    for p in ("hand_l", "hand_r"):
        if p not in lsp:
            continue
        for a, b in _runs([i for i, v in enumerate(lsp[p]) if v < dead]):
            if (b - a + 1) >= DEAD_PART_S * fps:
                R.flag("secondary", "dead", p, (F[a], F[b]),
                       f"the {p} does not move against the chest for {(b - a + 1) / fps:.1f} s: a live hand drifts, "
                       "breathes with the body, adjusts", "OVL33, TIM34")
    if hands and isinstance(hands.get("frames"), list) and hands["frames"]:
        for side in ("l", "r"):
            vals = []
            for fr in hands["frames"]:
                curls = [v for kname, v in (fr.get("curl") or fr.get("fingers") or {}).items()
                         if isinstance(v, (int, float)) and f"_{side}" in kname]
                if curls:
                    vals.append(sum(curls) / len(curls))
            if vals and max(vals) - min(vals) < 1.0:
                R.flag("secondary", "fingers_dead", f"fingers_{side}", (F[0], F[-1]),
                       f"the fingers of the {'left' if side == 'l' else 'right'} hand change their curl by "
                       f"{max(vals) - min(vals):.1f} deg in the whole shot: let them follow the hand and settle",
                       "OVL24, OVL28")
    else:
        R.sections["secondary"]["measured"]["fingers"] = "no hands_toes.json: the fingers were not measured"

    # --- timing ----------------------------------------------------------------------------------------------
    allsp = [max((sp[p][i] for p in sp), default=0.0) for i in range(m.n)]
    for a, b in _runs([i for i, v in enumerate(allsp) if v < dead]):
        if (b - a + 1) >= DEAD_HOLD_S * fps and not is_blocking:
            R.flag("timing", "dead_hold", "body", (F[a], F[b]),
                   f"the whole body is still for {(b - a + 1) / fps:.1f} s: a hold keeps moving a little (a moving hold)",
                   "TIM34")
    if len(keys) >= EVEN_SPANS + 1:
        spans = [b - a for a, b in zip(keys, keys[1:])]
        R.sections["timing"]["measured"]["blocking_spans"] = spans
        for i in range(len(spans) - EVEN_SPANS + 1):
            if len(set(spans[i:i + EVEN_SPANS])) == 1:
                R.flag("timing", "even", "keys", (keys[i], keys[i + EVEN_SPANS]),
                       f"{EVEN_SPANS} spans of {spans[i]} frames in a row between keys: an even rhythm", "TIM")
                break

    # --- squash and stretch ----------------------------------------------------------------------------------
    if m.has("pelvis") and m.has("head") and m.has("spine_03"):
        trunk, curve, hip = [], [], []
        for j in m.j:
            ax = _sub(j["head"], j["pelvis"])
            trunk.append(_len(ax))
            u = _unit(ax)
            d = _sub(j["spine_03"], j["pelvis"])
            curve.append(_len(_sub(d, _mul(u, _dot(d, u)))))
            hip.append(j["pelvis"][1])
        rng = {"trunk_length_cm": round((max(trunk) - min(trunk)) * 100, 2),
               "trunk_curve_cm": round((max(curve) - min(curve)) * 100, 2),
               "pelvis_height_cm": round((max(hip) - min(hip)) * 100, 2)}
        R.sections["squash_stretch"]["measured"] = rng
        lim = SQS_RANGE * height * 100
        if any(mv.values()) and all(v < lim for v in rng.values()):
            R.flag("squash_stretch", "rigid", "trunk", (F[0], F[-1]),
                   f"the trunk keeps its length, curve and height within {lim:.1f} cm through every move: compress "
                   "and extend the body with the weight (a realistic register keeps it small, never none)", "SQS")

    # --- exaggeration ----------------------------------------------------------------------------------------
    sizes = {p: round(max((sum(_len(_sub(world[p][i + 1], world[p][i])) for i in range(a, b))
                           for a, _, b in mv[p]), default=0.0) * 100, 1) for p in mv}
    R.sections["exaggeration"]["measured"] = {"largest_move_cm": sizes}
    if not style:
        R.unchecked("exaggeration", "no style range for this character (rig/style.json): the sizes are reported, "
                                    "not judged; the author judges the push")
    else:
        for p, cm in sizes.items():
            lo = (style.get("move_cm") or {}).get(p)
            if lo and cm < 0.5 * lo:
                R.flag("exaggeration", "small", p, (F[0], F[-1]),
                       f"the {p}'s largest move is {cm} cm, under half of the {lo} cm in her own clips", "EXG")

    # --- solid drawing: twinning ------------------------------------------------------------------------------
    if chest_ok:
        for pair in (("hand_l", "hand_r"), ("lowerarm_l", "lowerarm_r")):
            if not all(p in lsp for p in pair):
                continue
            a_, b_ = lsp[pair[0]], lsp[pair[1]]
            idx = [i for i in range(m.n) if max(a_[i], b_[i]) > rest]
            if len(idx) >= 6:
                c = _corr([a_[i] for i in idx], [b_[i] for i in idx])
                ratio = min(sum(a_[i] for i in idx), sum(b_[i] for i in idx)) / max(
                    sum(a_[i] for i in idx), sum(b_[i] for i in idx), 1e-9)
                R.sections["solid_drawing"]["measured"][f"{pair[0]}~{pair[1]}"] = {"corr": round(c, 3),
                                                                                  "ratio": round(ratio, 2)}
                if c >= UNISON and ratio >= UNISON_RATIO:
                    R.flag("solid_drawing", "unison", pair[0][:-2], (F[idx[0]], F[idx[-1]]),
                           f"the left and right {pair[0][:-2]} move in unison (speed correlation {c:.2f}): offset "
                           "them in time and size", "OVL30")
        for i in key_i:
            hl, hr = local.get("hand_l"), local.get("hand_r")
            if hl and hr:
                mir = (-hr[i][0], hr[i][1], hr[i][2])
                if _len(_sub(hl[i], mir)) < TWIN * k:
                    R.flag("solid_drawing", "twin_pose", "hands", (F[i], F[i]),
                           f"at the key f{F[i]} the hands mirror each other within {TWIN * 100 * k:.0f} cm: break the "
                           "symmetry", "PSE")
    R.sections["solid_drawing"]["measured"]["balance_and_ranges"] = "see body_check.json"

    # --- staging and appeal at the keys -----------------------------------------------------------------------
    if not key_i:
        R.unchecked("staging", "no blocking keys: no story keys to stage")
    for i in key_i:
        j = m.j[i]
        if not all(p in j for p in ("clavicle_l", "clavicle_r", "pelvis", "neck_01", "spine_03")):
            continue
        xs = sorted([j["clavicle_l"][0], j["clavicle_r"][0]])
        lo_y, hi_y = j["pelvis"][1], j["neck_01"][1]
        for h in ("hand_l", "hand_r"):
            if h not in j:
                continue
            p = j[h]
            front = xs[0] < p[0] < xs[1] and lo_y < p[1] < hi_y
            side = abs(p[2] - j["spine_03"][2]) < 0.12 * k and lo_y < p[1] < hi_y
            if front and side:
                R.flag("staging", "hidden_hand", h, (F[i], F[i]),
                       f"at the key f{F[i]} the {h} is inside the torso's outline from the front and the side: it does "
                       "not read in silhouette", "STG")
    for i in key_i:
        j = m.j[i]
        if not all(p in j for p in ("pelvis", "spine_03", "neck_01", "head", "ball_l", "ball_r")):
            continue
        base = j["ball_l"] if j["ball_l"][1] <= j["ball_r"][1] else j["ball_r"]
        pts = [base, j["pelvis"], j["spine_03"], j["neck_01"], j["head"]]
        bends = []
        for view in ((0, 1), (2, 1)):
            q = [(p[view[0]], p[view[1]]) for p in pts]
            ch = (q[-1][0] - q[0][0], q[-1][1] - q[0][1])
            L = math.hypot(*ch) or 1e-9
            bends.append(max(abs((p[0] - q[0][0]) * ch[1] - (p[1] - q[0][1]) * ch[0]) / L for p in q) / L)
        R.sections["appeal"]["measured"].setdefault("line_of_action", []).append([F[i], [round(b, 3) for b in bends]])
        if max(bends) < LINE_STRAIGHT:
            R.flag("appeal", "straight_line", "body", (F[i], F[i]),
                   f"at the key f{F[i]} the line of action, foot to head, is straight in front and side view: give it "
                   "a C or an S", "APL, PSE")
    for i, i2 in zip(key_i, key_i[1:]):
        common = [p for p in m.j[i] if p in m.j[i2] and p not in ("root", "com")]
        if common and "pelvis" in common:
            d = max(_len(_sub(_sub(m.j[i][p], m.j[i]["pelvis"]), _sub(m.j[i2][p], m.j[i2]["pelvis"]))) for p in common)
            R.sections["appeal"]["measured"].setdefault("key_contrast_cm", []).append([F[i], F[i2], round(d * 100, 1)])
    R.unchecked("appeal", "only the line of action and the contrast between keys are measured; whether it reads as her "
                          "and is pleasing to watch needs the author's eyes")
    sec = R.sections["appeal"]
    if sec["flags"]:
        sec["status"] = "flags"

    flags = [f for p in PRINCIPLES for f in R.sections[p]["flags"]]
    flags.sort(key=lambda fl: (fl["frames"][0], fl["principle"]))
    thresholds = {n: v for n, v in globals().items() if n.isupper() and isinstance(v, (int, float))
                  and n != "CHARACTER_BASE"}
    return {"principles": R.sections, "flags": flags, "thresholds": thresholds, "scale": round(k, 3)}


def undeclared(report: dict, gates_text: str) -> list[dict]:
    """The flags not declared in GATES.md under "## Declared" ("- <id>: <reason>"), the same reading as the gate."""
    from kei.gates.pipeline import _declared
    ids = _declared(gates_text)
    return [f for f in report.get("flags", []) if f["id"] not in ids]


def _blocking_keys(shot_dir: Path) -> list[int]:
    for rel in ("out_blocking/shot.json", "plan/plan.json"):
        p = Path(shot_dir) / rel
        if p.is_file():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            fs = [k.get("f") for k in data.get("keys") or [] if isinstance(k, dict)]
            fs = [int(f) for f in fs if isinstance(f, (int, float)) and float(f).is_integer()]
            if fs:
                return sorted(set(fs))
    return []


def check_principles(shot_dir: Path, pass_name: str, frames: list[dict], fps: float, height: float) -> Path:
    shot_dir = Path(shot_dir)
    out = shot_dir / f"out_{pass_name}"

    def _maybe(p: Path):
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
        except ValueError:
            return None
    report = {"tool": "kei check: principles", "pass": pass_name, "fps": fps,
              **measure(frames, fps, height, _blocking_keys(shot_dir), _maybe(out / "hands_toes.json"),
                        _maybe(shot_dir / "rig" / "style.json"), is_blocking=(pass_name == "blocking"))}
    report["summary"] = {p: s["status"] for p, s in report["principles"].items()}
    dst = out / "principles" / "principles.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return dst
