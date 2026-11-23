"""Read a C3D motion capture file: its parameters and its 3D marker points, standard library only.

read_c3d(path) -> C3d: labels, rate (frames a second), units ("mm", "cm" or "m") and frames, one {label: (x, y, z)}
per frame in the file's own units and axes (the lab's, usually z up), a marker the cameras lost on a frame left out of
that frame. Analog channels are skipped.

The format (c3d.org): a 512-byte header (word 1: the parameter block, byte 2 0x50; word 2: the points; word 3: the
analog samples per frame; words 4 and 5: the first and last frame; words 7-8: the scale, a float, negative when the
points are stored as floats; word 9: the data block; words 11-12: the frame rate), the parameter section (groups
and parameters, POINT:LABELS among them) from that block, then the data. The parameter section's fourth byte names
the processor: 84 Intel (little endian), 85 DEC (little endian words, DEC floats), 86 MIPS (big endian).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

INTEL, DEC, MIPS = 84, 85, 86


class C3dError(ValueError):
    pass


@dataclass
class C3d:
    labels: list
    rate: float
    units: str
    frames: list           # one {label: (x, y, z)} per frame
    first_frame: int = 1
    parameters: dict | None = None


class _Reader:
    def __init__(self, blob: bytes, processor: int):
        self.blob, self.processor = blob, processor
        self.end = ">" if processor == MIPS else "<"

    def int8(self, at):
        return struct.unpack_from("b", self.blob, at)[0]

    def uint8(self, at):
        return self.blob[at]

    def int16(self, at):
        return struct.unpack_from(self.end + "h", self.blob, at)[0]

    def uint16(self, at):
        return struct.unpack_from(self.end + "H", self.blob, at)[0]

    def float32(self, at):
        if self.processor == DEC:
            b = self.blob[at:at + 4]
            # a DEC float: its two 16-bit halves in the other order and an exponent offset by 2 (a factor of 4)
            return struct.unpack("<f", bytes((b[2], b[3], b[0], b[1])))[0] / 4.0 if any(b) else 0.0
        return struct.unpack_from(self.end + "f", self.blob, at)[0]


def _parameters(r: _Reader, start: int) -> dict:
    """{GROUP: {PARAM: value}}: a char array becomes a list of stripped strings (a string for one dimension), a
    number array a flat list (a single value for none)."""
    groups, out = {}, {}
    at = start + 4
    while at < len(r.blob):
        size = r.int8(at)
        ident = r.int8(at + 1)
        if size == 0 or ident == 0:
            break
        n = abs(size)
        name = r.blob[at + 2:at + 2 + n].decode("ascii", "replace").strip().upper()
        link = at + 2 + n
        step = r.int16(link)
        body = link + 2
        if ident < 0:
            groups[-ident] = name
            out.setdefault(name, {})
        else:
            kind, dims = r.int8(body), r.uint8(body + 1)
            shape = [r.uint8(body + 2 + i) for i in range(dims)]
            data = body + 2 + dims
            count = 1
            for d in shape:
                count *= d
            if kind == -1:            # characters: the first dimension is the length of each string
                raw = r.blob[data:data + count].decode("latin-1")
                if dims <= 1:
                    value = raw.strip()
                else:
                    w = shape[0]
                    value = [raw[i:i + w].strip() for i in range(0, len(raw), w)]
            else:
                width = {1: 1, 2: 2, 4: 4}.get(abs(kind))
                if width is None:
                    raise C3dError(f"parameter {name}: unknown data type {kind}")
                read = {1: r.uint8, 2: r.int16, 4: r.float32}[abs(kind)]
                vals = [read(data + i * width) for i in range(count)]
                value = vals[0] if dims == 0 else vals
            out.setdefault(groups.get(ident, f"GROUP{ident}"), {})[name] = value
        if step == 0:
            break
        at = link + step
    return out


def read_c3d(path) -> C3d:
    try:
        blob = Path(path).read_bytes()
    except OSError as e:
        raise C3dError(f"cannot read {path}: {e.strerror or e}") from e
    if len(blob) < 512 or blob[1] != 0x50:
        raise C3dError(f"{Path(path).name} is not a C3D file (no 0x50 key in its header)")
    pblock = blob[0]
    pstart = (pblock - 1) * 512
    if len(blob) < pstart + 4:
        raise C3dError(f"{Path(path).name}: the parameter section is missing")
    processor = blob[pstart + 3]
    if processor not in (INTEL, DEC, MIPS):
        raise C3dError(f"{Path(path).name}: unknown processor type {processor} (84 Intel, 85 DEC, 86 MIPS)")
    r = _Reader(blob, processor)
    points = r.uint16(2)
    analog = r.uint16(4)
    first, last = r.uint16(6), r.uint16(8)
    scale = r.float32(12)
    data_block = r.uint16(16)
    rate = r.float32(20)
    params = _parameters(r, pstart)
    point = params.get("POINT", {})
    labels = point.get("LABELS", [])
    if isinstance(labels, str):
        labels = [labels]
    labels = list(labels) + list(point.get("LABELS2", []) if isinstance(point.get("LABELS2"), list) else [])
    used = point.get("USED", points)
    points = int(used if isinstance(used, (int, float)) else points)
    if isinstance(point.get("SCALE"), float):
        scale = point["SCALE"]
    if isinstance(point.get("RATE"), float) and point["RATE"] > 0:
        rate = point["RATE"]
    if isinstance(point.get("DATA_START"), int) and point["DATA_START"] > 0:
        data_block = point["DATA_START"]
    nframes = last - first + 1
    if isinstance(point.get("FRAMES"), int) and point["FRAMES"] > 0 and last >= 65535:
        nframes = point["FRAMES"]      # a long capture keeps its frame count here
    units = str(point.get("UNITS", "mm")).strip().lower() or "mm"
    labels = [lab or f"point{i + 1}" for i, lab in enumerate(labels[:points])]
    labels += [f"point{i + 1}" for i in range(len(labels), points)]
    is_float = scale < 0
    width = 4 if is_float else 2
    per_frame = points * 4 * width + analog * width
    at = (data_block - 1) * 512
    frames = []
    for _ in range(nframes):
        if at + per_frame > len(blob):
            break
        fr = {}
        for i, lab in enumerate(labels):
            p = at + i * 4 * width
            if is_float:
                x, y, z, res = (r.float32(p + k * 4) for k in range(4))
                bad = res < 0 or int(res) & 0x8000 != 0
                k = 1.0
            else:
                x, y, z, res = (r.int16(p + k * 2) for k in range(4))
                bad = res < 0
                k = abs(scale)
            if not bad and not (x == 0 and y == 0 and z == 0):
                fr[lab] = (x * k, y * k, z * k)
        frames.append(fr)
        at += per_frame
    if not frames:
        raise C3dError(f"{Path(path).name} holds no frames of 3D points")
    return C3d(labels, float(rate), units, frames, first, params)
