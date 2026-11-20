"""A pass made after the passes review (at checks, self-review or delivery) goes back to the critics."""
from kei.conductor import pass_changes, pass_stamp
from kei.critic import panel_review
from kei.seats import FakeSeat, SeatResult
from kei.stages import stage_by_id
from shotkit import full

PASS = '{"verdict": "pass", "notes": []}'


def _pass(root, n, text="{}"):
    d = root / f"out_p{n}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "shot.json").write_text(text, encoding="utf-8")


def test_a_new_pass_after_the_passes_review_is_a_change_to_review(tmp_path):
    _pass(tmp_path, 9)
    approved = pass_stamp(tmp_path)
    assert pass_changes(tmp_path, "checks", approved) == []
    _pass(tmp_path, 10)
    changed = pass_changes(tmp_path, "self_review", approved)
    assert changed == ["pass:out_p10/shot.json (the panel last passed out_p9)"]
    assert pass_changes(tmp_path, "blocking", approved) == [], "only the stages after passes"
    assert pass_changes(tmp_path, "checks", None) == [], "nothing passed yet: nothing to compare"


def test_an_edited_pass_counts_too(tmp_path):
    _pass(tmp_path, 9)
    approved = pass_stamp(tmp_path)
    _pass(tmp_path, 9, '{"keys": []}')
    assert pass_changes(tmp_path, "deliver", approved)


def test_the_critics_review_the_late_pass_and_are_told_what_it_is(tmp_path):
    full(tmp_path, upto="self_review")
    calls = []
    seat = FakeSeat("c", lambda prompt, root: (calls.append(prompt), SeatResult(0, PASS))[1])
    changed = ["pass:out_p12/shot.json (the panel last passed out_p9)"]
    assert panel_review(stage_by_id("self_review"), tmp_path, "a crate lift", [seat], changed) == []
    assert len(calls) == 1 and "A new pass was made after the passes review: out_p12/shot.json" in calls[0]
    assert "The plan changed" not in calls[0]
    assert panel_review(stage_by_id("self_review"), tmp_path, "a crate lift", [seat], []) == []
    assert len(calls) == 1, "no new pass: no review"
