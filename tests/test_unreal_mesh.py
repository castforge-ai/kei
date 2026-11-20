"""The pass on the real mesh: the editor renders it with Movie Render Queue, Kei waits for the frames on the disk, draws a
contact sheet per view, and the critics are told to judge them. A fake editor, no Unreal."""
import json
import struct
import zlib
from pathlib import Path

import pytest

from kei.apps import unreal_mesh as M
from kei.apps.unreal import UnrealError
from kei.cli import main
from kei.sample import ShotError
from unrealkit import FakeEditor

ROOT = Path(__file__).resolve().parent.parent
SEQ = "/Game/Kei/walk_01/LS_walk_01_p1_1"


def mesh_shot(tmp_path, frames=12, unreal=True):
    shot = tmp_path / "walk_01"
    (shot / "unreal").mkdir(parents=True)
    (shot / "unreal" / "sequences.json").write_text(json.dumps({"p1": [SEQ]}))
    if unreal:
        (shot / "unreal" / "target.json").write_text(json.dumps({"kind": "open", "url": "http://127.0.0.1:1/mcp"}))
    out = shot / "out_p1"
    out.mkdir()
    (out / "shot.json").write_text(json.dumps({"rig": "unreal", "frames": frames, "keys": [{"f": 0}, {"f": 6}]}))
    (out / "joints.json").write_text(json.dumps({"fps": 24, "frames": [{"f": f, "joints": {"hips": [0, 0, 1]}}
                                                                       for f in range(frames)]}))
    return shot


def no_sleep(_s):
    pass


def test_the_level_then_the_open_then_the_render_and_a_sheet_per_view(tmp_path):
    shot = mesh_shot(tmp_path)
    ed = FakeEditor()
    with ed.server() as fake:
        rep = M.render_mesh(ed.client(), shot, "p1", timeout=5, sleep=no_sleep)
        assert fake.scripts == ["render_level", "render_mesh", "render_mesh"]
    opened, started = ed.mesh_calls
    assert opened == {"stage": "open", "sequence": SEQ}
    assert started["stage"] == "render" and started["last"] == 11 and started["views"] == list(M.VIEWS)
    assert started["level"] == M.LEVEL and started["views_folder"] == "/Game/Kei/walk_01/Views"
    assert started["out_dir"] == (shot / "out_p1" / "mesh").resolve().as_posix()
    assert rep["ok"] and rep["count"] == 12 and rep["level_made"] and set(rep["views"]) == set(M.VIEWS)
    for view in M.VIEWS:
        sheet = shot / "out_p1" / f"mesh_{view}.png"
        assert rep["views"][view]["sheets"] == [f"out_p1/mesh_{view}.png"]
        w, h, _ = M.read_rgb(sheet.read_bytes())
        assert w == M.COLUMNS * (M.TILE[0] + M.GAP) - M.GAP                                    # 12 frames, 2 rows
        assert h == M.HEADER_H + 2 * (M.TILE[1] + M.LABEL_H + M.GAP) - M.GAP
    saved = json.loads((shot / "out_p1" / "mesh_report.json").read_text())
    assert saved["ok"] and saved["sequence"] == SEQ and saved["renderer"] == "unreal_mrq"


def test_the_same_joints_are_not_rendered_twice_and_force_renders_again(tmp_path):
    shot = mesh_shot(tmp_path)
    ed = FakeEditor()
    with ed.server() as fake:
        M.render_mesh(ed.client(), shot, "p1", timeout=5, sleep=no_sleep)
        n = len(fake.scripts)
        again = M.render_mesh(ed.client(), shot, "p1", timeout=5, sleep=no_sleep)
        assert again["reused"] and len(fake.scripts) == n
        (shot / "out_p1" / "joints.json").write_text(json.dumps({"frames": [{"f": f, "joints": {}} for f in range(12)]}))
        M.render_mesh(ed.client(), shot, "p1", timeout=5, sleep=no_sleep)      # a new keying: rendered again
        assert len(fake.scripts) == 2 * n and ed.mesh_calls[-1]["stage"] == "render"
        M.render_mesh(ed.client(), shot, "p1", timeout=5, sleep=no_sleep, force=True)
        assert len(fake.scripts) == 3 * n
    assert len(ed.levels) == 1          # the level is made once; render_level only looks after that


def test_frames_that_never_arrive_are_a_failure_in_words_and_recorded(tmp_path):
    shot = mesh_shot(tmp_path)
    ed = FakeEditor()
    ed.mesh_written = 5
    clock = iter(range(0, 10000, 10))
    with ed.server():
        with pytest.raises(UnrealError, match=r"did not render the mesh frames in 30 s \(side 5 of 12"):
            M.render_mesh(ed.client(), shot, "p1", timeout=30, sleep=no_sleep, clock=lambda: next(clock))
    rep = json.loads((shot / "out_p1" / "mesh_report.json").read_text())
    assert rep["ok"] is False and "Movie Render Queue window" in rep["error"]
    assert not list((shot / "out_p1").glob("mesh_*.png"))          # no sheet stands in for the missing frames


def test_an_editor_refusal_is_recorded_and_raised(tmp_path):
    shot = mesh_shot(tmp_path)
    ed = FakeEditor()
    ed.mesh_error = "Movie Render Queue is rendering already: wait for it to finish, then render again"
    with ed.server():
        with pytest.raises(UnrealError, match="rendering already"):
            M.render_mesh(ed.client(), shot, "p1", timeout=5, sleep=no_sleep)
    assert "rendering already" in json.loads((shot / "out_p1" / "mesh_report.json").read_text())["error"]


