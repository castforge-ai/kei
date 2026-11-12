"""Read a glTF 2.0 file (.glb, or .gltf with embedded or neighbouring buffers) into a Model (kei.models.model).

glTF's axes are the common frame already (y up, the model facing +z, metres), so only kei.models.model.to_kei
applies. A node's transform is its matrix, or its translation, rotation (a quaternion x, y, z, w) and scale; a
node's world transform is its parent's times its own. A mesh's triangles (mode 4) are read with their indices; other
primitive modes are skipped. A skinned mesh's vertices go through its skin at the file's pose: each vertex is the
weighted sum of joint world times inverse bind matrix times the vertex, so the model reads in the pose it was saved
in, and the joints' heads are their world positions in that pose.

The file is untrusted. A buffer URI is read only as a data: URI or as a plain relative path inside the model's folder:
it is checked as text (decoded, no scheme, no drive, no leading slash or backslash, no '..' part) before any path is
built from it, so a URI can never make Windows reach a network share. Every accessor must fit in its buffer, every
index must name a vertex or a joint that exists, and a node tree with a cycle is refused. Draco-compressed meshes are
refused by name; sparse accessors are read without their sparse values, with a warning. Any other damage becomes a
ModelError naming the file.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import struct
from pathlib import Path
from urllib.parse import unquote

from kei.models.model import (IVORY, Joint, MeshData, Model, ModelError, colour_hex, finite_or_raise, flip, mirrors,
                              texture_path, to_kei)

COMPONENT = {5120: ("b", 1, 127.0), 5121: ("B", 1, 255.0), 5122: ("h", 2, 32767.0), 5123: ("H", 2, 65535.0),
             5125: ("I", 4, None), 5126: ("f", 4, None)}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
DAMAGE = (KeyError, IndexError, TypeError, ValueError, AttributeError, struct.error, RecursionError, MemoryError,
          OverflowError, binascii.Error, UnicodeDecodeError)


def _mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def _apply(m, v):
    return tuple(m[r][0] * v[0] + m[r][1] * v[1] + m[r][2] * v[2] + m[r][3] for r in range(3))


def _node_matrix(n: dict):
    if "matrix" in n:
        m = n["matrix"]                                    # column-major
        return [[float(m[c * 4 + r]) for c in range(4)] for r in range(4)]
    tx, ty, tz = n.get("translation", (0, 0, 0))
    x, y, z, w = n.get("rotation", (0, 0, 0, 1))
    sx, sy, sz = n.get("scale", (1, 1, 1))
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx], [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
            [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz], [0, 0, 0, 1]]


def _split_glb(blob: bytes, path: Path):
    if len(blob) < 20:
        raise ModelError(f"{path}: the GLB file is too short")
    _, _, length = struct.unpack_from("<III", blob, 0)
    pos, doc, binary = 12, None, b""
    while pos + 8 <= min(length, len(blob)):
        clen, ctype = struct.unpack_from("<II", blob, pos)
        chunk = blob[pos + 8:pos + 8 + clen]
        if ctype == 0x4E4F534A:
            doc = json.loads(chunk.decode("utf-8"))
        elif ctype == 0x004E4942:
            binary = chunk
        pos += 8 + clen
    if doc is None:
        raise ModelError(f"{path}: the GLB file has no JSON chunk")
    return doc, binary


def safe_relative(uri: str) -> str | None:
    """The URI as a plain relative path inside the model's folder, or None. Checked as text only: nothing here
    touches the file system."""
    text = unquote(uri).replace("\\", "/")
    if not text or "\x00" in text or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", text) or text.startswith("/"):
        return None                                     # a scheme (file:, http:, C:), an absolute path, a UNC path
    parts = text.split("/")
    if any(p in ("..", "") for p in parts[:-1]) or parts[-1] in ("", "..", "."):
        return None
    return text


def _buffers(doc: dict, binary: bytes, path: Path) -> list[bytes]:
    out = []
    for i, b in enumerate(doc.get("buffers", [])):
        uri = b.get("uri")
        if uri is None:
            out.append(binary)
        elif not isinstance(uri, str):
            raise ModelError(f"{path}: buffer {i} has a URI that is not text")
        elif uri.startswith("data:"):
            if "," not in uri:
                raise ModelError(f"{path}: buffer {i} is a data: URI with no data")
            try:
                out.append(base64.b64decode(uri.split(",", 1)[1], validate=False))
            except (binascii.Error, ValueError) as e:
                raise ModelError(f"{path}: buffer {i} is a data: URI Kei cannot decode ({e})") from e
        else:
            rel = safe_relative(uri)
            if rel is None:
                raise ModelError(f"{path}: buffer {i} must be a file inside the model's folder, not {uri!r}")
            folder = path.parent.resolve()
            target = (folder / rel).resolve()
            if folder not in target.parents:
                raise ModelError(f"{path}: buffer {i} points outside the model's folder: {uri}")
            try:
                out.append(target.read_bytes())
            except OSError as e:
                raise ModelError(f"{path}: cannot read buffer {uri}: {e}") from e
    return out


def _embedded_image(img: dict, views: list, bufs: list, path: Path) -> str | None:
    """An image stored in the file (a buffer view or a data: URI), written to a temporary file for the import's
    conversion (the caller writes each image once and lists it in Model.temp_files). Its path, or None."""
    import tempfile
    if "bufferView" in img:
        v = views[img["bufferView"]]
        data = bufs[v.get("buffer", 0)][v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]
    else:
        data = base64.b64decode(img["uri"].split(",", 1)[1])
    ext = ".png" if data[:4] == b"\x89PNG" else ".jpg"
    fd, name = tempfile.mkstemp(prefix="kei_texture_", suffix=ext)
    with open(fd, "wb") as f:
        f.write(data)
    return name


def read_gltf(blob: bytes, path: Path) -> Model:
    try:
        if blob[:4] == b"glTF":
            doc, binary = _split_glb(blob, path)
        else:
            doc, binary = json.loads(blob.decode("utf-8")), b""
        if not isinstance(doc, dict):
            raise ModelError(f"{path}: the glTF document is not an object")
    except ModelError:
        raise
    except DAMAGE as e:
        raise ModelError(f"{path}: not a readable glTF file ({e})") from e
    if "KHR_draco_mesh_compression" in (doc.get("extensionsRequired") or []) + (doc.get("extensionsUsed") or []):
        raise ModelError(f"{path}: the meshes are Draco-compressed, which Kei does not read; export the model "
                         "without Draco compression")
    try:
        return _scene(doc, _buffers(doc, binary, path), path)
    except ModelError:
        raise
    except DAMAGE as e:
        raise ModelError(f"{path}: the glTF file is damaged or uses something Kei does not read "
                         f"({type(e).__name__}: {e})") from e


def _scene(doc: dict, bufs: list[bytes], path: Path) -> Model:
    views, accessors = doc.get("bufferViews", []), doc.get("accessors", [])
    warnings = []

    def read(ai: int) -> list:
        a = accessors[ai]
        if a.get("componentType") not in COMPONENT or a.get("type") not in WIDTH:
            raise ModelError(f"{path}: accessor {ai} has no known componentType or type")
        fmt, size, norm = COMPONENT[a["componentType"]]
        width, count = WIDTH[a["type"]], int(a["count"])
        if count < 0:
            raise ModelError(f"{path}: accessor {ai} has a negative count")
        if a.get("sparse"):
            warnings.append(f"accessor {ai} is sparse; Kei reads its base values only")
        if "bufferView" not in a:
            if count > 10_000_000:
                raise ModelError(f"{path}: accessor {ai} claims {count} values with no data")
            return [tuple([0.0] * width) for _ in range(count)]
        v = views[a["bufferView"]]
        data = bufs[v.get("buffer", 0)]
        start = int(v.get("byteOffset", 0)) + int(a.get("byteOffset", 0))
        stride = int(v.get("byteStride") or size * width)
        end = start + stride * (count - 1) + size * width if count else start
        if start < 0 or stride <= 0 or end > len(data):
            raise ModelError(f"{path}: accessor {ai} reads past the end of its buffer")
        out = []
        item = struct.Struct("<" + fmt * width)
        for k in range(count):
            vals = item.unpack_from(data, start + k * stride)
            if norm is not None and a.get("normalized"):
                vals = tuple(max(-1.0, x / norm) for x in vals)
            out.append(vals)
        return out

    nodes = doc.get("nodes", [])
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            if not (isinstance(c, int) and 0 <= c < len(nodes)):
                raise ModelError(f"{path}: node {i} names a child {c!r} that does not exist")
            if c in parent:
                raise ModelError(f"{path}: node {c} has two parents")
            parent[c] = i
    for start in parent:
        seen, i = set(), start
        while i in parent:
            if i in seen:
                raise ModelError(f"{path}: the node hierarchy has a cycle (node {i})")
            seen.add(i)
            i = parent[i]
    cache = {}

    def world(i):
        if i not in cache:
            m = _node_matrix(nodes[i])
            cache[i] = _mul(world(parent[i]), m) if i in parent else m
        return cache[i]

    joint_nodes = sorted({j for s in doc.get("skins", []) for j in s.get("joints", [])})
    for j in joint_nodes:
        if not (isinstance(j, int) and 0 <= j < len(nodes)):
            raise ModelError(f"{path}: a skin names a joint node {j!r} that does not exist")
    names = {i: nodes[i].get("name") or f"joint_{i}" for i in joint_nodes}

    def depth(i):
        d = 0
        while i in parent:
            i, d = parent[i], d + 1
        return d
    joints = [Joint(names[i], names.get(parent.get(i)), to_kei(_apply(world(i), (0, 0, 0))))
              for i in sorted(joint_nodes, key=lambda i: (depth(i), i))]
    for j in joints:
        finite_or_raise(j.head, f"{path}: the position of joint {j.name!r}")

    mats = doc.get("materials", [])
    meshes, embedded = [], {}           # embedded: image index -> its temporary file, written once
    joint_set = set(joint_nodes)

    def joint_above(i):
        i = parent.get(i)
        while i is not None and i not in joint_set:
            i = parent.get(i)
        return names[i] if i is not None else None
    for ni, n in enumerate(nodes):
        if "mesh" not in n:
            continue
        mesh = doc["meshes"][n["mesh"]]
        skin = doc["skins"][n["skin"]] if "skin" in n else None
        if skin is not None:
            jw = [world(j) for j in skin["joints"]]
            if "inverseBindMatrices" in skin:
                ibm = [[[m[c * 4 + r] for c in range(4)] for r in range(4)] for m in read(skin["inverseBindMatrices"])]
                if len(ibm) < len(jw):
                    raise ModelError(f"{path}: a skin has fewer inverse bind matrices than joints")
            else:
                ibm = [[[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)] for _ in skin["joints"]]
            joint_m = [_mul(jw[k], ibm[k]) for k in range(len(jw))]
        for prim in mesh.get("primitives", []):
            if prim.get("mode", 4) != 4 or "POSITION" not in prim["attributes"]:
                continue
            pos = read(prim["attributes"]["POSITION"])
            idx = [int(i[0]) for i in read(prim["indices"])] if "indices" in prim else list(range(len(pos)))
            if any(not 0 <= i < len(pos) for i in idx):
                raise ModelError(f"{path}: a triangle index names a vertex that does not exist")
            weights, mirrored = None, False
            if skin is not None and "JOINTS_0" in prim["attributes"] and "WEIGHTS_0" in prim["attributes"]:
                js, ws = read(prim["attributes"]["JOINTS_0"]), read(prim["attributes"]["WEIGHTS_0"])
                if len(js) != len(pos) or len(ws) != len(pos):
                    raise ModelError(f"{path}: the joints or weights do not match the vertices")
                wtype = accessors[prim["attributes"]["WEIGHTS_0"]]["componentType"]
                if wtype != 5126:
                    norm = COMPONENT[wtype][2]
                    ws = [tuple(x / norm for x in w) for w in ws]
                verts, weights = [], []
                for p, j, w in zip(pos, js, ws):
                    total = sum(x for x in w if x > 0)
                    pairs = [(int(jj), ww / total) for jj, ww in zip(j, w) if ww > 0] if total > 0 else []
                    if any(not 0 <= jj < len(joint_m) for jj, _ in pairs):
                        raise ModelError(f"{path}: a vertex names a joint the skin does not have")
                    acc = [0.0, 0.0, 0.0]
                    for jj, ww in pairs:
                        q = _apply(joint_m[jj], p)
                        acc = [acc[k] + q[k] * ww for k in range(3)]
                    verts.append(to_kei(acc if pairs else _apply(world(ni), p)))
                    merged = {}
                    for jj, ww in pairs:
                        nm = names[skin["joints"][jj]]
                        merged[nm] = merged.get(nm, 0.0) + ww
                    weights.append(list(merged.items()))
            else:
                m = world(ni)
                verts = [to_kei(_apply(m, p)) for p in pos]
                mirrored = mirrors(m)             # a mirrored instance: its winding is reversed once more
            finite_or_raise(verts, f"{path}: a vertex position of mesh {n['mesh']}")
            tris = [(idx[k], idx[k + 1], idx[k + 2]) for k in range(0, len(idx) - 2, 3)]
            if not mirrored:
                tris = [flip(t) for t in tris]
            tri_uvs, texture = None, None
            if "TEXCOORD_0" in prim["attributes"]:
                uv = read(prim["attributes"]["TEXCOORD_0"])
                if len(uv) == len(pos):
                    tri_uvs = [tuple((float(uv[i][0]), float(uv[i][1])) for i in t) for t in tris]
                    finite_or_raise(tri_uvs, f"{path}: a texture coordinate of mesh {n['mesh']}")
            if tri_uvs and isinstance(prim.get("material"), int) and 0 <= prim["material"] < len(mats):
                ti = mats[prim["material"]].get("pbrMetallicRoughness", {}).get("baseColorTexture", {}).get("index")
                if isinstance(ti, int) and 0 <= ti < len(doc.get("textures", [])):
                    si = doc["textures"][ti].get("source")
                    images = doc.get("images", [])
                    if isinstance(si, int) and 0 <= si < len(images):
                        img = images[si]
                        if isinstance(img.get("uri"), str) and not img["uri"].startswith("data:"):
                            texture = texture_path(path.parent, img["uri"], warnings)
                        elif "bufferView" in img or (img.get("uri") or "").startswith("data:"):
                            if si not in embedded:
                                embedded[si] = _embedded_image(img, views, bufs, path)
                            texture = embedded[si]
            colour = IVORY
            if isinstance(prim.get("material"), int) and 0 <= prim["material"] < len(mats):
                f = mats[prim["material"]].get("pbrMetallicRoughness", {}).get("baseColorFactor")
                if f:
                    colour = colour_hex(f)
            meshes.append(MeshData(mesh.get("name") or f"mesh_{n['mesh']}", verts, tris, colour, weights,
                                   tri_uvs if texture else None, texture, joint_above(ni)))
    if not meshes:
        raise ModelError(f"{path}: the glTF file holds no triangle mesh")
    return Model(meshes, joints, str(path), warnings, list(embedded.values()))
