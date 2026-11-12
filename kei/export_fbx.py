"""Write an export scene (kei.export_scene) as binary FBX 7.4, the scene layer over kei.fbx.

The file holds what the glTF export holds: the skeleton as LimbNode models with their rest transforms (the Unreal
mannequin names and hierarchy), one mesh (one Geometry) with a material index per triangle and one UV set (a planar
front projection, so importers need not invent one), a Skin deformer with one
Cluster per bone (every vertex bound rigidly to its shape's bone, weight 1), a BindPose of the rest pose, the three
materials (diffuse colour; emissive colour and factor only when the glow is on), and the scene's animation when it
has one: one AnimationStack with one layer, per bone a rotation curve for X, Y and Z (Euler degrees, FBX's default
XYZ order: rotate about X, then Y, then Z) and a translation curve wherever the bone's local translation moves; a
property that carries a curve is flagged 'A+' (animated), as FBX writers mark it.

Axes and units: right-handed, y up, the model faces +z, its right is -x (the same mirror of Kei's world as the glTF
export: x -> -x, a rotation R -> D R D, D = diag(-1, 1, 1)), in centimetres: metres x 100, and GlobalSettings says
so: UpAxis 1 (Y), FrontAxis 2 (Z), CoordAxis 0 (X), every sign +1, UnitScaleFactor 1 (one unit is 1 cm). How a tool
brings these axes into its own (Unreal: z up) is that tool's import.

Colours are written linear, as the glTF factors are. Times are FBX's KTime: 46,186,158,000 ticks a second.
"""
from __future__ import annotations

import math
import struct
from pathlib import Path

from kei.characters import Character
from kei.export_gltf import MATERIAL_ORDER, _global, _linear, _reflect, to_gltf
from kei.export_scene import ExportScene, build_scene, quat_matrix
from kei.fbx import Node, P, fbx_file

CM = 100.0
KTIME = 46186158000
CREATOR = "Kei Animator, by Castforge"
# FileId and CreationTime are fixed values that belong with kei.fbx.FOOTER_ID, so the file is the same every time.
FILE_ID = bytes.fromhex("28b32aebb624ccc2bfc8b02aa92bfcf1")
CREATION_TIME = "1970-01-01 10:00:00:000"
TIME_MODES = {120: 1, 100: 2, 60: 3, 50: 4, 48: 5, 30: 6, 25: 10, 24: 11, 1000: 12, 96: 15, 72: 16}
TIME_MODE_CUSTOM = 14
KEY_LINEAR = 0x00000004                      # a key's interpolation flag: linear
KEY_WEIGHTS = 0x0D050D05                     # the default tangent weights (two 1/3s), stored as a float's bits


def _float_bits(n: int) -> float:
    return struct.unpack("<f", struct.pack("<I", n))[0]


# ---- rotations ------------------------------------------------------------------------------------------------------

