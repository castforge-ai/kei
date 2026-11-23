"""C3D capture: the reader (Intel, DEC and MIPS files, float and scaled integer points, lost markers), the joint
centres estimated from Plug-in Gait markers, and kei ref import of a .c3d."""
import json
import math
import struct

import pytest

from kei.c3d import DEC, INTEL, MIPS, C3dError, read_c3d
from kei.mocap import MocapError, import_reference, markers_to_bones

PLUG_IN_GAIT = ["LFWT", "RFWT", "LBWT", "RBWT", "LKNE", "RKNE", "LANK", "RANK", "LTOE", "RTOE", "LHEE", "RHEE",
                "LSHO", "RSHO", "LELB", "RELB", "LWRA", "LWRB", "RWRA", "RWRB", "LFIN", "RFIN", "C7", "CLAV", "T10",
                "STRN", "LFHD", "RFHD", "LBHD", "RBHD"]


def _dec(f: float) -> bytes:
    b = struct.pack("<f", f * 4.0) if f else b"\x00\x00\x00\x00"
    return bytes((b[2], b[3], b[0], b[1]))


def write_c3d(path, frames, labels, rate=120.0, processor=INTEL, floats=True, scale=0.1, prefix="Sub:"):
    """A minimal C3D: header, a POINT group (LABELS, USED, SCALE, RATE, UNITS mm), the points. A point missing from
    a frame's dict is written as lost (residual -1)."""
    end = ">" if processor == MIPS else "<"

    def f32(v):
        return _dec(v) if processor == DEC else struct.pack(end + "f", v)

    def i16(v):
        return struct.pack(end + "h", v)

    def u16(v):
        return struct.pack(end + "H", v)

    n = len(labels)
    s = -1.0 if floats else scale
    params = bytearray(struct.pack("BBBB", 1, 0x50, 1, processor))

    def entry(name: bytes, ident: int, body: bytes):
        nonlocal params
        params += struct.pack("bb", len(name), ident) + name
        params += i16(2 + len(body)) + body

    entry(b"POINT", -1, b"\x00")
    width = 12
    names = b"".join((prefix + lab).ljust(width).encode() for lab in labels)
    entry(b"LABELS", 1, struct.pack("bBBB", -1, 2, width, n) + names + b"\x00")
    entry(b"USED", 1, struct.pack("bB", 2, 0) + i16(n) + b"\x00")
    entry(b"SCALE", 1, struct.pack("bB", 4, 0) + f32(s) + b"\x00")
    entry(b"RATE", 1, struct.pack("bB", 4, 0) + f32(rate) + b"\x00")
    entry(b"UNITS", 1, struct.pack("bBB", -1, 1, 2) + b"mm" + b"\x00")
    params += b"\x00\x00"
    blocks = (len(params) + 511) // 512
    params += b"\x00" * (blocks * 512 - len(params))
    data_block = 2 + blocks
    header = bytearray(512)
    header[0], header[1] = 2, 0x50
    header[2:4], header[4:6] = u16(n), u16(0)
    header[6:8], header[8:10] = u16(1), u16(len(frames))
    header[12:16] = f32(s)
    header[16:18] = u16(data_block)
    header[20:24] = f32(rate)
    data = bytearray()
    for fr in frames:
        for lab in labels:
            p = fr.get(lab)
            if floats:
                data += b"".join(f32(c) for c in (p or (0.0, 0.0, 0.0))) + f32(0.0 if p else -1.0)
            else:
                q = [round(c / scale) for c in (p or (0.0, 0.0, 0.0))]
                data += b"".join(i16(c) for c in q) + i16(0 if p else -1)
    path.write_bytes(bytes(header) + bytes(params) + bytes(data))
    return path


@pytest.mark.parametrize("processor", [INTEL, DEC, MIPS])
@pytest.mark.parametrize("floats", [True, False])
def test_the_reader_reads_every_processor_and_both_point_kinds(tmp_path, processor, floats):
    frames = [{"A": (100.0 + f, -250.5, 1000.25), "B": (0.5, 2.0, 3.0 * f + 1)} for f in range(5)]
    del frames[2]["B"]
    c = read_c3d(write_c3d(tmp_path / "t.c3d", frames, ["A", "B"], processor=processor, floats=floats))
    assert c.labels == ["Sub:A", "Sub:B"] and c.rate == 120.0 and c.units == "mm" and len(c.frames) == 5
    assert "Sub:B" not in c.frames[2]
    tol = 1e-4 if floats else 0.051
    for fr, want in zip(c.frames, frames):
        for lab, p in want.items():
            assert math.dist(fr["Sub:" + lab], p) < tol


