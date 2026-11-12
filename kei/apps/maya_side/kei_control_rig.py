"""The control rig on a Kei character in Maya: the controls an animator moves by hand, and the ones Kei keys.

build(job, ns) builds it from kei.apps.maya_controls.control_rig_job on the joints that load_character made:
- c_world_ctl > c_root_ctl > c_body_ctl, and an FK control on every other joint on an offset group at the joint's rest
  (channels zero at rest), each joint driven through a parent constraint;
- arms and legs with an FK and an IK chain, blended on the bind joints by ikFk (0 FK, 1 IK) on a settings control,
  an IK handle (rotate plane) with a pole vector control;
- a reverse foot on each IK foot, the same roll as Kei's own rig: roll < 0 turns about the heel, 0 to ballAngle peels
  the heel about the ball, past ballAngle the toes turn about the toe tip, bank tips onto the outer (+) or inner edge,
  toeTap bends the toes at the ball, heelPivot and toePivot swivel the foot at the heel and at the toe;
- Kei's length scales as attributes: squash and neckStretch on c_body_ctl, stretch on each limb's settings control;
- names <side>_<part>_<kind>_ctl, colours by side (left blue, right red, centre yellow), each control's rotate order
  from the table in maya_controls (one reason each), channels that must not be animated locked and hidden.
Every control carries kei_role (and kei_bone for an FK control), so read_rig finds the map again.
"""
from __future__ import annotations

try:
    from . import kei_math as km
except ImportError:
    import kei_math as km

COLOURS = {"l": (0.1, 0.45, 1.0), "r": (1.0, 0.15, 0.15), "c": (1.0, 0.85, 0.1)}
ORDER_INDEX = {o: i for i, o in enumerate(km.ORDERS)}
LEG = ("thigh", "calf", "foot", "ball")
ARM = ("upperarm", "lowerarm", "hand")


# FK control radius (metres) by part: outside the body's surface so a hand can grab it, small enough to read the pose
FK_SIZE = {"spine": 0.17, "neck": 0.09, "head": 0.13, "clavicle": 0.06, "upperarm": 0.07, "lowerarm": 0.06,
           "hand": 0.065, "thigh": 0.11, "calf": 0.085, "foot": 0.08, "ball": 0.06}


def fk_size(bone: str, kind: str) -> float:
    if kind == "finger":
        return 0.012
    return FK_SIZE.get(bone.split("_")[0], 0.07)