def _rx(a):
    c, s = math.cos(a), math.sin(a)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def _ry(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def _rz(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _mul(p, q):
    return [[sum(p[i][k] * q[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _t(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def _wrap(v: float, near: float) -> float:
    """v plus the whole turns that bring it nearest `near`."""
    return v + 360.0 * round((near - v) / 360.0)


def euler_xyz(m, near=None) -> tuple[float, float, float]:
    """Euler angles (degrees) of a rotation matrix (rows) in FBX's XYZ order, m = Rz(c) Ry(b) Rx(a).

    With `near` (the previous frame's angles) it returns, of the two equivalent triples and their whole turns, the one
    closest to `near`, so a curve does not jump a turn between frames. At gimbal lock (b = +-90) Z keeps near's value
    (or 0) and X takes the rest."""
    cb = math.hypot(m[0][0], m[1][0])
    b = math.atan2(-m[2][0], cb)
    if cb > 1e-9:
        c = math.atan2(m[1][0], m[0][0])
    else:
        c = math.radians(near[2]) if near is not None else 0.0
    n = _mul(_t(_ry(b)), _mul(_t(_rz(c)), m))          # = Rx(a): fit X to the whole matrix, robust near the lock
    a = math.atan2(n[2][1], n[1][1])
    first = (math.degrees(a), math.degrees(b), math.degrees(c))
    if near is None:
        return first
    other = (first[0] + 180.0, 180.0 - first[1], first[2] + 180.0)
    best = None
    for cand in (first, other):
        e = tuple(_wrap(v, near[k]) for k, v in enumerate(cand))
        d = sum(abs(e[k] - near[k]) for k in range(3))
        if best is None or d < best[0]:
            best = (d, e)
    return best[1]


# ---- the scene in FBX axes ------------------------------------------------------------------------------------------

def _local(t, q, near=None):
    """A scene local transform in FBX axes: (translation in cm, Euler degrees)."""
    return tuple(CM * v for v in to_gltf(t)), euler_xyz(quat_matrix(_reflect(q)), near)


def _matrix(R, T) -> list[float]:
    """A 4x4 transform as FBX stores it: 16 doubles, column by column, the translation last."""
    return [R[0][0], R[1][0], R[2][0], 0.0, R[0][1], R[1][1], R[2][1], 0.0,
            R[0][2], R[1][2], R[2][2], 0.0, T[0], T[1], T[2], 1.0]


def _bone_global(bone):
    R, T = _global(bone)
    return R, [CM * v for v in T]


def _inverse(R, T):
    Rt = _t(R)
    return Rt, [-sum(Rt[r][k] * T[k] for k in range(3)) for r in range(3)]


def _p(name, kind, label, flags, *values):
    return Node("P", [name, kind, label, flags, *values])


def _p70(*props):
    return Node("Properties70", [], list(props))


def _template(kind: str) -> list:
    """The property templates a reader needs: a curve node's channels d|X, d|Y, d|Z are members of the compound d,
    which only its template declares (without it Unreal's FBX reader found no channels and ignored every curve), and
    a layer's full weight."""
    if kind == "AnimationCurveNode":
        return [Node("PropertyTemplate", ["FbxAnimCurveNode"], [_p70(_p("d", "Compound", "", ""))])]
    if kind == "AnimationLayer":
        return [Node("PropertyTemplate", ["FbxAnimLayer"], [_p70(
            _p("Weight", "Number", "", "A", 100.0), _p("Mute", "bool", "", "", 0), _p("Solo", "bool", "", "", 0),
            _p("Lock", "bool", "", "", 0), _p("BlendMode", "enum", "", "", 0),
            _p("RotationAccumulationMode", "enum", "", "", 0), _p("ScaleAccumulationMode", "enum", "", "", 0))])]
    return []


def _ktime(k: int, fps: float) -> int:
    return round(k * KTIME / fps)


class _Ids:
    def __init__(self):
        self.n = 1_000_000

    def __call__(self) -> int:
        self.n += 1
        return self.n


def fbx_from_scene(scene: ExportScene) -> bytes:
    """The binary FBX file of an export scene."""
    new = _Ids()
    objects, links = [], []

    def oo(child, parent):
        links.append(Node("C", ["OO", P("L", child), P("L", parent)]))

    def op(child, parent, prop):
        links.append(Node("C", ["OP", P("L", child), P("L", parent), prop]))

    # the skeleton; 'A+' marks a property that carries a curve (animatable, animated), 'A' one that does not
    a = scene.animation
    moves = [a is not None and any(math.dist(row[i], b.translation) > 1e-9 for row in a.translations)
             for i, b in enumerate(scene.bones)]
    bone_id, rest = {}, {}
    for i, b in enumerate(scene.bones):
        mid, aid = new(), new()
        bone_id[b.name] = mid
        t, e = _local(b.translation, b.rotation)
        rest[b.name] = (t, e)
        objects.append(Node("NodeAttribute", [P("L", aid), b.name + "\x00\x01NodeAttribute", "LimbNode"],
                            [_p70(_p("Size", "double", "Number", "", 1.0)), Node("TypeFlags", ["Skeleton"])]))
        objects.append(Node("Model", [P("L", mid), b.name + "\x00\x01Model", "LimbNode"], [
            Node("Version", [232]),
            _p70(_p("InheritType", "enum", "", "", 1),
                 _p("DefaultAttributeIndex", "int", "Integer", "", 0),
                 _p("Lcl Translation", "Lcl Translation", "", "A+" if moves[i] else "A", *t),
                 _p("Lcl Rotation", "Lcl Rotation", "", "A+" if a is not None else "A", *e),
                 _p("Lcl Scaling", "Lcl Scaling", "", "A", 1.0, 1.0, 1.0)),
            Node("Shading", [True]), Node("Culling", ["CullingOff"])]))
        oo(aid, mid)
    for b in scene.bones:
        oo(bone_id[b.name], 0 if b.parent is None else bone_id[b.parent])

    # the mesh: one geometry, the materials in MATERIAL_ORDER, a material index per triangle
    mats = {m.name: m for m in scene.materials}
    used = [name for name in MATERIAL_ORDER if any(m.material == name for m in scene.meshes)]
    verts, normals, poly, mat_index, owner = [], [], [], [], []
    for slot, name in enumerate(used):
        for m in scene.meshes:
            if m.material != name:
                continue
            base = len(owner)
            for v in m.vertices:
                verts += [CM * c for c in to_gltf(v)]
            for nrm in m.normals:
                normals += list(to_gltf(nrm))
            owner += m.weights or [[(m.bone, 1.0)]] * len(m.vertices)
            for tri in m.triangles:                          # the mirror flips the winding back to outward
                poly += [base + tri[0], base + tri[2], -(base + tri[1]) - 1]
                mat_index.append(slot)
    # one UV set, a planar front projection (u from x, v from height over 2 m), so importers need not invent one
    uvs = [min(1.0, max(0.0, c)) for k in range(0, len(verts), 3)
           for c in (0.5 + verts[k] / 200.0, verts[k + 1] / 200.0)]
    uv_index = [i if i >= 0 else -i - 1 for i in poly]
    mesh_id, geo_id, skin_id = new(), new(), new()
    objects.append(Node("Geometry", [P("L", geo_id), scene.title + "\x00\x01Geometry", "Mesh"], [
        _p70(),
        Node("GeometryVersion", [124]),
        Node("Vertices", [P("d", verts)]),
        Node("PolygonVertexIndex", [P("i", poly)]),
        Node("LayerElementNormal", [0], [
            Node("Version", [101]), Node("Name", [""]), Node("MappingInformationType", ["ByVertice"]),
            Node("ReferenceInformationType", ["Direct"]), Node("Normals", [P("d", normals)])]),
        Node("LayerElementSmoothing", [0], [
            Node("Version", [102]), Node("Name", [""]), Node("MappingInformationType", ["ByPolygon"]),
            Node("ReferenceInformationType", ["Direct"]), Node("Smoothing", [P("i", [1] * len(mat_index))])]),
        Node("LayerElementUV", [0], [
            Node("Version", [101]), Node("Name", ["UVMap"]), Node("MappingInformationType", ["ByPolygonVertex"]),
            Node("ReferenceInformationType", ["IndexToDirect"]), Node("UV", [P("d", uvs)]),
            Node("UVIndex", [P("i", uv_index)])]),
        Node("LayerElementMaterial", [0], [
            Node("Version", [101]), Node("Name", [""]), Node("MappingInformationType", ["ByPolygon"]),
            Node("ReferenceInformationType", ["IndexToDirect"]), Node("Materials", [P("i", mat_index)])]),
        Node("Layer", [0], [Node("Version", [100])] + [
            Node("LayerElement", [], [Node("Type", [kind]), Node("TypedIndex", [0])])
            for kind in ("LayerElementNormal", "LayerElementSmoothing", "LayerElementUV", "LayerElementMaterial")])]))
    objects.append(Node("Model", [P("L", mesh_id), scene.title + "\x00\x01Model", "Mesh"], [
        Node("Version", [232]),
        _p70(_p("InheritType", "enum", "", "", 1), _p("DefaultAttributeIndex", "int", "Integer", "", 0),
             _p("Lcl Translation", "Lcl Translation", "", "A", 0.0, 0.0, 0.0),
             _p("Lcl Rotation", "Lcl Rotation", "", "A", 0.0, 0.0, 0.0),
             _p("Lcl Scaling", "Lcl Scaling", "", "A", 1.0, 1.0, 1.0)),
        Node("Shading", [True]), Node("Culling", ["CullingOff"])]))
    oo(mesh_id, 0)
    oo(geo_id, mesh_id)
    for name in used:
        mat, mid = mats[name], new()
        props = [_p("ShadingModel", "KString", "", "", "Lambert"),
                 _p("DiffuseColor", "Color", "", "A", *_linear(mat.colour)),
                 _p("DiffuseFactor", "Number", "", "A", 1.0)]
        if mat.emission_strength > 0:
            props += [_p("EmissiveColor", "Color", "", "A", *_linear(mat.emission)),
                      _p("EmissiveFactor", "Number", "", "A", float(mat.emission_strength))]
        objects.append(Node("Material", [P("L", mid), name + "\x00\x01Material", ""], [
            Node("Version", [102]), Node("ShadingModel", ["lambert"]), Node("MultiLayer", [0]), _p70(*props)]))
        oo(mid, mesh_id)

    # the skin: a cluster per bone, the bind pose
    objects.append(Node("Deformer", [P("L", skin_id), scene.title + "\x00\x01Deformer", "Skin"], [
        Node("Version", [101]), Node("Link_DeformAcuracy", [50.0]), Node("SkinningType", ["Linear"])]))
    oo(skin_id, geo_id)
    pose_nodes = [Node("PoseNode", [], [Node("Node", [P("L", mesh_id)]),
                                        Node("Matrix", [P("d", _matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                                                                       [0, 0, 0]))])])]
    for b in scene.bones:
        cid = new()
        R, T = _bone_global(b)
        bound = [(i, w) for i, o in enumerate(owner) for n, w in o if n == b.name]
        objects.append(Node("Deformer", [P("L", cid), b.name + "\x00\x01SubDeformer", "Cluster"], [
            Node("Version", [100]), Node("UserData", ["", ""]),
            Node("Indexes", [P("i", [i for i, _ in bound])]), Node("Weights", [P("d", [w for _, w in bound])]),
            Node("Transform", [P("d", _matrix(*_inverse(R, T)))]),
            Node("TransformLink", [P("d", _matrix(R, T))])]))
        oo(cid, skin_id)
        oo(bone_id[b.name], cid)
        pose_nodes.append(Node("PoseNode", [], [Node("Node", [P("L", bone_id[b.name])]),
                                                Node("Matrix", [P("d", _matrix(R, T))])]))
    objects.append(Node("Pose", [P("L", new()), scene.title + "\x00\x01Pose", "BindPose"], [
        Node("Type", ["BindPose"]), Node("Version", [100]), Node("NbPoseNodes", [len(pose_nodes)])] + pose_nodes))

    # the animation
    stop = 0
    if a is not None:
        n = len(a.rotations)
        stop = _ktime(n - 1, a.fps)
        times = [_ktime(k, a.fps) for k in range(n)]
        stack_id, layer_id = new(), new()
        span = [_p(k, "KTime", "Time", "", P("L", v)) for k, v in
                (("LocalStart", 0), ("LocalStop", stop), ("ReferenceStart", 0), ("ReferenceStop", stop))]
        objects.append(Node("AnimationStack", [P("L", stack_id), "shot\x00\x01AnimStack", ""], [_p70(*span)]))
        objects.append(Node("AnimationLayer", [P("L", layer_id), "BaseLayer\x00\x01AnimLayer", ""], listed=True))
        oo(layer_id, stack_id)

        def track(bone, prop, label, rows):
            cn = new()
            objects.append(Node("AnimationCurveNode", [P("L", cn), label + "\x00\x01AnimCurveNode", ""], [
                _p70(*(_p("d|" + ax, "Number", "", "A", float(rows[0][k])) for k, ax in enumerate("XYZ")))]))
            oo(cn, layer_id)
            op(cn, bone_id[bone], prop)
            for k, ax in enumerate("XYZ"):
                cid = new()
                values = [float(r[k]) for r in rows]
                objects.append(Node("AnimationCurve", [P("L", cid), "\x00\x01AnimCurve", ""], [
                    Node("Default", [values[0]]), Node("KeyVer", [4009]),
                    Node("KeyTime", [P("l", times)]), Node("KeyValueFloat", [P("f", values)]),
                    Node("KeyAttrFlags", [P("i", [KEY_LINEAR])]),
                    Node("KeyAttrDataFloat", [P("f", [0.0, 0.0, _float_bits(KEY_WEIGHTS), 0.0])]),
                    Node("KeyAttrRefCount", [P("i", [n])])]))
                op(cid, cn, "d|" + ax)

        for i, b in enumerate(scene.bones):
            eulers, prev = [], rest[b.name][1]
            for row in a.rotations:
                prev = euler_xyz(quat_matrix(_reflect(row[i])), prev)
                eulers.append(prev)
            track(b.name, "Lcl Rotation", "R", eulers)
            if moves[i]:
                track(b.name, "Lcl Translation", "T", [tuple(CM * v for v in to_gltf(row[i])) for row in a.translations])

    fps = a.fps if a is not None else 24.0
    mode = TIME_MODES.get(int(fps), TIME_MODE_CUSTOM) if float(fps).is_integer() else TIME_MODE_CUSTOM
    settings = Node("GlobalSettings", [], [Node("Version", [1000]), _p70(
        _p("UpAxis", "int", "Integer", "", 1), _p("UpAxisSign", "int", "Integer", "", 1),
        _p("FrontAxis", "int", "Integer", "", 2), _p("FrontAxisSign", "int", "Integer", "", 1),
        _p("CoordAxis", "int", "Integer", "", 0), _p("CoordAxisSign", "int", "Integer", "", 1),
        _p("OriginalUpAxis", "int", "Integer", "", 1), _p("OriginalUpAxisSign", "int", "Integer", "", 1),
        _p("UnitScaleFactor", "double", "Number", "", 1.0), _p("OriginalUnitScaleFactor", "double", "Number", "", 1.0),
        _p("AmbientColor", "ColorRGB", "Color", "", 0.0, 0.0, 0.0),
        _p("DefaultCamera", "KString", "", "", "Producer Perspective"),
        _p("TimeMode", "enum", "", "", mode), _p("TimeProtocol", "enum", "", "", 2),
        _p("SnapOnFrameMode", "enum", "", "", 0),
        _p("TimeSpanStart", "KTime", "Time", "", P("L", 0)), _p("TimeSpanStop", "KTime", "Time", "", P("L", stop)),
        _p("CustomFrameRate", "double", "Number", "", float(fps)))])

    counts = {}
    for o in objects:
        counts[o.name] = counts.get(o.name, 0) + 1
    definitions = Node("Definitions", [], [Node("Version", [100]), Node("Count", [sum(counts.values()) + 1]),
                                           Node("ObjectType", ["GlobalSettings"], [Node("Count", [1])])]
                       + [Node("ObjectType", [k], [Node("Count", [v])] + _template(k)) for k, v in counts.items()])
    header = Node("FBXHeaderExtension", [], [
        Node("FBXHeaderVersion", [1003]), Node("FBXVersion", [7400]), Node("EncryptionType", [0]),
        Node("CreationTimeStamp", [], [Node("Version", [1000]), Node("Year", [1970]), Node("Month", [1]),
                                       Node("Day", [1]), Node("Hour", [10]), Node("Minute", [0]),
                                       Node("Second", [0]), Node("Millisecond", [0])]),
        Node("Creator", [CREATOR]),
        Node("OtherFlags", [], [Node("TCDefinition", [127])])])
    take = "shot" if a is not None else ""
    documents = Node("Documents", [], [Node("Count", [1]), Node("Document", [P("L", new()), "Scene", "Scene"], [
        _p70(_p("SourceObject", "object", "", ""), _p("ActiveAnimStackName", "KString", "", "", take)),
        Node("RootNode", [P("L", 0)])])])
    takes = Node("Takes", [], [Node("Current", [take])])
    if a is not None:
        takes.children.append(Node("Take", ["shot"], [Node("FileName", ["shot.tak"]),
                                                       Node("LocalTime", [P("L", 0), P("L", stop)]),
                                                       Node("ReferenceTime", [P("L", 0), P("L", stop)])]))
    return fbx_file([header, Node("FileId", [FILE_ID]), Node("CreationTime", [CREATION_TIME]),
                     Node("Creator", [CREATOR]), settings, documents, Node("References", []), definitions,
                     Node("Objects", [], objects), Node("Connections", [], links), takes])


def build_fbx(ch: Character, emission: float = 1.0, shot: dict | None = None, mode: str = "spline") -> bytes:
    """The .fbx bytes of a character, optionally animated by a shot: build_scene, then fbx_from_scene."""
    return fbx_from_scene(build_scene(ch, emission, shot, mode))


def export_fbx(ch: Character, path, emission: float = 1.0, shot: dict | None = None, mode: str = "spline") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_fbx(ch, emission, shot, mode))
    return path
