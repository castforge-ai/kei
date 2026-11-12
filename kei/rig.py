"""Kei's rig: a stick figure with the Unreal mannequin bone names, posed by channels. A port of the kit's rig4.js.

Units: metres, radians, frames. World axes: x is the character's right at yaw 0, y up, z forward.

Every bone has a head (its joint), a tail and a frame [X, Y, Z]: Y runs along the bone, Z is the side a hinge bends
toward, X = Y x Z. Most bone channels are [pitch, side, twist]: pitch tips the bone toward its Z, side toward its X,
twist turns it about its own axis after the swing.

CHANNELS (a pose may leave any out; a missing one takes the default stand, a short list takes the default tail)
  root [x, y, z]                pelvis joint in world space (standing about 0.98)
  yaw                           heading of the body (+ turns the front toward +x); the feet do not follow it
  pelvis [pitch, side]          + pitch tips the pelvis forward; + side drops the right hip
  spine [pitch, side, twist]    the whole spine, spread evenly over spine_01..spine_05
  spine1..spine5                extra bend of one segment
  sq, neckS                     spine and neck length scale (1 = rest)
  armSL, armSR, legSL, legSR    arm and leg length scale (upper and lower bone together)
  neck [pitch, side, turn]      spread over neck_01 and neck_02
  head [pitch, side, turn]      + pitch looks down, + turn looks toward the right
  clavL, clavR [elev, fwd]      + elev shrugs, + fwd rolls the shoulder forward
  armL, armR [pitch, roll, twist]  0 hangs, + pitch swings forward and up, + roll lifts out to the side
  elbowL, elbowR [flex, pron]   + flex bends the forearm, + pron rolls the thumb in
  handL, handR [flex, dev]      + flex bends toward the palm, + dev toward the thumb
  footL, footR [x, y, z, pitch, yaw]  the ankle target in world space at roll 0 (standing y = 0.08)
  rollL, rollR [roll, bank, ballMax]  < 0 heel strike, 0..ballMax heel peel, > ballMax toe-off; + bank: outer edge
  toeL, toeR                    extra bend of the ball joint
  kneeL, kneeR                  turns the knee about the hip to ankle line (+ outward)
  ikL, ikR [x, y, z, w]         arm IK: the wrist goes to [x, y, z] with weight w (0 = the FK arm)
  gripR, bladeS                 kept for the kit's shot format; props are not drawn here
  fingersL, fingersR            [thumb curl, thumb oppose, then curl and spread for index, middle, ring, pinky]

solve(pose) returns the joint positions: every bone head by its bone name, plus head_top, hand_l_tip, hand_r_tip,
ball_l_tip, ball_r_tip, heel_l, heel_r, sternum, nose and com (the centre of mass).

FINGERS are additions to the rig4 rig: solve() and BONES are the rig4 set unchanged, and skeleton(pose) gives every
bone of ALL_BONES (rig4 plus fingers) with its head, tail and frame. Finger bones carry the Unreal mannequin names:
<finger>_metacarpal_<s>, <finger>_01..03_<s> for index, middle, ring, pinky, and thumb_01..03_<s>, under hand_<s>.
A finger's curl (radians) is the total bend of its three joints, split in the measured relaxed-hand ratio: knuckle 1,
middle joint 2, tip 1.5. A finger bone's Z is the palm side (the side a curl bends toward). + spread fans the fingers
apart (the index toward the thumb, the ring and pinky away from it); + oppose swings the thumb across the palm and its
curl splits evenly over thumb_02 and thumb_03. The hand frame: Y along the hand, Z the thumb side, the palm faces +X
on the right hand and -X on the left.
"""
from __future__ import annotations

import math
from typing import NamedTuple

