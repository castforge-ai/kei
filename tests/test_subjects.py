from dataclasses import replace

from kei.seats import FakeSeat
from shotkit import STAGE_WRITERS, write
from test_conductor import CFG, Recorder, run_shot, shot, stage_of
from test_conductor_critic import always_pass, critic
from test_conductor_critic import run_shot as run_with_critics

ARCS = "# Arcs\n\nkind: principle\n\n### ARC1. Curves\nstages: all\n\nArc text.\n"
WALKS = "# Locomotion\n\nkind: subject\n\n### LOC1. Walk rule\nstages: all\n\nWalk text.\n"
THROWS = "# Actions\n\nkind: subject\n\n### ACT1. Throw rule\nstages: all\n\nThrow text.\n"


def config(tmp_path, **kw):
    d = tmp_path / "book"
    d.mkdir(exist_ok=True)
    for name, text in {"arcs": ARCS, "locomotion": WALKS, "actions": THROWS}.items():
        (d / f"{name}.md").write_text(text, encoding="utf-8")
    return replace(CFG, book=d, lessons=tmp_path / "lessons.local.md", **kw)


def brief_with(line):
    """A fake animator whose brief adds a Subjects line (or none)."""
    def fault(sid, n, r):
        if sid == "brief":
            STAGE_WRITERS["brief"](r)
            p = r / "PLAN.md"   # the shared fake plan names a subject; this test sets its own line, or none
            kept = "".join(ln for ln in p.read_text(encoding="utf-8").splitlines(keepends=True)
                           if not ln.startswith("Subjects:"))
            p.write_text(kept + (line + "\n" if line is not None else ""), encoding="utf-8")
            return True
        return False
    return fault


def prompts(rec, title):
    return [p for p in rec.prompts if stage_of(p) == title]


def test_the_brief_lists_the_subjects_and_gets_every_subject(tmp_path):
    rec = Recorder(brief_with("Subjects: locomotion"))
    run_shot(shot(tmp_path), "a walk", config(tmp_path), animator=FakeSeat("fake", rec))
    brief = prompts(rec, "Brief")[0]
    assert "ARC1" in brief and "LOC1" in brief and "ACT1" in brief   # the brief gets every subject's brief rules
    assert "locomotion: Locomotion" in brief and "actions: Actions" in brief


def test_a_walk_gets_walk_rules_and_no_throw_rules(tmp_path):
    rec = Recorder(brief_with("Subjects: locomotion"))
    state = run_shot(shot(tmp_path), "a walk", config(tmp_path), animator=FakeSeat("fake", rec))
    blocking = prompts(rec, "Blocking")[0]
    assert "ARC1" in blocking and "LOC1" in blocking and "ACT1" not in blocking
    assert state.status == "needs_approval"


def test_subjects_all_sends_every_subject(tmp_path):
    rec = Recorder(brief_with("Subjects: all"))
    run_shot(shot(tmp_path), "a walk", config(tmp_path), animator=FakeSeat("fake", rec))
    blocking = prompts(rec, "Blocking")[0]
    assert "LOC1" in blocking and "ACT1" in blocking


def test_a_missing_subjects_line_is_refused_at_the_brief(tmp_path):
    rec = Recorder(brief_with(None))
    state = run_shot(shot(tmp_path), "a walk", config(tmp_path), animator=FakeSeat("fake", rec))
    assert (state.stage, state.status) == ("brief", "needs_human")
    assert any("Subjects:" in m and "locomotion" in m for m in state.history[-1]["misses"])


def test_a_typo_is_refused_with_the_valid_names(tmp_path):
    rec = Recorder(brief_with("Subjects: locomtion"))
    state = run_shot(shot(tmp_path), "a walk", config(tmp_path), animator=FakeSeat("fake", rec))
    miss = " ".join(state.history[-1]["misses"])
    assert "locomtion" in miss and "actions" in miss and state.stage == "brief"


def test_no_line_after_the_brief_sends_every_subject(tmp_path):
    from kei.state import ShotState, save_state
    root = shot(tmp_path)
    for sid in ("brief", "rig", "weight", "understanding", "references", "study", "plan"):
        STAGE_WRITERS[sid](root)
    save_state(root, ShotState(stage="blocking", request="a walk"))
    rec = Recorder()
    run_shot(root, "a walk", config(tmp_path), animator=FakeSeat("fake", rec))
    blocking = prompts(rec, "Blocking")[0]
    assert "LOC1" in blocking and "ACT1" in blocking


