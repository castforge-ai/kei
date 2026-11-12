import json

from kei.gates.stage_gate import stage_misses
from kei.stages import STAGES, next_stage, stage_by_id
from shotkit import full, write

IDS = ["brief", "rig", "weight", "understanding", "references", "study", "plan", "blocking", "passes", "checks",
       "self_review", "deliver"]


def shot(tmp_path):
    root = tmp_path / "shots" / "box_fall"
    root.mkdir(parents=True)
    return root


def test_full_shot_holds_every_stage_up_to_passes(tmp_path):
    root = shot(tmp_path)
    full(root)
    assert stage_misses(root, stage_by_id("passes")) == []


def test_plan_only_shot_misses_from_rig(tmp_path):
    root = shot(tmp_path)
    full(root, upto="brief")
    assert stage_misses(root, stage_by_id("brief")) == []
    assert any(m.startswith("P2") for m in stage_misses(root, stage_by_id("rig")))


def test_unified_plan_contract_holds_p7(tmp_path):
    root = shot(tmp_path)
    full(root, upto="study")
    write(root, "plan/plan.json", json.dumps({"keys": [{"f": 0, "function": "slip", "kind": "key"}]}))
    write(root, "plan/plan_sheet.png")
    assert not any(m.startswith("P7") for m in stage_misses(root, stage_by_id("plan")))


def test_legacy_plan_contract_still_holds_p7(tmp_path):
    root = shot(tmp_path)
    full(root, upto="study")
    write(root, "plan/keys.json", json.dumps([{"f": 0, "fn": "slip"}]))
    write(root, "plan/pose_sheet.png")
    write(root, "plan/arcs.png")
    assert stage_misses(root, stage_by_id("plan")) == []


def test_plan_json_needs_frame_and_function(tmp_path):
    root = shot(tmp_path)
    full(root, upto="study")
    write(root, "plan/plan.json", json.dumps({"keys": [{"f": 0, "function": "x"}]}))
    write(root, "plan/plan_sheet.png")
    assert any(m.startswith("P7") for m in stage_misses(root, stage_by_id("plan")))


def test_later_stage_includes_earlier_misses(tmp_path):
    root = shot(tmp_path)
    full(root)
    (root / "plan" / "plan_sheet.png").unlink()
    assert any(m.startswith("P7") for m in stage_misses(root, stage_by_id("blocking")))


def test_checks_and_self_review(tmp_path):
    root = shot(tmp_path)
    full(root, upto="self_review")
    assert stage_misses(root, stage_by_id("self_review")) == []
    write(root, "out_p1/SELF_REVIEW_LOG.md", "## 2 READY\n## 3 NOT READY\n")
    assert any(m.startswith("P11") for m in stage_misses(root, stage_by_id("self_review")))


def test_checks_must_be_newer_than_the_pass(tmp_path):
    root = shot(tmp_path)
    full(root, upto="checks")
    import time
    time.sleep(0.05)
    write(root, "out_p1/shot.json", "{}")
    assert any(m.startswith("P10") for m in stage_misses(root, stage_by_id("checks")))


def test_no_pass_yet_misses_p10_and_p11(tmp_path):
    root = shot(tmp_path)
    full(root, upto="blocking")
    misses = stage_misses(root, stage_by_id("self_review"))
    assert any(m.startswith("P10") and "no pass yet" in m for m in misses)
    assert any(m.startswith("P11") and "no pass yet" in m for m in misses)


def test_full_delivery_holds(tmp_path):
    root = shot(tmp_path)
    full(root, upto="deliver")
    assert stage_misses(root, stage_by_id("deliver")) == []


def test_stage_order_is_fixed():
    assert [s.id for s in STAGES] == IDS
    assert next_stage("deliver") is None
    assert next_stage("brief").id == "rig"


def test_an_agent_cannot_switch_off_the_order_check(tmp_path):
    root = shot(tmp_path)
    full(root)
    import time
    time.sleep(0.05)
    write(root, "plan/plan_sheet.png")   # the plan redrawn after blocking
    write(root, "pipeline.json", '{"retro": "the planning was rebuilt after the fact, on purpose"}')
    assert any(m.startswith("ORDER") for m in stage_misses(root, stage_by_id("passes")))


def _plan_misses(tmp_path, keys):
    root = shot(tmp_path)
    full(root, upto="study")
    write(root, "plan/plan.json", json.dumps({"keys": keys}))
    write(root, "plan/plan_sheet.png")
    return [m for m in stage_misses(root, stage_by_id("plan")) if m.startswith("P7")]


def test_plan_accepts_short_standard_pose_names(tmp_path):
    keys = [{"f": f, "function": fn, "kind": "key"} for f, fn in ((0, "up"), (3, "down"), (6, "contact"))]
    assert _plan_misses(tmp_path, keys) == []


def test_plan_miss_names_the_key_frame_and_why(tmp_path):
    misses = _plan_misses(tmp_path, [{"f": 0, "function": "contact"}, {"f": 11, "function": ""},
                                     {"f": "14", "function": "passing"}, {"f": 20}])
    text = "\n".join(misses)
    assert len(misses) == 3
    assert "f 11" in text and "function" in text and "empty" in text
    assert "key 3" in text and "integer" in text and "'14'" in text
    assert "f 20" in text and "no \"function\"" in text


def test_plan_json_that_is_not_json_says_so(tmp_path):
    root = shot(tmp_path)
    full(root, upto="study")
    write(root, "plan/plan.json", "{not json")
    write(root, "plan/plan_sheet.png")
    misses = [m for m in stage_misses(root, stage_by_id("plan")) if m.startswith("P7")]
    assert any("not valid JSON" in m for m in misses)


def test_refs_line_naming_a_bare_refs_file_counts_its_rows(tmp_path):
    root = shot(tmp_path)
    full(root)
    plan = (root / "PLAN.md").read_text(encoding="utf-8")
    (root / "PLAN.md").write_text(plan.replace("Refs: refs/REFS.md", "Refs: REFS.md (3 vetted rows)"), encoding="utf-8")
    (root / "REFS.md").write_text((root / "refs" / "REFS.md").read_text(encoding="utf-8"), encoding="utf-8")
    assert not [m for m in stage_misses(root, stage_by_id("references")) if m.startswith("P5")]
