"""The control rig on Kei's own characters in Maya, Kei's side: what to build (control_rig_job), and Kei's poses as
control values (pose_to_controls, shot_keys). Standard library only.

The control rig (built by kei_control_rig.py in Maya) is the one an animator moves by hand, and the one Kei keys:
  c_world_ctl        placement; the feet, the poles and the arm IK controls live under it
  c_root_ctl         the root joint, on the floor under the pelvis
  c_body_ctl         the pelvis (the centre of mass control); the spine and the FK legs follow it; attributes
                     squash (Kei's sq) and neckStretch (neckS)
  <s>_<bone>_fk_ctl  one FK control on every other joint, fingers included, on an offset group at the joint's rest
  <s>_foot_ik_ctl    each foot's IK, with roll, ballAngle, bank, toeTap, heelPivot, toePivot
  <s>_leg_pv_ctl, <s>_arm_pv_ctl   the knee and elbow poles
  <s>_arm_ik_ctl     each wrist's IK
  <s>_leg_settings_ctl, <s>_arm_settings_ctl   ikFk (0 FK, 1 IK) and stretch (Kei's legS, armS)
Sides: l is the character's left, r its right, c the centre.

Kei keys whole poses on the controls: the FK controls always (so a switch to FK never pops), the leg IK as well (Kei's
legs are IK: ikFk 1), the arm IK matched to the FK arm (ikFk 0, Kei's arms are FK). Values are degrees and the
scene's linear unit.
"""
from __future__ import annotations

import math

from kei.apps.maya_side import kei_math as km
from kei.characters import load_character, rest_pose
from kei.rig import ALL_BONES, PARENTS, PROPORTIONS, _rot_frame, _skeleton, _yaw_frame, full_pose, skeleton
from kei.sample import cycle_travel, normalize_keys

# Each control's rotate order, with its reason. Kei's bone frames run Y along the bone: X is the pitch axis (the bend
# toward Z), Z the side axis, Y the twist.
ROTATE_ORDERS = {
    "body": ("zxy", "world aligned: yaw (y) last, so the body turns all the way round; pitch rarely reaches 90"),
    "root": ("zxy", "as the body: the heading (y) last, so the whole character turns all the way round"),
    "foot_ik": ("zxy", "yaw (y) last for the foot's heading, pitch (x) in the middle stays far from 90"),
    "arm_ik": ("yzx", "twist first, the side swing in the middle, the forward raise (x) last"),
    "spine": ("yzx", "twist first, side bend in the middle (small), pitch last: a spine can fold past 90 forward"),
    "limb": ("yzx", "twist first, side swing in the middle, the forward swing and the hinge bend (x) last"),
    "finger": ("yzx", "the curl (x) last: fingers curl past 90"),
}
SCALES = {"sq": ("c_body_ctl", "squash"), "neckS": ("c_body_ctl", "neckStretch"),
          "armSL": ("l_arm_settings_ctl", "stretch"), "armSR": ("r_arm_settings_ctl", "stretch"),
          "legSL": ("l_leg_settings_ctl", "stretch"), "legSR": ("r_leg_settings_ctl", "stretch")}
LEG = ("thigh", "calf", "foot", "ball")
ARM = ("upperarm", "lowerarm", "hand")
POLE_M = 0.4            # how far in front of the knee (behind the elbow) the pole controls sit, in metres
FINGER = ("thumb", "index", "middle", "ring", "pinky")


class ControlError(ValueError):
    """A control map or a pose Kei cannot turn into control values. The message names the control."""


def side_of(bone: str) -> str:
    return bone[-1] if bone.endswith(("_l", "_r")) else "c"


def part_of(bone: str) -> str:
    return bone[:-2] if bone.endswith(("_l", "_r")) else bone


def fk_name(bone: str) -> str:
    return f"{side_of(bone)}_{part_of(bone)}_fk_ctl"


def fk_kind(bone: str) -> str:
    p = part_of(bone)
    if p.split("_")[0] in FINGER:
        return "finger"
    if p.startswith(("spine", "neck", "head")):
        return "spine"
    return "limb"


FK_BONES = tuple(b for b in ALL_BONES if b not in ("root", "pelvis"))


def _props(ch) -> dict:
    return {**PROPORTIONS, **(ch.proportions or {})}


def _world(B) -> dict:
    """Bone world rotation and position, in the right-handed world, metres."""
    return {n: (km.mirror_frame(b.frame), km.mirror_point(b.head)) for n, b in B.items()}