def test_old_frames_are_cleared_before_a_render(tmp_path):
    shot = mesh_shot(tmp_path)
    stale = shot / "out_p1" / "mesh" / "side" / "f0040.png"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"old")
    ed = FakeEditor()
    with ed.server():
        M.render_mesh(ed.client(), shot, "p1", timeout=5, sleep=no_sleep)
    assert not stale.exists()


def test_a_pass_never_keyed_in_unreal_is_refused(tmp_path):
    shot = mesh_shot(tmp_path)
    (shot / "unreal" / "sequences.json").write_text("{}")
    ed = FakeEditor()
    with ed.server():
        with pytest.raises(ShotError, match="kei unreal key"):
            M.render_mesh(ed.client(), shot, "p1", timeout=5, sleep=no_sleep)


def test_wait_returns_once_every_frame_is_there_and_stopped_growing(tmp_path):
    folder = tmp_path / "mesh"
    for v in ("side", "feet"):
        (folder / v).mkdir(parents=True)
        for f in range(3):
            (folder / v / f"f{f:04d}.png").write_bytes(b"x" * 10)
    slept = []
    M.wait_for_frames(folder, ("side", "feet"), [0, 1, 2], 60, sleep=slept.append)
    assert len(slept) == 1          # one more look, to see the last files stopped growing


def _png(w, h, colour, rows):
    """A PNG with each row's own filter byte, as a writer like Movie Render Queue's may choose."""
    raw = b"".join(bytes([kind]) + bytes(line) for kind, line in rows)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, colour, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _filter(kind, line, prev, bpp):
    out = []
    for x in range(len(line)):
        a = line[x - bpp] if x >= bpp else 0
        b = prev[x]
        c = prev[x - bpp] if x >= bpp else 0
        if kind == 0:
            pred = 0
        elif kind == 1:
            pred = a
        elif kind == 2:
            pred = b
        elif kind == 3:
            pred = (a + b) // 2
        else:
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pred = a if pa <= pb and pa <= pc else b if pb <= pc else c
        out.append((line[x] - pred) & 255)
    return out


def test_an_rgba_png_with_every_filter_reads_back_exactly():
    w, h, bpp = 7, 5, 4
    pixels = [[(x * 37 + y * 91 + i * 53) % 256 for x in range(w) for i in range(bpp)] for y in range(h)]
    rows, prev = [], [0] * (w * bpp)
    for y, line in enumerate(pixels):
        rows.append((y % 5, _filter(y % 5, line, prev, bpp)))
        prev = line
    got_w, got_h, rgb = M.read_rgb(_png(w, h, 6, rows))
    want = bytearray(v for line in pixels for x in range(w) for v in line[x * 4:x * 4 + 3])
    assert (got_w, got_h) == (w, h) and rgb == want


def test_a_png_kei_cannot_read_says_why():
    with pytest.raises(ValueError, match="colour type 3"):
        M.read_rgb(_png(1, 1, 3, [(0, [0])]))


def test_the_critics_are_told_where_the_mesh_frames_are_or_why_there_are_none(tmp_path):
    shot = mesh_shot(tmp_path)
    assert "NOT rendered on the mesh" in "\n".join(M.mesh_lines(shot, ["p1"]))
    ed = FakeEditor()
    with ed.server():
        M.render_mesh(ed.client(), shot, "p1", timeout=5, sleep=no_sleep)
    text = "\n".join(M.mesh_lines(shot, ["p1"]))
    assert "out_p1/mesh_side.png" in text and "out_p1/mesh_feet.png" in text and "out_p1/mesh/side/f0000.png" in text
    rep = json.loads((shot / "out_p1" / "mesh_report.json").read_text())
    (shot / "out_p1" / "mesh_report.json").write_text(json.dumps({**rep, "ok": False, "error": "no frames"}))
    assert "FAILED (no frames)" in "\n".join(M.mesh_lines(shot, ["p1"]))
    assert M.mesh_lines(mesh_shot(tmp_path / "kei_rig", unreal=False), ["p1"]) == []


def test_kei_unreal_render_mesh_prints_the_sheets(tmp_path, monkeypatch, capsys):
    from kei.apps import unreal_stage
    shot = mesh_shot(tmp_path)
    got = {}

    def fake(shot_dir, name, timeout, force=False):
        got.update(name=name, timeout=timeout, force=force)
        return {"pass": name, "frames": [0, 11], "sequence": SEQ, "warnings": ["motion blur could not be turned off"],
                "views": {v: {"sheets": [f"out_p1/mesh_{v}.png"], "folder": f"out_p1/mesh/{v}"} for v in M.VIEWS}}
    monkeypatch.setattr(unreal_stage, "render_mesh", fake)
    assert main(["unreal", "render-mesh", str(shot), "p1", "--timeout", "90", "--force"]) == 0
    out = capsys.readouterr().out
    assert got == {"name": "p1", "timeout": 90.0, "force": True}
    assert "out_p1/mesh_feet.png" in out and "motion blur" in out and "mesh_report.json" in out


def test_the_editor_scripts_keep_kei_s_rules():
    side = ROOT / "kei" / "apps" / "unreal_side"
    mesh = (side / "render_mesh.py").read_text(encoding="utf-8")
    level = (side / "render_level.py").read_text(encoding="utf-8")
    assert "r.MotionBlurQuality" in mesh and "MoviePipelinePIEExecutor" in mesh and "GameModeBase" in mesh
    assert "delete_asset" not in mesh and "delete_asset" not in level           # Kei never deletes an asset here
    assert "never clears your queue" in mesh and "is_rendering()" in mesh
    assert "new_level_from_template" in level and "duplicate_asset" not in level   # copying a map can crash the editor
    assert "load_level(before)" in level and "get_dirty_map_packages" in level
    for text in (mesh, level):
        assert "KEI_ROOT" in text