PROPORTIONS = {
    "spine": [0.1, 0.1, 0.1, 0.1, 0.1], "neck": [0.05, 0.05], "head": 0.13,
    "sternumDrop": 0.04, "clavicle": 0.19, "upperarm": 0.28, "lowerarm": 0.26, "hand": 0.08, "gripAt": 0.045,
    "hipWidth": 0.1, "hipDrop": 0.03, "thigh": 0.46, "calf": 0.45,
    "ankleH": 0.08, "heelBack": 0.05, "ballFwd": 0.14, "toeFwd": 0.2, "toeH": 0.005, "edge": 0.04,
    "blade": 0.95, "guard": 0.09, "guardAt": 0.06, "pommel": 0.1, "racket": 0.62, "shield": 0.25,
}

BONES = ("root", "pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02", "head",
         "clavicle_l", "upperarm_l", "lowerarm_l", "hand_l", "clavicle_r", "upperarm_r", "lowerarm_r", "hand_r",
         "thigh_l", "calf_l", "foot_l", "ball_l", "thigh_r", "calf_r", "foot_r", "ball_r")


def _finger_bones(s: str) -> tuple[str, ...]:
    out = []
    for f in ("index", "middle", "ring", "pinky"):
        out += [f"{f}_metacarpal_{s}", f"{f}_01_{s}", f"{f}_02_{s}", f"{f}_03_{s}"]
    return tuple(out + [f"thumb_01_{s}", f"thumb_02_{s}", f"thumb_03_{s}"])


FINGER_BONES = _finger_bones("l") + _finger_bones("r")
ALL_BONES = BONES + FINGER_BONES


def _parents() -> dict[str, str | None]:
    p = {"root": None, "pelvis": "root", "spine_01": "pelvis", "spine_02": "spine_01", "spine_03": "spine_02",
         "spine_04": "spine_03", "spine_05": "spine_04", "neck_01": "spine_05", "neck_02": "neck_01",
         "head": "neck_02"}
    for s in "lr":
        p.update({f"clavicle_{s}": "spine_05", f"upperarm_{s}": f"clavicle_{s}", f"lowerarm_{s}": f"upperarm_{s}",
                  f"hand_{s}": f"lowerarm_{s}", f"thigh_{s}": "pelvis", f"calf_{s}": f"thigh_{s}",
                  f"foot_{s}": f"calf_{s}", f"ball_{s}": f"foot_{s}"})
        for f in ("index", "middle", "ring", "pinky"):
            p.update({f"{f}_metacarpal_{s}": f"hand_{s}", f"{f}_01_{s}": f"{f}_metacarpal_{s}",
                      f"{f}_02_{s}": f"{f}_01_{s}", f"{f}_03_{s}": f"{f}_02_{s}"})
        p.update({f"thumb_01_{s}": f"hand_{s}", f"thumb_02_{s}": f"thumb_01_{s}", f"thumb_03_{s}": f"thumb_02_{s}"})
    return p


PARENTS = _parents()   # every bone's parent, in the Unreal mannequin hierarchy (root has none)

DEFAULT_POSE = {
    "root": [0, 0.98, 0], "yaw": 0, "pelvis": [0, 0], "spine": [0.05, 0, 0],
    "spine1": [0, 0, 0], "spine2": [0, 0, 0], "spine3": [0, 0, 0], "spine4": [0, 0, 0], "spine5": [0, 0, 0],
    "sq": 1, "neckS": 1, "armSL": 1, "armSR": 1, "legSL": 1, "legSR": 1,
    "neck": [0, 0, 0], "head": [0.1, 0, 0], "clavL": [0, 0], "clavR": [0, 0],
    "armL": [0.05, 0.12, 0], "armR": [0.05, 0.12, 0], "elbowL": [0.15, 0], "elbowR": [0.15, 0],
    "handL": [0, 0], "handR": [0, 0],
    "footL": [-0.1, 0.08, 0, 0, 0], "footR": [0.1, 0.08, 0, 0, 0], "rollL": [0, 0, 0.6], "rollR": [0, 0, 0.6],
    "toeL": 0, "toeR": 0, "kneeL": 0, "kneeR": 0, "ikL": [0, 0, 0, 0], "ikR": [0, 0, 0, 0], "gripR": [0, 0],
    "bladeS": 1,
}

