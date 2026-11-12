"""A small reader for binary FBX 7.x, for the tests: it parses a file back into a node tree and checks every length.

read_fbx(blob) -> (version, [FbxNode]); each FbxNode has name, props (Python values; arrays as lists) and children.
It raises ValueError on a wrong header, a node whose end offset does not match its content, a bad array or footer.
Written from the documented layout (the same facts kei.fbx writes from), independently of kei.fbx's code.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"
SCALARS = {"Y": "<h", "C": "<?", "I": "<i", "F": "<f", "D": "<d", "L": "<q"}
ARRAYS = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "?"}
FOOTER_END = bytes.fromhex("f85a8c6adef5d97eece90ce3758f290b")


@dataclass
class FbxNode:
    name: str
    props: list
    children: list = field(default_factory=list)
    types: str = ""
    listed: bool = False          # the record carries a child list (closed by a null record), even an empty one

    def find(self, name: str) -> "FbxNode | None":
        return next((c for c in self.children if c.name == name), None)

    def all(self, name: str) -> list:
        return [c for c in self.children if c.name == name]


def _prop(blob: bytes, pos: int):
    code = chr(blob[pos])
    pos += 1
    if code in SCALARS:
        fmt = SCALARS[code]
        return code, struct.unpack_from(fmt, blob, pos)[0], pos + struct.calcsize(fmt)
    if code in ARRAYS:
        n, enc, clen = struct.unpack_from("<III", blob, pos)
        pos += 12
        raw = blob[pos:pos + clen]
        if enc == 1:
            raw = zlib.decompress(raw)
        elif enc != 0:
            raise ValueError(f"array encoding {enc}")
        fmt = "<" + ARRAYS[code] * n
        if len(raw) != struct.calcsize(fmt):
            raise ValueError(f"array of {n} {code} has {len(raw)} bytes")
        return code, list(struct.unpack(fmt, raw)), pos + clen
    if code in "SR":
        n = struct.unpack_from("<I", blob, pos)[0]
        data = blob[pos + 4:pos + 4 + n]
        return code, (data.decode("utf-8") if code == "S" else bytes(data)), pos + 4 + n
    raise ValueError(f"unknown property type {code!r} at {pos - 1}")


def _node(blob: bytes, pos: int, wide: bool = False):
    """One node record; `wide` is the 7.5 layout (64-bit end offset and counts, a 25-byte null record)."""
    head, fmt = (25, "<QQQ") if wide else (13, "<III")
    end, nprops, plen = struct.unpack_from(fmt, blob, pos)
    nlen = blob[pos + head - 1]
    if end == 0:
        if blob[pos:pos + head] != b"\x00" * head:
            raise ValueError(f"bad null record at {pos}")
        return None, pos + head
    name = blob[pos + head:pos + head + nlen].decode("ascii")
    p = pos + head + nlen
    props, types, start = [], "", p
    for _ in range(nprops):
        code, value, p = _prop(blob, p)
        props.append(value)
        types += code
    if p - start != plen:
        raise ValueError(f"{name}: property list is {p - start} bytes, the record says {plen}")
    node = FbxNode(name, props, [], types)
    if p < end:
        while True:
            child, p = _node(blob, p, wide)
            if child is None:
                node.listed = True
                break
            node.children.append(child)
    if p != end:
        raise ValueError(f"{name}: ends at {p}, the record says {end}")
    return node, end


def read_fbx(blob: bytes):
    if blob[:23] != MAGIC:
        raise ValueError("not a binary FBX file")
    version = struct.unpack_from("<I", blob, 23)[0]
    pos, nodes = 27, []
    while True:
        node, pos = _node(blob, pos, version >= 7500)
        if node is None:
            break
        nodes.append(node)
    footer = blob[pos:]
    if len(footer) < 16 + 4 + 4 + 120 + 16 or footer[-16:] != FOOTER_END:
        raise ValueError("no FBX footer")
    tail = blob[-(16 + 120 + 4 + 4):]          # 4 zero bytes, the version, 120 zero bytes, the end magic
    if tail[:4] != b"\x00" * 4 or struct.unpack_from("<I", tail, 4)[0] != version or tail[8:128] != b"\x00" * 120:
        raise ValueError("bad FBX footer")
    if (len(blob) - 16 - 120 - 4 - 4) % 16:
        raise ValueError("the footer's padding does not align to 16 bytes")
    return version, nodes
