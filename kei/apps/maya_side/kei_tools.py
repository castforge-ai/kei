"""The named tools Kei calls inside Maya. Each tool has typed inputs (checked before the call) and a kind: "read"
leaves the scene as it was, "change" runs inside one undo chunk per call, so one undo removes the whole call. There is
no tool that runs any code it is sent.

The same functions run in both ways: called directly in a background mayapy job (run_job.py), or sent through the
Kei host in the user's open Maya (kei_host.py), which runs them on Maya's main thread.

Kei's numbers come in metres, in the right-handed world with y up (kei_math). The tools convert to the scene's linear
unit and up axis, and back when they read.
"""
from __future__ import annotations

import math
import os
import re

try:
    from . import kei_math as km
except ImportError:                 # copied flat into a folder on Maya's path
    import kei_math as km

UNIT_PER_M = {"mm": 1000.0, "cm": 100.0, "m": 1.0, "km": 0.001, "in": 39.37007874, "ft": 3.280839895,
              "yd": 1.093613298}
TYPES = {"str": str, "int": int, "number": (int, float), "bool": bool, "list": list, "dict": dict}
TOOLS: dict = {}


class ToolError(ValueError):
    """A call Kei sent is wrong: an unknown tool, a missing or mistyped input, a locked channel. It names the field."""


def tool_entry(fn, kind: str, **inputs) -> dict:
    """A tool table entry: the function, its kind (read or change) and its inputs (name -> type name, or (type name,
    default) for an optional one)."""
    return {"fn": fn, "kind": kind, "inputs": inputs}


def tool(kind: str, **inputs):
    """Register a tool in TOOLS."""
    def deco(fn):
        TOOLS[fn.__name__] = tool_entry(fn, kind, **inputs)
        return fn
    return deco


def check_inputs(name: str, inputs, tools: dict | None = None) -> dict:
    """The inputs with their defaults, or a ToolError that names the tool and the field."""
    tools = TOOLS if tools is None else tools
    if name not in tools:
        raise ToolError(f"unknown tool {name!r}")
    if not isinstance(inputs, dict):
        raise ToolError(f"{name}: inputs must be an object")
    spec = tools[name]["inputs"]
    for k in inputs:
        if k not in spec:
            raise ToolError(f"{name}: unknown input {k!r}")
    out = {}
    for k, t in spec.items():
        tname, default, required = (t, None, True) if isinstance(t, str) else (t[0], t[1], False)
        if k not in inputs:
            if required:
                raise ToolError(f"{name}: input {k!r} is missing")
            out[k] = default
            continue
        v = inputs[k]
        ok = isinstance(v, TYPES[tname]) and not (tname in ("int", "number") and isinstance(v, bool))
        if not ok and not (v is None and not required):
            raise ToolError(f"{name}: input {k!r} must be {tname}")
        out[k] = v
    return out


def in_degrees():
    """Kei's angles are degrees: a tool runs with Maya's angle unit set to degrees, and the scene's own unit (radians
    in some studios) is put back after, so nothing in the scene changes."""
    import contextlib
    try:
        from maya import cmds
    except ImportError:
        return contextlib.nullcontext()

    @contextlib.contextmanager
    def unit():
        was = cmds.currentUnit(q=True, angle=True)
        if was != "deg":
            cmds.currentUnit(angle="deg")
        try:
            yield
        finally:
            if was != "deg":
                cmds.currentUnit(angle=was)
    return unit()


def call(name: str, inputs: dict | None = None):
    """Check the inputs and run the tool, in degrees; a change tool runs in one undo chunk."""
    args = check_inputs(name, inputs or {})
    t = TOOLS[name]
    with in_degrees():
        if t["kind"] != "change":
            return t["fn"](**args)
        from maya import cmds
        cmds.undoInfo(openChunk=True, chunkName="kei_" + name)
        try:
            return t["fn"](**args)
        finally:
            cmds.undoInfo(closeChunk=True)


# ---------------- units and axes ----------------
def unit_per_m() -> float:
    from maya import cmds
    return UNIT_PER_M[cmds.currentUnit(q=True, linear=True)]


def up_axis() -> str:
    from maya import cmds
    return cmds.upAxis(q=True, axis=True)


def to_metres(p, f=None, up=None) -> list[float]:
    """A world point of the scene in metres, y up (a z up scene is turned back)."""
    f = f or unit_per_m()
    up = up or up_axis()
    x, y, z = (c / f for c in p)
    return [x, z, -y] if up == "z" else [x, y, z]


def save_as(path: str) -> str:
    from maya import cmds
    kind = "mayaBinary" if path.lower().endswith(".mb") else "mayaAscii"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    cmds.file(rename=path)
    cmds.file(save=True, type=kind, force=True)
    return path


# ---------------- scene ----------------
@tool("read")
def scene_info():
    """The scene's file, whether it has unsaved changes, its units and up axis, and the Kei rigs in it."""
    from maya import cmds
    rigs = [n for n in cmds.ls("*:kei_rig", "kei_rig", type="transform") or []]
    return {"maya_version": cmds.about(version=True), "scene": cmds.file(q=True, sceneName=True),
            "unsaved": bool(cmds.file(q=True, modified=True)), "batch": bool(cmds.about(batch=True)),
            "units": cmds.currentUnit(q=True, linear=True), "up": cmds.upAxis(q=True, axis=True), "rigs": rigs,
            "start": cmds.playbackOptions(q=True, min=True), "end": cmds.playbackOptions(q=True, max=True)}