# Fingers: additions to the rig4 stand. The default is the relaxed hand (kei.hands.PRESETS["relaxed"]).
FINGER_POSE = {
    "fingersL": [0.35, 0.35, 1.25, 0.0, 1.4, 0.0, 1.5, 0.0, 1.6, 0.0],
    "fingersR": [0.35, 0.35, 1.25, 0.0, 1.4, 0.0, 1.5, 0.0, 1.6, 0.0],
}
STAND = {**DEFAULT_POSE, **FINGER_POSE}
CHANNELS = tuple(STAND)

FINGERS = ("index", "middle", "ring", "pinky")
CURL_SPLIT = (1.0, 2.0, 1.5)     # knuckle, middle joint, tip: the measured relaxed-hand ratio
THUMB_SPLIT = (0.0, 1.0, 1.0)    # thumb_01 is set by oppose; the curl bends thumb_02 and thumb_03
# The hand for a hand length of 0.08 m (scaled with PROPORTIONS["hand"]), in the hand frame: along (Y), thumb side
# (Z), palm side. base: the metacarpal's start; knuckle: the finger's _01 joint; splay: the rest angle toward the
# thumb side; fan: how much of the spread the finger takes; lengths: the three phalanges.
HAND = {
    "index": {"base": (0.012, 0.010, 0.0), "knuckle": (0.080, 0.024, 0.0), "splay": 0.10, "fan": 1.0,
              "lengths": (0.040, 0.024, 0.019)},
    "middle": {"base": (0.012, 0.003, 0.0), "knuckle": (0.083, 0.007, 0.0), "splay": 0.0, "fan": 0.15,
               "lengths": (0.045, 0.028, 0.020)},
    "ring": {"base": (0.012, -0.004, 0.0), "knuckle": (0.079, -0.010, 0.0), "splay": -0.08, "fan": -0.5,
             "lengths": (0.042, 0.026, 0.019)},
    "pinky": {"base": (0.010, -0.010, 0.0), "knuckle": (0.071, -0.025, 0.0), "splay": -0.18, "fan": -1.0,
              "lengths": (0.033, 0.020, 0.017)},
    "thumb": {"base": (0.016, 0.020, 0.010), "aim": (0.5, 0.3), "lengths": (0.042, 0.032, 0.026)},
}
KNUCKLE_ARCH = 0.12     # the straight finger tips this much toward the palm from its metacarpal (radians)

# Mass of the body parts for the centre of mass: the kit's bent-spine table, on the joint names above.
MASS = (("pelvis", "spine_03", 0.43 * 0.34), ("spine_03", "spine_05", 0.43 * 0.34), ("spine_05", "neck_01", 0.43 * 0.32),
        ("neck_01", "head_top", 0.1), ("upperarm_l", "lowerarm_l", 0.03), ("lowerarm_l", "hand_l", 0.025),
        ("upperarm_r", "lowerarm_r", 0.03), ("lowerarm_r", "hand_r", 0.025),
        ("thigh_l", "calf_l", 0.1), ("calf_l", "foot_l", 0.05), ("thigh_r", "calf_r", 0.1), ("calf_r", "foot_r", 0.05))


# ---------------- vectors and frames ----------------
def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _len(a):
    return math.hypot(a[0], a[1], a[2])


def _norm(a):
    n = math.hypot(a[0], a[1], a[2]) or 1
    return (a[0] / n, a[1] / n, a[2] / n)


def _lerp(a, b, u):
    return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _rot(v, k, a):
    """v turned by angle a about the unit axis k (Rodrigues)."""
    c, s = math.cos(a), math.sin(a)
    kv, kx = _dot(k, v), _cross(k, v)
    return tuple(v[i] * c + kx[i] * s + k[i] * kv * (1 - c) for i in range(3))


def _about(p, pivot, k, a):
    return _add(pivot, _rot(_sub(p, pivot), k, a))