def _foot_frame(f) -> list[list[float]]:
    G = _yaw_frame(f[4])
    G = _rot_frame(G, G[0], f[3])
    return km.mirror_frame(G)


def _scale_coeffs(ch) -> dict:
    """{bone: {channel: [kx, ky, kz]}}: how a bone's head moves in its parent's space per unit of a length scale."""
    base = rest_pose(ch)
    B0 = _world(skeleton(base, ch.proportions))
    out = {}
    for c in SCALES:
        B1 = _world(skeleton({**base, c: 2.0}, ch.proportions))
        for n in ALL_BONES:
            p = PARENTS[n]
            if p is None:
                continue
            t0, _ = km.local(B0[p][0], B0[p][1], B0[n][0], B0[n][1])
            t1, _ = km.local(B1[p][0], B1[p][1], B1[n][0], B1[n][1])
            k = [b - a for a, b in zip(t0, t1)]
            if max(abs(x) for x in k) > 1e-9:
                out.setdefault(n, {})[c] = k
    return out


def _deg(R, order, near=None) -> list[float]:
    nr = None if near is None else [math.radians(a) for a in near]
    return [math.degrees(a) for a in km.matrix_euler(R, order, nr)]


def control_rig_job(name: str) -> dict:
    """What build_control_rig needs for a Kei character, in the right-handed world in metres."""
    ch = load_character(name)
    P = _props(ch)
    pose = rest_pose(ch)
    B = skeleton(pose, ch.proportions)
    W = _world(B)
    fk = [{"bone": b, "name": fk_name(b), "parent": PARENTS[b], "side": side_of(b), "kind": fk_kind(b),
           "order": ROTATE_ORDERS[fk_kind(b)][0], "length": math.dist(B[b].head, B[b].tail)} for b in FK_BONES]
    legs, arms = {}, {}
    for s, sg in (("l", -1), ("r", 1)):
        f = pose["foot" + s.upper()]
        knee, thighZ = W[f"calf_{s}"][1], km.mirror_point(B[f"thigh_{s}"].frame[2])
        legs[s] = {"ankle": list(km.mirror_point(f[:3])), "frame_deg": _deg(_foot_frame(f), ROTATE_ORDERS["foot_ik"][0]),
                   "heel": [0.0, -P["ankleH"], -P["heelBack"]], "ball": [0.0, -P["ankleH"], P["ballFwd"]],
                   "toe": [0.0, -P["ankleH"] + P["toeH"], P["toeFwd"]], "edge": P["edge"], "sg": sg,
                   "pole": [knee[i] + thighZ[i] * POLE_M for i in range(3)]}
        elbow, upZ = W[f"lowerarm_{s}"][1], km.mirror_point(B[f"upperarm_{s}"].frame[2])
        R, wrist = W[f"hand_{s}"]
        arms[s] = {"wrist": list(wrist), "frame_deg": _deg(R, ROTATE_ORDERS["arm_ik"][0]),
                   "pole": [elbow[i] - upZ[i] * POLE_M for i in range(3)]}
    return {"character": ch.name, "fk": fk, "legs": legs, "arms": arms, "scales": _scale_coeffs(ch),
            "scale_attrs": {c: list(v) for c, v in SCALES.items()},
            "orders": {k: v[0] for k, v in ROTATE_ORDERS.items()},
            "pelvis": {"pos": list(W["pelvis"][1]), "frame_deg": _deg(W["pelvis"][0], ROTATE_ORDERS["body"][0])},
            "root": list(W["root"][1])}


ROLES = ("world", "root", "body", "fk", "foot_ik", "leg_pv", "arm_ik", "arm_pv", "leg_settings", "arm_settings")


class Rest:
    """A character's rest values for pose_to_controls, computed once."""

    def __init__(self, name: str):
        self.ch = load_character(name)
        self.pose = rest_pose(self.ch)
        self.W = _world(skeleton(self.pose, self.ch.proportions))
        self.job = control_rig_job(name)


def _check_map(rig: dict) -> set[str]:
    names = set()
    for c in rig.get("controls", []):
        if c.get("role") not in ROLES:
            raise ControlError(f"control {c.get('name')!r} in the map has a role Kei does not know: {c.get('role')!r}")
        names.add(c["name"].split(":")[-1])
    return names


