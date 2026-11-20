"""kei vary starts a new shot from an approved one at the stage the change needs, with the note for that stage."""
import json

import pytest

from kei.cli import main
from kei.conductor import carried_notes
from kei.signoff import SignOffError
from kei.state import ShotState, load_state, save_state
from kei.vary import vary


def approved(tmp_path):
    root = tmp_path / "lift"
    for rel, text in (("BRIEF.md", "brief"), ("PLAN.md", "plan"), ("plan/plan.json", '{"keys": []}'),
                      ("out_blocking/shot.json", "{}"), ("out_p3/shot.json", "{}"), ("lift_report.html", "r"),
                      ("lift_pack.html", "p"), ("lift_p3.glb", "g"), ("KEI_RECORD.md", "rec"),
                      ("refs/REFS.md", "refs")):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    from kei.plan_lock import approve_plan
    save_state(root, ShotState(stage="deliver", status="done", request="lift a crate",
                               approved_plan=approve_plan(root),
                               history=[{"stage": "deliver", "result": "approved", "words": "good"}]))
    return root


def test_a_variation_keeps_the_early_stages_and_starts_at_the_plan_with_the_note(tmp_path):
    src = approved(tmp_path)
    dest = vary(src, "heavier crate, tired")
    assert dest.name == "lift-heavier-crate-tired"
    for kept in ("BRIEF.md", "PLAN.md", "plan/plan.json", "refs/REFS.md"):
        assert (dest / kept).is_file()
    for gone in ("out_blocking", "out_p3", "lift_report.html", "lift_pack.html", "lift_p3.glb", "KEI_RECORD.md"):
        assert not (dest / gone).exists()
    s = load_state(dest)
    assert (s.stage, s.status, s.approved_plan) == ("plan", "running", None)
    assert "variation: heavier crate, tired" in s.request
    assert not any(h.get("result") == "approved" for h in s.history)
    assert carried_notes(s)["author"] == ["Variation of the approved shot lift: heavier crate, tired"]
    assert load_state(src).status == "done"


def test_from_blocking_the_plan_stays_approved(tmp_path):
    src = approved(tmp_path)
    s = load_state(vary(src, "angry", from_stage="blocking"))
    assert s.stage == "blocking" and s.approved_plan and "plan/plan.json" in s.approved_plan


def test_from_passes_blocking_is_kept(tmp_path):
    dest = vary(approved(tmp_path), "looser arms", from_stage="passes")
    assert (dest / "out_blocking" / "shot.json").is_file() and not (dest / "out_p3").exists()


@pytest.mark.parametrize("status", ["needs_approval", "running", "rejected"])
def test_only_a_signed_off_shot_varies(tmp_path, status):
    src = approved(tmp_path)
    s = load_state(src)
    s.status = status
    save_state(src, s)
    with pytest.raises(SignOffError, match="not a signed-off shot"):
        vary(src, "x")


def test_a_second_variation_gets_its_own_folder_and_an_empty_note_is_refused(tmp_path):
    src = approved(tmp_path)
    a, b = vary(src, "tired"), vary(src, "tired")
    assert a != b and b.name == "lift-tired-2"
    with pytest.raises(SignOffError, match="needs a note"):
        vary(src, "  ")


def test_the_command(tmp_path, capsys):
    src = approved(tmp_path)
    assert main(["vary", str(src), "--note", "tired", "--to", str(tmp_path / "v1")]) == 0
    assert "kei run" in capsys.readouterr().out and (tmp_path / "v1" / ".kei" / "state.json").is_file()
    assert main(["vary", str(src), "--note", "tired", "--to", str(tmp_path / "v1")]) == 1