def _rot_y(v, a):
    return (v[0] * math.cos(a) + v[2] * math.sin(a), v[1], -v[0] * math.sin(a) + v[2] * math.cos(a))


def _yaw_frame(a):
    return (_rot_y((1, 0, 0), a), (0, 1, 0), _rot_y((0, 0, 1), a))


def _rot_frame(F, k, a):
    return tuple(_rot(c, k, a) for c in F) if a else F


def _swing(F, pitch, side, twist):
    """The bone rule: pitch toward Z and side toward X as one rotation vector, then twist about the new Y."""
    G = F
    m = math.hypot(pitch, side)
    if m > 1e-12:
        G = _rot_frame(G, _norm(_add(_mul(F[0], pitch), _mul(F[2], -side))), m)
    if twist:
        G = _rot_frame(G, G[1], twist)
    return G


FOOT_HEAD_LO, FOOT_HEAD_HI = math.sin(75 * math.pi / 180), math.sin(85 * math.pi / 180)


def _foot_heading(G):
    """The foot's heading on the floor (aims the knee pole), with no flip when the toes pass vertical."""
    old = (G[2][0], 0, G[2][2])
    rob = _norm((G[2][0] - G[2][1] * G[1][0], 0, G[2][2] - G[2][1] * G[1][2]))
    if _dot(old, rob) <= 0:
        return rob
    w = _clamp((abs(G[2][1]) - FOOT_HEAD_LO) / (FOOT_HEAD_HI - FOOT_HEAD_LO), 0, 1)
    if w <= 0:
        return _norm(old)
    if w >= 1:
        return rob
    o = _norm(old)
    w = w * w * (3 - 2 * w)
    return _norm(_add(_mul(o, 1 - w), _mul(rob, w)))


def _transport(v, a, b):
    """v turned by the smallest rotation that takes unit a to unit b."""
    c = _cross(a, b)
    s, d = _len(c), _dot(a, b)
    if s < 1e-9:
        if d > 0:
            return v
        axis = _norm(_cross(a, (1, 0, 0))) if abs(a[0]) < 0.9 else _norm(_cross(a, (0, 1, 0)))
        return _rot(v, axis, math.pi)
    return _rot(v, _mul(c, 1 / s), math.atan2(s, d))


def _frame_yz(Y, z_hint):
    Y = _norm(Y)
    Z = _sub(z_hint, _mul(Y, _dot(z_hint, Y)))
    Z = _norm(_cross((1, 0, 0), Y)) if _len(Z) < 1e-9 else _norm(Z)
    return (_cross(Y, Z), Y, Z)


# ---------------- the pose ----------------
class PoseError(ValueError):
    """A pose names a channel the rig does not have, or gives it the wrong shape."""


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_channels(pose: dict, where: str = "pose", allowed: tuple[str, ...] = ()) -> None:
    """Refuse an unknown channel name or a value of the wrong shape, naming it."""
    if not isinstance(pose, dict):
        raise PoseError(f"{where}: needs an object of channels")
    for c, v in pose.items():
        if c in allowed:
            continue
        if c not in STAND:
            raise PoseError(f"{where}: unknown channel {c!r}")
        d = STAND[c]
        if isinstance(d, list):
            if not (isinstance(v, list) and 0 < len(v) <= len(d) and all(map(_number, v))):
                raise PoseError(f"{where}: {c} needs a list of 1 to {len(d)} numbers")
        elif not _number(v):
            raise PoseError(f"{where}: {c} needs a number")
        elif c in LENGTH_SCALES and v <= 0:
            raise PoseError(f"{where}: {c} is a length scale and needs a number above 0")


LENGTH_SCALES = ("sq", "neckS", "armSL", "armSR", "legSL", "legSR", "bladeS")
IK_BONES = ("thigh", "calf", "upperarm", "lowerarm")


