"""Task 10 of plan 7: the conductor's Unreal steps, the setup text and the commands. A fake editor, no Unreal."""
import dataclasses
import json

import pytest

from kei.apps import unreal_stage
from kei.apps.unreal import NeedsHuman, UnrealError
from kei.cli import main
from kei.conductor import run_shot as _run_shot
from kei.seats import FakeSeat, SeatResult
from kei.state import ShotState, load_state, save_state
from test_conductor import CFG, IDS, Recorder, passed, shot
from test_unreal_readback import standing
from unrealkit import FakeEditor


def run_shot(*args, **kwargs):
    return _run_shot(*args, review=lambda stage, shot_dir, changed: [], **kwargs)


def cfg_for(fake, **kw):
    return dataclasses.replace(CFG, app="unreal", unreal_url=fake.url, **kw)


def write_unreal_shot(root, pass_name="p1", keys=None):
    out = root / f"out_{pass_name}"
    out.mkdir(parents=True, exist_ok=True)
    keys = keys or [{"f": 0, "pelvis_ctrl.location.z": 90.0}, {"f": 12, "foot_l_ik_ctrl.location.z": 8.0}]
    (out / "shot.json").write_text(json.dumps({"rig": "unreal", "fps": 24, "frames": 12, "keys": keys}))


def test_an_unreal_shot_asks_which_editor_before_any_stage_runs(tmp_path):
    root = shot(tmp_path)
    ed = FakeEditor()
    ran = []
    with ed.server() as fake:
        state = run_shot(root, "a walk", cfg_for(fake),
                         animator=FakeSeat("fake", lambda p, r: ran.append(p) or SeatResult(0, "")))
    assert state.status == "needs_answer" and ran == []
    q = state.questions[0]
    assert q["kind"] == "unreal_target" and "ThirdPersonTest" in q["text"] and "Manny" in q["text"]
    assert "Kei's own rig" in q["text"]


def test_kei_answer_takes_the_number_and_refuses_one_out_of_range(tmp_path, capsys):
    root = shot(tmp_path)
    ed = FakeEditor()
    with ed.server() as fake:
        run_shot(root, "a walk", cfg_for(fake), animator=FakeSeat("fake", lambda p, r: SeatResult(0, "")))
        assert main(["answer", str(root), "--text", "9"]) == 1
        assert "from 1 to 2" in "".join(capsys.readouterr()) and load_state(root).status == "needs_answer"
        assert main(["answer", str(root), "--text", "1"]) == 0
    target = json.loads((root / "unreal" / "target.json").read_text())
    assert target == {"kind": "open", "url": fake.url, "project": "ThirdPersonTest"}


def test_one_full_shot_from_brief_to_needs_approval_every_gate_green(tmp_path):
    root = shot(tmp_path)
    ed = FakeEditor()
    with ed.server() as fake:
        run_shot(root, "a walk", cfg_for(fake), animator=FakeSeat("fake", lambda p, r: SeatResult(0, "")))
        assert main(["answer", str(root), "--text", "1"]) == 0
        state = run_shot(root, "a walk", cfg_for(fake), animator=FakeSeat("fake", Recorder()))
    assert state.status == "needs_approval" and passed(state) == IDS
    rig = json.loads((root / "rig" / "unreal_rig.json").read_text())
    assert rig["source"] == "unreal" and len(rig["controls"]) == 5
    assert fake.scripts.count("read_rig") == 1 and ed.saved == []       # the rig read saved nothing


def test_the_open_setting_with_one_editor_never_asks(tmp_path):
    root = shot(tmp_path)
    ed = FakeEditor()
    with ed.server() as fake:
        state = run_shot(root, "a walk", cfg_for(fake, unreal_session="open"),
                         animator=FakeSeat("fake", Recorder()))
    assert state.status == "needs_approval"
    assert json.loads((root / "unreal" / "target.json").read_text())["kind"] == "open"


