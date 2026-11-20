"""kei trails: part paths with a dot per frame, one pass or several overlaid."""
import json
from pathlib import Path

import pytest

from kei.cli import main
from kei.trails import TrailsError, draw_trails
from test_sheet import decode

ROOT = Path(__file__).resolve().parent.parent
WALK = {**json.loads((ROOT / "tests" / "fixtures" / "walks" / "kei_p10_approved.json").read_text(encoding="utf-8")),
        "loop": False}


def _pass(root, name):
    d = root / f"out_{name}"
    d.mkdir(parents=True)
    (d / "shot.json").write_text(json.dumps(WALK), encoding="utf-8")


def test_two_passes_overlay_in_their_colours(tmp_path):
    _pass(tmp_path, "p1")
    _pass(tmp_path, "p2")
    out = draw_trails(tmp_path, ["p1", "p2"], ["hand_l_tip", "head"], "0-20", "kei")
    w, h, px = decode(out.read_bytes())
    assert out == tmp_path / "out_p2" / "trails" / "trails.png" and w == 1040
    colours = {px(x, y) for y in range(0, h, 2) for x in range(0, w, 2)}
    assert (40, 110, 200) in colours and (200, 60, 40) in colours


def test_an_unknown_part_is_refused_and_the_cli_writes_the_file(tmp_path, capsys):
    _pass(tmp_path, "p1")
    with pytest.raises(TrailsError, match="no part"):
        draw_trails(tmp_path, ["p1"], ["wing"], None, "kei")
    assert main(["trails", str(tmp_path), "p1", "--parts", "pelvis", "--character", "kei"]) == 0
    assert "trails.png" in capsys.readouterr().out
