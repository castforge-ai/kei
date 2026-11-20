"""Critic notes have a severity: blocking notes send back, minor notes ride along; the critic sees the contract."""
from kei.conductor import carried_notes, run_shot
from kei.critic import critic_prompt
from kei.seats import FakeSeat
from kei.stages import stage_by_id
from kei.state import ShotState
from shotkit import full
from test_conductor import Recorder, shot
from test_conductor_critic import CFG, PASS, critic


def test_the_critic_prompt_carries_the_stage_contract_and_ends_with_the_verdict_format(tmp_path):
    full(tmp_path, upto="blocking")
    p = critic_prompt(stage_by_id("blocking"), tmp_path, "a box falls", [])
    assert "The stage's contract" in p and "Block the shot: key poses only" in p
    assert p.rstrip().endswith("send_back only for a blocking note.")
    assert '"minor"' in p and "judge the acting first" in p


def test_minor_notes_reach_the_animator_with_a_send_back(tmp_path):
    root = shot(tmp_path)
    answers = iter(['{"verdict": "send_back", "notes": ["f9: the hips sink too late"], '
                    '"minor": ["f40: a touch more overlap"]}'])
    c = critic("c1", lambda t, p: next(answers, PASS) if t == "Plan" else PASS)
    rec = Recorder()
    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", rec), critics=[c])
    after = [p for p in rec.prompts if "critic c1: f9: the hips sink too late" in p]
    assert after and "(minor) critic c1: f40: a touch more overlap" in after[0]


def test_carried_notes_label_the_minor_ones():
    st = ShotState(stage="plan", history=[{"stage": "plan", "result": "send_back", "misses": ["critic a: f1: x"],
                                           "minor": ["critic a: f2: y"]}])
    assert carried_notes(st)["critics"] == ["critic a: f1: x", "(minor) critic a: f2: y"]