def check_proportions(proportions, where: str = "props.proportions") -> None:
    """Refuse an unknown proportion name or a value of the wrong shape (spine 5 numbers, neck 2), naming it.
    A length is 0 or more; the four IK bones (thigh, calf, upperarm, lowerarm) are above 0."""
    if not isinstance(proportions, dict):
        raise PoseError(f"{where}: needs an object of proportions")
    for k, v in proportions.items():
        if k not in PROPORTIONS:
            raise PoseError(f"{where}: unknown proportion {k!r}")
        d = PROPORTIONS[k]
        if isinstance(d, list):
            if not (isinstance(v, list) and len(v) == len(d) and all(_number(x) and x >= 0 for x in v)):
                raise PoseError(f"{where}: {k} needs a list of {len(d)} numbers, 0 or more")
        elif not (_number(v) and v >= 0):
            raise PoseError(f"{where}: {k} needs a number, 0 or more")
        elif k in IK_BONES and v <= 0:
            raise PoseError(f"{where}: {k} needs a number above 0")


def full_pose(pose: dict, base: dict | None = None) -> dict:
    """Every channel: a missing one comes from base (the default stand), a short list takes base's tail."""
    base = STAND if base is None else base
    out = {}
    for c in CHANNELS:
        src = pose.get(c, base.get(c, STAND[c]))
        if isinstance(STAND[c], list):
            a = list(src)
            a += STAND[c][len(a):]
            out[c] = a
        else:
            out[c] = src
    return out


def _fingers(put, wrist, Fhd, side: str, vals: list, k: float) -> None:
    """The finger bones of one hand: put(name, head, tail, frame). k scales the hand layout (hand length / 0.08)."""
    sg, lo = (1 if side == "R" else -1), side.lower()
    X, Y, Z = Fhd
    palm = _mul(X, sg)

    def at(q):
        return _add(wrist, _add(_add(_mul(Y, q[0] * k), _mul(Z, q[1] * k)), _mul(palm, q[2] * k)))

    for i, f in enumerate(FINGERS):
        lay, curl, spread = HAND[f], vals[2 + 2 * i], vals[3 + 2 * i]
        base, knuckle = at(lay["base"]), at(lay["knuckle"])
        put(f"{f}_metacarpal_{lo}", base, knuckle, _frame_yz(_sub(knuckle, base), palm))
        # the straight finger: the hand's Y turned toward the thumb side by the splay and the spread, about the palm
        # normal, then arched toward the palm at the knuckle
        d = _rot(Y, _norm(_cross(Y, Z)), lay["splay"] + spread * lay["fan"])
        F = _swing(_frame_yz(d, palm), KNUCKLE_ARCH, 0, 0)
        pos = knuckle
        for j in range(3):
            F = _swing(F, curl * CURL_SPLIT[j] / sum(CURL_SPLIT), 0, 0)
            tail = _add(pos, _mul(F[1], lay["lengths"][j] * k))
            put(f"{f}_0{j + 1}_{lo}", pos, tail, F)
            pos = tail
    lay, curl, oppose = HAND["thumb"], vals[0], vals[1]
    # the thumb at rest: from its base, turned toward the thumb side (aim[0]) and toward the palm (aim[1]); oppose
    # turns it about the hand's long axis, across the palm
    d = _rot(Y, _norm(_cross(Y, Z)), lay["aim"][0])
    d = _norm(_add(d, _mul(palm, math.tan(lay["aim"][1]))))
    F = _frame_yz(d, _sub(palm, _mul(Z, 0.5)))
    if oppose:
        F = _rot_frame(F, Y, sg * oppose)
    pos = at(lay["base"])
    for j in range(3):
        F = _swing(F, curl * THUMB_SPLIT[j] / sum(THUMB_SPLIT), 0, 0)
        tail = _add(pos, _mul(F[1], lay["lengths"][j] * k))
        put(f"thumb_0{j + 1}_{lo}", pos, tail, F)
        pos = tail


