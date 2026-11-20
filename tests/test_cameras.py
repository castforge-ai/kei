"""The follow camera and the plan's delivery camera: a travelling loop can be judged in Kei's own renders."""
import json
import math

import pytest

from kei.characters.profile import decode_png
from kei.cli import main
from kei.render import Camera, render_shot, stride_tick
from kei.sample import ShotError

WALK = {"rig": "v4", "fps": 24, "frames": 8, "loop": True, "keys": [
    {"f": 0, "root": [0, 0.9, 0.0], "footL": [-0.12, 0.09, 0.2, 0, 0], "footR": [0.12, 0.09, -0.2, 0, 0]},
    {"f": 4, "root": [0, 0.92, 0.6], "footL": [-0.12, 0.09, 0.2, 0, 0], "footR": [0.12, 0.09, 1.0, 0, 0]},
    {"f": 8, "root": [0, 0.9, 1.2], "footL": [-0.12, 0.09, 1.4, 0, 0], "footR": [0.12, 0.09, 1.0, 0, 0]}]}


def write(tmp_path, shot, camera=None):
    out = tmp_path / "out_blocking"
    out.mkdir(parents=True, exist_ok=True)
    (out / "shot.json").write_text(json.dumps(shot), encoding="utf-8")
    if camera is not None:
        (tmp_path / "plan").mkdir(exist_ok=True)
        (tmp_path / "plan" / "plan.json").write_text(json.dumps({"keys": [], "camera": camera}), encoding="utf-8")
    return out / "shot.json"


def figure_columns(png: bytes, x0: int, x1: int) -> tuple[float, int]:
    """The middle column of the figure's pixels (above the ground, off the background) between x0 and x1."""
    w, h, rows = decode_png(png)
    xs = [x for y in range(20, int(h * 0.6)) for x in range(x0 + 2, x1 - 2)
          if sum(abs(c - 250) for c in rows[y][x]) > 40]
    return (sum(xs) / len(xs) if xs else -1), len(xs)


def side_drift(frames, size):
    centres = [figure_columns(p.read_bytes(), size, 2 * size)[0] for p in frames]   # the side panel is second
    return max(centres) - min(centres)


def test_stride_ticks_repeat_over_one_cycle():
    assert stride_tick(1.2) == pytest.approx(0.6)      # 1.2 m a cycle: two ticks of 0.6 m, so the seam repeats
    assert stride_tick(1.28) == pytest.approx(0.427, abs=1e-3)
    assert stride_tick(0.0) == pytest.approx(0.5)


def test_the_follow_camera_keeps_a_travelling_walk_in_place(tmp_path):
    src = write(tmp_path, WALK)
    fixed = render_shot(src, tmp_path / "fixed", "spline", size=120, character="kei")
    follow = render_shot(src, tmp_path / "follow", "spline", size=120, character="kei", camera="follow")
    assert side_drift(fixed["frames"][:-1], 120) > 20          # with the fixed camera the walk crosses the panel
    assert side_drift(follow["frames"][:-1], 120) < 6          # the follow camera rides the travel


def test_camera_from_the_plan_is_side_at_yaw_0_and_front_at_yaw_90():
    side = Camera.from_plan({"yaw_deg": 0, "target_m": [0, 0.9, 0], "span_m": 2})
    front = Camera.from_plan({"yaw_deg": 90, "target_m": [0, 0.9, 0], "span_m": 2})
    assert side.project((0, 1, 1))[0] == pytest.approx(1)      # forward is screen right from the side
    assert front.project((1, 1, 0))[0] == pytest.approx(-1)    # the character's right is screen left from the front


def test_a_perspective_camera_matches_the_target_plane_and_shrinks_what_is_farther():
    cam = Camera.from_plan({"yaw_deg": 0, "target_m": [0, 0.95, 0], "lens_mm": 50, "distance_m": 6.5})
    assert cam.project((0, 1.45, 0.3)) == pytest.approx((0.3, 1.45))     # on the target plane: true size
    far = cam.project((-0.5, 1.45, 0.3))                                 # half a metre farther from the camera
    assert 0 < far[0] < 0.3
    assert cam.span == pytest.approx(6.5 * 20.25 / 50, rel=1e-3)         # the frame's height at the target


def test_kei_render_through_the_delivery_camera(tmp_path, capsys):
    write(tmp_path, WALK, {"yaw_deg": 5, "target_m": [0, 0.95, 0.6], "lens_mm": 50, "distance_m": 6.5,
                           "aspect": "16:9", "follow": True})
    assert main(["render", str(tmp_path), "blocking", "--camera", "delivery", "--size", "90"]) == 0
    out = tmp_path / "out_blocking" / "delivery"
    w, h, _ = decode_png((out / "frames" / "f0000.png").read_bytes())
    assert (w, h) == (160, 90)
    assert "delivery" in capsys.readouterr().out


def test_delivery_without_a_plan_camera_says_what_to_add(tmp_path, capsys):
    write(tmp_path, WALK)
    assert main(["render", str(tmp_path), "blocking", "--camera", "delivery"]) == 1
    out = "".join(capsys.readouterr())
    assert 'plan/plan.json has no "camera"' in out


def test_a_bad_camera_is_refused_with_its_key():
    with pytest.raises(ShotError, match="yaw_deg"):
        Camera.from_plan({"yaw_deg": "side", "target_m": [0, 1, 0], "span_m": 2})


def test_an_unknown_camera_key_is_refused_with_its_name():
    with pytest.raises(ShotError, match="yaw_degrees"):
        Camera.from_plan({"yaw_degrees": 90, "target_m": [0, 1, 0], "span_m": 2})


def test_a_camera_may_carry_a_name_and_notes():
    cam = Camera.from_plan({"name": "delivery", "yaw_note": "three quarter", "yaw_deg": 30, "target_m": [0, 1, 0],
                            "span_m": 2})
    assert cam is not None
