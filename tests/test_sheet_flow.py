import json
import os
import sys

from kei.cli import main
from kei.seats import FakeSeat
from shotkit import STAGE_WRITERS, write
from test_conductor import Recorder, run_shot, shot, CFG

DRAWN = {"keys": [{"f": 0, "function": "slip", "kind": "key", "drawing": {"lines": [[0, 0, 1, 0]], "com": [0.5, 0]}},
                  {"f": 9, "function": "contact", "kind": "key", "drawing": {"lines": [[0, 0, 0, 1]]}}],
         "arcs": {"corner": [[0, 0, 1], [9, 1, 0]]}}


def plan_without_sheet(plan):
    def fault(sid, n, r):
        if sid == "plan":
            write(r, "plan/plan.json", json.dumps(plan))
            return True
        return False
    return fault


def test_conductor_draws_the_sheet_after_the_plan_stage(tmp_path):
    root = shot(tmp_path)
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(plan_without_sheet(DRAWN))))
    assert (root / "plan" / "plan_sheet.png").read_bytes()[:4] == b"\x89PNG"
    assert "plan" in [h["stage"] for h in state.history if h["result"] == "pass"]


def test_conductor_does_not_draw_without_drawings(tmp_path):
    root = shot(tmp_path)
    bare = {"keys": [{"f": 0, "function": "slip", "kind": "key"}]}
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(plan_without_sheet(bare))))
    assert state.stage == "plan" and state.status == "needs_human"
    misses = [m for h in state.history if h["stage"] == "plan" for m in h["misses"]]
    assert any("the plan sheet cannot be drawn" in m and "f 0" in m for m in misses)
    assert not (root / "plan" / "plan_sheet.png").exists()


def test_agent_sheet_is_replaced(tmp_path):
    root = shot(tmp_path)

    def fault(sid, n, r):
        if sid == "plan":
            write(r, "plan/plan.json", json.dumps(DRAWN))
            sheet = write(r, "plan/plan_sheet.png", "agent")
            t = os.path.getmtime(r / "plan" / "plan.json") + 5
            os.utime(sheet, (t, t))
            return True
        return False

    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(fault)))
    data = (root / "plan" / "plan_sheet.png").read_bytes()
    assert data[:4] == b"\x89PNG" and data != b"agent"


def test_plan_change_in_blocking_redraws_the_sheet(tmp_path):
    root = shot(tmp_path)
    seen = {}

    def fault(sid, n, r):
        if sid == "blocking" and n == 1:
            seen["before"] = (r / "plan" / "plan_sheet.png").read_bytes()
            moved = json.loads(json.dumps(DRAWN))
            moved["keys"][1]["drawing"]["lines"] = [[0, 0, 2, 2]]
            write(r, "plan/plan.json", json.dumps(moved))
        return False

    changes = []

    def review(stage, d, changed):
        if stage.id == "blocking":
            changes.append(list(changed))
            seen["after"] = (d / "plan" / "plan_sheet.png").read_bytes()
        return []

    run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(fault)), review=review)
    assert seen["after"] != seen["before"]
    assert "plan/plan.json" in changes[0] and "plan/plan_sheet.png" in changes[0]


def test_kei_sheet_command(tmp_path, capsys):
    write(tmp_path, "plan/plan.json", json.dumps(DRAWN))
    assert main(["sheet", str(tmp_path)]) == 0
    assert (tmp_path / "plan" / "plan_sheet.png").exists()
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["sheet", str(empty)]) == 1
    assert "Traceback" not in capsys.readouterr().out


def test_plan_change_in_passes_keeps_the_order_check(tmp_path):
    from shotkit import touch_later
    root = shot(tmp_path)

    def fault(sid, n, r):
        if sid == "passes" and n == 1:
            STAGE_WRITERS["passes"](r)
            moved = json.loads((r / "plan" / "plan.json").read_text(encoding="utf-8"))
            moved["keys"][0]["drawing"]["lines"] = [[0, 0, 2, 1]]
            touch_later(r, "plan/plan.json", json.dumps(moved))
            return True
        return False

    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(fault)))
    assert state.status == "needs_approval", state.history[-1]
