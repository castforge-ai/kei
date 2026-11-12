"""Fixes from the branch review: the configured character reaches the seat, emission is clamped, a shot needs a pass."""
import json
import os
from dataclasses import replace

from kei.characters import load_character, rest_pose
from kei.cli import main
from kei.render import draw_character_views
from kei.seats import FakeSeat
from test_conductor import CFG, Recorder, run_shot, shot, stage_of
from test_shot_character import STAND, shot_folder


def test_the_seat_sees_the_configured_character_and_the_brief_names_it(tmp_path, monkeypatch):
    monkeypatch.delenv("KEI_CHARACTER", raising=False)
    seen = []

    def fault(sid, n, r):
        seen.append(os.environ.get("KEI_CHARACTER"))
        return False

    rec = Recorder(fault)
    run_shot(shot(tmp_path), "a stand", replace(CFG, character="keira"), animator=FakeSeat("fake", rec))
    assert seen and set(seen) == {"keira"}
    brief = next(p for p in rec.prompts if stage_of(p) == "Brief")
    assert "configured default is keira" in brief
    assert os.environ.get("KEI_CHARACTER") is None          # restored after the run


def test_render_takes_the_seat_default_without_reading_a_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("KEI_CHARACTER", "keira")
    root = shot_folder(tmp_path)
    assert main(["bake", str(root), "p1", "--config", str(tmp_path / "missing.toml")]) == 0
    data = json.loads((root / "out_p1" / "joints.json").read_text(encoding="utf-8"))
    assert data["character"] == "keira"


def test_a_named_character_needs_no_config(tmp_path, monkeypatch):
    monkeypatch.delenv("KEI_CHARACTER", raising=False)
    root = shot_folder(tmp_path, {**STAND, "character": "kei"})
    assert main(["bake", str(root), "p1", "--config", str(tmp_path / "missing.toml")]) == 0


def test_emission_is_clamped_like_the_export():
    ch = load_character("kei")
    pose = rest_pose(ch)
    one = draw_character_views(ch, pose, size=120, views=("front",), emission=1.0)
    assert draw_character_views(ch, pose, size=120, views=("front",), emission=3.0) == one
    zero = draw_character_views(ch, pose, size=120, views=("front",), emission=0.0)
    assert draw_character_views(ch, pose, size=120, views=("front",), emission=-1.0) == zero


def test_a_shot_without_a_pass_is_refused_even_with_a_character(tmp_path, capsys):
    root = shot_folder(tmp_path)
    assert main(["render", str(root), "--character", "kei", "--out", str(tmp_path / "x")]) == 1
    assert "pass" in capsys.readouterr().out
    assert not (tmp_path / "x").exists()