@tool("change", path="str")
def save_temp_copy(path):
    """A copy of the whole open scene, unsaved changes included, written to path. The user's own file, the scene's
    name and its unsaved state stay as they were (an export, not a save)."""
    from maya import cmds
    path = path.replace("\\", "/")
    if not path.lower().endswith(".ma"):
        raise ToolError(f"save_temp_copy: the copy must be a .ma file, not {path!r}")
    own = [p for p in (cmds.file(q=True, list=True) or []) if p]
    same = os.path.normcase(os.path.abspath(path))
    scene = cmds.file(q=True, sceneName=True)
    if scene and os.path.normcase(os.path.abspath(scene)) == same:
        raise ToolError(f"save_temp_copy: {path} is the open scene's own file; Kei never writes it")
    if any(os.path.normcase(os.path.abspath(p)) == same for p in own):
        raise ToolError(f"save_temp_copy: {path} is a file the open scene uses (a reference); Kei never writes it")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmds.file(path, exportAll=True, type="mayaAscii", force=True, preserveReferences=True)
    return {"copy": path, "scene": cmds.file(q=True, sceneName=True), "unsaved": bool(cmds.file(q=True, modified=True))}


# ---------------- Kei's characters ----------------
def _linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _rgb(hexcol: str) -> list[float]:
    return [int(hexcol[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]


def _material(cmds, ns: str, m: dict) -> str:
    sh = cmds.shadingNode("standardSurface", asShader=True, name=f"{ns}:{m['name']}_mat")
    sg = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=f"{ns}:{m['name']}_SG")
    cmds.connectAttr(sh + ".outColor", sg + ".surfaceShader", force=True)
    base = [_linear(c) for c in _rgb(m["colour"])]
    cmds.setAttr(sh + ".baseColor", *base, type="double3")
    cmds.setAttr(sh + ".base", 1.0)
    cmds.setAttr(sh + ".specular", 0.2)
    glow = float(m["emission_strength"])
    cmds.setAttr(sh + ".emission", glow)
    cmds.setAttr(sh + ".emissionColor", *[_linear(c) for c in _rgb(m["emission"])], type="double3")
    cmds.addAttr(sh, longName="kei_colour", dataType="string")
    cmds.setAttr(sh + ".kei_colour", m["colour"], type="string")
    if m.get("texture"):        # an imported character's base colour image, read on the mesh's uvs
        tex = cmds.shadingNode("file", asTexture=True, isColorManaged=True, name=f"{ns}:{m['name']}_file")
        place = cmds.shadingNode("place2dTexture", asUtility=True, name=f"{ns}:{m['name']}_place")
        for a in ("coverage", "translateFrame", "rotateFrame", "mirrorU", "mirrorV", "stagger", "wrapU", "wrapV",
                  "repeatUV", "offset", "rotateUV", "noiseUV", "vertexUvOne", "vertexUvTwo", "vertexUvThree",
                  "vertexCameraOne"):
            cmds.connectAttr(f"{place}.{a}", f"{tex}.{a}", force=True)
        cmds.connectAttr(place + ".outUV", tex + ".uvCoord", force=True)
        cmds.connectAttr(place + ".outUvFilterSize", tex + ".uvFilterSize", force=True)
        cmds.setAttr(tex + ".fileTextureName", m["texture"], type="string")
        cmds.setAttr(tex + ".colorSpace", "sRGB", type="string")
        cmds.connectAttr(tex + ".outColor", sh + ".baseColor", force=True)
    return sg


def _mesh(cmds, ns: str, m: dict, joints: list, parent: str, f: float, sg: str) -> str:
    """One mesh skinned to the joints: each point on its one bone ("bone", Kei's own characters), or on its bones
    with their weights ("weights": [[bone index, weight], ...] per point, an imported character's smooth parts), with
    per-triangle uvs ("uvs": u0, v0, u1, v1, u2, v2, v from the bottom) when it has them."""
    import maya.api.OpenMaya as om
    import maya.api.OpenMayaAnim as oma
    pts = om.MPointArray([om.MPoint(p[0] * f, p[1] * f, p[2] * f) for p in m["points"]])
    counts = om.MIntArray([3] * len(m["triangles"]))
    conn = om.MIntArray([i for tri in m["triangles"] for i in tri])
    fn = om.MFnMesh()
    if m.get("uvs"):
        us = om.MFloatArray([t[i] for t in m["uvs"] for i in (0, 2, 4)])
        vs = om.MFloatArray([t[i] for t in m["uvs"] for i in (1, 3, 5)])
        obj = fn.create(pts, counts, conn, us, vs)
        fn.assignUVs(counts, om.MIntArray(range(len(us))))
    else:
        obj = fn.create(pts, counts, conn)
    fn.setVertexNormals(om.MVectorArray([om.MVector(*n) for n in m["normals"]]), om.MIntArray(range(len(pts))))
    tr = om.MFnDagNode(obj).fullPathName()
    tr = cmds.rename(tr, f"{ns}:{m['name']}")
    tr = cmds.parent(tr, parent)[0]
    cmds.sets(tr, edit=True, forceElement=sg)
    weights = m.get("weights") or [[[b, 1.0]] for b in m["bone"]]
    used = sorted({b for vw in weights for b, _ in vw})
    infl = [joints[i] for i in used]
    most = max(len(vw) for vw in weights)
    skin = cmds.skinCluster(infl + [tr], toSelectedBones=True, bindMethod=0, maximumInfluences=most,
                            obeyMaxInfluences=True, normalizeWeights=1, name=f"{ns}:{m['name']}_skin")[0]
    sel = om.MSelectionList()
    sel.add(skin)
    sel.add(tr)
    sk = oma.MFnSkinCluster(sel.getDependNode(0))
    dag = sel.getDagPath(1)
    dag.extendToShape()
    order = {p.partialPathName().split("|")[-1]: i for i, p in enumerate(sk.influenceObjects())}
    col = {i: order[joints[i].split("|")[-1]] for i in used}
    n, k = len(m["points"]), len(order)
    w = om.MDoubleArray(n * k, 0.0)
    for v, vw in enumerate(weights):
        for b, x in vw:
            w[v * k + col[b]] += x
    comp = om.MFnSingleIndexedComponent()
    cobj = comp.create(om.MFn.kMeshVertComponent)
    comp.setCompleteData(n)
    sk.setWeights(dag, cobj, om.MIntArray(range(k)), w, normalize=False)
    return tr


@tool("change", job="dict", namespace=("str", None), variant=("str", None))
def load_character(job, namespace=None, variant=None):
    """Build a Kei character from its job (kei.apps.maya_scene.character_job): joints with the mannequin names in
    the rest pose, meshes rigidly skinned to their bones, and its materials, under <ns>:kei_rig. variant "test" adds
    a locked channel (hand_r.rotateX) and a rotate limit (head rotateX within 30 deg), for the adapter's tests."""
    from maya import cmds
    ns = namespace or job["character"]
    if not cmds.namespace(exists=ns):
        cmds.namespace(add=ns)
    f = unit_per_m()
    top = cmds.createNode("transform", name=f"{ns}:kei_rig")
    if up_axis() == "z":
        cmds.setAttr(top + ".rotateX", 90)
    for attr, val in (("kei_character", job["character"]), ("kei_units", cmds.currentUnit(q=True, linear=True))):
        cmds.addAttr(top, longName=attr, dataType="string")
        cmds.setAttr(f"{top}.{attr}", val, type="string")
    skel = cmds.createNode("transform", name=f"{ns}:skeleton", parent=top)
    geo = cmds.createNode("transform", name=f"{ns}:geometry", parent=top)
    joints, by_name = [], {}
    for b in job["bones"]:
        parent = by_name[b["parent"]] if b["parent"] else skel
        j = cmds.createNode("joint", name=f"{ns}:{b['name']}", parent=parent)
        j = cmds.ls(j, long=True)[0]
        cmds.setAttr(j + ".translate", *[c * f for c in b["translate"]], type="double3")
        cmds.setAttr(j + ".jointOrient", *b["orient"], type="double3")
        finger = b["name"].split("_")[0] in ("thumb", "index", "middle", "ring", "pinky")
        cmds.setAttr(j + ".radius", 0.5 if finger else 1.5)
        cmds.setAttr(j + ".segmentScaleCompensate", 0)
        joints.append(j)
        by_name[b["name"]] = j
    sgs = {m["name"]: _material(cmds, ns, m) for m in job["materials"]}
    for m in job["meshes"]:
        if m["points"]:
            _mesh(cmds, ns, m, joints, geo, f, sgs[m["material"]])
    if variant == "test":
        hand = by_name["hand_r"]
        cmds.setAttr(hand + ".rotateX", lock=True)
        head = by_name["head"]
        cmds.transformLimits(head, rotationX=(-30, 30), enableRotationX=(True, True))
    cmds.select(clear=True)
    return {"top": top, "namespace": ns, "joints": len(joints), "units": cmds.currentUnit(q=True, linear=True),
            "up": up_axis()}


@tool("change", job="dict", namespace=("str", None))
def build_control_rig(job, namespace=None):
    """Build the animator's control rig on a loaded Kei character (job: kei.apps.maya_controls.control_rig_job).
    Returns the control map: every control with its role, its rotate order and its keyable channels."""
    from maya import cmds
    try:
        from . import kei_control_rig
    except ImportError:
        import kei_control_rig
    ns = namespace or job["character"]
    if not cmds.objExists(f"{ns}:kei_rig"):
        raise ToolError(f"build_control_rig: no {ns}:kei_rig in the scene; load the character first")
    built = kei_control_rig.build(cmds, job, ns, unit_per_m())
    return control_map(ns, built["controls"])


def control_map(ns: str, controls: list[dict]) -> dict:
    from maya import cmds
    out = []
    for c in controls:
        out.append({**c, "name": c["name"].split("|")[-1],
                    "keyable": cmds.listAttr(c["name"], keyable=True, unlocked=True) or []})
    return {"character": cmds.getAttr(f"{ns}:kei_rig.kei_character"), "namespace": ns, "unit_per_m": unit_per_m(),
            "units": cmds.currentUnit(q=True, linear=True), "up": up_axis(), "controls": out}


TANGENT = {"step": ("clamped", "step"), "linear": ("linear", "linear"), "spline": ("spline", "spline"),
           "flat": ("flat", "flat"), "auto": ("auto", "auto")}


def _key_target(cmds, plug: str) -> tuple[str, str]:
    if not isinstance(plug, str) or "." not in plug:
        raise ToolError(f"set_keys: {plug!r} is not a control.channel")
    node, attr = plug.rsplit(".", 1)
    found = cmds.ls(node, long=True) or []
    if len(found) != 1:
        raise ToolError(f"set_keys: {'no' if not found else 'more than one'} node named {node!r}")
    node = found[0]
    if not cmds.attributeQuery(attr, node=node, exists=True):
        raise ToolError(f"set_keys: {node.split('|')[-1]} has no channel {attr!r}")
    if cmds.getAttr(f"{node}.{attr}", lock=True) or not cmds.getAttr(f"{node}.{attr}", keyable=True):
        raise ToolError(f"set_keys: {node.split('|')[-1]}.{attr} is locked or not keyable; Kei does not key it")
    return node, attr


def _limit(cmds, node: str, attr: str):
    flags = {"rotateX": "rx", "rotateY": "ry", "rotateZ": "rz", "translateX": "tx", "translateY": "ty",
             "translateZ": "tz"}
    if attr not in flags or cmds.nodeType(node) not in ("transform", "joint"):
        return None
    on = cmds.transformLimits(node, q=True, **{"e" + flags[attr]: True})
    lim = cmds.transformLimits(node, q=True, **{flags[attr]: True})
    lo = round(lim[0], 6) if on[0] else None     # Maya keeps limits in radians: 30 deg reads 29.999999...
    hi = round(lim[1], 6) if on[1] else None
    return None if lo is None and hi is None else (lo, hi)


def _clamp_spline_tangents(cmds, keys, plugs, layer):
    """Give every spline key Kei's clamped slope, so Maya plays the curve Kei bakes: a held pose stays held and no
    curve overshoots its keys (kei.sample). The slope is set as a fixed tangent angle, in the curve's own unit (degrees
    or the scene's length) per frame, the measure Maya's tangent angles use here (checked against a Maya bake)."""
    for plug, (node, attr) in plugs.items():
        series = sorted((k["f"], float(k["channels"][plug]), k.get("tangent", "spline")) for k in keys
                        if plug in k["channels"])
        if len(series) < 2:
            continue
        slopes = km.clamped_slopes([s[0] for s in series], [s[1] for s in series])
        curves = (cmds.animLayer(layer, q=True, findCurveForPlug=f"{node}.{attr}") or []) if layer else []
        target = curves[0] if curves else node
        akw = {} if curves else {"attribute": attr}
        for (f, _v, tangent), m in zip(series, slopes):
            if tangent != "spline":
                continue
            ang = math.degrees(math.atan(m))
            cmds.keyTangent(target, time=(f, f), lock=False, **akw)
            cmds.keyTangent(target, time=(f, f), inTangentType="fixed", outTangentType="fixed", inAngle=ang,
                            outAngle=ang, **akw)


@tool("change", keys="list", layer=("str", None), feedback=("str", None), feedback_controls=("list", None),
      controls_layer=("list", None))
def set_keys(keys, layer=None, feedback=None, feedback_controls=None, controls_layer=None):
    """Key each channel of each key: keys = [{"f", "tangent": step|linear|spline|flat, "channels": {"node.attr":
    value}}]. Values are degrees and the scene's unit. The channels' old keys (on the layer, when one is given) are
    cleared first, so a pass replaces the last one. A locked or unkeyable channel is refused, by name, before any key.
    A value beyond a channel's limit is keyed as asked and reported (asked versus reached)."""
    from maya import cmds
    plugs = {}
    for k in keys:
        if not isinstance(k, dict) or not isinstance(k.get("channels"), dict) or "f" not in k:
            raise ToolError("set_keys: each key needs f and channels")
        if k.get("tangent", "spline") not in TANGENT:
            raise ToolError(f"set_keys: key f {k['f']}: unknown tangent {k.get('tangent')!r}")
        for plug in k["channels"]:
            if plug not in plugs:
                plugs[plug] = _key_target(cmds, plug)
    nodes = sorted({n for n, _ in plugs.values()})
    muted = []
    if layer:
        # an override layer per pass: its keys replace what is under it (an additive layer would add a pass to the
        # last one, and to a channel whose rest is not zero); the other kei_ passes are muted, never deleted
        if not cmds.objExists(layer):
            cmds.animLayer(layer, override=True)
        else:
            cmds.animLayer(layer, edit=True, override=True)
        cmds.animLayer(layer, edit=True, mute=False)
        for other in cmds.ls(type="animLayer") or []:
            if other.startswith("kei_") and other != layer and not cmds.animLayer(other, q=True, mute=True):
                cmds.animLayer(other, edit=True, mute=True)
                muted.append(other)
        cmds.select(nodes, replace=True)
        cmds.animLayer(layer, edit=True, addSelectedObjects=True)
        cmds.select(clear=True)
        for node, attr in plugs.values():
            curves = cmds.animLayer(layer, q=True, findCurveForPlug=f"{node}.{attr}") or []
            for crv in curves:
                cmds.cutKey(crv, clear=True)
    else:
        for node, attr in plugs.values():
            cmds.cutKey(node, attribute=attr, clear=True)
    clipped = []
    for k in keys:
        if k.get("wrap") is not None and not isinstance(k["wrap"], bool):
            raise ToolError(f"set_keys: key f {k['f']}: wrap is true or false")
        itt, ott = TANGENT[k.get("tangent", "spline")]
        for plug, v in k["channels"].items():
            node, attr = plugs[plug]
            kw = {"animLayer": layer} if layer else {}
            cmds.setKeyframe(node, attribute=attr, time=k["f"], value=float(v), inTangentType=itt,
                             outTangentType=ott, **kw)
            lim = _limit(cmds, node, attr)
            if lim and ((lim[0] is not None and v < lim[0]) or (lim[1] is not None and v > lim[1])):
                reached = max(lim[0], v) if lim[0] is not None else v
                reached = min(lim[1], reached) if lim[1] is not None else reached
                clipped.append({"f": k["f"], "channel": plug, "asked": v, "reached": reached})
    _clamp_spline_tangents(cmds, keys, plugs, layer)
    wraps = [k for k in keys if k.get("wrap")]
    if wraps:       # a loop: the seam keys keep the slope their wrap neighbours gave them, then the wraps go
        real = [k["f"] for k in keys if not k.get("wrap")]
        for node, attr in plugs.values():
            kw = {"animLayer": layer} if layer else {}
            for t in (min(real), max(real)):
                curves = (cmds.animLayer(layer, q=True, findCurveForPlug=f"{node}.{attr}") or []) if layer else []
                target = curves[0] if curves else node
                akw = {} if curves else {"attribute": attr}
                cmds.keyTangent(target, time=(t, t), lock=False, **akw)
                cmds.keyTangent(target, time=(t, t), inTangentType="fixed", outTangentType="fixed", **akw)
            for w in wraps:
                curves = (cmds.animLayer(layer, q=True, findCurveForPlug=f"{node}.{attr}") or []) if layer else []
                if curves:
                    cmds.cutKey(curves[0], time=(w["f"], w["f"]), clear=True)
                else:
                    cmds.cutKey(node, attribute=attr, time=(w["f"], w["f"]), clear=True)
    real_keys = len([k for k in keys if not k.get("wrap")])
    made = None
    if feedback:        # the animator's layer for this pass, in the same undo chunk as the keys
        made = make_feedback_layer(cmds, feedback, layer, feedback_controls or nodes)
    shown = make_controls_layer(cmds, controls_layer) if controls_layer else None
    return {"keys": real_keys, "channels": len(plugs), "clipped": clipped, "muted": muted, "feedback": made,
            "controls_layer": shown}


@tool("read", joints="list", start="number", end="number")
def read_samples(joints, start, end):
    """Each joint's world position (metres, y up) and rotation (its X, Y, Z axes) on every frame from start to end."""
    from maya import cmds
    f, up = unit_per_m(), up_axis()
    full = {}
    for j in joints:
        found = cmds.ls(j, long=True) or []
        if len(found) != 1:
            raise ToolError(f"read_samples: {'no' if not found else 'more than one'} joint named {j!r}")
        full[j] = found[0]
    frames = []
    now = cmds.currentTime(q=True)
    fr = int(round(start))
    while fr <= end + 1e-9:
        cmds.currentTime(fr, update=True)
        pos, rot = {}, {}
        for j, node in full.items():
            m = cmds.xform(node, q=True, worldSpace=True, matrix=True)
            pos[j] = to_metres(m[12:15], f, up)
            axes = []
            for r in range(3):
                v = m[r * 4:r * 4 + 3]
                n = math.sqrt(sum(x * x for x in v)) or 1.0
                axes.append(to_metres([x / n * f for x in v], f, up))
            rot[j] = axes
        frames.append({"f": fr, "pos": pos, "axes": rot})
        fr += 1
    cmds.currentTime(now, update=True)
    return {"frames": frames}


FPS = {24: "film", 25: "pal", 30: "ntsc", 48: "show", 50: "palf", 60: "ntscf"}


@tool("change", start="number", end="number", fps=("number", 24))
def set_time(start, end, fps=24):
    """The scene's frame rate and playback range."""
    from maya import cmds
    unit = FPS.get(int(fps)) if float(fps).is_integer() else None
    cmds.currentUnit(time=unit or f"{fps}fps", updateAnimation=False)    # the scene's keys stay on their frames
    cmds.playbackOptions(minTime=start, maxTime=end, animationStartTime=start, animationEndTime=end)
    return {"start": start, "end": end, "fps": fps}


BACKGROUND_ONLY = {"playblast", "export_fbx", "read_rig",   # they change (or nudge) the scene they run on: Kei
                   "read_feedback_layers", "set_feedback_mute"}   # runs them on a copy only


# ---------------- the animator's feedback layers ----------------
FEEDBACK = "feedback"       # a layer named feedback or feedback_<anything> holds the animator's corrections


def is_feedback(layer: str) -> bool:
    return layer.split("|")[-1].rpartition(":")[2].lower().startswith(FEEDBACK)


PASS_NAME = re.compile(r"blocking|p\d+")


def _short_layer(layer: str) -> str:
    return layer.split("|")[-1].rpartition(":")[2]


def layer_pass(layer: str) -> str | None:
    """The pass a feedback layer belongs to (feedback_p24 to p24, feedback_blocking to blocking), or None for a layer
    the animator named (feedback, feedback_knee)."""
    rest = _short_layer(layer)[len(FEEDBACK):].lstrip("_")
    return rest if PASS_NAME.fullmatch(rest) else None


def feedback_layers(pass_name: str | None = None) -> tuple[list[str], list[dict]]:
    """The feedback layers to read for a pass: its own feedback_<pass> and every layer not tied to a pass; and the
    layers of other passes, named and left alone. With no pass, every feedback layer is read."""
    from maya import cmds
    read, other = [], []
    for n in cmds.ls(type="animLayer") or []:
        if not is_feedback(n):
            continue
        owner = layer_pass(n)
        if pass_name is not None and owner is not None and owner != pass_name:
            other.append({"layer": n, "pass": owner})
        else:
            read.append(n)
    return read, other


def make_feedback_layer(cmds, name: str, above: str | None, controls: list[str]) -> dict:
    """An empty additive layer for the animator's corrections, directly above Kei's pass layer, with the controls on
    it, selected and preferred so the animator's next key lands on it (the other layers are deselected). A layer of
    that name that exists is left exactly as it is: Kei never changes, mutes, clears or deletes a feedback layer."""
    if name in (cmds.ls(type="animLayer") or []):
        return {"layer": name, "created": False}
    cmds.animLayer(name, override=False)
    if above and above in (cmds.ls(type="animLayer") or []):
        cmds.animLayer(name, edit=True, moveLayerAfter=above)
    nodes = []
    for c in controls:
        found = cmds.ls(c, long=True) or []
        if len(found) == 1:
            nodes.append(found[0])
    if nodes:
        cmds.select(nodes, replace=True)
        cmds.animLayer(name, edit=True, addSelectedObjects=True)
        cmds.select(clear=True)
    for other in cmds.ls(type="animLayer") or []:
        if other != name and (cmds.animLayer(other, q=True, selected=True)
                              or cmds.animLayer(other, q=True, preferred=True)):
            cmds.animLayer(other, edit=True, selected=False, preferred=False)
    cmds.animLayer(name, edit=True, selected=True, preferred=True)
    return {"layer": name, "created": True, "controls": len(nodes)}


CONTROLS_LAYER = "kei_controls"


def make_controls_layer(cmds, controls: list[str]) -> dict | None:
    """A display layer with every control of the rig, so the animator shows, hides, selects or templates them all at
    once. A display layer that already holds them all is used as it is. Otherwise Kei makes kei_controls (or adds to
    it) with the controls that sit in no display layer: a control in one of the animator's own display layers stays
    there, because a node belongs to one display layer only and Kei never reorganizes the animator's scene."""
    nodes = []
    for c in controls:
        found = cmds.ls(c, long=True) or []
        if len(found) == 1 and found[0] not in nodes:
            nodes.append(found[0])
    if not nodes:
        return None

    def members(layer):
        return set(cmds.editDisplayLayerMembers(layer, q=True, fullNames=True) or [])
    layers = [d for d in cmds.ls(type="displayLayer") or [] if d != "defaultLayer"]
    want = set(nodes)
    for d in layers:
        if want <= members(d):
            return {"layer": d, "created": False, "added": 0}
    owner = {}
    for d in layers:
        if d != CONTROLS_LAYER:
            for n in members(d) & want:
                owner[n] = d
    free = [n for n in nodes if n not in owner]
    exists = CONTROLS_LAYER in layers
    if not free and not exists:
        return {"layer": None, "created": False, "added": 0, "kept_in_your_layers": sorted(set(owner.values()))}
    if not exists:
        cmds.createDisplayLayer(name=CONTROLS_LAYER, empty=True, noRecurse=True)
    added = [n for n in free if n not in members(CONTROLS_LAYER)]
    if added:
        cmds.editDisplayLayerMembers(CONTROLS_LAYER, *added, noRecurse=True)
    return {"layer": CONTROLS_LAYER, "created": not exists, "added": len(added),
            "kept_in_your_layers": sorted(set(owner.values()))}


@tool("change", controls="list")
def controls_layer(controls):
    """The display layer with every control of the rig (make_controls_layer), on its own."""
    from maya import cmds
    return make_controls_layer(cmds, controls)


@tool("change", mute="bool", pass_name=("str", None))
def set_feedback_mute(mute, pass_name=None):
    """Mute (or unmute) the feedback layers a read of the pass takes, to draw Kei's pass before and after the
    animator's corrections. It changes the scene it runs on, so Kei runs it on a copy only, never on the animator's
    own layers."""
    from maya import cmds
    layers, _ = feedback_layers(pass_name)
    for layer in layers:
        cmds.animLayer(layer, edit=True, mute=mute)
    return {"layers": layers, "mute": mute}


def _namespace(node: str) -> str:
    return node.split("|")[-1].rpartition(":")[0]


@tool("read", rig=("str", None), start=("number", 0), end=("number", None), pass_name=("str", None))
def read_feedback_layers(rig=None, start=0, end=None, pass_name=None):
    """The animator's corrections: every channel keyed on a layer named feedback*, on every frame from start to end,
    as its value and its offset from Kei's own pass (the scene with every feedback layer muted). Each layer is read
    alone, on top of Kei's pass, so an additive and an override layer both give the right offset. A row is a frame the
    animator keyed, or a frame the correction changes. Keys outside start..end are reported, never wrapped; a control
    outside the rig's namespace is named, not read; a locked channel is marked; a value beyond a limit gives the asked
    and the reached value. With a pass, its own layer feedback_<pass> and the animator's own feedback layers are
    read; a layer of another pass is named in other_pass and left alone. The layers are muted and unmuted while it
    reads, so Kei runs it on a copy only; their mute states are put back."""
    from maya import cmds
    end = cmds.playbackOptions(q=True, max=True) if end is None else end
    frames = list(range(int(round(start)), int(round(end)) + 1))
    layers, other_pass = feedback_layers(pass_name)
    out = {"layers": {}, "modes": {}, "outside": [], "other_rig": [], "other_pass": other_pass,
           "units": cmds.currentUnit(q=True, linear=True),
           "unit_per_m": unit_per_m(), "start": frames[0], "end": frames[-1]}
    plugs, keyed = {}, {}
    for layer in layers:
        out["modes"][layer] = "override" if cmds.animLayer(layer, q=True, override=True) else "additive"
        mine = []
        for plug in cmds.animLayer(layer, q=True, attribute=True) or []:
            node, attr = plug.rsplit(".", 1)
            if rig is not None and _namespace(node) != rig:
                out["other_rig"].append({"layer": layer, "control": node, "attr": attr})
                continue
            times = []
            for crv in cmds.animLayer(layer, q=True, findCurveForPlug=plug) or []:
                times += cmds.keyframe(crv, q=True, timeChange=True) or []
            if not times:       # added to the layer with its node, never keyed there: not a correction
                continue
            keyed[(layer, plug)] = sorted({int(round(t)) for t in times})
            for t in keyed[(layer, plug)]:
                if t < frames[0] or t > frames[-1]:
                    out["outside"].append({"layer": layer, "control": node, "attr": attr, "frame": t})
            mine.append(plug)
        plugs[layer] = mine
    was = {layer: bool(cmds.animLayer(layer, q=True, mute=True)) for layer in layers}
    now = cmds.currentTime(q=True)

    def sample(ps):
        # each frame is made current and read there: getAttr's time flag does not blend animation layers (Maya
        # 2027 gave the value under an additive layer), so it is never used here
        got = {p: {} for p in ps}
        for f in frames:
            cmds.currentTime(f, update=True)
            for p in ps:
                got[p][f] = cmds.getAttr(p)
        return got
    try:
        for layer in layers:
            cmds.animLayer(layer, edit=True, mute=True)
        every = sorted({p for ps in plugs.values() for p in ps})
        base = sample(every)
        for layer in layers:
            cmds.animLayer(layer, edit=True, mute=False)
            on = sample(plugs[layer])
            rows = []
            for plug in plugs[layer]:
                node, attr = plug.rsplit(".", 1)
                locked = bool(cmds.getAttr(plug, lock=True))
                lim = _limit(cmds, node, attr)
                for f in frames:
                    v = on[plug][f]
                    off = v - base[plug][f]
                    key = f in keyed[(layer, plug)]
                    if not key and abs(off) < 1e-6:
                        continue
                    row = {"control": node, "attr": attr, "frame": f, "value": v, "offset": off, "key": key}
                    if locked:
                        row["locked"] = True
                    if lim and ((lim[0] is not None and v < lim[0]) or (lim[1] is not None and v > lim[1])):
                        reached = max(lim[0], v) if lim[0] is not None else v
                        row["asked"] = v
                        row["reached"] = min(lim[1], reached) if lim[1] is not None else reached
                    rows.append(row)
            out["layers"][layer] = rows
            cmds.animLayer(layer, edit=True, mute=True)
    finally:
        for layer, m in was.items():
            cmds.animLayer(layer, edit=True, mute=m)
        cmds.currentTime(now, update=True)
    return out

VIEWS = {   # camera direction (from the character toward the camera), right-handed, y up; ortho or not
    "front": ((0.0, 0.0, 1.0), True), "side": ((-1.0, 0.0, 0.0), True), "top": ((0.0, 1.0, 0.0001), True),
    "three quarter": ((-0.7071, 0.25, 0.7071), False)}


def _bounds(cmds, nodes, start, end):
    lo, hi = [1e30] * 3, [-1e30] * 3
    for t in sorted({int(start), int((start + end) / 2), int(end)}):
        cmds.currentTime(t, update=True)
        b = cmds.exactWorldBoundingBox(nodes)
        lo = [min(a, c) for a, c in zip(lo, b[:3])]
        hi = [max(a, c) for a, c in zip(hi, b[3:])]
    return lo, hi


def _aim(d):
    """Camera rotation (degrees, xyz) that looks along -d."""
    x, y, z = d
    yaw = math.degrees(math.atan2(x, z))
    pitch = -math.degrees(math.atan2(y, math.hypot(x, z)))
    return (pitch, yaw, 0.0)


@tool("change", folder="str", start="number", end="number", views=("list", None), width=("int", 640),
      height=("int", 360), nodes=("list", None))
def playblast(folder, start, end, views=None, width=640, height=360, nodes=None):
    """Preview frames of each view (front, side, top, three quarter) into folder/<view>/f0000.png..., framed on the
    nodes (default: every Kei rig's geometry) over the whole range. It moves the default camera, so Kei runs it on a
    copy of the scene, never in the user's open scene."""
    from maya import cmds
    views = views or list(VIEWS)
    for v in views:
        if v not in VIEWS:
            raise ToolError(f"playblast: unknown view {v!r}; use {', '.join(VIEWS)}")
    nodes = nodes or cmds.ls("*:geometry", "geometry", type="transform") or cmds.ls(type="mesh")
    lo, hi = _bounds(cmds, nodes, start, end)
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    span = max(b - a for a, b in zip(lo, hi)) * 1.25
    cam = "persp"
    shape = cmds.listRelatives(cam, shapes=True)[0]
    cmds.setAttr(shape + ".farClipPlane", span * 100)
    cmds.setAttr(shape + ".nearClipPlane", span * 0.001)
    out = {}
    for v in views:
        d, ortho = VIEWS[v]
        n = math.sqrt(sum(c * c for c in d))
        d = [c / n for c in d]
        cmds.setAttr(shape + ".orthographic", ortho)
        if ortho:
            cmds.setAttr(shape + ".orthographicWidth", span * width / height if v != "top" else span)
        dist = span * 3
        cmds.xform(cam, worldSpace=True, translation=[centre[i] + d[i] * dist for i in range(3)],
                   rotation=_aim(d))
        if not ortho:
            cmds.setAttr(shape + ".focalLength", 35.0 * dist / (span * 1.6))
        sub = os.path.join(folder, v.replace(" ", "_"))
        os.makedirs(sub, exist_ok=True)
        cmds.playblast(startTime=start, endTime=end, format="image", compression="png", viewer=False,
                       offScreen=True, filename=os.path.join(sub, "pb"), forceOverwrite=True, percent=100,
                       widthHeight=(width, height), showOrnaments=False, framePadding=4)
        files = []
        for fr in range(int(start), int(end) + 1):
            src = os.path.join(sub, f"pb.{fr:04d}.png")
            dst = os.path.join(sub, f"f{fr - int(start):04d}.png")
            if os.path.isfile(src):
                os.replace(src, dst)
                files.append(dst)
        out[v] = {"folder": sub, "frames": len(files)}
    return {"views": out, "renderer": "maya playblast", "camera_span": span}


@tool("change", path="str", start="number", end="number", namespace=("str", None))
def export_fbx(path, start, end, namespace=None):
    """FBX of the skeleton and its meshes, the controls baked onto the joints on every frame, the control rig and
    the namespace removed, so the file holds only joints, meshes and keys with the mannequin names. It changes the
    scene it runs on, so Kei runs it on a copy, never in the user's open scene."""
    from maya import cmds, mel
    if any(ch in path for ch in "\"\r\n"):
        raise ToolError(f"export_fbx: a path may not hold quotes or line breaks: {path!r}")
    ns = namespace or (cmds.ls("*:kei_rig")[0].split(":")[0] if cmds.ls("*:kei_rig") else None)
    pat = f"{ns}:*" if ns else "*"
    joints = [j for j in cmds.ls(pat, type="joint", long=True) or [] if "_ik_grp" not in j and not j.endswith("_ik")]
    if not joints:
        raise ToolError("export_fbx: no joints to export")
    cmds.bakeResults(joints, time=(start, end), simulation=True, attribute=["tx", "ty", "tz", "rx", "ry", "rz"],
                     disableImplicitControl=True, preserveOutsideKeys=False, sampleBy=1)
    cons = cmds.listRelatives(joints, type="constraint", fullPath=True) or []
    if cons:
        cmds.delete(cons)
    for grp in (f"{ns}:controls", f"{ns}:rig_internal") if ns else ("controls", "rig_internal"):
        if cmds.objExists(grp):
            cmds.delete(grp)
    if ns and cmds.namespace(exists=ns):
        cmds.namespace(removeNamespace=ns, mergeNamespaceWithRoot=True)
    if not cmds.pluginInfo("fbxmaya", q=True, loaded=True):
        cmds.loadPlugin("fbxmaya", quiet=True)
    top = [t for t in cmds.ls("kei_rig", long=True) or []] or cmds.ls(assemblies=True)
    for line in ("FBXResetExport", "FBXExportInAscii -v false", "FBXExportBakeComplexAnimation -v false",
                 "FBXExportSkins -v true", "FBXExportShapes -v false", "FBXExportConstraints -v false",
                 "FBXExportUpAxis y", "FBXExportFileVersion -v FBX202000",
                 "FBXExportEmbeddedTextures -v true"):      # an imported character's texture travels in the file
        mel.eval(line)
    path = path.replace("\\", "/")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cmds.select(top, replace=True)
    # quotes and line breaks are refused above, so the path cannot leave its MEL string (cmds.file would cut a
    # path at a semicolon, which FBXExport keeps)
    mel.eval('FBXExport -f "%s" -s' % path.replace("\\", "/"))
    return {"fbx": path, "joints": len(joints), "bytes": os.path.getsize(path)}


NUDGE = {"translate": 0.1, "rotate": 10.0}     # metres and degrees: a channel nudged this much shows what it moves


def _limits(cmds, node: str) -> dict:
    out = {}
    for attr in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
        lim = _limit(cmds, node, attr)
        if lim:
            out[attr] = [lim[0], lim[1]]
    return out


def limits_of(node: str) -> dict:
    """A node's enabled translate and rotate limits, rotations in degrees."""
    from maya import cmds
    with in_degrees():
        return _limits(cmds, node)


def _pose_of(cmds, joints: list[str]) -> list:
    return [cmds.xform(j, q=True, worldSpace=True, matrix=True) for j in joints]


@tool("read", namespace=("str", None))
def read_rig(namespace=None):
    """The rig in a namespace (or the whole scene): its joints, its controls with their keyable unlocked channels and
    limits, the joints each control moves (found by nudging each channel and putting it back), the units and the up
    axis. A rig with no control curves is keyed on its joints, so its joints are its controls."""
    from maya import cmds
    pats = [f"{namespace}:*"] if namespace else []      # no namespace: every node, in any namespace

    def ls(kind):
        return cmds.ls(*pats, type=kind, long=True) or []
    joints = [j for j in ls("joint") if "_ik_grp" not in j]
    short = {j: cmds.ls(j)[0] for j in joints}
    jinfo = []
    for j in joints:
        p = cmds.listRelatives(j, parent=True, fullPath=True)
        jinfo.append({"name": short[j], "parent": short.get(p[0]) if p else None})
    kei = [t for t in ls("transform") if cmds.attributeQuery("kei_role", node=t, exists=True)]
    if kei:
        ctls = kei
    else:
        curves = ls("nurbsCurve")
        ctls = sorted({cmds.listRelatives(c, parent=True, fullPath=True)[0] for c in curves}) or joints
    f = unit_per_m()
    controls = []
    for ctl in ctls:
        keyable = cmds.listAttr(ctl, keyable=True, unlocked=True) or []
        before = _pose_of(cmds, joints)
        moves = set()
        for attr in keyable:
            plug = f"{ctl}.{attr}"
            if cmds.connectionInfo(plug, isDestination=True) or cmds.getAttr(plug, type=True) not in (
                    "double", "doubleLinear", "doubleAngle", "float"):
                continue
            kind = "translate" if attr.startswith("translate") else "rotate"
            step = NUDGE[kind] * (f if kind == "translate" else 1.0)
            v = cmds.getAttr(plug)
            if cmds.attributeQuery(attr, node=ctl, maxExists=True):
                hi = cmds.attributeQuery(attr, node=ctl, maximum=True)[0]
                lo = cmds.attributeQuery(attr, node=ctl, minimum=True)[0] if cmds.attributeQuery(
                    attr, node=ctl, minExists=True) else v - 1.0
                step = min(step, (hi - lo) / 2.0)
                if v + step > hi:
                    step = -step
            elif cmds.attributeQuery(attr, node=ctl, minExists=True) and v - abs(step) < cmds.attributeQuery(
                    attr, node=ctl, minimum=True)[0]:
                step = abs(step)
            cmds.setAttr(plug, v + step)
            try:
                after = _pose_of(cmds, joints)
            finally:
                cmds.setAttr(plug, v)
            for j, a, b in zip(joints, before, after):
                if max(abs(x - y) for x, y in zip(a, b)) > 1e-6:
                    moves.add(short[j])
        role = cmds.getAttr(ctl + ".kei_role") if ctl in kei else ("joint" if ctl in short else "control")
        controls.append({"name": cmds.ls(ctl)[0], "role": role, "keyable": keyable, "limits": _limits(cmds, ctl),
                         "moves": sorted(moves),
                         "rotate_order": km.ORDERS[cmds.getAttr(ctl + ".rotateOrder")]})
    tops = [t for t in ls("transform") if cmds.attributeQuery("kei_character", node=t, exists=True)]
    kei_rigs = [{"node": cmds.ls(t)[0], "namespace": cmds.ls(t)[0].rpartition(":")[0],
                 "character": cmds.getAttr(t + ".kei_character")} for t in tops]
    return {"units": cmds.currentUnit(q=True, linear=True), "up": up_axis(), "unit_per_m": f, "joints": jinfo,
            "controls": controls, "kei_rigs": kei_rigs}


def joint_world_metres(names: list[str]) -> dict:
    """World positions of joints, in metres with y up."""
    from maya import cmds
    f, up = unit_per_m(), up_axis()
    return {n: to_metres(cmds.xform(n, q=True, worldSpace=True, translation=True), f, up) for n in names}
