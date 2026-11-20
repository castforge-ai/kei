"""Write an export scene (kei.export_scene) as binary glTF 2.0 (.glb), by hand with struct and json.

The file holds the skeleton (the scene's bones: Unreal mannequin names and hierarchy), the bind pose (the rest pose),
one mesh with a primitive per material (body, joint, emission), every vertex skinned to its mesh's bones, each shot
object as its own unskinned mesh under its own node, and one animation per clip: per joint a rotation and a
translation per frame, per object the same. With no character mesh (build_scene mesh=False) the skin stays, unused.

Axes: glTF's own. y is up, the model faces +z, its right is -x, units are metres. Kei's world has x on the
character's right, so every point goes through to_gltf, x -> -x (D = diag(-1, 1, 1)); a joint's glTF rotation is
D R D for the scene's rotation R, which keeps it a proper rotation with y along the bone, and a local translation t
becomes D t. How a tool brings glTF's axes into its own (Unreal: z up, the model facing +y) is that tool's import. The
convention is also written into the file at asset.extras.kei_axes (extras are flat strings for Unreal).
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

from kei.characters import Character
from kei.export_scene import ExportScene, build_scene, mat_quat, quat_matrix

COMPONENTS = {5126: ("f", 4), 5125: ("I", 4), 5123: ("H", 2)}      # float, unsigned int, unsigned short
TYPES = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}
JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963
MATERIAL_ORDER = ("body", "joint", "emission")
ROUGHNESS = {"body": 0.55, "joint": 0.7, "emission": 0.4}
AXES = "glTF axes: y up, the model faces +z, its right is -x (Kei's x on the character's right becomes -x)"


def to_gltf(p) -> tuple[float, float, float]:
    """A Kei world point or direction in glTF axes."""
    return (-p[0], p[1], p[2])


def _linear(hex_colour: str) -> list[float]:
    """An sRGB '#rrggbb' as linear RGB factors, as glTF material factors are."""
    out = []
    for i in (1, 3, 5):
        c = int(hex_colour[i:i + 2], 16) / 255
        out.append(round(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4, 6))
    return out


def _reflect(q) -> list[float]:
    """A scene rotation in glTF axes: D R D as a quaternion."""
    R = quat_matrix(q)
    sign = (-1, 1, 1)
    return list(mat_quat([[sign[r] * R[r][c] * sign[c] for c in range(3)] for r in range(3)]))


def _global(bone):
    """A bone's rest transform in glTF axes: (rotation rows, translation)."""
    X, Y, Z = (to_gltf(v) for v in bone.frame)
    cols = ((-X[0], -X[1], -X[2]), Y, Z)          # D applied on the right: the first column negated
    return [[cols[c][r] for c in range(3)] for r in range(3)], list(to_gltf(bone.head))


class _Bin:
    """The binary chunk being built: buffer views and accessors are appended to the glTF document."""

    def __init__(self, doc: dict):
        self.doc, self.data = doc, bytearray()
        doc["bufferViews"], doc["accessors"] = [], []

    def add(self, fmt: str, comp: int, kind: str, rows, target: int | None = None, bounds: bool = False) -> int:
        n = TYPES[kind]
        while len(self.data) % 4:
            self.data.append(0)
        start = len(self.data)
        for row in rows:
            self.data += struct.pack("<" + fmt * n, *row)
        view = {"buffer": 0, "byteOffset": start, "byteLength": len(self.data) - start}
        if target:
            view["target"] = target
        self.doc["bufferViews"].append(view)
        acc = {"bufferView": len(self.doc["bufferViews"]) - 1, "componentType": comp, "count": len(rows),
               "type": kind}
        if bounds:
            # min and max of the values as stored (float32), so a reader's bounds check agrees exactly
            stored = [struct.unpack("<" + fmt * n, struct.pack("<" + fmt * n, *row)) for row in rows]
            acc["min"] = [min(r[k] for r in stored) for k in range(n)]
            acc["max"] = [max(r[k] for r in stored) for k in range(n)]
        self.doc["accessors"].append(acc)
        return len(self.doc["accessors"]) - 1