def pose_to_controls(pose: dict, rig: dict, rest: Rest | None = None, near: dict | None = None) -> dict:
    """{"<ns>:<control>.<attr>": value} for a Kei pose (any channels; missing ones take the stand). rig is the control
    map (maya_controls.json): its namespace, unit_per_m and controls. near (the last key's values) keeps each Euler
    angle close to the key before."""
    known = _check_map(rig)
    rest = rest or Rest(rig["character"])
    ns, f = rig["namespace"], float(rig["unit_per_m"])
    near = near or {}
    p = full_pose(pose)
    Bk = skeleton(p, rest.ch.proportions)
    W, R0 = _world(Bk), rest.W
    out = {}

    def put(ctl, attr, v):
        if ctl not in known:
            raise ControlError(f"the control map has no {ctl}")
        out[f"{ns}:{ctl}.{attr}"] = v

    def rot(ctl, R, order):
        nr = [near.get(f"{ns}:{ctl}.rotate{a}") for a in "XYZ"]
        d = _deg(R, order, nr if None not in nr else None)
        for a, v in zip("XYZ", d):
            put(ctl, "rotate" + a, v)

    def move(ctl, t):
        for a, v in zip("XYZ", t):
            put(ctl, "translate" + a, v * f)

    # root and body
    move("c_root_ctl", [a - b for a, b in zip(W["root"][1], R0["root"][1])])
    body_rest_rot, body_rest_pos = R0["pelvis"]
    rel = [W["pelvis"][1][i] - W["root"][1][i] - (body_rest_pos[i] - R0["root"][1][i]) for i in range(3)]
    move("c_body_ctl", km.apply(km.transpose(body_rest_rot), rel))
    rot("c_body_ctl", km.mul(km.transpose(body_rest_rot), W["pelvis"][0]), ROTATE_ORDERS["body"][0])
    # FK on every other joint: the rotation from the rest local rotation to the posed one
    for b in FK_BONES:
        par = PARENTS[b]
        JO = km.mul(km.transpose(R0[par][0]), R0[b][0])
        L = km.mul(km.transpose(W[par][0]), W[b][0])
        rot(fk_name(b), km.mul(km.transpose(JO), L), ROTATE_ORDERS[fk_kind(b)][0])
    # legs: IK foot at the ankle target (before the roll), the roll channels, the pole in the knee plane
    for s in "lr":
        S = s.upper()
        foot, roll, leg = p["foot" + S], p["roll" + S], rest.job["legs"][s]
        G0 = km.euler_matrix([math.radians(a) for a in leg["frame_deg"]], ROTATE_ORDERS["foot_ik"][0])
        A = km.mirror_point(foot[:3])
        move(f"{s}_foot_ik_ctl", km.apply(km.transpose(G0), [A[i] - leg["ankle"][i] for i in range(3)]))
        rot(f"{s}_foot_ik_ctl", km.mul(km.transpose(G0), _foot_frame(foot)), ROTATE_ORDERS["foot_ik"][0])
        for attr, v in (("roll", math.degrees(roll[0])), ("bank", math.degrees(roll[1])),
                        ("ballAngle", math.degrees(max(0.0, roll[2]))), ("toeTap", math.degrees(p["toe" + S])),
                        ("heelPivot", 0.0), ("toePivot", 0.0)):
            put(f"{s}_foot_ik_ctl", attr, v)
        knee, z = W[f"calf_{s}"][1], km.mirror_point(Bk[f"thigh_{s}"].frame[2])
        move(f"{s}_leg_pv_ctl", [knee[i] + z[i] * POLE_M - leg["pole"][i] for i in range(3)])
        put(f"{s}_leg_settings_ctl", "ikFk", 1.0)
        put(f"{s}_leg_settings_ctl", "stretch", float(p["legS" + S]))
        # arms: FK (ikFk 0), the IK control and pole matched to the FK arm
        arm = rest.job["arms"][s]
        H0 = km.euler_matrix([math.radians(a) for a in arm["frame_deg"]], ROTATE_ORDERS["arm_ik"][0])
        Rh, wrist = W[f"hand_{s}"]
        move(f"{s}_arm_ik_ctl", km.apply(km.transpose(H0), [wrist[i] - arm["wrist"][i] for i in range(3)]))
        rot(f"{s}_arm_ik_ctl", km.mul(km.transpose(H0), Rh), ROTATE_ORDERS["arm_ik"][0])
        elbow, uz = W[f"lowerarm_{s}"][1], km.mirror_point(Bk[f"upperarm_{s}"].frame[2])
        move(f"{s}_arm_pv_ctl", [elbow[i] - uz[i] * POLE_M - arm["pole"][i] for i in range(3)])
        put(f"{s}_arm_settings_ctl", "ikFk", 0.0)
        put(f"{s}_arm_settings_ctl", "stretch", float(p["armS" + S]))
    put("c_body_ctl", "squash", float(p["sq"]))
    put("c_body_ctl", "neckStretch", float(p["neckS"]))
    return out