def _skeleton(pose: dict, proportions: dict | None = None, fingers: bool = False):
    """Bones {name: (head, tail, frame, scale)}, extra points and the leg over-reach, for a full pose. fingers adds
    the finger bones."""
    P = {**PROPORTIONS, **proportions} if proportions else PROPORTIONS
    p = full_pose(pose)
    B = {}
    root = tuple(p["root"])

    def put(name, head, tail, F, scale=1):
        B[name] = (head, tail, F, scale)

    def sign(side):
        return 1 if side == "R" else -1

    # pelvis and spine
    Fp = _swing(_yaw_frame(p["yaw"]), p["pelvis"][0], p["pelvis"][1], 0)
    put("root", (root[0], 0, root[2]), root, _yaw_frame(0))
    sq, ns = p["sq"], p["neckS"]
    F, pos = Fp, root
    put("pelvis", pos, _add(pos, _mul(Fp[1], 0.0001)), Fp)
    sp = p["spine"]
    for k in range(5):
        e = p[f"spine{k + 1}"]
        F = _swing(F, sp[0] / 5 + e[0], sp[1] / 5 + e[1], sp[2] / 5 + e[2])
        tail = _add(pos, _mul(F[1], P["spine"][k] * sq))
        put(f"spine_0{k + 1}", pos, tail, F, sq)
        pos = tail
    Fc, chest = F, pos
    # neck and head
    nk, hd = p["neck"], p["head"]
    for k in range(2):
        F = _swing(F, nk[0] / 2, nk[1] / 2, nk[2] / 2)
        tail = _add(pos, _mul(F[1], P["neck"][k] * ns))
        put(f"neck_0{k + 1}", pos, tail, F, ns)
        pos = tail
    F = _swing(F, hd[0], hd[1], hd[2])
    head_top = _add(pos, _mul(F[1], P["head"]))
    put("head", pos, head_top, F)
    Fh, neck_top = F, pos
    # clavicles, arms, hands
    sternum = _add(chest, _mul(Fc[1], -P["sternumDrop"]))

    def arm(side):
        sg, lo = sign(side), side.lower()
        cl, a_s = p["clav" + side], p["armS" + side]
        Fcl = _swing(_frame_yz(_mul(Fc[0], sg), Fc[2]), cl[1], -sg * cl[0], 0)
        sh = _add(sternum, _mul(Fcl[1], P["clavicle"]))
        put("clavicle_" + lo, sternum, sh, Fcl)
        a = p["arm" + side]
        Fua = _swing(_frame_yz(_mul(Fc[1], -1), Fc[2]), a[0], -sg * a[1], -sg * a[2])
        eb = p["elbow" + side]
        elbow = _add(sh, _mul(Fua[1], P["upperarm"] * a_s))
        Fla = _swing(Fua, eb[0], 0, sg * eb[1])
        wrist = _add(elbow, _mul(Fla[1], P["lowerarm"] * a_s))
        ik = p["ik" + side]
        if ik[3] > 0:   # two-bone IK to the wrist, pole = the FK elbow plane, blended by weight
            w = _clamp(ik[3], 0, 1)
            tgt = _lerp(wrist, (ik[0], ik[1], ik[2]), w)
            L1, L2 = P["upperarm"] * a_s, P["lowerarm"] * a_s
            d = _sub(tgt, sh)
            dl = _clamp(_len(d), abs(L1 - L2) + 1e-3, L1 + L2 - 1e-4)
            ax = _norm(d)
            down = _mul(Fua[1], -1)
            bend = _norm(_sub(down, _mul(ax, _dot(down, ax))))
            fk_bend = _sub(_lerp(sh, wrist, 0.5), elbow)
            pole = _sub(fk_bend, _mul(ax, _dot(fk_bend, ax)))
            pole = bend if _len(pole) < 1e-6 else _norm(pole)
            ang = math.acos(_clamp((L1 * L1 + dl * dl - L2 * L2) / (2 * L1 * dl), -1, 1))
            new_elbow = _add(sh, _add(_mul(ax, L1 * math.cos(ang)), _mul(pole, -L1 * math.sin(ang))))
            y1 = _norm(_sub(new_elbow, sh))
            fu = tuple(_transport(c, Fua[1], y1) for c in Fua)
            wr = _add(sh, _mul(ax, dl))
            y2 = _norm(_sub(wr, new_elbow))
            fl = tuple(_transport(c, Fla[1], y2) for c in Fla)
            Fua, Fla, elbow, wrist = fu, fl, new_elbow, wr
        put("upperarm_" + lo, sh, elbow, Fua, a_s)
        put("lowerarm_" + lo, elbow, wrist, Fla, a_s)
        hn = p["hand" + side]
        Fhd = _swing(Fla, hn[1], sg * hn[0], 0)
        put("hand_" + lo, wrist, _add(wrist, _mul(Fhd[1], P["hand"])), Fhd)
        if fingers:
            _fingers(put, wrist, Fhd, side, p["fingers" + side], P["hand"] / 0.08)

    arm("L")
    arm("R")
    # legs and feet
    extra = {}
    over = 0.0

    def leg(side):
        nonlocal over
        sg, lo = sign(side), side.lower()
        f, rl, l_s = p["foot" + side], p["roll" + side], p["legS" + side]
        hip = _add(root, _add(_mul(Fp[0], sg * P["hipWidth"]), _mul(Fp[1], -P["hipDrop"])))
        G = _yaw_frame(f[4])
        G = _rot_frame(G, G[0], f[3])
        A0 = (f[0], f[1], f[2])

        def loc(q):
            return _add(A0, _add(_add(_mul(G[0], q[0]), _mul(G[1], q[1])), _mul(G[2], q[2])))

        st = {"A": A0, "H": loc((0, -P["ankleH"], -P["heelBack"])), "B": loc((0, -P["ankleH"], P["ballFwd"])),
              "T": loc((0, -P["ankleH"] + P["toeH"], P["toeFwd"])), "Gf": G, "Gb": G}

        def rot(piv, k, a, toes_too):
            for n in ("A", "H", "B"):
                st[n] = _about(st[n], piv, k, a)
            st["Gf"] = _rot_frame(st["Gf"], k, a)
            if toes_too:
                st["T"] = _about(st["T"], piv, k, a)
                st["Gb"] = _rot_frame(st["Gb"], k, a)

        if rl[1]:
            rot(_add(st["H"], _mul(G[0], sg * (1 if rl[1] > 0 else -1) * P["edge"])), G[2], -sg * rl[1], True)
        r0, bmax = rl[0], max(0, rl[2])
        if r0 < 0:
            rot(st["H"], G[0], r0, True)
        elif r0 > 0:
            rot(st["B"], G[0], min(r0, bmax), False)
            if r0 > bmax:
                rot(st["T"], G[0], r0 - bmax, True)
        toe = p["toe" + side]
        if toe:
            st["T"] = _about(st["T"], st["B"], st["Gb"][0], toe)
            st["Gb"] = _rot_frame(st["Gb"], st["Gb"][0], toe)
        A, Gf, Gb = st["A"], st["Gf"], st["Gb"]
        # leg IK to the rolled ankle; the knee pole is carried with the leg
        L1, L2 = P["thigh"] * l_s, P["calf"] * l_s
        d = _sub(A, hip)
        dl = _len(d)
        reach = L1 + L2 - 1e-4
        o = 0.0
        if dl > reach:
            o, dl = dl - reach, reach
        if dl < 0.05:
            dl = 0.05
        ax = _norm(d)
        pole0 = _norm(_add(_mul(Fp[2], 0.5), _mul(_foot_heading(Gf), 0.5)))
        pole = _transport(pole0, _mul(Fp[1], -1), ax)
        kt = p["knee" + side]
        if kt:
            pole = _rot(pole, ax, -sg * kt)
        pole = _sub(pole, _mul(ax, _dot(pole, ax)))
        pole = Fp[2] if _len(pole) < 1e-9 else _norm(pole)
        ang = math.acos(_clamp((L1 * L1 + dl * dl - L2 * L2) / (2 * L1 * dl), -1, 1))
        knee = _add(hip, _add(_mul(ax, L1 * math.cos(ang)), _mul(pole, L1 * math.sin(ang))))
        ankle = _add(hip, _mul(ax, dl))
        H, Bl, T = st["H"], st["B"], st["T"]
        shift = _sub(ankle, A)
        if _len(shift) > 1e-12:
            H, Bl, T = _add(H, shift), _add(Bl, shift), _add(T, shift)
        over = max(over, o)
        Ft = _frame_yz(_sub(knee, hip), pole)
        yc = _norm(_sub(ankle, knee))
        put("thigh_" + lo, hip, knee, Ft, l_s)
        put("calf_" + lo, knee, ankle, (Ft[0], yc, _cross(Ft[0], yc)), l_s)
        put("foot_" + lo, ankle, Bl, _frame_yz(_sub(Bl, ankle), Gf[1]))
        put("ball_" + lo, Bl, T, _frame_yz(_sub(T, Bl), Gb[1]))
        extra["heel_" + lo] = H

    leg("L")
    leg("R")
    extra["sternum"] = sternum
    extra["nose"] = _add(_lerp(neck_top, head_top, 0.6), _mul(Fh[2], 0.09))
    return B, extra, over


