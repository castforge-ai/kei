"""KEI_RECORD.md: Kei writes the shot's bookkeeping itself before each review."""
import json

from kei.record import NAME, write_record
from kei.state import ShotState


def test_the_record_lists_the_stage_each_pass_with_its_hash_and_flags_and_the_unchecked_count(tmp_path):
    for name, n in (("blocking", 3), ("p1", 5), ("p2", 6)):
        d = tmp_path / f"out_{name}"
        d.mkdir()
        (d / "shot.json").write_text(json.dumps({"frames": 24, "keys": [{"f": i} for i in range(n)]}), encoding="utf-8")
    (tmp_path / "out_p2" / "principles").mkdir()
    (tmp_path / "out_p2" / "principles" / "principles.json").write_text(json.dumps({"flags": [
        {"id": "timing.even.body.f0"}, {"id": "solid_drawing.twin_pose.hands.f9"}]}), encoding="utf-8")
    (tmp_path / "GATES.md").write_text("## Declared\n- timing.even.body.f0: wanted\n", encoding="utf-8")
    (tmp_path / "PLAN.md").write_text("Speed 1.4 m/s (unchecked).\n", encoding="utf-8")
    text = write_record(tmp_path, ShotState(stage="passes", status="running", request="a walk", attempts=2)).read_text(
        encoding="utf-8")
    assert "Breakdowns, spline and polish (passes)" in text and "Tries at this stage: 2" in text
    rows = [ln for ln in text.splitlines() if ln.startswith("| ") and not ln.startswith("| pass")]
    assert [r.split("|")[1].strip() for r in rows] == ["blocking", "p1", "p2"]
    assert rows[2].split("|")[6].strip() == "1"           # one principle flag open, the other declared
    assert "## Unchecked numbers: 1" in text and (tmp_path / NAME).is_file()


def test_the_animator_and_the_critics_are_told_the_record_is_keis(tmp_path):
    from kei.critic import critic_prompt
    from kei.prompts import RECORD_RULE
    from kei.stages import stage_by_id
    assert "KEI_RECORD.md" in RECORD_RULE
    assert "never note a stage line, a version number" in critic_prompt(stage_by_id("plan"), tmp_path, "a walk", [])
