"""The Blender adapter: Kei's key poses keyed in a background Blender, the joints Blender plays read back for the
checks, previews rendered there. The conversions are checked without Blender; the live tests run when Blender is
installed and skip with the reason when it is not."""
import json
import math
import shutil

import pytest

from kei.apps import blender_shot as bs
from kei.apps.blender import BlenderError, find_blender
from kei.characters import load_character, on_character, rest_pose
from kei.cli import EXIT_DONE, EXIT_ERROR, main
from kei.config import ConfigError, load_config
from kei.rig import skeleton
from kei.sample import bake

SHOT = {"rig": "v4", "fps": 24, "frames": 12, "character": "kei",
        "keys": [{"f": 0, "root": [0, 0.915, 0], "footL": [-0.15, 0.09, 0], "footR": [0.15, 0.09, 0]},
                 {"f": 6, "root": [0.05, 0.86, 0.1], "spine": [0.6, 0.2, 0.3], "armR": [1.4, 0.3, 0.4],
                  "elbowR": [1.2, 0.5], "head": [0.3, 0, 0.6], "footL": [-0.15, 0.09, 0],
                  "footR": [0.2, 0.25, 0.25, 0.4, 0]},
                 {"f": 12, "root": [0, 0.915, 0.2], "footL": [-0.15, 0.09, 0.2], "footR": [0.15, 0.09, 0.2]}]}


def _cols(axes):
    return [[axes[c][r] for c in range(3)] for r in range(3)]


def _mm(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)] for r in range(3)]


def _t(m):
    return [[m[c][r] for c in range(3)] for r in range(3)]


def fake_samples(shot, ch):
    """What Blender gives back when it plays Kei's poses exactly: each bone's head and its turn from rest, in
    Blender's axes."""
    rest = skeleton(rest_pose(ch), ch.proportions)
    out = []
    for fr in bake(on_character(shot, ch)):
        B = skeleton(fr["pose"], ch.proportions)
        pos, turn = {}, {}
        for n in bs.key_job(shot, ch, "spline")["sample"]:
            pos[n] = list(bs._mul(bs.C, B[n].head))
            d = _mm(_cols(B[n].frame), _t(_cols(rest[n].frame)))
            turn[n] = _mm(_mm(bs.C, d), _t(bs.C))
        out.append({"f": fr["f"], "pos": pos, "turn": turn})
    return out


def test_the_joints_come_back_as_kei_solves_them():
    ch = load_character("keira")
    got = bs.joints_from_blender(fake_samples(SHOT, ch), ch)
    want = bake(on_character(SHOT, ch))
    for g, w in zip(got, want):
        for n, p in w["joints"].items():
            assert math.dist(g["joints"][n], p) < 1e-4, (g["f"], n)


def test_the_key_job_holds_whole_poses_on_the_key_frames():
    ch = load_character("kei")
    job = bs.key_job(SHOT, ch, "step")
    assert [k["f"] for k in job["keys"]] == [0, 6, 12] and job["interpolation"] == "CONSTANT"
    assert bs.key_job(SHOT, ch, "spline")["interpolation"] == "BEZIER"
    k = job["keys"][1]
    assert set(k["poles"]) == {"l", "r"} and "finger" not in str(sorted(k["poles"]))
    B = skeleton(bake(on_character(SHOT, ch))[6]["pose"], ch.proportions)
    assert k["bones"]["hand_r"]["head"] == list(B["hand_r"].head)
    knee = B["calf_l"].head
    assert abs(math.dist(k["poles"]["l"], knee) - bs.POLE_M) < 1e-9
    assert k["poles"]["l"][2] > knee[2]                      # in front of the knee


def test_kei_bake_refuses_a_blender_shot(tmp_path, capsys):
    (tmp_path / "s" / "blender").mkdir(parents=True)
    (tmp_path / "s" / "out_p1").mkdir()
    (tmp_path / "s" / "out_p1" / "shot.json").write_text(json.dumps(SHOT), encoding="utf-8")
    assert main(["bake", str(tmp_path / "s"), "p1"]) == EXIT_ERROR
    assert "kei blender key" in "".join(capsys.readouterr())


