"""An object in a pass's shot.json is drawn in every view and checked by kei check, with no seat script."""
import json
from pathlib import Path

from kei.body_check import check_pass
from kei.render import render_post, render_shot
from test_sheet import decode

ROOT = Path(__file__).resolve().parent.parent
WALK = ROOT / "tests" / "fixtures" / "walks" / "kei_p10_approved.json"
BOX = {"name": "crate", "shape": "box", "size": [0.4, 0.4, 0.4], "rest": [0.7, 0.2, 0.0], "colour": "#ff0000"}


def _shot(tmp_path, frames=2, **obj):
    shot = json.loads(WALK.read_text(encoding="utf-8"))
    src = tmp_path / "out_p1" / "shot.json"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(json.dumps({**shot, "frames": frames, "loop": False, "objects": [{**BOX, **obj}]}), encoding="utf-8")
    return src


def _red(px, x0, y0, x1, y1) -> int:
    return sum(1 for y in range(y0, y1) for x in range(x0, x1)
               if (lambda c: c[0] > 120 and c[1] < 60 and c[2] < 60)(px(x, y)))


def test_the_crate_is_drawn_in_all_four_post_views(tmp_path):
    r = render_post(_shot(tmp_path), tmp_path / "post", "spline", "kei", height=240, video=False)
    w, h, px = decode(r["frames"][0].read_bytes())
    half = w // 2
    for qx, qy in ((0, 0), (1, 0), (0, 1), (1, 1)):     # side, three quarter, front, back
        assert _red(px, qx * half, qy * half, (qx + 1) * half, (qy + 1) * half) > 20, (qx, qy)


def test_the_crate_is_drawn_in_the_review_render(tmp_path):
    src = _shot(tmp_path)
    r = render_shot(src, tmp_path / "out", "spline", size=120, character="kei")
    w, h, px = decode(r["frames"][0].read_bytes())
    assert _red(px, 0, 0, w, h) > 40


def test_kei_check_flags_a_crate_under_the_floor(tmp_path):
    _shot(tmp_path, frames=6, rest=[0.7, 0.17, 0.0])
    report = json.loads(check_pass(tmp_path, "p1", "kei", "spline").read_text(encoding="utf-8"))
    obj = [fl for fl in report["flags"] if fl["check"] == "objects"]
    assert obj and obj[0]["rule"] == "hard" and "under the ground" in obj[0]["what"]
    assert report["objects"]["crate"]["holds"] == []


def test_kei_check_is_quiet_about_a_crate_resting_on_the_floor(tmp_path):
    _shot(tmp_path, frames=6)
    report = json.loads(check_pass(tmp_path, "p1", "kei", "spline").read_text(encoding="utf-8"))
    assert not [fl for fl in report["flags"] if fl["check"] == "objects"]
