"""Kei counts the (unchecked) marks itself and shows them to the critics and in kei status."""
from kei.cli import main
from kei.critic import critic_prompt
from kei.stages import stage_by_id
from kei.state import ShotState, save_state
from kei.unchecked import unchecked


def shot(tmp_path):
    (tmp_path / "PLAN.md").write_text("Contact at f12.\nA knee about 5 deg (unchecked) at contact.\n", encoding="utf-8")
    (tmp_path / "REFS.md").write_text("Walk 1.4 m/s (unchecked); cadence 110 (Unchecked).\n", encoding="utf-8")
    save_state(tmp_path, ShotState(stage="plan", status="running", request="a walk"))
    return tmp_path


def test_kei_counts_every_mark_with_its_file_and_line(tmp_path):
    marks = unchecked(shot(tmp_path))
    assert [(m["file"], m["line"]) for m in marks] == [("PLAN.md", 2), ("REFS.md", 1), ("REFS.md", 1)]


def test_the_critic_gets_the_count_and_is_told_a_mark_is_no_send_back(tmp_path):
    p = critic_prompt(stage_by_id("plan"), shot(tmp_path), "a walk", [])
    assert "Kei counted 3 (unchecked)" in p and "Do not send the stage back over a mark" in p


def test_kei_status_prints_the_count(tmp_path, capsys):
    assert main(["status", str(shot(tmp_path))]) == 0
    assert "unchecked numbers: 3" in capsys.readouterr().out