TANGENTS = {"step": "step", "linear": "linear", "spline": "spline"}


def _moved(key: dict, travel, sign: int) -> dict:
    """A key with the root, the feet and the IK targets moved on (or back) by one cycle of travel."""
    out = dict(key)
    for c in ("root", "footL", "footR", "ikL", "ikR"):
        v = list(key[c])
        v[0] += sign * travel[0]
        v[2] += sign * travel[2]
        out[c] = v
    return out


def shot_keys(shot: dict, rig: dict, mode: str) -> list[dict]:
    """The set_keys list for a Kei-rig shot: each key's pose as control values. Blocking is stepped; spline keys use
    Maya's spline tangent (the slope from the neighbour keys, as Kei's auto tangent), a flat key stays flat.

    A loop's first and last keys take their slope across the seam, as Kei's sampler does: two wrap keys go out with
    the list (the key before the last, one cycle earlier, and the second key, one cycle later, moved by the travel),
    marked "wrap", so set_keys can fix those two slopes and then remove the wrap keys."""
    rest = Rest(rig["character"])
    keys = normalize_keys(shot)
    n = shot["frames"]
    plan = [(k, False) for k in keys]
    if mode != "step" and shot.get("loop") and len(keys) > 2:
        travel = cycle_travel(shot, keys)
        before = {**_moved(keys[-2], travel, -1), "f": keys[-2]["f"] - n}
        after = {**_moved(keys[1], travel, 1), "f": keys[1]["f"] + n}
        plan = [(before, True)] + plan + [(after, True)]
    out, last = [], None
    for k, wrap in plan:
        vals = pose_to_controls(k, rig, rest, near=last)
        last = vals
        tangent = "step" if mode == "step" else ("flat" if k["tangent"] == "flat" and mode == "spline"
                                                  else TANGENTS[mode])
        out.append({"f": k["f"], "tangent": tangent, "channels": vals, **({"wrap": True} if wrap else {})})
    return out

# ---------------- reading back ----------------
def kei_frame(axes) -> tuple:
    """A joint's axes read from Maya (right-handed world, rows X, Y, Z) as a Kei bone frame (X, Y, Z)."""
    return (tuple(-c for c in km.mirror_point(axes[0])), km.mirror_point(axes[1]), km.mirror_point(axes[2]))


def joints_from_samples(samples: dict, name: str) -> list[dict]:
    """read_samples output as Kei's joints per frame (the names kei.rig.solve gives, tips, heels, sternum, nose and
    the centre of mass included), in Kei's world."""
    from kei.rig import BONES, com
    offs = extra_offsets(name)
    out = []
    for fr in samples["frames"]:
        pos = {k.split(":")[-1]: v for k, v in fr["pos"].items()}
        axes = {k.split(":")[-1]: v for k, v in fr["axes"].items()}
        j = {n: km.mirror_point(pos[n]) for n in BONES}
        for point, (bone, o) in offs.items():
            F = kei_frame(axes[bone])
            head = km.mirror_point(pos[bone])
            j[point] = tuple(head[i] + sum(o[a] * F[a][i] for a in range(3)) for i in range(3))
        j["com"] = com(j)
        out.append({"f": fr["f"], "joints": j})
    return out

EXTRA = {"head_top": ("head", "tail"), "hand_l_tip": ("hand_l", "tail"), "hand_r_tip": ("hand_r", "tail"),
         "ball_l_tip": ("ball_l", "tail"), "ball_r_tip": ("ball_r", "tail")}


def extra_offsets(name: str) -> dict:
    """The points Kei's checks use that are not joints (tips, heels, sternum, nose), as offsets in a bone's frame at
    rest, in Kei's world (so they ride on the Maya joints that come back)."""
    ch = load_character(name)
    B, extra, _ = _skeleton(rest_pose(ch), ch.proportions)
    out = {}

    def off(point, bone):
        head, _, F, _ = B[bone]
        d = [point[i] - head[i] for i in range(3)]
        out[point_name] = (bone, [sum(F[a][i] * d[i] for i in range(3)) for a in range(3)])

    for point_name, (bone, _) in EXTRA.items():
        off(B[bone][1], bone)
    for s in "lr":
        point_name = f"heel_{s}"
        off(extra[point_name], f"foot_{s}")
    point_name = "sternum"
    off(extra["sternum"], "clavicle_l")     # the clavicles start at the sternum, whatever the spine's length scale
    point_name = "nose"
    off(extra["nose"], "head")
    return out
