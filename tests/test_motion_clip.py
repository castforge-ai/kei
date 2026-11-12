"""The README motion clip in tools/validate_characters.py: a loop that starts and ends on rest, framed once for the
whole clip, drawn with no label on a light background."""
import importlib.util
from pathlib import Path

import pytest

from kei.characters import CHARACTERS, load_character, rest_pose
from kei.characters.mesh import pose_mesh
from kei.sample import bake

TOOL = Path(__file__).resolve().parents[1] / "tools" / "validate_characters.py"


@pytest.fixture(scope="module")
def vc():
    spec = importlib.util.spec_from_file_location("validate_characters", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("name", CHARACTERS)
def test_motion_clip_is_a_seamless_loop_on_rest(vc, name):
    rest = rest_pose(load_character(name))
    keys = vc.clip_motion(rest)
    fs = [k["f"] for k in keys]
    assert fs == sorted(fs) and fs[0] == 0
    assert 72 <= fs[-1] <= 144                      # 3 to 6 s at 24 fps
    strip = [{c: v for c, v in k.items() if c not in ("f", "name")} for k in (keys[0], keys[-1])]
    assert strip[0] == strip[1] == rest             # the loop opens and closes on the character's own rest
    assert {"wave out", "point", "offer palm up", "twist and look back"} <= {k["name"] for k in keys}


def test_motion_framing_holds_every_frame(vc):
    ch = load_character("kei")
    keys = vc.clip_motion(rest_pose(ch))
    shot = {"rig": "v4", "fps": 24, "frames": keys[-1]["f"], "loop": True, "keys": keys,
            "props": {"proportions": ch.proportions}}
    frames = bake(shot, "spline")[:shot["frames"]:12]
    parts = [pose_mesh(ch, fr["pose"]) for fr in frames]
    bounds = vc.motion_bounds(parts)
    assert set(bounds) == set(vc.MOTION_VIEWS)
    height = 120
    widths = vc.motion_widths(bounds, height)
    assert all(w % 2 == 0 and w > 0 for w in widths.values())
    for p in (parts[0], parts[len(parts) // 2]):
        cv = vc.motion_frame(ch, p, bounds, height, widths)
        assert (cv.w, cv.h) == (sum(widths.values()), height)
        px = cv.px
        corners = [tuple(px[i:i + 3]) for i in (0, (cv.w - 1) * 3, (cv.h - 1) * cv.w * 3)]
        assert all(c == vc.MOTION_BG for c in corners)      # no border, no label: the light background
        figure = sum(1 for i in range(0, len(px), 3) if tuple(px[i:i + 3]) not in (vc.MOTION_BG, vc.MOTION_GROUND))
        assert figure > 0.08 * cv.w * cv.h                  # the figure fills a good part of the frame