def gltf_from_scene(scene: ExportScene) -> tuple[dict, bytes]:
    """The glTF document (a dict) and its binary chunk for an export scene."""
    emission = next(m.emission_strength for m in scene.materials if m.name == "emission")
    doc = {"asset": {"version": "2.0", "generator": "Kei Animator, by Castforge",
                     # flat strings: Unreal's glTF import reads extras as strings and logs an error on an object
                     "extras": {"kei_character": scene.name, "kei_axes": AXES, "kei_units": scene.units,
                                "kei_bind_pose": "the character's rest pose", "kei_emission": f"{emission:g}"}},
           "scene": 0}
    out = _Bin(doc)
    index = {b.name: i for i, b in enumerate(scene.bones)}
    nodes = []
    for b in scene.bones:
        node = {"name": b.name, "translation": list(to_gltf(b.translation)), "rotation": _reflect(b.rotation)}
        kids = [index[c.name] for c in scene.bones if c.parent == b.name]
        if kids:
            node["children"] = kids
        nodes.append(node)
    roots = [index[b.name] for b in scene.bones if b.parent is None]
    top = list(roots)
    if scene.meshes:
        top.append(len(nodes))
        nodes.append({"name": scene.title, "mesh": 0, "skin": 0})
    object_node = {}
    for o in scene.objects:
        object_node[o.name] = len(nodes)
        top.append(len(nodes))
        nodes.append({"name": o.name, "translation": list(to_gltf(o.translation)), "rotation": _reflect(o.rotation)})
    doc["nodes"] = nodes
    doc["scenes"] = [{"name": scene.title, "nodes": top}]
    ibm = []                      # the inverse of each joint's rest transform, column-major
    for b in scene.bones:
        R, T = _global(b)
        Rt = [[R[c][r] for c in range(3)] for r in range(3)]
        t = [-sum(Rt[r][k] * T[k] for k in range(3)) for r in range(3)]
        cols = [[Rt[0][c], Rt[1][c], Rt[2][c], 0.0] for c in range(3)] + [t + [1.0]]
        ibm.append(tuple(v for col in cols for v in col))
    doc["skins"] = [{"name": scene.title, "joints": list(range(len(scene.bones))), "skeleton": roots[0],
                     "inverseBindMatrices": out.add("f", 5126, "MAT4", ibm)}]
    doc["materials"], prims = [], []
    mats = {m.name: m for m in scene.materials}
    for name in MATERIAL_ORDER:
        pos, nrm, joints, weights, idx = [], [], [], [], []
        for m in scene.meshes:
            if m.material != name:
                continue
            base = len(pos)
            pos += [to_gltf(v) for v in m.vertices]
            nrm += [to_gltf(n) for n in m.normals]
            for vw in (m.weights or [[(m.bone, 1.0)]] * len(m.vertices)):
                vw = sorted(vw, key=lambda nw: -nw[1])[:4]
                t = sum(w for _, w in vw)
                joints.append(tuple([index[n] for n, _ in vw] + [0] * (4 - len(vw))))
                weights.append(tuple([w / t for _, w in vw] + [0.0] * (4 - len(vw))))
            idx += [(base + a,) for t in m.triangles for a in (t[0], t[2], t[1])]   # the reflection flips winding
        if not pos:
            continue
        mat = mats[name]
        entry = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": _linear(mat.colour) + [1.0],
                                                        "metallicFactor": 0.0, "roughnessFactor": ROUGHNESS[name]}}
        if mat.emission_strength > 0 or name == "emission":
            entry["emissiveFactor"] = [round(c * mat.emission_strength, 6) for c in _linear(mat.emission)]
        doc["materials"].append(entry)
        prims.append({"attributes": {"POSITION": out.add("f", 5126, "VEC3", pos, ARRAY_BUFFER, bounds=True),
                                     "NORMAL": out.add("f", 5126, "VEC3", nrm, ARRAY_BUFFER),
                                     "JOINTS_0": out.add("H", 5123, "VEC4", joints, ARRAY_BUFFER),
                                     "WEIGHTS_0": out.add("f", 5126, "VEC4", weights, ARRAY_BUFFER)},
                      "indices": out.add("I", 5125, "SCALAR", idx, ELEMENT_ARRAY_BUFFER),
                      "material": len(doc["materials"]) - 1, "mode": 4})
    doc["meshes"] = [{"name": scene.title, "primitives": prims}] if prims else []
    for o in scene.objects:                 # an object: its own unskinned mesh and material, under its own node
        if not o.vertices:
            continue
        mat = mats[o.material]
        doc["materials"].append({"name": o.material, "pbrMetallicRoughness": {
            "baseColorFactor": _linear(mat.colour) + [1.0], "metallicFactor": 0.0, "roughnessFactor": 0.8}})
        prim = {"attributes": {"POSITION": out.add("f", 5126, "VEC3", [to_gltf(v) for v in o.vertices],
                                                   ARRAY_BUFFER, bounds=True),
                               "NORMAL": out.add("f", 5126, "VEC3", [to_gltf(n) for n in o.normals], ARRAY_BUFFER)},
                "indices": out.add("I", 5125, "SCALAR", [(a,) for t in o.triangles for a in (t[0], t[2], t[1])],
                                   ELEMENT_ARRAY_BUFFER),
                "material": len(doc["materials"]) - 1, "mode": 4}
        nodes[object_node[o.name]]["mesh"] = len(doc["meshes"])
        doc["meshes"].append({"name": o.name, "primitives": [prim]})
    if not doc["meshes"]:
        del doc["meshes"]
    if not doc["materials"]:
        del doc["materials"]
    anims = []
    for a in scene.clips():
        times = out.add("f", 5126, "SCALAR", [(k / a.fps,) for k in range(len(a.rotations))], bounds=True)
        samplers, channels = [], []
        for i, b in enumerate(scene.bones):
            rots, prev = [], None
            for row in a.rotations:
                q = _reflect(row[i])
                if prev is not None and sum(x * y for x, y in zip(prev, q)) < 0:
                    q = [-c for c in q]
                rots.append(tuple(q))
                prev = q
            tracks = (("translation", [to_gltf(row[i]) for row in a.translations], "VEC3"),
                      ("rotation", rots, "VEC4"))
            for path, rows, kind in tracks:
                samplers.append({"input": times, "output": out.add("f", 5126, kind, rows), "interpolation": "LINEAR"})
                channels.append({"sampler": len(samplers) - 1, "target": {"node": i, "path": path}})
        for name, rows in a.objects.items():
            rots, prev = [], None
            for _, q in rows:
                q = _reflect(q)
                if prev is not None and sum(x * y for x, y in zip(prev, q)) < 0:
                    q = [-c for c in q]
                rots.append(tuple(q))
                prev = q
            tracks = (("translation", [to_gltf(t) for t, _ in rows], "VEC3"), ("rotation", rots, "VEC4"))
            for path, vals, kind in tracks:
                samplers.append({"input": times, "output": out.add("f", 5126, kind, vals), "interpolation": "LINEAR"})
                channels.append({"sampler": len(samplers) - 1, "target": {"node": object_node[name], "path": path}})
        anims.append({"name": a.name, "samplers": samplers, "channels": channels})
    if anims:
        doc["animations"] = anims
    doc["buffers"] = [{"byteLength": len(out.data)}]
    return doc, bytes(out.data)


