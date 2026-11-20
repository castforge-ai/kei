"""A long render is drawn in several processes, and its frames are the same as one process draws."""
import json
import shutil
from pathlib import Path

import pytest

from kei.render import render_post, render_shot

ROOT = Path(__file__).resolve().parent.parent
WALK = json.loads((ROOT / "tests" / "fixtures" / "walks" / "kei_p10_approved.json").read_text(encoding="utf-8"))
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is not installed")


@needs_ffmpeg
def test_parallel_frames_match_the_serial_ones(tmp_path):
    src = tmp_path / "shot.json"
    src.write_text(json.dumps({**WALK, "loop": False}), encoding="utf-8")
    a = render_post(src, tmp_path / "one", "spline", "kei", height=96, workers=1, video=False)
    b = render_post(src, tmp_path / "two", "spline", "kei", height=96, workers=2, video=False)
    assert len(a["frames"]) == len(b["frames"]) >= 24
    assert all(x.read_bytes() == y.read_bytes() for x, y in zip(a["frames"], b["frames"]))
    c = render_shot(src, tmp_path / "three", "spline", size=48, character="kei", workers=2)
    assert c["kind"] == "mp4" and len(list((tmp_path / "three" / "frames").glob("f*.png"))) == len(a["frames"])
