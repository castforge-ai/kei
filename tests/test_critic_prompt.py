from kei.critic import critic_prompt
from kei.stages import stage_by_id
from shotkit import full


def test_critic_prompt_names_the_stage_and_asks_for_json(tmp_path):
    full(tmp_path, upto="blocking")
    p = critic_prompt(stage_by_id("blocking"), tmp_path, "a box falls", [])
    assert "Stage under review: Blocking" in p
    assert '{"verdict"' in p
    assert "Request: a box falls" in p
    assert "- plan/plan_sheet.png" in p
    assert "The plan changed" not in p


def test_critic_prompt_flags_a_plan_change(tmp_path):
    full(tmp_path, upto="blocking")
    p = critic_prompt(stage_by_id("blocking"), tmp_path, "a box falls", ["plan/plan_sheet.png"])
    assert "The plan changed since it was approved: plan/plan_sheet.png" in p


def test_critic_prompt_asks_for_a_side_view_balance_read_at_every_key(tmp_path):
    # The author caught a walk falling behind on the side view that both critics passed (2026-11-02).
    full(tmp_path, upto="blocking")
    p = critic_prompt(stage_by_id("blocking"), tmp_path, "a walk", [])
    assert "side view" in p and "every key" in p
    assert "falls behind" in p
