"""kei render --post: a clean, smooth video to post, with no review marks."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from kei.cli import main
from kei.render import render_post
from test_sheet import decode

ROOT = Path(__file__).resolve().parent.parent
WALK = ROOT / "tests" / "fixtures" / "walks" / "kei_p10_approved.json"
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffmpeg is not installed")


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=codec_name,width,height,pix_fmt,r_frame_rate,nb_frames", "-of", "json", str(path)],
                         capture_output=True, text=True).stdout
    return json.loads(out)["streams"][0]


@needs_ffmpeg
def test_the_post_video_is_a_square_grid_of_four_views_in_h264(tmp_path):
    shot = json.loads(WALK.read_text(encoding="utf-8"))
    src = tmp_path / "shot.json"
    src.write_text(json.dumps({**shot, "frames": 4, "loop": False}), encoding="utf-8")
    r = render_post(src, tmp_path / "post", "spline", "kei", height=160, name="kei_walk")
    p = _probe(r["video"])
    assert (p["codec_name"], p["width"], p["height"], p["pix_fmt"]) == ("h264", 160, 160, "yuv420p")
    assert p["r_frame_rate"] == "24/1"


def test_a_post_frame_carries_no_label_border_or_tick(tmp_path):
    shot = json.loads(WALK.read_text(encoding="utf-8"))
    src = tmp_path / "shot.json"
    src.write_text(json.dumps({**shot, "frames": 2, "loop": False}), encoding="utf-8")
    r = render_post(src, tmp_path / "post", "spline", "kei", height=200, name="kei_walk", video=False)
    w, h, px = decode(r["frames"][0].read_bytes())
    page = px(0, 0)
    # the label strip and the panel borders of the review render: all page in the post
    assert all(px(x, y) == page for y in range(0, 14) for x in range(w))
    assert all(px(w // 2, y) == page for y in range(0, 20))
    # the review font's ink (20, 20, 20) is nowhere
    assert not any(px(x, y) == (20, 20, 20) for y in range(h) for x in range(w))


def test_kei_render_post_writes_into_the_chosen_folder(tmp_path, capsys):
    shot_dir = tmp_path / "shot"
    (shot_dir / "out_p1").mkdir(parents=True)
    shot = json.loads(WALK.read_text(encoding="utf-8"))
    (shot_dir / "out_p1" / "shot.json").write_text(json.dumps({**shot, "frames": 2, "loop": False}))
    out = tmp_path / "linkedin"
    assert main(["render", str(shot_dir), "p1", "--character", "kei", "--post", "--size", "80",
                 "--out", str(out)]) == 0
    assert list(out.glob("*_post.*")), list(out.iterdir())
    assert not (shot_dir / "out_p1" / "post").exists()


def test_a_character_render_is_540_pixels_a_panel_by_default(tmp_path, monkeypatch):
    import kei.cli as cli
    seen = {}

    def fake(src, out, mode, size=360, **kw):
        seen["size"] = size
        return {"frames": [], "stills": [], "keys": out / "keys.png", "playback": out / "p.mp4", "kind": "mp4"}
    monkeypatch.setattr(cli, "render_shot", fake)
    shot_dir = tmp_path / "shot"
    (shot_dir / "out_p1").mkdir(parents=True)
    (shot_dir / "out_p1" / "shot.json").write_text(WALK.read_text(encoding="utf-8"))
    assert main(["render", str(shot_dir), "p1", "--character", "kei"]) == 0
    assert seen["size"] == 540


def test_every_post_view_loops_with_no_jump_at_the_seam_and_the_figure_centred(tmp_path):
    # The author, 2026-11-02, on the first post video: the two top views do not loop, they should.
    src = tmp_path / "shot.json"
    src.write_text(WALK.read_text(encoding="utf-8"), encoding="utf-8")
    r = render_post(src, tmp_path / "post", "spline", "kei", height=160, name="kei_walk", video=False)
    played = len(r["frames"]) - 1          # a loop's last frame repeats frame 0 and is not played
    for view, px in r["pelvis_px"].items():
        for ax in (0, 1):      # across and up: a raised camera turns the travel into a climb up the screen too
            steps = [abs(px[i + 1][ax] - px[i][ax]) for i in range(played - 1)]
            seam = abs(px[0][ax] - px[played - 1][ax])
            assert seam <= max(steps) + 1, (view, ax, seam, max(steps))
        mean_x = sum(p[0] for p in px[:played]) / played
        assert abs(mean_x - 40) < 8, (view, mean_x)     # 80 px panels: the figure sits near the middle


def test_the_three_quarter_camera_looks_down_on_the_figure():
    # The author, 2026-11-02: the 3/4 view should be higher up, not just 3/4 on the horizontal plane.
    import math
    from kei.render import _CAMERA, _view
    toward = _CAMERA["three quarter"][0]
    elevation = math.degrees(math.asin(toward[1]))
    assert 20 <= elevation <= 25
    # the camera above: a point on the ground nearer the camera draws lower on the screen than one farther away
    near = _view("three quarter", (toward[0], 0.0, toward[2]))
    far = _view("three quarter", (-toward[0], 0.0, -toward[2]))
    assert near[1] < far[1]


@pytest.mark.parametrize("fixture,name", [("kei_p10_approved.json", "kei"), ("keira_p8_falls_back.json", "keira")])
@pytest.mark.parametrize("follow", [False, True])
def test_the_whole_figure_stays_inside_every_panel_on_every_frame(fixture, name, follow):
    from kei.characters import load_character
    from kei.render import (CHARACTER_VIEWS, LABEL, POST_VIEWS, _character_parts, _scale, _view, bake,
                            character_points, fit, travel_line)
    ch = load_character(name)
    shot = json.loads((WALK.parent / fixture).read_text(encoding="utf-8"))
    shot = {**shot, "props": {**(shot.get("props") or {}), "proportions": ch.proportions}}
    frames = bake(shot, "spline")
    parts = [_character_parts(ch, fr["pose"]) for fr in frames]
    pts = [{**character_points(p), "pelvis": fr["joints"]["pelvis"]} for p, fr in zip(parts, frames)]
    views = tuple(dict.fromkeys(CHARACTER_VIEWS + POST_VIEWS))
    bounds = fit(pts, views, follow=travel_line(shot, frames) if follow else None)
    size = 200
    for f, pp in enumerate(parts):
        for view in ("three quarter", "side", "front"):
            c_h, c_v, span = bounds[f][view]
            s = _scale(span, size)
            for p in pp:
                for v in p.verts:
                    h, u = _view(view, v)
                    x, y = size / 2 + (h - c_h) * s, LABEL + (size - LABEL) / 2 - (u - c_v) * s
                    assert 0 <= x < size and LABEL <= y < size, (view, f, round(x), round(y))


def test_a_post_has_no_line_of_travel_and_a_review_keeps_it(tmp_path):
    """The raised three quarter view of a post shows the figure alone; a review render keeps the line of travel."""
    from kei.characters import load_character, rest_pose
    from kei.render import GROUND, draw_character_views
    shot = json.loads(WALK.read_text(encoding="utf-8"))
    src = tmp_path / "shot.json"
    src.write_text(json.dumps({**shot, "frames": 2, "loop": False}), encoding="utf-8")
    r = render_post(src, tmp_path / "post", "spline", "kei", height=200, name="kei_walk", video=False)
    w, h, px = decode(r["frames"][0].read_bytes())
    assert not any(px(x, y) == GROUND for y in range(h // 2) for x in range(w // 2, w))   # the three quarter panel
    kei = load_character("kei")
    w, h, px = decode(draw_character_views(kei, rest_pose(kei), size=200, views=("three quarter",)))
    assert any(px(x, y) == GROUND for y in range(h) for x in range(w))


def _foot(y):
    from kei.characters.mesh import Part
    sole = [(x, y, z) for x in (-0.05, 0.05) for z in (-0.06, 0.16)]
    return [Part("foot_l", "body", sole, [(0, 1, 0)] * 4, [], 0)]


def test_a_planted_foot_casts_a_soft_shadow_and_a_lifted_one_casts_none():
    from kei.render import _contact_shadows
    from kei.sheet import WHITE, _Canvas

    def to_px(p):                       # a plain top view: 1000 px a metre, the foot in the middle
        return 100 + p[0] * 1000, 100 - p[2] * 1000
    planted, lifted = _Canvas(200, 200), _Canvas(200, 200)
    _contact_shadows(planted, 0, 0, _foot(0.0), to_px)
    _contact_shadows(lifted, 0, 0, _foot(0.3), to_px)
    centre = (50 * 200 + 100) * 3                       # under the middle of the sole (x 0, z 0.05)
    assert planted.px[centre] < WHITE[0] - 10
    edge = (50 * 200 + 190) * 3                         # 9 cm beside the sole: untouched
    assert planted.px[edge] == WHITE[0]
    assert bytes(lifted.px) == bytes(_Canvas(200, 200).px)