class Builder:
    def __init__(self, cmds, job: dict, ns: str, f: float):
        self.c, self.job, self.ns, self.f = cmds, job, ns, f
        self.top = f"{ns}:kei_rig"
        self.controls: list[dict] = []
        self.top_m = cmds.xform(self.top, q=True, worldSpace=True, matrix=True)

    # ---------------- small helpers ----------------
    def n(self, name: str) -> str:
        return f"{self.ns}:{name}"

    def joint(self, bone: str) -> str:
        return self.n(bone)

    def node(self, kind: str, name: str, parent: str | None = None) -> str:
        if parent:
            return self.c.createNode(kind, name=self.n(name), parent=parent)
        return self.c.createNode(kind, name=self.n(name))

    def rig_matrix(self, rot, pos) -> list[float]:
        """A world matrix (Maya's row form) for a rotation and position in the rig's space (metres), under the top
        node (its up axis turn and its placement)."""
        f = self.f
        rows = km.transpose(rot)
        local = [*rows[0], 0.0, *rows[1], 0.0, *rows[2], 0.0, pos[0] * f, pos[1] * f, pos[2] * f, 1.0]
        t = self.top_m
        return [sum(local[r * 4 + k] * t[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]

    def place(self, node: str, matrix: list[float]) -> None:
        self.c.xform(node, worldSpace=True, matrix=matrix)

    def lock(self, ctl: str, attrs) -> None:
        for a in attrs:
            self.c.setAttr(f"{ctl}.{a}", lock=True, keyable=False, channelBox=False)

    def shape(self, ctl: str, kind: str, size: float, side: str, normal=(0, 1, 0)) -> None:
        c, s = self.c, size * self.f
        if kind == "circle":
            crv = c.circle(normal=normal, radius=s, sections=12, constructionHistory=False)[0]
        elif kind == "box":
            p = [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1), (1, -1, -1),
                 (1, 1, -1), (1, 1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1)]
            crv = c.curve(degree=1, point=[(x * s, y * s, z * s) for x, y, z in p])
        elif kind == "diamond":
            p = [(0, 1, 0), (1, 0, 0), (0, -1, 0), (-1, 0, 0), (0, 1, 0), (0, 0, 1), (0, -1, 0), (0, 0, -1), (0, 1, 0)]
            crv = c.curve(degree=1, point=[(x * s, y * s, z * s) for x, y, z in p])
        else:   # cross: the settings controls
            p = [(-1, 0, 0), (1, 0, 0), (0, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 0), (0, 0, 1), (0, 0, -1)]
            crv = c.curve(degree=1, point=[(x * s, y * s, z * s) for x, y, z in p])
        shp = c.listRelatives(crv, shapes=True, fullPath=True)[0]
        c.parent(shp, ctl, relative=True, shape=True)
        c.delete(crv)
        shp = c.listRelatives(ctl, shapes=True, fullPath=True)[0]
        c.rename(shp, ctl.split("|")[-1] + "Shape")
        shp = c.listRelatives(ctl, shapes=True, fullPath=True)[0]
        c.setAttr(shp + ".overrideEnabled", 1)
        c.setAttr(shp + ".overrideRGBColors", 1)
        c.setAttr(shp + ".overrideColorRGB", *COLOURS[side])

    def ctl(self, name: str, parent: str, matrix, role: str, side: str, order: str, shape: str, size: float,
            bone: str | None = None, normal=(0, 1, 0)) -> str:
        ofs = self.node("transform", name[:-4] + "_ofs", parent)
        if matrix is not None:
            self.place(ofs, matrix)
        ctl = self.node("transform", name, ofs)
        self.shape(ctl, shape, size, side, normal)
        self.c.setAttr(ctl + ".rotateOrder", ORDER_INDEX[order])
        for attr, val in (("kei_role", role), ("kei_bone", bone or "")):
            self.c.addAttr(ctl, longName=attr, dataType="string")
            self.c.setAttr(f"{ctl}.{attr}", val, type="string")
            self.c.setAttr(f"{ctl}.{attr}", lock=True)
        self.controls.append({"name": ctl, "role": role, "bone": bone, "side": side, "rotate_order": order})
        return ctl

    def attr(self, node: str, name: str, default: float, lo=None, hi=None) -> str:
        kw = {}
        if lo is not None:
            kw["minValue"] = lo
        if hi is not None:
            kw["maxValue"] = hi
        self.c.addAttr(node, longName=name, attributeType="double", defaultValue=default, keyable=True, **kw)
        return f"{node}.{name}"

    def util(self, kind: str, name: str) -> str:
        return self.c.createNode(kind, name=self.n(name))

    # ---------------- length scales ----------------
    def scaled_translate(self, target: str, bone: str) -> None:
        """target.translate = rest + sum over Kei's scales of (scale - 1) x the bone's coefficient."""
        coeffs = self.job["scales"].get(bone)
        if not coeffs:
            return
        c, f = self.c, self.f
        rest = c.getAttr(target + ".translate")[0]
        pma = self.util("plusMinusAverage", f"{target.split(':')[-1]}_len_sum")
        c.setAttr(pma + ".input3D[0]", *rest, type="double3")
        for i, (channel, k) in enumerate(sorted(coeffs.items()), start=1):
            ctl, attr = self.job["scale_attrs"][channel]
            less = self.util("addDoubleLinear", f"{target.split(':')[-1]}_{channel}_less1")
            c.connectAttr(f"{self.n(ctl)}.{attr}", less + ".input1")
            c.setAttr(less + ".input2", -1.0)
            md = self.util("multiplyDivide", f"{target.split(':')[-1]}_{channel}_len")
            for a in "XYZ":
                c.connectAttr(less + ".output", f"{md}.input1{a}")
            c.setAttr(md + ".input2", *[x * f for x in k], type="double3")
            c.connectAttr(md + ".output", f"{pma}.input3D[{i}]")
        c.connectAttr(pma + ".output3D", target + ".translate", force=True)

    # ---------------- the build ----------------
    def build(self) -> dict:
        c, job = self.c, self.job
        controls = self.node("transform", "controls", self.top)
        internal = self.node("transform", "rig_internal", self.top)
        c.setAttr(internal + ".visibility", 0)
        world = self.ctl("c_world_ctl", controls, None, "world", "c", job["orders"]["root"], "circle", 0.6)
        self.lock(world, ("visibility",))
        root_m = c.xform(self.joint("root"), q=True, worldSpace=True, matrix=True)
        root = self.ctl("c_root_ctl", world, root_m, "root", "c", job["orders"]["root"], "circle", 0.45)
        self.lock(root, ("scaleX", "scaleY", "scaleZ", "visibility"))
        pelvis_m = c.xform(self.joint("pelvis"), q=True, worldSpace=True, matrix=True)
        body = self.ctl("c_body_ctl", root, pelvis_m, "body", "c", job["orders"]["body"], "box", 0.16)
        self.lock(body, ("scaleX", "scaleY", "scaleZ", "visibility"))
        self.attr(body, "squash", 1.0, 0.01)
        self.attr(body, "neckStretch", 1.0, 0.01)
        settings = {}
        # FK on every joint but root and pelvis, parent before child
        fk = {"pelvis": body}
        for e in job["fk"]:
            parent = fk[e["parent"]]
            m = c.xform(self.joint(e["bone"]), q=True, worldSpace=True, matrix=True)
            size = fk_size(e["bone"], e["kind"])
            ctl = self.ctl(e["name"], parent, m, "fk", e["side"], e["order"], "circle", size, e["bone"])
            self.lock(ctl, ("translateX", "translateY", "translateZ", "scaleX", "scaleY", "scaleZ", "visibility"))
            fk[e["bone"]] = ctl
        self.fk = fk
        # settings controls: the leg's beside the hip on the body, the arm's on the clavicle
        for s in "lr":
            for limb, parent, at in (("leg", body, f"thigh_{s}"), ("arm", fk[f"clavicle_{s}"], f"upperarm_{s}")):
                m = c.xform(self.joint(at), q=True, worldSpace=True, matrix=True)
                st = self.ctl(f"{s}_{limb}_settings_ctl", parent, m, f"{limb}_settings", s, "xyz", "cross", 0.05)
                ofs = c.listRelatives(st, parent=True, fullPath=True)[0]
                c.move(-0.12 * self.f if s == "l" else 0.12 * self.f, 0, 0, ofs, relative=True, worldSpace=True)
                self.lock(st, ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ", "scaleX",
                               "scaleY", "scaleZ", "visibility"))
                self.attr(st, "ikFk", 1.0 if limb == "leg" else 0.0, 0.0, 1.0)
                self.attr(st, "stretch", 1.0, 0.01)
                settings[(s, limb)] = st
        for e in job["fk"]:     # the length scales, now that their settings controls exist
            self.scaled_translate(c.listRelatives(fk[e["bone"]], parent=True, fullPath=True)[0], e["bone"])
        for s in "lr":
            self.leg(s, world, body, internal, settings[(s, "leg")])
            self.arm(s, world, internal, settings[(s, "arm")])
        # drive every other bind joint from its FK control (root and pelvis from theirs)
        c.parentConstraint(root, self.joint("root"), maintainOffset=True)
        c.parentConstraint(body, self.joint("pelvis"), maintainOffset=True)
        blended = {f"{p}_{s}" for s in "lr" for p in LEG + ARM}
        for e in job["fk"]:
            if e["bone"] not in blended:
                c.parentConstraint(fk[e["bone"]], self.joint(e["bone"]), maintainOffset=True)
        c.select(clear=True)
        return {"controls": self.controls}

    def chain(self, bones, parent: str, suffix: str) -> list[str]:
        """A copy of the bind joints, at the same rest, rotations moved into the joint orient."""
        c, out, par = self.c, [], parent
        for b in bones:
            j = c.createNode("joint", name=self.n(f"{b}_{suffix}"), parent=par)
            self.place(j, c.xform(self.joint(b), q=True, worldSpace=True, matrix=True))
            out.append(j)
            par = j
        c.makeIdentity(out[0], apply=True, rotate=True, translate=False, scale=False)
        for j, b in zip(out[1:], bones[1:]):
            self.scaled_translate(j, b)
        return out

    def blend(self, bones, fk_nodes, ik_nodes, ikfk: str) -> None:
        c = self.c
        rev = self.util("reverse", f"{bones[0]}_ikFk_rev")
        c.connectAttr(ikfk, rev + ".inputX")
        for b, a, k in zip(bones, fk_nodes, ik_nodes):
            con = c.parentConstraint(a, k, self.joint(b), maintainOffset=True)[0]
            c.setAttr(con + ".interpType", 2)
            w = c.parentConstraint(con, q=True, weightAliasList=True)
            c.connectAttr(rev + ".outputX", f"{con}.{w[0]}")
            c.connectAttr(ikfk, f"{con}.{w[1]}")

    def leg(self, s: str, world: str, body: str, internal: str, settings: str) -> None:
        c, f, job = self.c, self.f, self.job
        leg = job["legs"][s]
        bones = [f"{p}_{s}" for p in LEG]
        grp = self.node("transform", f"{s}_leg_ik_grp", body)
        c.setAttr(grp + ".visibility", 0)
        ik = self.chain(bones, grp, "ik")
        foot_rot = km.euler_matrix([km.math.radians(a) for a in leg["frame_deg"]], job["orders"]["foot_ik"])
        foot = self.ctl(f"{s}_foot_ik_ctl", world, self.rig_matrix(foot_rot, leg["ankle"]), "foot_ik", s,
                        job["orders"]["foot_ik"], "box", 0.07)
        self.lock(foot, ("scaleX", "scaleY", "scaleZ", "visibility"))
        roll = self.attr(foot, "roll", 0.0)
        ball_angle = self.attr(foot, "ballAngle", km.math.degrees(0.6), 0.0)
        bank = self.attr(foot, "bank", 0.0)
        tap = self.attr(foot, "toeTap", 0.0)
        heel_piv = self.attr(foot, "heelPivot", 0.0)
        toe_piv = self.attr(foot, "toePivot", 0.0)
        H, B, T = ([x * f for x in leg[k]] for k in ("heel", "ball", "toe"))
        g = {}
        g["heel"] = self.node("transform", f"{s}_heel_roll", foot)
        g["toe"] = self.node("transform", f"{s}_toe_roll", g["heel"])
        g["ball"] = self.node("transform", f"{s}_ball_roll", g["toe"])
        g["bankA"] = self.node("transform", f"{s}_bank_foot", g["ball"])
        ankle = self.node("transform", f"{s}_ankle_piv", g["bankA"])
        g["bankB"] = self.node("transform", f"{s}_bank_toes", g["toe"])
        g["tap"] = self.node("transform", f"{s}_toe_tap", g["bankB"])
        toes = self.node("transform", f"{s}_toes_piv", g["tap"])
        # bank: the pivot on the outer edge for + and the inner edge for -, turning about the foot's Z
        cond = self.util("condition", f"{s}_bank_side")
        c.connectAttr(bank, cond + ".firstTerm")
        c.setAttr(cond + ".operation", 2)      # greater than
        sg, e = leg["sg"], leg["edge"] * f
        c.setAttr(cond + ".colorIfTrue", -sg * e, H[1], H[2], type="double3")
        c.setAttr(cond + ".colorIfFalse", sg * e, H[1], H[2], type="double3")
        mdl = self.util("multDoubleLinear", f"{s}_bank_sign")
        c.connectAttr(bank, mdl + ".input1")
        c.setAttr(mdl + ".input2", float(sg))
        for grp in (g["bankA"], g["bankB"]):
            c.connectAttr(cond + ".outColor", grp + ".rotatePivot")
            c.connectAttr(mdl + ".output", grp + ".rotateZ")
        # each roll pivot is the point after the bank (Kei turns about the banked heel, ball and toe)
        for key, P in (("heel", H), ("toe", T), ("ball", B)):
            pm = self.util("pointMatrixMult", f"{s}_{key}_banked")
            c.setAttr(pm + ".inPoint", *P, type="double3")
            c.connectAttr(g["bankA"] + ".matrix", pm + ".inMatrix")
            c.connectAttr(pm + ".output", g[key] + ".rotatePivot")
        heel_c = self.util("condition", f"{s}_roll_heel")
        c.connectAttr(roll, heel_c + ".firstTerm")
        c.setAttr(heel_c + ".operation", 4)    # less than 0: the heel takes the roll
        c.connectAttr(roll, heel_c + ".colorIfTrueR")
        c.setAttr(heel_c + ".colorIfFalseR", 0)
        c.connectAttr(heel_c + ".outColorR", g["heel"] + ".rotateX")
        clamp = self.util("clamp", f"{s}_roll_ball")
        c.connectAttr(roll, clamp + ".inputR")
        c.connectAttr(ball_angle, clamp + ".maxR")
        c.connectAttr(clamp + ".outputR", g["ball"] + ".rotateX")
        less = self.util("plusMinusAverage", f"{s}_roll_past_ball")
        c.setAttr(less + ".operation", 2)
        c.connectAttr(roll, less + ".input1D[0]")
        c.connectAttr(ball_angle, less + ".input1D[1]")
        toe_c = self.util("condition", f"{s}_roll_toe")
        c.connectAttr(less + ".output1D", toe_c + ".firstTerm")
        c.setAttr(toe_c + ".operation", 2)
        c.connectAttr(less + ".output1D", toe_c + ".colorIfTrueR")
        c.setAttr(toe_c + ".colorIfFalseR", 0)
        c.connectAttr(toe_c + ".outColorR", g["toe"] + ".rotateX")
        c.connectAttr(heel_piv, g["heel"] + ".rotateY")
        c.connectAttr(toe_piv, g["toe"] + ".rotateY")
        c.setAttr(g["tap"] + ".rotatePivot", *B, type="double3")
        c.connectAttr(tap, g["tap"] + ".rotateX")
        # the IK: a rotate plane handle at the ankle, the pole in front of the knee
        handle = c.ikHandle(startJoint=ik[0], endEffector=ik[2], solver="ikRPsolver", name=self.n(f"{s}_leg_ikh"))[0]
        handle = c.parent(handle, internal)[0]
        self.reach(s, ik, ankle, handle, settings + ".stretch")
        c.orientConstraint(ankle, ik[2], maintainOffset=True)
        c.orientConstraint(toes, ik[3], maintainOffset=True)
        pv = self.ctl(f"{s}_leg_pv_ctl", world, self.rig_matrix(km.identity(), leg["pole"]), "leg_pv", s, "xyz",
                      "diamond", 0.035)
        self.lock(pv, ("rotateX", "rotateY", "rotateZ", "scaleX", "scaleY", "scaleZ", "visibility"))
        c.poleVectorConstraint(pv, handle)
        self.blend(bones, [self.fk[b] for b in bones], ik, settings + ".ikFk")
        self.visibility(settings + ".ikFk", [foot, pv], [self.fk[bones[0]]])

    def reach(self, s: str, ik: list, ankle: str, handle: str, stretch: str) -> None:
        """The leg handle at the ankle target, pulled back toward the hip when the target is out of reach, the same as
        Kei's own leg: its reach is the thigh and the calf less 0.1 mm, so a leg at full stretch keeps a trace of bend
        (the knee then sits where Kei's rig puts it, not on the straight line)."""
        c, f = self.c, self.f
        hip = self.node("transform", f"{s}_hip_piv", c.listRelatives(ik[0], parent=True, fullPath=True)[0])
        self.place(hip, c.xform(ik[0], q=True, worldSpace=True, matrix=True))   # not the joint: no cycle
        loc = {}
        for key, node in (("ankle", ankle), ("hip", hip)):
            mm = self.util("multMatrix", f"{s}_{key}_in_rig")
            c.connectAttr(node + ".worldMatrix[0]", mm + ".matrixIn[0]")
            c.connectAttr(self.top + ".worldInverseMatrix[0]", mm + ".matrixIn[1]")
            dm = self.util("decomposeMatrix", f"{s}_{key}_in_rig_dm")
            c.connectAttr(mm + ".matrixSum", dm + ".inputMatrix")
            loc[key] = dm + ".outputTranslate"
        dist = self.util("distanceBetween", f"{s}_leg_dist")
        c.connectAttr(loc["hip"], dist + ".point1")
        c.connectAttr(loc["ankle"], dist + ".point2")
        rest = sum(sum(x * x for x in c.getAttr(j + ".translate")[0]) ** 0.5 for j in ik[1:3])
        full = self.util("multDoubleLinear", f"{s}_leg_length")
        c.connectAttr(stretch, full + ".input1")
        c.setAttr(full + ".input2", rest)
        reach = self.util("addDoubleLinear", f"{s}_leg_reach")
        c.connectAttr(full + ".output", reach + ".input1")
        c.setAttr(reach + ".input2", -1e-4 * f)
        ratio = self.util("multiplyDivide", f"{s}_leg_ratio")
        c.setAttr(ratio + ".operation", 2)
        c.connectAttr(reach + ".output", ratio + ".input1X")
        c.connectAttr(dist + ".distance", ratio + ".input2X")
        cond = self.util("condition", f"{s}_leg_out_of_reach")
        c.connectAttr(dist + ".distance", cond + ".firstTerm")
        c.connectAttr(reach + ".output", cond + ".secondTerm")
        c.setAttr(cond + ".operation", 2)
        c.connectAttr(ratio + ".outputX", cond + ".colorIfTrueR")
        c.setAttr(cond + ".colorIfFalseR", 1.0)
        vec = self.util("plusMinusAverage", f"{s}_leg_vec")
        c.setAttr(vec + ".operation", 2)
        c.connectAttr(loc["ankle"], vec + ".input3D[0]")
        c.connectAttr(loc["hip"], vec + ".input3D[1]")
        short = self.util("multiplyDivide", f"{s}_leg_vec_short")
        c.connectAttr(vec + ".output3D", short + ".input1")
        for a in "XYZ":
            c.connectAttr(cond + ".outColorR", f"{short}.input2{a}")
        tgt = self.util("plusMinusAverage", f"{s}_leg_target")
        c.connectAttr(loc["hip"], tgt + ".input3D[0]")
        c.connectAttr(short + ".output", tgt + ".input3D[1]")
        c.connectAttr(tgt + ".output3D", handle + ".translate", force=True)

    def arm(self, s: str, world: str, internal: str, settings: str) -> None:
        c, job = self.c, self.job
        arm = job["arms"][s]
        bones = [f"{p}_{s}" for p in ARM]
        grp = self.node("transform", f"{s}_arm_ik_grp", self.fk[f"clavicle_{s}"])
        c.setAttr(grp + ".visibility", 0)
        ik = self.chain(bones, grp, "ik")
        rot = km.euler_matrix([km.math.radians(a) for a in arm["frame_deg"]], job["orders"]["arm_ik"])
        hand = self.ctl(f"{s}_arm_ik_ctl", world, self.rig_matrix(rot, arm["wrist"]), "arm_ik", s,
                        job["orders"]["arm_ik"], "box", 0.045)
        self.lock(hand, ("scaleX", "scaleY", "scaleZ", "visibility"))
        handle = c.ikHandle(startJoint=ik[0], endEffector=ik[2], solver="ikRPsolver", name=self.n(f"{s}_arm_ikh"))[0]
        c.parent(handle, hand)
        c.setAttr(handle + ".visibility", 0)
        c.orientConstraint(hand, ik[2], maintainOffset=True)
        pv = self.ctl(f"{s}_arm_pv_ctl", world, self.rig_matrix(km.identity(), arm["pole"]), "arm_pv", s, "xyz",
                      "diamond", 0.03)
        self.lock(pv, ("rotateX", "rotateY", "rotateZ", "scaleX", "scaleY", "scaleZ", "visibility"))
        c.poleVectorConstraint(pv, handle)
        self.blend(bones, [self.fk[b] for b in bones], ik, settings + ".ikFk")
        self.visibility(settings + ".ikFk", [hand, pv], [self.fk[bones[0]]])

    def visibility(self, ikfk: str, ik_ctls, fk_ctls) -> None:
        """The IK controls show while ikFk is above 0, the FK chain while it is below 1."""
        c = self.c
        for ctls, op, name in ((ik_ctls, 2, "ik"), (fk_ctls, 4, "fk")):
            cond = self.util("condition", ikfk.split(":")[-1].replace(".", "_") + f"_{name}_vis")
            c.connectAttr(ikfk, cond + ".firstTerm")
            c.setAttr(cond + ".secondTerm", 0.0 if name == "ik" else 1.0)
            c.setAttr(cond + ".operation", op)
            c.setAttr(cond + ".colorIfTrueR", 1)
            c.setAttr(cond + ".colorIfFalseR", 0)
            for ctl in ctls:
                ofs = c.listRelatives(ctl, parent=True, fullPath=True)[0]
                c.connectAttr(cond + ".outColorR", ofs + ".visibility")


def build(cmds, job: dict, ns: str, f: float) -> dict:
    return Builder(cmds, job, ns, f).build()