def test_a_subject_added_in_blocking_is_reviewed_and_reaches_the_next_prompt(tmp_path):
    def fault(sid, n, r):
        if sid == "brief":
            return brief_with("Subjects: locomotion")(sid, n, r)
        if sid == "blocking" and n == 1:
            STAGE_WRITERS["blocking"](r)
            p = r / "PLAN.md"
            p.write_text(p.read_text(encoding="utf-8").replace("Subjects: locomotion",
                                                               "Subjects: locomotion, actions"), encoding="utf-8")
            return True
        return False

    rec = Recorder(fault)
    c = critic("c1", always_pass)
    run_with_critics(shot(tmp_path), "a walk", config(tmp_path), animator=FakeSeat("fake", rec), critics=[c])
    reviewed = next(p for p in c.prompts if "Stage under review: Blocking" in p)
    assert "The plan changed since it was approved: PLAN.md" in reviewed
    assert "ACT1" in prompts(rec, "Breakdowns, spline and polish")[0]


def test_a_single_file_book_needs_no_subjects_line(tmp_path):
    book = tmp_path / "rules.md"
    book.write_text(ARCS, encoding="utf-8")
    rec = Recorder()
    state = run_shot(shot(tmp_path), "a walk", replace(CFG, book=book), animator=FakeSeat("fake", rec))
    assert state.status == "needs_approval"


def edit_plan_at(stage_title_id, new_text_fn):
    def fault(sid, n, r):
        if sid == "brief":
            return brief_with("Subjects: locomotion, actions")(sid, n, r)
        if sid == stage_title_id and n == 1:
            STAGE_WRITERS[sid](r)
            p = r / "PLAN.md"
            p.write_text(new_text_fn(p.read_text(encoding="utf-8")), encoding="utf-8")
            return True
        return False
    return fault


def test_narrowing_the_line_later_never_drops_a_subject(tmp_path):
    rec = Recorder(edit_plan_at("rig", lambda t: t.replace("Subjects: locomotion, actions", "Subjects: locomotion")))
    run_shot(shot(tmp_path), "a walk", config(tmp_path), animator=FakeSeat("fake", rec))
    assert "ACT1" in prompts(rec, "Blocking")[0]


def test_an_emptied_line_later_never_drops_a_subject(tmp_path):
    rec = Recorder(edit_plan_at("rig", lambda t: t.replace("Subjects: locomotion, actions", "Subjects:")))
    run_shot(shot(tmp_path), "a walk", config(tmp_path), animator=FakeSeat("fake", rec))
    blocking = prompts(rec, "Blocking")[0]
    assert "LOC1" in blocking and "ACT1" in blocking


def test_a_typo_added_later_is_refused_at_that_stage(tmp_path):
    rec = Recorder(edit_plan_at("rig", lambda t: t.replace("Subjects: locomotion, actions",
                                                           "Subjects: locomotion, actions, crechers")))
    state = run_shot(shot(tmp_path), "a walk", config(tmp_path), animator=FakeSeat("fake", rec))
    rig = [h for h in state.history if h["stage"] == "rig"]
    assert any("crechers" in m for h in rig for m in h["misses"])


def test_a_second_subjects_line_adds_to_the_first(tmp_path):
    rec = Recorder(brief_with("Subjects: locomotion\nSubjects: actions"))
    run_shot(shot(tmp_path), "a walk", config(tmp_path), animator=FakeSeat("fake", rec))
    blocking = prompts(rec, "Blocking")[0]
    assert "LOC1" in blocking and "ACT1" in blocking


def test_bullet_bold_and_lowercase_lines_are_read(tmp_path):
    from kei.topics import shot_subjects
    for line in ("- Subjects: locomotion", "**Subjects:** locomotion", "subjects: locomotion"):
        (tmp_path / "PLAN.md").write_text("# x\n" + line + "\n", encoding="utf-8")
        assert shot_subjects(tmp_path) == ["locomotion"], line


def test_too_many_rules_stop_for_a_person_and_never_ask_for_fewer_subjects(tmp_path):
    rec = Recorder(brief_with("Subjects: all"))
    state = run_shot(shot(tmp_path), "a walk", config(tmp_path, max_rule_chars=130), animator=FakeSeat("fake", rec))
    assert state.status == "needs_human"
    text = " ".join(state.history[-1]["misses"])
    assert "max_chars" in text and "fewer" not in text


def test_the_critic_gets_what_the_animator_got(tmp_path):
    rec = Recorder(edit_plan_at("blocking", lambda t: t.replace("Subjects: locomotion, actions", "Subjects: locomotion")))
    c = critic("c1", always_pass)
    run_with_critics(shot(tmp_path), "a walk", config(tmp_path), animator=FakeSeat("fake", rec), critics=[c])
    reviewed = next(p for p in c.prompts if "Stage under review: Blocking" in p)
    assert "ACT1" in reviewed and "ACT1" in prompts(rec, "Blocking")[0]


def test_a_topic_named_all_is_refused(tmp_path):
    import pytest
    from kei.book import BookError, load_topics
    d = tmp_path / "b"
    d.mkdir()
    (d / "all.md").write_text(WALKS, encoding="utf-8")
    with pytest.raises(BookError):
        load_topics(d)
