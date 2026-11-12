from kei.plan_lock import approve_plan, plan_changes
from shotkit import full, write


def test_no_approved_plan_means_no_change(tmp_path):
    write(tmp_path, "plan/plan.json", '{"keys": []}')
    assert plan_changes(tmp_path, None) == []


def test_change_after_approval_is_found(tmp_path):
    full(tmp_path, upto="plan")
    approved = approve_plan(tmp_path)
    assert plan_changes(tmp_path, approved) == []
    write(tmp_path, "plan/plan_sheet.png", "redrawn")
    assert plan_changes(tmp_path, approved) == ["plan/plan_sheet.png"]
    approved = approve_plan(tmp_path)
    assert plan_changes(tmp_path, approved) == []


def test_removed_plan_file_is_a_change(tmp_path):
    full(tmp_path, upto="plan")
    approved = approve_plan(tmp_path)
    (tmp_path / "plan" / "plan.json").unlink()
    assert plan_changes(tmp_path, approved) == ["plan/plan.json"]
