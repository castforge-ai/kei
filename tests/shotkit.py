"""Test helpers: write the files each stage of a small test shot (a box falls off a table) must leave."""
import json
import os
import time
from pathlib import Path

PLAN = """# Test: a box falls
The brief: a box falls off a table.
Idea sentence: a box slips, tips and lands flat.
Understanding score: 60
Refs: refs/REFS.md
Short look: three clips of boxes tipping off a table, measured frame by frame
Subjects: actions
## Departures
- the bounce is one frame shorter than the clips, for snap
## X-sheet
| frames | function |
|---|---|
| 0-10 | slip |
"""
REFS = """| Ref | Tier | What it gives | Our checks | Verdict |
|---|---|---|---|---|
| clip one | R | the tip time | agrees | keep, the timing |
| clip two | R | the bounce | agrees | keep, the bounce |
| clip three | B | the settle | noisy | flag, the order only |
"""
CHAR = """## Box
- Rig: one root bone, no children
- Mass: 2 kg
- Class: light
"""
GATES = """## Blocking gate: pass
- balance: the box rests on its edge in the tip key
- arcs: the corner draws one arc to the floor
- timing: the fall is 9 frames from the tip
- story: the paused tip frame reads as about to fall
## Breakdowns gate: pass
- the favouring is on the fall
## Spline gate: pass
- curves out_p1/curves.png read smooth
## Polish gate: pass
- the settle holds
"""


def write(root, rel, text="x"):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def touch_later(root, rel, text="x"):
    """Write a file whose modification time is clearly after every file written before it."""
    time.sleep(0.05)
    return write(root, rel, text)


# What each stage leaves, in stage order. Order checks compare modification times, so each stage writes later.
def stage_brief(root):
    write(root, "PLAN.md", PLAN)


def stage_rig(root):
    write(root, "CHARACTER.md", CHAR.replace("- Mass: 2 kg\n- Class: light\n", ""))


def stage_weight(root):
    write(root, "CHARACTER.md", CHAR)


def stage_understanding(root):
    pass  # the score line is part of PLAN.md


def stage_references(root):
    write(root, "refs/REFS.md", REFS)


def stage_study(root):
    pass  # the Departures section is part of PLAN.md


def stage_plan(root):
    write(root, "plan/plan.json", json.dumps({"keys": [
        {"f": 0, "function": "slip", "kind": "key", "drawing": {"lines": [[0, 0, 1, 0]]}},
        {"f": 9, "function": "contact", "kind": "key", "drawing": {"lines": [[0, 0, 0, 1]]}}]}))
    write(root, "plan/plan_sheet.png")


def stage_blocking(root):
    touch_later(root, "out_blocking/key_f0000.png")
    write(root, "out_blocking/key_f0009.png")
    write(root, "out_blocking/blocking.mp4")
    write(root, "GATES.md", GATES.split("## Breakdowns")[0])


def stage_passes(root):
    touch_later(root, "out_p1/curves.png")
    write(root, "out_p1/shot.json", "{}")
    write(root, "GATES.md", GATES)


def stage_checks(root):
    touch_later(root, "out_p1/body_check/body_check.json", "{}")


def stage_self_review(root):
    write(root, "out_p1/SELF_REVIEW_LOG.md", "## 1 NOT READY\n## 2 READY\n")


def stage_deliver(root):
    write(root, "video/shot.mp4")
    write(root, "REVIEW.md", "## What I learned\n- a box needs one frame of hold before it tips\n")
    write(root, os.path.join("..", "GROWTH.md"), "## %s\n- learned\n" % Path(root).resolve().name)


STAGE_WRITERS = {
    "brief": stage_brief, "rig": stage_rig, "weight": stage_weight, "understanding": stage_understanding,
    "references": stage_references, "study": stage_study, "plan": stage_plan, "blocking": stage_blocking,
    "passes": stage_passes, "checks": stage_checks, "self_review": stage_self_review, "deliver": stage_deliver,
}


def full(root, upto="passes"):
    for sid, fn in STAGE_WRITERS.items():
        fn(root)
        if sid == upto:
            break
