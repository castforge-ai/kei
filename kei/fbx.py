"""Binary FBX 7.4, the file layer: node records, typed properties, arrays, the header and the footer.

Written from the publicly documented binary layout, with struct and zlib only. A file is the header, a list of node
records, an empty (null) record, and the footer. A node record (FBX before 7.5) is:

  uint32 end offset (absolute, in the file), uint32 property count, uint32 property bytes, uint8 name length, name,
  the properties, then the child records and a 13-byte null record when the node has children, no properties, or
  an empty child list that a reader expects (Node.listed: the FBX SDK skipped every animation curve until the
  AnimationLayer record, which has no children, closed its empty list this way).

A property is a one-byte type code and its value: Y int16, C bool, I int32, F float32, D float64, L int64, S string
and R raw bytes (uint32 length, then the bytes), and the arrays f, d, l, i, b (uint32 count, uint32 encoding,
uint32 byte length, then the values; encoding 1 is zlib, used here above COMPRESS_ABOVE bytes).

The scene layer (models, geometry, skin, materials, animation) is kei.export_fbx.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

VERSION = 7400
HEADER = b"Kaydara FBX Binary  \x00\x1a\x00"
COMPRESS_ABOVE = 128                 # bytes: an array larger than this is written zlib-compressed
# The footer's fixed blocks. FOOTER_ID belongs with the fixed FileId and CreationTime kei.export_fbx writes.
FOOTER_ID = bytes.fromhex("fabcab09d0c8d466b176fb831cf7267e")
FOOTER_END = bytes.fromhex("f85a8c6adef5d97eece90ce3758f290b")
NULL_RECORD = b"\x00" * 13

SCALARS = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}
ARRAYS = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "?"}


@dataclass(frozen=True)
class P:
    """A property with an explicit FBX type code (where the Python type alone does not say which)."""
    code: str
    value: object

    def __post_init__(self):
        if self.code not in SCALARS and self.code not in ARRAYS and self.code not in "SR":
            raise ValueError(f"unknown FBX property type {self.code!r}")


@dataclass
class Node:
    name: str
    props: list = field(default_factory=list)
    children: list = field(default_factory=list)
    listed: bool = False              # write the child list's null record even when the list is empty


def _typed(v) -> P:
    """A plain Python value's FBX type: bool C, int I, float D, str S, bytes R; P is kept as it is."""
    if isinstance(v, P):
        return v
    if isinstance(v, bool):
        return P("C", v)
    if isinstance(v, int):
        return P("I", v)
    if isinstance(v, float):
        return P("D", v)
    if isinstance(v, str):
        return P("S", v)
    if isinstance(v, (bytes, bytearray)):
        return P("R", bytes(v))
    raise TypeError(f"no FBX property type for {type(v).__name__}")


def encode_property(v) -> bytes:
    p = _typed(v)
    code = p.code.encode("ascii")
    if p.code in SCALARS:
        return code + struct.pack(SCALARS[p.code], p.value)
    if p.code in "SR":
        data = p.value.encode("utf-8") if p.code == "S" else p.value
        return code + struct.pack("<I", len(data)) + data
    values = list(p.value)
    raw = struct.pack("<" + ARRAYS[p.code] * len(values), *values)
    if len(raw) > COMPRESS_ABOVE:
        data, enc = zlib.compress(raw), 1
    else:
        data, enc = raw, 0
    return code + struct.pack("<III", len(values), enc, len(data)) + data


def encode_node(node: Node, offset: int) -> bytes:
    """The node's record when it starts at byte `offset` of the file (end offsets are absolute)."""
    name = node.name.encode("ascii")
    props = b"".join(encode_property(v) for v in node.props)
    head_len = 13 + len(name)
    body = bytearray()
    pos = offset + head_len + len(props)
    for child in node.children:
        rec = encode_node(child, pos)
        body += rec
        pos += len(rec)
    if node.children or node.listed or not node.props:
        body += NULL_RECORD
    end = offset + head_len + len(props) + len(body)
    return struct.pack("<IIIB", end, len(node.props), len(props), len(name)) + name + props + bytes(body)


def fbx_file(nodes: list, version: int = VERSION) -> bytes:
    """A whole binary FBX file: the header, the top-level nodes, the null record and the footer."""
    out = bytearray(HEADER + struct.pack("<I", version))
    for node in nodes:
        out += encode_node(node, len(out))
    out += NULL_RECORD
    out += FOOTER_ID
    pad = -len(out) % 16
    out += b"\x00" * (pad or 16)
    out += b"\x00" * 4 + struct.pack("<I", version) + b"\x00" * 120 + FOOTER_END
    return bytes(out)
