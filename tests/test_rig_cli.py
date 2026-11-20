import json
import os
import time

import pytest

from kei.cli import main
from kei.gates.pipeline import check
from kei.prompts import HERE as PROMPTS
from kei.rig import CHANNELS
from shotkit import full

WALK = {"rig": "v4", "fps": 12, "frames": 16, "loop": False, "keys": [
    {"f": 0, "name": "contact", "root": [0, 0.95, 0], "footL": [-0.1, 0.08, 0.3], "footR": [0.1, 0.08, -0.3],
     "rollL": [-0.3], "rollR": [0.7], "armL": [-0.4, 0.12, 0], "armR": [0.4, 0.12, 0]},
    {"f": 4, "name": "down", "root": [0, 0.9, 0.15], "rollL": [0], "rollR": [1.0], "spine": [0.15, 0, 0]},
    {"f": 8, "name": "passing", "root": [0, 0.97, 0.3], "footR": [0.1, 0.2, 0.3], "rollR": [0], "spine": [0.05, 0, 0]},
    {"f": 16, "name": "contact", "root": [0, 0.95, 0.6], "footR": [0.1, 0.08, 0.9], "rollR": [-0.3], "rollL": [0.7],
     "armL": [0.4, 0.12, 0], "armR": [-0.4, 0.12, 0]},
]}


def shot_dir(tmp_path, pass_name="blocking", shot=WALK):
    root = tmp_path / "walk"
    (root / f"out_{pass_name}").mkdir(parents=True)
    (root / f"out_{pass_name}" / "shot.json").write_text(json.dumps(shot), encoding="utf-8")
    return root


def test_pose_prints_the_joints(tmp_path, capsys):
    p = tmp_path / "pose.json"
    p.write_text(json.dumps({"armR": [1.5, 0.2, 0]}), encoding="utf-8")
    assert main(["pose", str(p)]) == 0
    joints = json.loads(capsys.readouterr().out)
    assert set(joints) >= {"hand_r", "head_top", "ball_l_tip", "heel_r", "com"}
    assert len(joints["hand_r"]) == 3


def test_pose_with_an_unknown_channel_exits_1(tmp_path, capsys):
    p = tmp_path / "pose.json"
    p.write_text(json.dumps({"armRight": [1.5, 0.2, 0]}), encoding="utf-8")
    assert main(["pose", str(p)]) == 1
    assert "armRight" in "".join(capsys.readouterr())


def test_pose_missing_file_exits_1(tmp_path, capsys):
    assert main(["pose", str(tmp_path / "none.json")]) == 1
    assert "".join(capsys.readouterr()).startswith("kei: ")


def test_render_blocking_end_to_end(tmp_path, capsys):
    root = shot_dir(tmp_path)
    assert main(["render", str(root), "blocking", "--size", "48"]) == 0
    out = root / "out_blocking"
    said = capsys.readouterr().out
    playback = [p for p in (out / "blocking.mp4", out / "blocking.gif") if p.is_file()]
    assert len(playback) == 1 and playback[0].name in said
    assert len(list((out / "frames").glob("f*.png"))) == 17
    # the gate's key stills: one per key of the shot, by frame
    assert sorted(p.name for p in out.glob("key_f*.png")) == [f"key_f{k['f']:04d}.png" for k in WALK["keys"]]
    assert (out / "keys.png").is_file()
    assert not [m for m in check(str(root))[0] if m.startswith("P8") and "still" in m]


def test_render_defaults_to_step_for_blocking_and_spline_after(tmp_path, capsys):
    root = shot_dir(tmp_path)
    main(["render", str(root), "blocking", "--size", "48"])
    assert "mode step" in capsys.readouterr().out
    (root / "out_p1").mkdir()
    (root / "out_p1" / "shot.json").write_text(json.dumps(WALK), encoding="utf-8")
    main(["render", str(root), "p1", "--size", "48"])
    assert "mode spline" in capsys.readouterr().out
    main(["render", str(root), "p1", "--mode", "linear", "--size", "48"])
    assert "mode linear" in capsys.readouterr().out


def test_render_without_a_shot_json_exits_1(tmp_path, capsys):
    (tmp_path / "s").mkdir()
    assert main(["render", str(tmp_path / "s"), "blocking"]) == 1
    assert "shot.json" in "".join(capsys.readouterr())


def test_render_a_bad_key_exits_1_and_names_it(tmp_path, capsys):
    bad = {**WALK, "keys": [{"f": 0}, {"f": 5, "elbowLeft": [0.5, 0]}]}
    root = shot_dir(tmp_path, shot=bad)
    assert main(["render", str(root), "blocking"]) == 1
    out = "".join(capsys.readouterr())
    assert "elbowLeft" in out and "f 5" in out


def test_render_a_shot_that_is_not_v4_exits_1(tmp_path, capsys):
    root = shot_dir(tmp_path, shot={**WALK, "rig": "v2"})
    assert main(["render", str(root), "blocking"]) == 1
    assert "v4" in "".join(capsys.readouterr())