def test_the_config_takes_blender(tmp_path):
    from kei.config import example_config
    base = example_config().read_text(encoding="utf-8").split("[apps]")[0]
    p = tmp_path / "kei.toml"
    p.write_text(base + '[apps]\napp = "blender"\n[apps.blender]\npath = "C:/Blender/blender.exe"\n', encoding="utf-8")
    c = load_config(p)
    assert c.app == "blender" and c.blender == "C:/Blender/blender.exe"
    p.write_text(base + '[apps.blender]\npath = 3\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="apps.blender.path"):
        load_config(p)


def test_a_missing_blender_says_where_to_set_it(tmp_path, monkeypatch):
    monkeypatch.setenv("KEI_BLENDER", str(tmp_path / "nope.exe"))
    with pytest.raises(BlenderError, match="KEI_BLENDER"):
        find_blender()


# ---- live, in Blender -----------------------------------------------------------------------------------------------

def _blender():
    try:
        return find_blender()[0]
    except BlenderError as e:
        pytest.skip(f"no Blender: {e}")


@pytest.fixture(scope="module")
def keyed(tmp_path_factory):
    _blender()
    shot = tmp_path_factory.mktemp("bl") / "shot"
    (shot / "out_p1").mkdir(parents=True)
    (shot / "out_p1" / "shot.json").write_text(json.dumps(SHOT), encoding="utf-8")
    assert main(["blender", "setup", str(shot), "--character", "kei"]) == EXIT_DONE
    assert main(["blender", "key", str(shot), "p1"]) == EXIT_DONE
    return shot


def test_blender_plays_the_key_poses_exactly(keyed):
    data = json.loads((keyed / "out_p1" / "joints.json").read_text())
    assert data["source"] == "blender" and len(data["frames"]) == 13
    want = bake(on_character(SHOT, load_character("kei")))
    for f in (0, 6, 12):
        worst = max(math.dist(data["frames"][f]["joints"][n], p) for n, p in want[f]["joints"].items())
        assert worst < 0.001, (f, worst)
    rig = json.loads((keyed / "rig" / "blender_rig.json").read_text())
    assert max(p["knee_error_m"] for p in rig["poles"].values()) < 0.001
    assert (keyed / "out_p1" / "scene.blend").is_file()


def test_kei_check_measures_what_blender_plays(keyed):
    assert main(["check", str(keyed), "p1"]) in (0, 1, 2, 3)
    report = json.loads((keyed / "out_p1" / "body_check" / "body_check.json").read_text())
    assert report["joints_from"] == "blender"


def test_kei_render_makes_blender_previews(keyed):
    if shutil.which("ffmpeg") is None:
        pytest.skip("no ffmpeg")
    assert main(["render", str(keyed), "p1"]) == EXIT_DONE
    for view in bs.VIEWS:
        assert (keyed / "out_p1" / "blender_render" / f"{view}.mp4").stat().st_size > 1000


# ---- the run --------------------------------------------------------------------------------------------------------

def test_a_blender_run_with_no_blender_pauses_with_the_reason(tmp_path, monkeypatch):
    from kei.config import Config, SeatSpec
    from kei.conductor import run_shot
    from kei.seats import FakeSeat
    from test_conductor import Recorder, shot
    monkeypatch.setenv("KEI_BLENDER", str(tmp_path / "no_blender.exe"))
    cfg = Config(animator=SeatSpec(name="fake", cmd=["unused"]), app="blender")
    rec = Recorder()
    state = run_shot(shot(tmp_path), "a box falls", cfg, animator=FakeSeat("fake", rec), review=lambda s, d, c: [])
    assert state.status == "paused_machine" and rec.prompts == []
    assert "KEI_BLENDER" in json.dumps(state.history[-1])


def test_a_blender_run_sets_the_scene_up_before_the_first_stage(tmp_path):
    _blender()
    from kei.config import Config, SeatSpec
    from kei.conductor import run_shot
    from kei.seats import FakeSeat
    from test_conductor import Recorder, shot
    root = shot(tmp_path)
    cfg = Config(animator=SeatSpec(name="fake", cmd=["unused"]), app="blender")
    run_shot(root, "a box falls", cfg, animator=FakeSeat("fake", Recorder()), review=lambda s, d, c: [])
    assert bs.scene_path(root).is_file()
    assert json.loads((root / "rig" / "blender_rig.json").read_text())["character"] == "kei"