def test_choosing_kei_s_own_rig_runs_the_shot_with_no_unreal_at_all(tmp_path):
    root = shot(tmp_path)
    ed = FakeEditor()
    with ed.server() as fake:
        run_shot(root, "a walk", cfg_for(fake), animator=FakeSeat("fake", lambda p, r: SeatResult(0, "")))
        assert main(["answer", str(root), "--text", "2"]) == 0
        n = len(fake.requests)
        state = run_shot(root, "a walk", cfg_for(fake), animator=FakeSeat("fake", Recorder()))
        assert state.status == "needs_approval" and len(fake.requests) == n
    assert not unreal_stage.is_unreal_shot(root) and not (root / "rig" / "unreal_rig.json").exists()


def test_no_editor_asks_with_kei_s_own_rig_and_the_setup_step_and_look_again_asks_afresh(tmp_path):
    root = shot(tmp_path)
    cfg = dataclasses.replace(CFG, app="unreal", unreal_url="http://127.0.0.1:1/mcp")
    state = run_shot(root, "a walk", cfg, animator=FakeSeat("fake", lambda p, r: SeatResult(0, "")))
    assert state.status == "needs_answer" and "kei unreal setup" in state.questions[0]["text"]
    assert main(["answer", str(root), "--text", "1"]) == 0         # look again: nothing is kept
    assert not (root / "unreal" / "target.json").exists()
    ed = FakeEditor()
    with ed.server() as fake:
        state = run_shot(root, "a walk", cfg_for(fake), animator=FakeSeat("fake", lambda p, r: SeatResult(0, "")))
    assert state.status == "needs_answer" and "ThirdPersonTest" in state.questions[0]["text"]


def test_the_editor_stops_answering_during_passes_the_shot_is_paused_for_the_machine_then_resumes(tmp_path):   # Focus 5
    root = shot(tmp_path)
    ed = FakeEditor()
    with ed.server() as fake:
        cfg = cfg_for(fake, unreal_session="open")
        calls = {"n": 0}

        def animator(prompt, shot_dir):
            rec = Recorder()
            result = rec(prompt, shot_dir)
            if "Breakdowns, spline and polish" in prompt and calls["n"] == 0:
                calls["n"] += 1
                write_unreal_shot(shot_dir)
                fake.stopped = True                                    # the editor goes away mid pass
                with pytest.raises(UnrealError):
                    unreal_stage.key_pass(shot_dir, "p1", cfg)
            return result
        state = run_shot(root, "a walk", cfg, animator=FakeSeat("fake", animator))
        assert state.status == "paused_machine" and state.stage == "passes"
        assert "stopped answering" in state.history[-1]["misses"][0]
        assert not (root / "unreal" / "PAUSED.md").exists()
        # still down: the shot stays paused, and says which editor
        state = run_shot(root, "a walk", cfg, animator=FakeSeat("fake", Recorder()))
        assert state.status == "paused_machine" and "does not answer" in state.history[-1]["misses"][0]
        fake.stopped = False                                           # the editor is back
        state = run_shot(root, "a walk", cfg, animator=FakeSeat("fake", Recorder()))
    assert state.status == "needs_approval" and state.stage != "brief"
    assert "passes" in passed(state)


def test_a_user_asset_made_dirty_stops_the_shot_with_needs_human_naming_it(tmp_path):
    root = shot(tmp_path)
    ed = FakeEditor()
    with ed.server() as fake:
        cfg = cfg_for(fake, unreal_session="open")

        def animator(prompt, shot_dir):
            result = Recorder()(prompt, shot_dir)
            if "Breakdowns, spline and polish" in prompt:
                write_unreal_shot(shot_dir)
                ed.user_dirty = "/Game/Maps/Level01"
                with pytest.raises(NeedsHuman):
                    unreal_stage.key_pass(shot_dir, "p1", cfg)
            return result
        state = run_shot(root, "a walk", cfg, animator=FakeSeat("fake", animator))
    assert state.status == "needs_human" and "/Game/Maps/Level01" in state.history[-1]["misses"][0]
    assert ed.saved == []


def test_a_rig_probe_that_leaves_a_control_changed_stops_the_shot_for_a_person(tmp_path):
    root = shot(tmp_path)
    ed = FakeEditor()
    ed.leave_changed = "pelvis_ctrl"
    with ed.server() as fake:
        state = run_shot(root, "a walk", cfg_for(fake, unreal_session="open"),
                         animator=FakeSeat("fake", Recorder()))
    assert state.status == "needs_human" and "pelvis_ctrl" in state.history[-1]["misses"][0]


