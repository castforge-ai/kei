"""The critics judge an Unreal pass on the real mesh: the conductor renders it before the review, a failed render pauses
the review in words, and the critic prompt names the sheets and what on them is a fault. A fake editor, no Unreal."""
import dataclasses

import pytest

from kei.apps import unreal_mesh as M
from kei.apps.unreal import UnrealError
from kei.critic import critic_prompt, passes_under_review
from kei.stages import stage_by_id
from test_unreal_mesh import mesh_shot, no_sleep
from unrealkit import FakeEditor


def test_the_critic_prompt_carries_the_mesh_rules_and_the_sheets(tmp_path):
    shot = mesh_shot(tmp_path)
    ed = FakeEditor()
    with ed.server():
        M.render_mesh(ed.client(), shot, "p1", timeout=5, sleep=no_sleep)
    p = critic_prompt(stage_by_id("passes"), shot, "a walk", [])
    assert "judge these frames first" in p and "out_p1/mesh_three_quarter.png" in p
    assert "toes folded or bent the wrong way" in p and "a frozen limb" in p and "a planted foot that slides" in p
    assert "Never hand one of these to the author as a sign-off check" in p
    assert passes_under_review(shot, "passes", ["pass:p2"]) == ["p1", "p2"]


def test_a_shot_on_kei_s_own_rig_gets_no_mesh_lines(tmp_path):
    shot = mesh_shot(tmp_path, unreal=False)
    assert "judge these frames first" not in critic_prompt(stage_by_id("passes"), shot, "a walk", [])


def test_the_conductor_renders_before_a_review_and_a_failure_pauses_in_words(tmp_path, monkeypatch):
    from kei import conductor
    from kei.apps import unreal_stage
    from test_conductor import CFG
    shot = mesh_shot(tmp_path)
    asked = []

    def fail(shot_dir, name, timeout):
        asked.append((name, timeout))
        raise UnrealError("the editor did not render the mesh frames in 1200 s")
    monkeypatch.setattr(unreal_stage, "render_mesh", fail)
    why = conductor._render_mesh(shot, "passes", [], CFG)
    assert asked == [("p1", 1200)]
    assert "the critics have not judged p1" in why and "mesh_review" in why and "1200 s" in why
    assert conductor._render_mesh(shot, "deliver", [], CFG) is None                  # no pass under review there
    assert conductor._render_mesh(shot, "passes", [], dataclasses.replace(CFG, unreal_mesh_review="off")) is None
    monkeypatch.setattr(unreal_stage, "render_mesh", lambda *a: asked.append(a) or {"ok": True})
    assert conductor._render_mesh(shot, "passes", [], CFG) is None and len(asked) == 2


def test_a_failed_render_pauses_the_review_and_the_resume_reviews(tmp_path, monkeypatch):
    from kei import conductor
    from kei.conductor import run_shot
    from kei.seats import FakeSeat
    from test_conductor import CFG, Recorder, shot as new_shot
    root = new_shot(tmp_path)
    reviewed = []
    answer = {"why": "Kei could not render it on the real mesh"}
    monkeypatch.setattr(conductor, "_render_mesh",
                        lambda d, stage_id, changed, config: answer["why"] if stage_id == "blocking" else None)

    def review(stage, d, changed):
        reviewed.append(stage.id)
        return []
    state = run_shot(root, "a walk", CFG, animator=FakeSeat("fake", Recorder()), review=review)
    assert state.status == "paused_machine" and state.stage == "blocking" and "blocking" not in reviewed
    assert "real mesh" in state.history[-1]["misses"][0]
    answer["why"] = None
    state = run_shot(root, "a walk", CFG, animator=FakeSeat("fake", Recorder()), review=review)
    assert "blocking" in reviewed and state.status == "needs_approval"


def test_the_setting_is_on_by_default_and_checked(tmp_path):
    from kei.config import ConfigError, load_config_text
    base = '[animator]\ncmd = ["x"]\n'
    assert load_config_text(base, tmp_path / "kei.toml").unreal_mesh_review == "on"
    cfg = load_config_text(base + '[apps.unreal]\nmesh_review = "off"\nmesh_timeout = 600\n', tmp_path / "kei.toml")
    assert cfg.unreal_mesh_review == "off" and cfg.unreal_mesh_timeout == 600
    with pytest.raises(ConfigError, match="mesh_review"):
        load_config_text(base + '[apps.unreal]\nmesh_review = "maybe"\n', tmp_path / "kei.toml")
    with pytest.raises(ConfigError, match="mesh_timeout"):
        load_config_text(base + '[apps.unreal]\nmesh_timeout = 5\n', tmp_path / "kei.toml")