def build_gltf(ch: Character, emission: float = 1.0, shot: dict | None = None,
        mode: str = "spline", **scene):
    """The glTF document and binary chunk of a character: build_scene, then gltf_from_scene."""
    return gltf_from_scene(build_scene(ch, emission, shot, mode, **scene))


def pack_glb(doc: dict, binary: bytes) -> bytes:
    """The two chunks of a .glb: the JSON padded with spaces, the binary padded with zeros, each to 4 bytes."""
    text = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    binary = binary + b"\x00" * (-len(binary) % 4)
    length = 12 + 8 + len(text) + 8 + len(binary)
    return (struct.pack("<4sII", b"glTF", 2, length) + struct.pack("<II", len(text), JSON_CHUNK) + text
            + struct.pack("<II", len(binary), BIN_CHUNK) + binary)


def build_glb(ch: Character, emission: float = 1.0, shot: dict | None = None,
        mode: str = "spline", **scene) -> bytes:
    """The .glb bytes of a character, optionally animated by a shot."""
    return pack_glb(*build_gltf(ch, emission, shot, mode, **scene))


def export_glb(ch: Character, path, emission: float = 1.0, shot: dict | None = None,
               mode: str = "spline", **scene) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_glb(ch, emission, shot, mode, **scene))
    return path


def read_glb(blob: bytes) -> tuple[dict, bytes]:
    """The JSON document and binary chunk of a .glb, checked: header, chunk types, lengths. Raises ValueError."""
    if len(blob) < 20:
        raise ValueError("too short for a .glb")
    magic, version, length = struct.unpack_from("<4sII", blob, 0)
    if magic != b"glTF" or version != 2:
        raise ValueError("not a binary glTF 2.0 file")
    if length != len(blob):
        raise ValueError(f"the header says {length} bytes, the file has {len(blob)}")
    jlen, jtype = struct.unpack_from("<II", blob, 12)
    if jtype != JSON_CHUNK or 20 + jlen > len(blob):
        raise ValueError("the first chunk is not a whole JSON chunk")
    doc = json.loads(blob[20:20 + jlen].decode("utf-8"))
    binary = b""
    if 20 + jlen < len(blob):
        blen, btype = struct.unpack_from("<II", blob, 20 + jlen)
        if btype != BIN_CHUNK or 28 + jlen + blen != len(blob):
            raise ValueError("the second chunk is not a whole BIN chunk")
        binary = blob[28 + jlen:]
    return doc, binary
