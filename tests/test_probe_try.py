"""kei probe v2 (speed, acceleration, balance margin, channels, palm gap, relative positions), kei try, kei sweep."""
import json

import pytest

from kei.cli import main
from kei.probe import ProbeError, probe
from test_pose_record import WALK, _shot

FULL = json.loads(WALK.read_text(encoding="utf-8"))["frames"]


def test_probe_reads_speed_acceleration_and_an_offset_from_another_joint(tmp_path):
    _shot(tmp_path)
    t = probe(tmp_path, "p1", "1-3", ["hand_l", "hand_l@spine_03", "com_margin", "ch:spine"], "kei")
    r = t["rows"][1]
    assert r["hand_l"]["speed_mps"] >= 0 and r["hand_l"]["accel_g"] is not None
    assert len(r["hand_l@spine_03"]["offset_m"]) == 3
    assert r["com_margin"]["outside_m"] is None or r["com_margin"]["outside_m"] >= 0
    assert r["ch:spine"]["value"] is not None


def test_probe_reads_the_palms_gap_to_an_object(tmp_path):
    _shot(tmp_path, objects=[{"name": "ball", "shape": "sphere", "size": [0.2], "rest": [0.5, 0.1, 0.0]}])
    r = probe(tmp_path, "p1", "0", ["palm_gap:ball"], "kei")["rows"][0]
    assert r["palm_gap:ball"]["l"] > 0 and r["palm_gap:ball"]["r"] > 0


def test_probe_refuses_a_channel_or_object_that_is_not_there(tmp_path):
    _shot(tmp_path)
    for name in ("ch:wings", "palm_gap:crate", "hand_l@wing"):
        with pytest.raises(ProbeError):
            probe(tmp_path, "p1", "0", [name], "kei")


def test_probe_prints_the_new_readings_from_the_cli(tmp_path, capsys):
    _shot(tmp_path)
    assert main(["probe", str(tmp_path), "p1", "--character", "kei", "--frames", "1-2", "--joints",
                 "hand_l,com_margin,hand_l@pelvis,ch:spine"]) == 0
    out = capsys.readouterr().out
    assert "m/s" in out and " g" in out and "hand_l@pelvis (" in out


def test_kei_try_reports_the_flags_an_edit_brings_and_leaves_the_shot_alone(tmp_path, capsys):
    _shot(tmp_path, frames=FULL)
    before = (tmp_path / "out_p1" / "shot.json").read_bytes()
    assert main(["try", str(tmp_path), "p1", "set", "--frame", "4", "--channel", "root",
                 "--value", "0,0.6,0", "--character", "kei"]) == 0
    out = capsys.readouterr().out
    assert "on a copy" in out and "flags:" in out and "- new:" in out   # a root lifted 0.6 m leaves the floor
    assert (tmp_path / "out_p1" / "shot.json").read_bytes() == before
    assert not (tmp_path / "out_p1" / "body_check").exists()


def test_kei_sweep_prints_a_line_per_value_and_marks_the_fewest_flags(tmp_path, capsys):
    _shot(tmp_path, frames=FULL)
    assert main(["sweep", str(tmp_path), "p1", "--frame", "4", "--channel", "root", "--index", "1",
                 "--from", "0", "--to", "0.6", "--steps", "3", "--character", "kei"]) == 0
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("- ")]
    assert len(lines) == 3 and sum("fewest flags" in ln for ln in lines) == 1
    assert json.loads((tmp_path / "out_p1" / "shot.json").read_text(encoding="utf-8"))["frames"] == FULL