BAD_SHOTS = {
    "fps_text": ({**WALK, "fps": "fast"}, "fps"),
    "fps_zero": ({**WALK, "fps": 0}, "fps"),
    "fps_inf": ({**WALK, "fps": float("inf")}, "fps"),
    "f_nan": ({**WALK, "keys": [{"f": 0}, {"f": float("nan")}]}, '"f"'),
    "prop_unknown": ({**WALK, "props": {"proportions": {"femur": 0.5}}}, "femur"),
    "prop_text": ({**WALK, "props": {"proportions": {"thigh": "long"}}}, "thigh"),
    "prop_spine_4": ({**WALK, "props": {"proportions": {"spine": [0.1, 0.1, 0.1, 0.1]}}}, "spine"),
    "prop_spine_text": ({**WALK, "props": {"proportions": {"spine": [0.1, 0.1, "a", 0.1, 0.1]}}}, "spine"),
    "prop_neck_3": ({**WALK, "props": {"proportions": {"neck": [0.05, 0.05, 0.05]}}}, "neck"),
    "prop_neck_number": ({**WALK, "props": {"proportions": {"neck": 0.1}}}, "neck"),
    "prop_not_object": ({**WALK, "props": {"proportions": [1, 2]}}, "proportions"),
    "prop_thigh_zero": ({**WALK, "props": {"proportions": {"thigh": 0}}}, "thigh"),
    "prop_negative": ({**WALK, "props": {"proportions": {"head": -0.1}}}, "head"),
    "leg_scale_zero": ({**WALK, "keys": [{"f": 0}, {"f": 4, "legSL": 0}]}, "legSL"),
    "arm_scale_zero": ({**WALK, "keys": [{"f": 0, "armSR": 0}]}, "armSR"),
}


@pytest.mark.parametrize("cmd", ["render", "bake"])
@pytest.mark.parametrize("case", list(BAD_SHOTS), ids=list(BAD_SHOTS))
def test_a_bad_shot_gives_one_line_and_exits_1(tmp_path, capsys, cmd, case):
    shot, word = BAD_SHOTS[case]
    root = shot_dir(tmp_path, "p1", shot)
    assert main([cmd, str(root), "p1"]) == 1
    out = capsys.readouterr()
    assert out.err.startswith("kei: ") and len(out.err.strip().splitlines()) == 1 and word in out.err
    assert "Traceback" not in out.err and out.out == ""


@pytest.mark.parametrize("cmd", ["render", "bake"])
def test_a_truncated_shot_json_gives_one_line_and_exits_1(tmp_path, capsys, cmd):
    root = shot_dir(tmp_path, "p1")
    src = root / "out_p1" / "shot.json"
    src.write_text(src.read_text(encoding="utf-8")[:57], encoding="utf-8")
    assert main([cmd, str(root), "p1"]) == 1
    out = "".join(capsys.readouterr())
    assert out.startswith("kei: ") and len(out.strip().splitlines()) == 1 and "JSON" in out


def test_bake_writes_per_frame_joints(tmp_path, capsys):
    root = shot_dir(tmp_path, "p1")
    assert main(["bake", str(root), "p1"]) == 0
    data = json.loads((root / "out_p1" / "joints.json").read_text(encoding="utf-8"))
    assert data["fps"] == 12 and data["mode"] == "spline"
    assert [fr["f"] for fr in data["frames"]] == list(range(17))
    assert len(data["frames"][3]["joints"]["calf_l"]) == 3
    assert "joints.json" in capsys.readouterr().out


def test_bake_without_a_shot_exits_1(tmp_path):
    (tmp_path / "s").mkdir()
    assert main(["bake", str(tmp_path / "s"), "p1"]) == 1


@pytest.mark.parametrize("name", ["blocking.md", "passes.md"])
def test_prompts_state_the_format_the_channels_and_the_commands(name):
    text = (PROMPTS / name).read_text(encoding="utf-8")
    for cmd in ("kei pose", "kei render", "kei bake"):
        assert cmd in text, cmd
    assert '"rig": "v4"' in text and "whole poses" in text
    for c in CHANNELS:
        if c not in ("gripR", "bladeS"):
            assert c in text, c


def test_blocking_gate_accepts_a_gif(tmp_path):
    root = tmp_path / "shots" / "box_fall"
    root.mkdir(parents=True)
    full(root)
    mp4 = root / "out_blocking" / "blocking.mp4"
    t = os.path.getmtime(mp4)
    mp4.unlink()
    gif = root / "out_blocking" / "blocking.gif"
    gif.write_text("x")
    os.utime(gif, (t, t))
    assert not [m for m in check(str(root))[0] if m.startswith(("P8", "ORDER"))]


def test_blocking_gate_needs_two_key_stills(tmp_path):
    root = tmp_path / "shots" / "box_fall"
    root.mkdir(parents=True)
    full(root)
    out = root / "out_blocking"
    for p in out.glob("*.png"):
        p.unlink()
    (out / "keys.png").write_text("x")
    (out / "key_f0000.png").write_text("x")
    (out / "frames").mkdir()
    (out / "frames" / "f0001.png").write_text("x")
    # one key still plus the key sheet is a one-key blocking: it misses
    assert any(m.startswith("P8") and "key still" in m for m in check(str(root))[0])
    (out / "key_f0009.png").write_text("x")
    assert not [m for m in check(str(root))[0] if m.startswith("P8")]


def test_blocking_gate_without_a_playback_still_misses(tmp_path):
    root = tmp_path / "shots" / "box_fall"
    root.mkdir(parents=True)
    full(root)
    (root / "out_blocking" / "blocking.mp4").unlink()
    assert any(m.startswith("P8 no out_blocking/blocking.mp4") for m in check(str(root))[0])


def test_order_uses_the_gif_when_there_is_no_mp4(tmp_path):
    root = tmp_path / "shots" / "box_fall"
    root.mkdir(parents=True)
    full(root)
    (root / "out_blocking" / "blocking.mp4").unlink()
    gif = root / "out_blocking" / "blocking.gif"
    gif.write_text("x")
    later = time.time() + 1000
    os.utime(gif, (later, later))
    assert any(m.startswith("ORDER out_p1") for m in check(str(root))[0])