class Bone(NamedTuple):
    head: tuple[float, float, float]
    tail: tuple[float, float, float]
    frame: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]   # X, Y, Z


def skeleton(pose: dict, proportions: dict | None = None) -> dict[str, Bone]:
    """Every bone of ALL_BONES, fingers included: its head (the joint), its tail and its frame (X, Y, Z: Y along the
    bone, Z the side a hinge bends toward)."""
    B = _skeleton(pose, proportions, fingers=True)[0]
    return {n: Bone(B[n][0], B[n][1], B[n][2]) for n in ALL_BONES}


def solve(pose: dict, proportions: dict | None = None) -> dict[str, tuple[float, float, float]]:
    """Joint positions by name for a pose (see the module docstring). proportions overrides PROPORTIONS fields."""
    B, extra, _ = _skeleton(pose, proportions)
    j = {name: B[name][0] for name in BONES}
    j["head_top"] = B["head"][1]
    for side in "lr":
        j[f"hand_{side}_tip"] = B[f"hand_{side}"][1]
        j[f"ball_{side}_tip"] = B[f"ball_{side}"][1]
        j[f"heel_{side}"] = extra[f"heel_{side}"]
    j["sternum"], j["nose"] = extra["sternum"], extra["nose"]
    j["com"] = com(j)
    return j


