"""Read a binary FBX 7.x file into a Model (kei.models.model), with the standard library only.

The node layer reads the publicly documented binary layout (the same facts kei.fbx writes from): 32-bit records
before version 7500, 64-bit records from 7500, scalar, string, raw and array properties, zlib arrays.

The scene layer reads what an import needs:
  GlobalSettings  UpAxis, FrontAxis, CoordAxis and their signs, UnitScaleFactor (centimetres per file unit)
  Model           Lcl Translation, Lcl Rotation (degrees, XYZ order: X first), Lcl Scaling, PreRotation,
                  PostRotation and the Geometric transform (which moves the geometry only); a model's world
                  transform is its parent's times its own
  Geometry        Vertices and PolygonVertexIndex (a negative index closes a polygon); polygons are fanned
  Material        DiffuseColor (linear RGB), and the texture connected to its base colour (an OP connection on
                  DiffuseColor, Maya|baseColor or the like; a normal, bump or roughness map is not the colour)
  Deformer        a Skin and its Clusters: Indexes, Weights and TransformLink (the joint's world at the bind)
  LimbNode, Null  the joints: a model that a Cluster links to, or any LimbNode model
Rotation and scaling pivots and offsets are not read: exporters of game models leave them at zero.

The axes: the file's up, front and right (coord) axes become y, z and x of the common frame (glTF axes); the unit
becomes metres; then kei.models.model.to_kei.
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

from kei.models.model import (IVORY, Joint, MeshData, Model, ModelError, colour_hex, finite_or_raise, flip, mirrors,
                              texture_path, to_kei)

SCALARS = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}
ARRAYS = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "?"}


class FbxNode:
    __slots__ = ("name", "props", "children")

    def __init__(self, name, props, children):
        self.name, self.props, self.children = name, props, children

    def find(self, name):
        return next((c for c in self.children if c.name == name), None)

    def all(self, name):
        return [c for c in self.children if c.name == name]


MAX_ARRAY = 512 * 1024 * 1024        # bytes: an array larger than this is refused (a model is far smaller)
MAX_DEPTH = 64                        # nested records: deeper than this is refused
ITEM = {"f": 4, "d": 8, "l": 8, "i": 4, "b": 1}


def _prop(blob: bytes, pos: int):
    code = chr(blob[pos])
    pos += 1
    if code in SCALARS:
        fmt = SCALARS[code]
        return struct.unpack_from(fmt, blob, pos)[0], pos + struct.calcsize(fmt)
    if code in ARRAYS:
        n, enc, clen = struct.unpack_from("<III", blob, pos)
        pos += 12
        expected = n * ITEM[code]
        if expected > MAX_ARRAY or pos + clen > len(blob):
            raise ValueError(f"an array of {n} {code} values is larger than Kei reads, or runs past the file")
        raw = blob[pos:pos + clen]
        if enc == 1:
            d = zlib.decompressobj()
            raw = d.decompress(raw, expected + 1)        # never inflate past what the count says
        elif enc != 0:
            raise ValueError(f"array encoding {enc}")
        if len(raw) != expected:
            raise ValueError(f"an array of {n} {code} has {len(raw)} bytes")
        return list(struct.unpack(f"<{n}{ARRAYS[code]}", raw)), pos + clen
    if code in "SR":
        n = struct.unpack_from("<I", blob, pos)[0]
        if pos + 4 + n > len(blob):
            raise ValueError("a string runs past the end of the file")
        data = blob[pos + 4:pos + 4 + n]
        return (data.decode("utf-8", "replace") if code == "S" else bytes(data)), pos + 4 + n
    raise ValueError(f"unknown property type {code!r} at byte {pos - 1}")


def _node(blob: bytes, pos: int, wide: bool, depth: int = 0):
    if depth > MAX_DEPTH:
        raise ValueError("records nested deeper than Kei reads")
    head, fmt = (25, "<QQQ") if wide else (13, "<III")
    if pos + head > len(blob):
        raise ValueError("a record runs past the end of the file")
    end, nprops, _ = struct.unpack_from(fmt, blob, pos)
    if end == 0:
        return None, pos + head
    nlen = blob[pos + head - 1]
    p = pos + head + nlen
    if not p <= end <= len(blob):
        raise ValueError(f"a record at byte {pos} ends at {end}, outside the file or before its own name")
    name = blob[pos + head:p].decode("ascii", "replace")
    props = []
    for _ in range(nprops):
        v, p = _prop(blob, p)
        props.append(v)
    if p > end:
        raise ValueError(f"the record {name!r} at byte {pos} has properties past its end")
    children = []
    while p < end:
        child, q = _node(blob, p, wide, depth + 1)
        if q <= p:
            raise ValueError(f"a record at byte {p} does not advance")
        p = q
        if child is None:
            break
        children.append(child)
    return FbxNode(name, props, children), end


def read_nodes(blob: bytes) -> list[FbxNode]:
    """The top-level nodes of a binary FBX file. Raises ValueError (or struct.error, zlib.error) on damage."""
    if blob[:20] != b"Kaydara FBX Binary  ":
        raise ValueError("not a binary FBX file")
    version = struct.unpack_from("<I", blob, 23)[0]
    pos, nodes, wide = 27, [], version >= 7500
    while pos < len(blob):
        node, q = _node(blob, pos, wide)
        if q <= pos:
            raise ValueError(f"a record at byte {pos} does not advance")
        pos = q
        if node is None:
            break
        nodes.append(node)
    return nodes


# ---------------- matrices: 4x4 as rows ----------------
def _mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def _apply(m, v):
    return tuple(m[r][0] * v[0] + m[r][1] * v[1] + m[r][2] * v[2] + m[r][3] for r in range(3))


def _ident():
    return [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]


def _translate(t):
    m = _ident()
    m[0][3], m[1][3], m[2][3] = t
    return m


def _scale(s):
    m = _ident()
    m[0][0], m[1][1], m[2][2] = s
    return m


def _euler(deg):
    """Rotation by deg[0] about X, then deg[1] about Y, then deg[2] about Z (FBX's default order): Rz Ry Rx."""
    x, y, z = (math.radians(d) for d in deg)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    rx = [[1, 0, 0, 0], [0, cx, -sx, 0], [0, sx, cx, 0], [0, 0, 0, 1]]
    ry = [[cy, 0, sy, 0], [0, 1, 0, 0], [-sy, 0, cy, 0], [0, 0, 0, 1]]
    rz = [[cz, -sz, 0, 0], [sz, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    return _mul(rz, _mul(ry, rx))


def _transpose3(m):
    out = _ident()
    for r in range(3):
        for c in range(3):
            out[r][c] = m[c][r]
    return out


def _props70(node) -> dict:
    out = {}
    p70 = node.find("Properties70") if node is not None else None
    for p in (p70.children if p70 else []):
        if p.props:
            out[p.props[0]] = p.props[4:]
    return out


def _vec(props, key, default):
    v = props.get(key)
    return tuple(float(x) for x in v[:3]) if v and len(v) >= 3 else default


def _local(props) -> list:
    t = _vec(props, "Lcl Translation", (0.0, 0.0, 0.0))
    r = _vec(props, "Lcl Rotation", (0.0, 0.0, 0.0))
    s = _vec(props, "Lcl Scaling", (1.0, 1.0, 1.0))
    pre = _vec(props, "PreRotation", (0.0, 0.0, 0.0))
    post = _vec(props, "PostRotation", (0.0, 0.0, 0.0))
    m = _mul(_translate(t), _mul(_euler(pre), _mul(_euler(r), _mul(_transpose3(_euler(post)), _scale(s)))))
    return m


def _geometric(props) -> list:
    t = _vec(props, "GeometricTranslation", (0.0, 0.0, 0.0))
    r = _vec(props, "GeometricRotation", (0.0, 0.0, 0.0))
    s = _vec(props, "GeometricScaling", (1.0, 1.0, 1.0))
    return _mul(_translate(t), _mul(_euler(r), _scale(s)))


def _name(node) -> str:
    raw = node.props[1] if len(node.props) > 1 and isinstance(node.props[1], str) else ""
    return raw.split("\x00\x01")[0].split("::")[-1]


def _int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError, OverflowError):
        return default


def _axes(gs: dict, warnings: list):
    """The common frame's x, y, z as the file's axes (unit vectors), and metres per file unit."""
    def axis(key, default):
        i = _int((gs.get(key) or [default])[0], default)
        sign = _int((gs.get(key + "Sign") or [1])[0], 1) or 1
        v = [0.0, 0.0, 0.0]
        v[i if 0 <= i <= 2 else default] = float(1 if sign > 0 else -1)
        return v
    up, front, right = axis("UpAxis", 1), axis("FrontAxis", 2), axis("CoordAxis", 0)
    if len({tuple(map(abs, up)), tuple(map(abs, front)), tuple(map(abs, right))}) < 3:
        up, front, right = [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]
    try:
        unit = float((gs.get("UnitScaleFactor") or [1.0])[0])
    except (TypeError, ValueError):
        unit = float("nan")
    if not (math.isfinite(unit) and unit > 0):
        warnings.append(f"UnitScaleFactor {gs.get('UnitScaleFactor')} is not a size; read as centimetres")
        unit = 1.0
    return right, up, front, unit / 100.0


DAMAGE = (KeyError, IndexError, TypeError, ValueError, AttributeError, struct.error, zlib.error, RecursionError,
          MemoryError, OverflowError)


def _uv_layer(geo, nverts: int):
    """A function (corner number, vertex index) -> (u, v from the image's top) for the geometry's first UV layer,
    or None. Mapping ByPolygonVertex or ByControlPoint (ByVertice), reference Direct or IndexToDirect."""
    layer = geo.find("LayerElementUV")
    if layer is None or layer.find("UV") is None:
        return None
    mapping = (layer.find("MappingInformationType").props[0] if layer.find("MappingInformationType") else
               "ByPolygonVertex")
    ref = (layer.find("ReferenceInformationType").props[0] if layer.find("ReferenceInformationType") else "Direct")
    uv = layer.find("UV").props[0]
    index = layer.find("UVIndex").props[0] if layer.find("UVIndex") is not None else None
    by_corner = mapping == "ByPolygonVertex"
    if mapping not in ("ByPolygonVertex", "ByControlPoint", "ByVertice", "ByVertex"):
        return None

    def get(corner, vertex):
        k = corner if by_corner else vertex
        if ref == "IndexToDirect":
            if index is None or not 0 <= k < len(index):
                return None
            k = index[k]
        if not 0 <= 2 * k + 1 < len(uv):
            return None
        return (float(uv[2 * k]), 1.0 - float(uv[2 * k + 1]))      # FBX's v runs up; Kei's from the top
    return get


BASE_COLOUR = ("diffusecolor", "diffuse", "basecolor", "base_color", "base_color_map", "tex_color_map",
               "basecolormap", "albedo")


def _base_colour(prop: str) -> bool:
    """Whether a texture connected to a material on this property feeds its base colour (DiffuseColor,
    Maya|baseColor, Maya|TEX_color_map, 3dsMax|Parameters|base_color_map), not a normal, bump or roughness map."""
    return prop.split("|")[-1].strip().lower() in BASE_COLOUR


def read_fbx_model(blob: bytes, path: Path) -> Model:
    try:
        nodes = read_nodes(blob)
    except DAMAGE as e:
        raise ModelError(f"{path}: not a readable binary FBX file ({e})") from e
    try:
        return _scene(nodes, path)
    except ModelError:
        raise
    except DAMAGE as e:
        raise ModelError(f"{path}: the FBX file is damaged or uses something Kei does not read "
                         f"({type(e).__name__}: {e})") from e


def _scene(nodes, path: Path) -> Model:
    warnings = []
    top = {n.name: n for n in nodes}
    objects = top.get("Objects")
    if objects is None:
        raise ModelError(f"{path}: the FBX file has no Objects")
    gs = {}
    if top.get("GlobalSettings") is not None:
        gs = {k: v for k, v in _props70(top["GlobalSettings"]).items()}
    right, up, front, metres = _axes(gs, warnings)
    det = (right[0] * (up[1] * front[2] - up[2] * front[1]) - right[1] * (up[0] * front[2] - up[2] * front[0])
           + right[2] * (up[0] * front[1] - up[1] * front[0]))
    left_handed = det < 0          # the file's axes are a mirror of the common frame: its triangles wind the other way

    def to_common(p):
        return (sum(p[i] * right[i] for i in range(3)) * metres, sum(p[i] * up[i] for i in range(3)) * metres,
                sum(p[i] * front[i] for i in range(3)) * metres)

    by_id = {}
    for o in objects.children:
        if o.props and isinstance(o.props[0], int):
            by_id[o.props[0]] = o
    parent_of, children_of, channel = {}, {}, {}
    for c in (top["Connections"].children if top.get("Connections") else []):
        if len(c.props) >= 3 and c.props[0] in ("OO", "OP"):
            child, parent = c.props[1], c.props[2]
            if c.props[0] == "OO" or (c.props[0] == "OP" and len(c.props) > 3):
                children_of.setdefault(parent, []).append(child)
            if c.props[0] == "OP" and len(c.props) > 3 and isinstance(c.props[3], str):
                channel[(child, parent)] = c.props[3]       # the property the child feeds (a texture's channel)
            if c.props[0] == "OO":
                parent_of.setdefault(child, parent)

    def is_model(i):
        return by_id.get(i) is not None and by_id[i].name == "Model"

    for start in list(parent_of):
        seen, i = set(), start
        while i in parent_of and is_model(i):
            if i in seen:
                raise ModelError(f"{path}: the model hierarchy has a cycle ({_name(by_id[i])})")
            seen.add(i)
            i = parent_of[i]
    for o in objects.children:
        if o.name == "Model":
            pr = _props70(o)
            if _int((pr.get("RotationOrder") or [0])[0], 0) != 0:
                warnings.append(f"{_name(o)}: RotationOrder {pr['RotationOrder'][0]} is read as XYZ")
            for key in ("RotationPivot", "ScalingPivot", "RotationOffset", "ScalingOffset"):
                v = pr.get(key)
                if v and any(abs(float(c)) > 1e-9 for c in v[:3]):
                    warnings.append(f"{_name(o)}: {key} is not read")
    world_cache = {}

    def world(i):
        if i in world_cache:
            return world_cache[i]
        m = _local(_props70(by_id[i]))
        p = parent_of.get(i)
        if p is not None and is_model(p):
            m = _mul(world(p), m)
        world_cache[i] = m
        return m

    # joints: LimbNode models, and any model a Cluster links to
    clusters = [o for o in objects.children if o.name == "Deformer" and len(o.props) > 2 and o.props[2] == "Cluster"]
    linked = {}
    for cl in clusters:
        for k in children_of.get(cl.props[0], []):
            if is_model(k):
                linked[cl.props[0]] = k
    joint_ids = {o.props[0] for o in objects.children if o.name == "Model" and len(o.props) > 2
                 and o.props[2] in ("LimbNode", "Root")}
    joint_ids |= set(linked.values())
    bind_head = {}
    for cl in clusters:
        tl = cl.find("TransformLink")
        k = linked.get(cl.props[0])
        if k is not None and tl is not None and tl.props and len(tl.props[0]) == 16:
            m = tl.props[0]                       # column-major 4x4
            bind_head[k] = (m[12], m[13], m[14])
    joints, names = [], {}
    for i in joint_ids:
        names[i] = _name(by_id[i]) or f"joint_{i}"

    def depth(i):
        d, p = 0, parent_of.get(i)
        while p in joint_ids:
            d, p = d + 1, parent_of.get(p)
        return d
    for i in sorted(joint_ids, key=lambda i: (depth(i), names[i])):
        head = bind_head.get(i) or _apply(world(i), (0.0, 0.0, 0.0))
        p = parent_of.get(i)
        joints.append(Joint(names[i], names[p] if p in joint_ids else None, to_kei(to_common(head))))
        finite_or_raise(joints[-1].head, f"{path}: the position of joint {names[i]!r}")

    meshes = []
    for geo in objects.children:
        if geo.name != "Geometry" or len(geo.props) < 3 or geo.props[2] != "Mesh":
            continue
        vnode, inode = geo.find("Vertices"), geo.find("PolygonVertexIndex")
        if vnode is None or inode is None:
            continue
        owner = next((p for p in [parent_of.get(geo.props[0])] if p is not None and is_model(p)), None)
        if owner is None:
            owner = next((m for m, kids in children_of.items() if geo.props[0] in kids and is_model(m)), None)
        if owner is None:
            continue
        mnode = by_id[owner]
        m = _mul(world(owner), _geometric(_props70(mnode)))
        keep = left_handed != mirrors(m)       # a mirrored instance in a mirrored frame winds as the common frame does
        raw = vnode.props[0]
        if not isinstance(raw, list) or len(raw) % 3:
            raise ModelError(f"{path}: a geometry's vertex array is not a list of x, y, z")
        verts = [to_kei(to_common(_apply(m, (raw[k], raw[k + 1], raw[k + 2])))) for k in range(0, len(raw), 3)]
        finite_or_raise(verts, f"{path}: a vertex position of {_name(mnode) or _name(geo)!r}")
        uvget = _uv_layer(geo, len(verts))
        tris, tri_uvs, poly, corners, corner = [], [], [], [], 0
        for idx in inode.props[0]:
            v = -idx - 1 if idx < 0 else idx
            poly.append(v)
            corners.append(uvget(corner, v) if uvget else None)
            corner += 1
            if idx < 0:
                if any(not 0 <= i < len(verts) for i in poly):
                    raise ModelError(f"{path}: a polygon index names a vertex that does not exist")
                for k in range(1, len(poly) - 1):
                    t, uv = (poly[0], poly[k], poly[k + 1]), (corners[0], corners[k], corners[k + 1])
                    tris.append(t if keep else flip(t))
                    tri_uvs.append(uv if keep else flip(uv))
                poly, corners = [], []
        colour, texture = IVORY, None
        for k in children_of.get(owner, []):
            if by_id.get(k) is not None and by_id[k].name == "Material":
                d = _props70(by_id[k]).get("DiffuseColor")
                if d and len(d) >= 3:
                    colour = colour_hex(d)
                for t in children_of.get(k, []):
                    tex = by_id.get(t)
                    if tex is None or tex.name != "Texture" or not _base_colour(channel.get((t, k), "")):
                        continue
                    nodes_ = [tex] + [by_id[c] for c in children_of.get(t, []) if by_id.get(c) is not None]
                    for n in nodes_:
                        for key in ("RelativeFilename", "FileName", "Filename"):
                            f = n.find(key)
                            if f is not None and f.props and isinstance(f.props[0], str) and f.props[0]:
                                texture = texture_path(path.parent, f.props[0], warnings)
                                break
                        if texture or any(n.find(k) for k in ("RelativeFilename", "FileName", "Filename")):
                            break
                    break
                break
        skin = None
        skins = [k for k in children_of.get(geo.props[0], []) if by_id.get(k) is not None
                 and by_id[k].name == "Deformer" and len(by_id[k].props) > 2 and by_id[k].props[2] == "Skin"]
        if skins:
            acc = [[] for _ in verts]
            for cid in children_of.get(skins[0], []):
                cl = by_id.get(cid)
                if cl is None or cid not in linked:
                    continue
                ix, wt = cl.find("Indexes"), cl.find("Weights")
                if ix is None or wt is None:
                    continue
                for i, w in zip(ix.props[0], wt.props[0]):
                    if 0 <= i < len(acc) and w > 0:
                        acc[i].append((names[linked[cid]], float(w)))
            skin = []
            for w in acc:
                total = sum(x for _, x in w)
                skin.append([(n, x / total) for n, x in w] if total > 0 else [])
            if not any(skin):
                skin = None
        has_uv = uvget is not None and all(c is not None for uv in tri_uvs for c in uv)
        if has_uv:
            finite_or_raise(tri_uvs, f"{path}: a texture coordinate of {_name(mnode) or _name(geo)!r}")
        above = parent_of.get(owner)
        while above is not None and is_model(above) and above not in joint_ids:
            above = parent_of.get(above)
        meshes.append(MeshData(_name(mnode) or _name(geo), verts, tris, colour, skin,
                               tri_uvs if has_uv else None, texture if has_uv else None,
                               names[above] if above in joint_ids else None))
    if not meshes:
        raise ModelError(f"{path}: the FBX file holds no mesh")
    return Model(meshes, joints, str(path), warnings)