def test_a_file_that_is_not_c3d_is_refused(tmp_path):
    (tmp_path / "x.c3d").write_bytes(b"hello" * 200)
    with pytest.raises(C3dError, match="not a C3D"):
        read_c3d(tmp_path / "x.c3d")


def standing(f=0, step=0.0):
    """Plug-in Gait markers on a standing person 1.7 m tall, in a lab with x forward, y left, z up, mm; moved
    forward by step."""
    m = {"LFWT": (80, 120, 1000), "RFWT": (80, -120, 1000), "LBWT": (-80, 80, 1010), "RBWT": (-80, -80, 1010),
         "LKNE": (20, 140, 500), "RKNE": (20, -140, 500), "LANK": (-10, 120, 80), "RANK": (-10, -120, 80),
         "LTOE": (130, 110, 40), "RTOE": (130, -110, 40), "LHEE": (-70, 110, 50), "RHEE": (-70, -110, 50),
         "LSHO": (0, 190, 1440), "RSHO": (0, -190, 1440), "LELB": (-10, 250, 1150), "RELB": (-10, -250, 1150),
         "LWRA": (20, 240, 880), "LWRB": (-20, 240, 880), "RWRA": (20, -240, 880), "RWRB": (-20, -240, 880),
         "LFIN": (0, 240, 800), "RFIN": (0, -240, 800), "C7": (-90, 0, 1480), "CLAV": (60, 0, 1430),
         "T10": (-110, 0, 1250), "STRN": (100, 0, 1250), "LFHD": (90, 60, 1650), "RFHD": (90, -60, 1650),
         "LBHD": (-90, 60, 1640), "RBHD": (-90, -60, 1640)}
    return {k: (v[0] + step, v[1], v[2]) for k, v in m.items()}


def test_joint_centres_sit_inside_the_markers(tmp_path):
    frames = [standing(f, step=10.0 * f) for f in range(12)]
    del frames[5]["LKNE"]                                    # a marker the cameras lost for a frame
    bones, mapping, unit, skipped = markers_to_bones(read_c3d(write_c3d(tmp_path / "w.c3d", frames, PLUG_IN_GAIT)))
    assert unit == "mm" and skipped == 0 and len(bones) == 12
    b = bones[0]
    # the hips: inside the waist markers and below them; the knees and ankles: in from the lateral markers
    assert abs(b["thigh_l"][1] - b["thigh_r"][1]) < 24 and b["thigh_l"][2] < 100 - 0.5
    for s, sign in (("l", 1), ("r", -1)):
        assert abs(b[f"calf_{s}"][1]) < 14 and abs(b[f"foot_{s}"][1]) < 12
    assert b["head"][2] > b["neck_01"][2] > b["spine_05"][2] > b["pelvis"][2]
    assert abs(b["foot_l"][2] - 8.0) < 0.6                    # the floor goes under the ankles (8 cm), cm z up
    # left in the lab is left on Kei's side too: the y axis flips into Kei's left handed space
    assert b["upperarm_l"][1] < 0 < b["upperarm_r"][1]
    assert math.dist(bones[5]["calf_l"], _mid(bones[4]["calf_l"], bones[6]["calf_l"])) < 1e-6   # the gap filled
    assert mapping["LKNE"] == "Sub:LKNE" and mapping["lasi"] == "Sub:LFWT"     # the markers each estimate used


def _mid(a, b):
    return tuple((a[i] + b[i]) / 2 for i in range(3))


def test_a_marker_set_kei_cannot_read_is_named(tmp_path):
    frames = [{k: v for k, v in standing().items() if k not in ("LKNE", "C7")}]
    labels = [lab for lab in PLUG_IN_GAIT if lab not in ("LKNE", "C7")]
    with pytest.raises(MocapError, match="LKNE.*C7|C7.*LKNE"):
        markers_to_bones(read_c3d(write_c3d(tmp_path / "x.c3d", frames, labels)))


def test_kei_ref_import_takes_a_c3d(tmp_path):
    frames = [standing(f, step=11.0 * f) for f in range(48)]      # 1.32 m/s at 120 fps
    src = write_c3d(tmp_path / "walk.c3d", frames, PLUG_IN_GAIT)
    r = import_reference(tmp_path / "shot", src, "made for the test")
    m = r["measures"]
    assert m["frames"] == 48 and m["fps"] == 120.0 and abs(m["speed_m_s"] - 1.32) < 0.01
    assert 1.5 < m["height_m"] < 1.9
    source = (r["folder"] / "SOURCE.md").read_text()
    assert "estimated from the skin markers" in source and "Licence: made for the test" in source
    assert json.loads((r["folder"] / "joints.json").read_text())[0]["joints"]["head_top"]