def com(joints: dict) -> tuple[float, float, float]:
    """The centre of mass: the mid point of each body part weighted by its share of the mass."""
    s, m = (0.0, 0.0, 0.0), 0.0
    for a, b, w in MASS:
        s = _add(s, _mul(_lerp(joints[a], joints[b], 0.5), w))
        m += w
    return _mul(s, 1 / m)


def over_reach(pose: dict, proportions: dict | None = None) -> float:
    """How far (m) the farther foot target lies beyond the leg's reach; 0 when both feet reach."""
    return _skeleton(pose, proportions)[2]


def bone_lengths(pose: dict, proportions: dict | None = None) -> dict[str, tuple[float, float]]:
    """{bone: (length now, rest length times its length scale)} for every bone but root and pelvis."""
    P = {**PROPORTIONS, **proportions} if proportions else PROPORTIONS
    B = _skeleton(pose, proportions)[0]
    out = {}
    for n in BONES[2:]:
        head, tail, _, scale = B[n]
        kind = n.rsplit("_", 1)[0]
        if kind == "spine":
            rest = P["spine"][int(n[-1]) - 1]
        elif kind == "neck":
            rest = P["neck"][int(n[-1]) - 1]
        elif kind == "foot":
            rest = math.hypot(P["ballFwd"], P["ankleH"])
        elif kind == "ball":
            rest = math.hypot(P["toeFwd"] - P["ballFwd"], P["toeH"])
        else:
            rest = P[kind]
        out[n] = (_len(_sub(tail, head)), rest * scale)
    return out