def test_several_characters_stop_the_shot_until_the_config_names_one(tmp_path):
    from unrealkit import MANNY
    root = shot(tmp_path)
    quinn = {**MANNY, "name": "Quinn", "mesh": "/Game/Characters/Mannequins/Meshes/SKM_Quinn_Simple"}
    ed = FakeEditor(characters=(MANNY, quinn))
    with ed.server() as fake:
        state = run_shot(root, "a walk", cfg_for(fake, unreal_session="ask"),
                         animator=FakeSeat("fake", lambda p, r: SeatResult(0, "")))
        assert state.status == "needs_answer"
        assert main(["answer", str(root), "--text", "1"]) == 0
        state = run_shot(root, "a walk", cfg_for(fake), animator=FakeSeat("fake", Recorder()))
        assert state.status == "needs_human" and "[apps.unreal] mesh" in state.history[-1]["misses"][0]
        assert main(["retry", str(root)]) == 0                          # after naming the mesh in kei.toml
        state = run_shot(root, "a walk", cfg_for(fake, unreal_mesh=quinn["mesh"]), animator=FakeSeat("fake", Recorder()))
    assert state.status == "needs_approval"
    assert json.loads((root / "unreal" / "character.json").read_text())["name"] == "Quinn"


def test_the_commands_key_render_and_bake_a_pass_end_to_end(tmp_path, capsys):
    root = tmp_path / "shots" / "walk_01"
    root.mkdir(parents=True)
    ed = FakeEditor(bones=standing)
    ed.baked = lambda f: {b: [f, 0, 8] for b in ("foot_l", "ik_foot_l", "foot_r", "ik_foot_r", "hand_l", "ik_hand_l",
                                                  "hand_r", "ik_hand_r", "ik_hand_gun")}
    with ed.server() as fake:
        toml = tmp_path / "kei.toml"
        toml.write_text(f'[animator]\ncmd = ["x"]\n[apps]\napp = "unreal"\n[apps.unreal]\nurl = "{fake.url}"\n'
                        'session = "open"\n', encoding="utf-8")
        from kei.config import load_config
        assert unreal_stage.prepare(root, load_config(toml)) is None
        write_unreal_shot(root, "blocking")
        assert main(["unreal", "key", str(root), "blocking", "--config", str(toml)]) == 0
        out = "".join(capsys.readouterr())
        assert "saved /Game/Kei/walk_01/LS_walk_01_blocking_1" in out and "joints.json" in out
        assert (root / "out_blocking" / "joints.json").is_file()
        assert main(["render", str(root), "blocking", "--size", "48"]) == 0
        assert "renderer: kei" in "".join(capsys.readouterr())
        assert main(["bake", str(root), "blocking"]) == 1          # kei bake would replace Unreal's joints
        assert "is an Unreal shot" in "".join(capsys.readouterr())
        # an export before sign-off is refused; after it, the bake runs and is checked
        save_state(root, ShotState(stage="deliver", status="needs_approval"))
        assert main(["export", "--shot", str(root), "--pass", "blocking", "--to", "unreal"]) == 1
        assert "approved shot" in "".join(capsys.readouterr())
        save_state(root, ShotState(stage="deliver", status="done"))
        assert main(["export", "--shot", str(root), "--pass", "blocking", "--to", "unreal"]) == 0
        assert "every ik_ bone follows its bone on every frame" in "".join(capsys.readouterr())


def test_kei_unreal_setup_prints_every_step(capsys):
    assert main(["unreal", "setup"]) == 0
    out = capsys.readouterr().out
    for need in ("https://github.com/believer-oss/claireon", "-StartMCPServer", "Python Editor Script Plugin",
                 "Content/Kei/", "[apps.unreal]", 'app = "unreal"', "127.0.0.1", "Claireon 2.2.0", "5.8.3"):
        assert need in out, need
    assert chr(0x2014) not in out


def test_an_unreal_shot_is_marked_by_its_folder_or_the_config():
    assert unreal_stage.wants_unreal(__import__("pathlib").Path("nowhere"), "unreal")
    assert not unreal_stage.wants_unreal(__import__("pathlib").Path("nowhere"), "kei")
