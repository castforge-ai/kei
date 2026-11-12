"""Character folders: one folder per character, its rig and weight evaluated once, its shots inside."""
import json
import re
from pathlib import Path

from kei import character_folder as cf
from kei.conductor import run_shot as _run_shot
from kei.config import Config, SeatSpec
from kei.seats import FakeSeat, SeatResult
from kei.state import load_state
from shotkit import PLAN, STAGE_WRITERS, write

CFG = Config(animator=SeatSpec(name="fake", cmd=["unused"]), max_attempts=3)

TITLES = {"Brief": "brief", "Rig evaluation": "rig", "Weight evaluation": "weight",
          "Understanding score": "understanding", "Reference search": "references", "Study": "study",
          "Plan": "plan", "Blocking": "blocking", "Breakdowns, spline and polish": "passes",
          "All the checks": "checks", "Self-review": "self_review", "Delivery": "deliver"}


def run_shot(*args, review=None, **kwargs):
    return _run_shot(*args, review=review or (lambda stage, shot_dir, changed: []), **kwargs)


def stage_of(prompt):
    return TITLES[re.search(r"^Stage: (.+)$", prompt, re.M).group(1)]


def plan_for(*names):
    return PLAN + "".join(f"Character: {n}\n" for n in names)


class Animator:
    """A fake animator. The rig and weight stages write one CHARACTER.md section per character of the shot."""

    def __init__(self, names, evidence=False):
        self.names = names
        self.evidence = evidence
        self.prompts = []

    def __call__(self, prompt, root):
        self.prompts.append(prompt)
        sid = stage_of(prompt)
        if sid == "brief":
            write(root, "PLAN.md", plan_for(*self.names))
        elif sid in ("rig", "weight"):
            path = Path(root) / "CHARACTER.md"
            text = path.read_text(encoding="utf-8") if path.is_file() else "# CHARACTER\n\n"
            for n in self.names:
                if f"## {n}\n" in text:
                    continue   # a section Kei put there (reused) is kept as it is
                text += f"## {n}\nRig: {n}'s rig, measured in this shot\n"
                if sid == "weight":
                    pass
            if sid == "weight":
                text = re.sub(r"(Rig: (\w+)'s rig, measured in this shot\n)(?!Mass)",
                              r"\1Mass: 60 kg\nClass: average\n", text)
            path.write_text(text, encoding="utf-8")
            if self.evidence:
                write(root, f"{sid}_eval/probe.json", "{}")
        else:
            STAGE_WRITERS[sid](root)
        return SeatResult(0, "done")

    def stages(self):
        return [stage_of(p) for p in self.prompts]


SAVED = """## {name}
Fingerprint: {fp}
Evaluated: 2026-11-01 in walk_one
Rig: the saved rig of {name}
Mass: 70 kg
Class: heavy
"""


def saved_folder(tmp_path, name, fp=None, folder_name=None):
    folder = tmp_path / "shots" / (folder_name or name)
    folder.mkdir(parents=True)
    (folder / "CHARACTER.md").write_text(SAVED.format(name=name, fp=fp or cf.fingerprint(name)), encoding="utf-8")
    return folder


# 1. Detection

def test_a_shot_in_a_folder_named_after_its_character_is_in_a_character_folder(tmp_path):
    shot = tmp_path / "kei" / "walk"
    shot.mkdir(parents=True)
    assert cf.character_folder(shot, ["kei"]) == tmp_path / "kei"


def test_a_parent_holding_the_characters_section_is_a_character_folder(tmp_path):
    folder = tmp_path / "heroes"
    (folder / "walk").mkdir(parents=True)
    (folder / "CHARACTER.md").write_text("## keira\nRig: x\n", encoding="utf-8")
    assert cf.character_folder(folder / "walk", ["keira"]) == folder
    assert cf.character_folder(folder / "walk", ["kei"]) is None


def test_a_shot_in_an_ordinary_folder_is_not_in_a_character_folder(tmp_path):
    shot = tmp_path / "shots" / "walk"
    shot.mkdir(parents=True)
    assert cf.character_folder(shot, ["kei"]) is None


def test_the_shot_characters_are_every_character_line_else_the_default(tmp_path):
    write(tmp_path, "PLAN.md", plan_for("kei", "Keira"))
    assert cf.shot_characters(tmp_path, "kei") == ["kei", "keira"]
    write(tmp_path, "PLAN.md", PLAN)
    assert cf.shot_characters(tmp_path, "keira") == ["keira"]


# 4. The fingerprint

def test_the_fingerprint_changes_when_a_character_file_changes(tmp_path, monkeypatch):
    from imported_kit import make_imported
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    folder = make_imported(tmp_path / "chars", "synth")
    before = cf.fingerprint("synth")
    assert cf.fingerprint("synth") == before
    mesh = folder / "mesh.json"
    mesh.write_text(mesh.read_text(encoding="utf-8").replace("]", "] ", 1), encoding="utf-8")
    assert cf.fingerprint("synth") != before


def test_the_fit_approval_alone_does_not_change_the_fingerprint(tmp_path, monkeypatch):
    from imported_kit import make_imported, unconfirm
    from kei.characters.imported import confirm
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    folder = make_imported(tmp_path / "chars", "synth", confirmed=False)
    before = cf.fingerprint("synth")
    confirm(folder)
    assert cf.fingerprint("synth") == before
    unconfirm(folder)


# 2. Reuse

def test_a_fresh_saved_evaluation_is_reused_without_the_animator(tmp_path):
    folder = saved_folder(tmp_path, "kei")
    shot = folder / "walk_two"
    shot.mkdir()
    rec = Animator(["kei"])
    state = run_shot(shot, "a walk", CFG, animator=FakeSeat("fake", rec))
    assert state.status == "needs_approval"
    assert "rig" not in rec.stages() and "weight" not in rec.stages()
    passed = [h["stage"] for h in state.history if h["result"] == "pass"]
    assert passed[:3] == ["brief", "rig", "weight"]
    reused = [h for h in state.history if h["result"] == "reused"]
    assert [h["stage"] for h in reused] == ["rig", "weight"]
    assert "reused kei/CHARACTER.md from 2026-11-01" in reused[0]["reused"]
    text = (shot / "CHARACTER.md").read_text(encoding="utf-8")
    assert "Rig: the saved rig of kei" in text and "Class: heavy" in text


def test_reuse_still_runs_the_gate(tmp_path, monkeypatch):
    folder = saved_folder(tmp_path, "kei")
    shot = folder / "walk_two"
    shot.mkdir()
    import kei.conductor as conductor
    real = conductor.stage_misses
    seen = []

    def spy(shot_dir, stage):
        seen.append(stage.id)
        return real(shot_dir, stage)
    monkeypatch.setattr(conductor, "stage_misses", spy)
    run_shot(shot, "a walk", CFG, animator=FakeSeat("fake", Animator(["kei"])))
    assert "rig" in seen and "weight" in seen


def test_reuse_copies_the_evidence_into_the_shot(tmp_path):
    folder = saved_folder(tmp_path, "kei")
    write(folder, "rig_eval/rig_probe.json", '{"saved": 1}')
    write(folder, "weight_eval/mass.json", '{"saved": 2}')
    shot = folder / "walk_two"
    shot.mkdir()
    run_shot(shot, "a walk", CFG, animator=FakeSeat("fake", Animator(["kei"])))
    assert json.loads((shot / "rig_eval" / "rig_probe.json").read_text(encoding="utf-8")) == {"saved": 1}
    assert (shot / "weight_eval" / "mass.json").is_file()


# 3. Save

def test_a_shot_in_a_character_folder_saves_its_evaluation(tmp_path):
    folder = tmp_path / "shots" / "kei"
    shot = folder / "walk_one"
    shot.mkdir(parents=True)
    rec = Animator(["kei"], evidence=True)
    state = run_shot(shot, "a walk", CFG, animator=FakeSeat("fake", rec))
    assert state.status == "needs_approval"
    assert "rig" in rec.stages()
    saved = cf.saved_evaluation(folder, "kei")
    assert saved is not None and saved.fingerprint == cf.fingerprint("kei")
    assert "Rig: kei's rig, measured in this shot" in saved.text and "Class: average" in saved.text
    assert re.match(r"\d{4}-\d{2}-\d{2}$", saved.date)
    assert (folder / "rig_eval" / "probe.json").is_file() and (folder / "weight_eval" / "probe.json").is_file()


def test_the_next_shot_reuses_what_the_first_saved(tmp_path):
    folder = tmp_path / "shots" / "kei"
    (folder / "walk_one").mkdir(parents=True)
    (folder / "walk_two").mkdir()
    run_shot(folder / "walk_one", "a walk", CFG, animator=FakeSeat("fake", Animator(["kei"])))
    second = Animator(["kei"])
    run_shot(folder / "walk_two", "a second walk", CFG, animator=FakeSeat("fake", second))
    assert "rig" not in second.stages() and "weight" not in second.stages()


# 4. Stale

def test_a_changed_character_file_makes_the_next_shot_evaluate_again(tmp_path, monkeypatch):
    from imported_kit import make_imported
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    chars = make_imported(tmp_path / "chars", "synth")
    folder = tmp_path / "shots" / "synth"
    (folder / "walk_one").mkdir(parents=True)
    run_shot(folder / "walk_one", "a walk", CFG, animator=FakeSeat("fake", Animator(["synth"])))
    old = cf.saved_evaluation(folder, "synth")
    mesh = chars / "mesh.json"
    mesh.write_text(mesh.read_text(encoding="utf-8").replace("]", "] ", 1), encoding="utf-8")   # a refit
    (folder / "walk_two").mkdir()
    second = Animator(["synth"])
    state = run_shot(folder / "walk_two", "a second walk", CFG, animator=FakeSeat("fake", second))
    assert state.status == "needs_approval"
    assert "rig" in second.stages() and "weight" in second.stages()
    new = cf.saved_evaluation(folder, "synth")
    assert new.fingerprint == cf.fingerprint("synth") != old.fingerprint
    assert (folder / "CHARACTER.md").read_text(encoding="utf-8").count("## synth") == 1


def test_a_stale_section_is_not_reused(tmp_path):
    folder = saved_folder(tmp_path, "kei", fp="0" * 16)
    shot = folder / "walk_two"
    shot.mkdir()
    rec = Animator(["kei"])
    run_shot(shot, "a walk", CFG, animator=FakeSeat("fake", rec))
    assert "rig" in rec.stages()
    assert cf.saved_evaluation(folder, "kei").fingerprint == cf.fingerprint("kei")


# 5. Outside a folder, and two characters

def test_a_shot_outside_a_character_folder_evaluates_and_saves_nothing(tmp_path):
    shot = tmp_path / "shots" / "walk"
    shot.mkdir(parents=True)
    rec = Animator(["kei"])
    state = run_shot(shot, "a walk", CFG, animator=FakeSeat("fake", rec))
    assert state.status == "needs_approval"
    assert "rig" in rec.stages() and "weight" in rec.stages()
    assert not any(h["result"] == "reused" for h in state.history)
    assert not (tmp_path / "shots" / "CHARACTER.md").exists()


def test_two_characters_reuse_the_one_saved_and_evaluate_the_other(tmp_path):
    folder = saved_folder(tmp_path, "kei")
    shot = folder / "duet"
    shot.mkdir()
    rec = Animator(["kei", "keira"])
    state = run_shot(shot, "kei and keira walk together", CFG, animator=FakeSeat("fake", rec))
    assert state.status == "needs_approval"
    rig = [p for p in rec.prompts if stage_of(p) == "rig"]
    assert rig and "reused kei/CHARACTER.md from 2026-11-01" in rig[0] and "keira" in rig[0]
    text = (shot / "CHARACTER.md").read_text(encoding="utf-8")
    assert "Rig: the saved rig of kei" in text and "Rig: keira's rig, measured in this shot" in text
    assert cf.saved_evaluation(folder, "keira").fingerprint == cf.fingerprint("keira")
    assert cf.saved_evaluation(folder, "kei").date == "2026-11-01"   # the fresh one is left as it was


def test_a_reused_section_the_animator_drops_is_put_back(tmp_path):
    folder = saved_folder(tmp_path, "kei")
    shot = folder / "duet"
    shot.mkdir()
    rec = Animator(["kei", "keira"])

    def careless(prompt, root):
        out = rec(prompt, root)
        if stage_of(prompt) == "rig":
            write(root, "CHARACTER.md", "## keira\nRig: keira's rig, measured in this shot\n")
        return out
    run_shot(shot, "a duet", CFG, animator=FakeSeat("fake", careless))
    assert "Rig: the saved rig of kei" in (shot / "CHARACTER.md").read_text(encoding="utf-8")


# 6. A vetted REFS.md of the same action as a draft

def test_the_action_is_the_action_line_else_the_first_action_word_of_the_request(tmp_path):
    write(tmp_path, "PLAN.md", PLAN)
    assert cf.shot_action(tmp_path, "a heavy looping walk cycle") == "walk"
    assert cf.shot_action(tmp_path, "Kei runs to the door") == "run"
    assert cf.shot_action(tmp_path, "a box falls") == "fall"
    write(tmp_path, "PLAN.md", PLAN + "Action: jump\n")
    assert cf.shot_action(tmp_path, "a walk") == "jump"


def sibling(folder, name, request, refs_rel="REFS.md"):
    from shotkit import REFS
    from kei.state import ShotState, save_state
    d = folder / name
    write(d, "PLAN.md", plan_for("kei") + ("" if refs_rel == "REFS.md" else f"Refs: {refs_rel}\n"))
    write(d, refs_rel, REFS)
    save_state(d, ShotState(stage="deliver", status="done", request=request))
    return (d / refs_rel).resolve()


def test_a_sibling_shot_of_the_same_action_gives_its_refs_as_a_draft(tmp_path):
    folder = tmp_path / "shots" / "kei"
    old = sibling(folder, "walk_one", "a walk with personality", "refs/REFS.md")
    sibling(folder, "jump_box", "a jump over a box")
    shot = folder / "walk_two"
    write(shot, "PLAN.md", plan_for("kei"))
    assert cf.draft_refs(shot, "a tired walking cycle") == [old]


def test_the_references_prompt_names_the_draft_to_re_vet(tmp_path):
    folder = tmp_path / "shots" / "kei"
    old = sibling(folder, "walk_one", "a walk with personality")
    shot = folder / "walk_two"
    shot.mkdir()
    rec = Animator(["kei"])
    run_shot(shot, "a tired walk", CFG, animator=FakeSeat("fake", rec))
    refs = [p for p in rec.prompts if stage_of(p) == "references"][0]
    assert str(old) in refs
    assert "draft" in refs and "never copy" in refs
    assert str(old) not in [p for p in rec.prompts if stage_of(p) == "study"][0]


def test_no_draft_for_another_action_or_outside_a_character_folder(tmp_path):
    folder = tmp_path / "shots" / "kei"
    sibling(folder, "jump_box", "a jump over a box")
    shot = folder / "walk_two"
    write(shot, "PLAN.md", plan_for("kei"))
    assert cf.draft_refs(shot, "a walk") == []
    plain = tmp_path / "other"
    sibling(plain, "walk_one", "a walk")
    write(plain / "walk_two", "PLAN.md", plan_for("kei"))
    assert cf.draft_refs(plain / "walk_two", "a walk") == []


# 7. kei shots tidy

def tidy_folder(tmp_path):
    from kei.state import ShotState, save_state
    root = tmp_path / "kei-shots"
    write(root / "walk_one", "PLAN.md", plan_for("kei"))
    write(root / "keira_walk", "kei.toml", '[shot]\ncharacter = "keira"\n')
    write(root / "keira_walk", "PLAN.md", PLAN)
    write(root / "busy_walk", "PLAN.md", plan_for("kei"))
    save_state(root / "busy_walk", ShotState(stage="blocking", status="running", request="a walk"))
    write(root / "kei" / "jump", "PLAN.md", plan_for("kei"))   # already in its character folder
    write(root / "notes", "x.txt", "not a shot")
    return root


def test_tidy_dry_run_lists_the_moves_and_moves_nothing(tmp_path, capsys):
    from kei.cli import main
    root = tidy_folder(tmp_path)
    assert main(["shots", "tidy", str(root), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "walk_one -> kei/walk_one" in out
    assert "keira_walk -> keira/keira_walk" in out
    assert "busy_walk" in out and "running" in out
    assert "jump" not in out and "notes" not in out
    assert (root / "walk_one").is_dir() and not (root / "kei" / "walk_one").exists()


def test_tidy_never_moves_without_apply(tmp_path, capsys):
    from kei.cli import main
    root = tidy_folder(tmp_path)
    assert main(["shots", "tidy", str(root)]) == 0
    assert "--apply" in capsys.readouterr().out
    assert (root / "walk_one").is_dir() and (root / "keira_walk").is_dir()


def test_tidy_apply_moves_each_shot_and_refuses_a_running_one(tmp_path, capsys):
    from kei.cli import main
    root = tidy_folder(tmp_path)
    assert main(["shots", "tidy", str(root), "--apply"]) == 0
    assert (root / "kei" / "walk_one" / "PLAN.md").is_file() and not (root / "walk_one").exists()
    assert (root / "keira" / "keira_walk" / "kei.toml").is_file()
    assert (root / "busy_walk").is_dir() and not (root / "kei" / "busy_walk").exists()
    assert (root / "kei" / "jump" / "PLAN.md").is_file()
    assert "refused" in capsys.readouterr().out


def test_tidy_refuses_a_move_onto_an_existing_folder(tmp_path, capsys):
    from kei.cli import main
    root = tidy_folder(tmp_path)
    write(root / "kei" / "walk_one", "PLAN.md", "another shot")
    assert main(["shots", "tidy", str(root), "--apply"]) == 0
    assert (root / "walk_one" / "PLAN.md").is_file()
    assert (root / "kei" / "walk_one" / "PLAN.md").read_text(encoding="utf-8") == "another shot"


# The run log says what was reused

def test_kei_run_prints_what_it_reused(tmp_path, capsys, monkeypatch):
    import kei.cli as cli
    from kei.state import ShotState, save_state

    def fake_run(shot, request, config):
        state = load_state(shot)
        state.history.append({"stage": "rig", "result": "reused", "misses": [],
                              "reused": "reused kei/CHARACTER.md from 2026-11-01 (kei)"})
        state.status = "needs_human"
        save_state(shot, state)
        return state
    monkeypatch.setattr(cli, "run_shot", fake_run)
    save_state(tmp_path, ShotState(request="a walk", history=[{"stage": "brief", "result": "reused", "misses": [],
                                                                "reused": "an older run"}]))
    cli.main(["run", str(tmp_path)])
    out = capsys.readouterr().out
    assert "reused kei/CHARACTER.md from 2026-11-01 (kei)" in out and "an older run" not in out


# Short headings: "## kei" for kei_model

def imported(tmp_path, monkeypatch, name="hero_model", title="Hero Shape"):
    from imported_kit import make_imported
    monkeypatch.setenv("KEI_CHARACTERS", str(tmp_path / "chars"))
    folder = make_imported(tmp_path / "chars", name)
    data = json.loads((folder / "character.json").read_text(encoding="utf-8"))
    data["title"] = title
    (folder / "character.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    return folder


def test_a_heading_may_name_the_character_without_model_or_by_its_display_name(tmp_path, monkeypatch):
    imported(tmp_path, monkeypatch)
    for head in ("hero_model", "hero", "Hero Shape", "HERO"):
        assert cf.section_for(f"# x\n\n## {head}\nRig: r\n", "hero_model") == f"## {head}\nRig: r\n"
    assert cf.section_for("## heroine\nRig: r\n", "hero_model") is None


def test_a_parent_whose_sheet_uses_the_short_name_is_the_character_folder(tmp_path, monkeypatch):
    imported(tmp_path, monkeypatch)
    folder = tmp_path / "shots" / "heroes"
    (folder / "walk").mkdir(parents=True)
    (folder / "CHARACTER.md").write_text("## hero\nRig: r\n", encoding="utf-8")
    assert cf.character_folder(folder / "walk", ["hero_model"]) == folder


def test_a_short_heading_in_the_shot_is_saved_under_the_full_name(tmp_path, monkeypatch):
    imported(tmp_path, monkeypatch)
    folder = tmp_path / "shots" / "hero_model"
    shot = folder / "walk"
    write(shot, "PLAN.md", plan_for("hero_model"))
    write(shot, "CHARACTER.md", "# CHARACTER\n\n## hero\nRig: measured\nMass: 80 kg\nClass: heavy\n")
    assert cf.save_evaluations(shot, "kei", today="2026-11-06") == ["hero_model"]
    text = (folder / "CHARACTER.md").read_text(encoding="utf-8")
    assert text.startswith("## hero_model\n") and "Rig: measured" in text and "## hero\n" not in text
    assert cf.saved_evaluation(folder, "hero_model").date == "2026-11-06"


def test_a_stale_short_section_in_the_folder_is_replaced_by_the_full_name(tmp_path, monkeypatch):
    imported(tmp_path, monkeypatch)
    folder = tmp_path / "shots" / "hero_model"
    write(folder, "CHARACTER.md", "## hero\nFingerprint: 0000\nEvaluated: 2026-01-01 in old\nRig: old\nMass: 1 kg\n"
                                  "Class: light\n")
    shot = folder / "walk"
    write(shot, "PLAN.md", plan_for("hero_model"))
    write(shot, "CHARACTER.md", "## Hero Shape\nRig: new\nMass: 80 kg\nClass: heavy\n")
    cf.save_evaluations(shot, "kei", today="2026-11-06")
    text = (folder / "CHARACTER.md").read_text(encoding="utf-8")
    assert text.count("## ") == 1 and "## hero_model\n" in text and "Rig: new" in text


def test_a_fresh_short_section_in_the_folder_is_reused(tmp_path, monkeypatch):
    imported(tmp_path, monkeypatch)
    folder = tmp_path / "shots" / "hero_model"
    write(folder, "CHARACTER.md", SAVED.format(name="hero", fp=cf.fingerprint("hero_model")))
    shot = folder / "walk"
    write(shot, "PLAN.md", plan_for("hero_model"))
    reuse = cf.plan_reuse(shot, "kei")
    assert reuse is not None and reuse.whole and list(reuse.saved) == ["hero_model"]
    write(shot, "CHARACTER.md", "## hero\nRig: an older try\n")
    cf.apply_reuse(shot, reuse)
    text = (shot / "CHARACTER.md").read_text(encoding="utf-8")
    assert text.count("## ") == 1 and "Rig: the saved rig of hero" in text


# The references draft with no Character line: the config's default character

def test_draft_refs_falls_back_to_the_default_character(tmp_path):
    from shotkit import REFS
    from kei.state import ShotState, save_state
    folder = tmp_path / "shots" / "keira"
    for name, request in (("walk_one", "a walk"), ("walk_two", "a second walk")):
        write(folder / name, "PLAN.md", PLAN)
    write(folder / "walk_one", "REFS.md", REFS)
    save_state(folder / "walk_one", ShotState(stage="deliver", status="done", request="a walk"))
    assert cf.draft_refs(folder / "walk_two", "a second walk") == []
    assert cf.draft_refs(folder / "walk_two", "a second walk", default="keira") == [
        (folder / "walk_one" / "REFS.md").resolve()]


def test_the_references_prompt_uses_the_default_character_for_the_draft(tmp_path):
    from dataclasses import replace
    from shotkit import REFS
    from kei.state import ShotState, save_state
    folder = tmp_path / "shots" / "keira"
    write(folder / "walk_one", "PLAN.md", PLAN)
    write(folder / "walk_one", "REFS.md", REFS)
    save_state(folder / "walk_one", ShotState(stage="deliver", status="done", request="a walk"))
    shot = folder / "walk_two"
    shot.mkdir()

    class NoLine(Animator):
        def __call__(self, prompt, root):
            out = super().__call__(prompt, root)
            if stage_of(prompt) == "brief":
                write(root, "PLAN.md", PLAN)
            return out
    rec = NoLine(["keira"])
    run_shot(shot, "a tired walk", replace(CFG, character="keira"), animator=FakeSeat("fake", rec))
    refs = [p for p in rec.prompts if stage_of(p) == "references"][0]
    assert str((folder / "walk_one" / "REFS.md").resolve()) in refs


# GROWTH.md: in the shot folder, beside it, or, for a shot moved into a character folder, beside that folder

def delivered(root, plan=PLAN):
    from shotkit import full
    full(root, upto="self_review")
    write(root, "PLAN.md", plan)
    write(root, "video/shot.mp4")
    write(root, "REVIEW.md", "## What I learned\n- a box needs one frame of hold before it tips\n")


def p12(root):
    from kei.gates.pipeline import check
    return [m for m in check(str(root), deliver=True)[0] if m.startswith("P12")]


def growth(folder, shot_name):
    write(folder, "GROWTH.md", f"## {shot_name}\n- learned\n")


def test_growth_beside_the_shot_still_counts(tmp_path):
    root = tmp_path / "kei-shots" / "walk"
    delivered(root)
    assert p12(root)
    growth(tmp_path / "kei-shots", "walk")
    assert p12(root) == []


def test_growth_in_the_shot_folder_counts(tmp_path):
    root = tmp_path / "kei-shots" / "walk"
    delivered(root)
    growth(root, "walk")
    assert p12(root) == []


def test_growth_beside_the_character_folder_counts_for_a_moved_shot(tmp_path):
    shots = tmp_path / "kei-shots"
    root = shots / "kei_model" / "walk"
    delivered(root, plan_for("kei_model"))
    growth(shots, "walk")
    assert p12(root) == []


def test_growth_two_levels_up_does_not_count_outside_a_character_folder(tmp_path):
    root = tmp_path / "kei-shots" / "misc" / "walk"
    delivered(root)
    growth(tmp_path / "kei-shots", "walk")
    assert p12(root)


def test_growth_beside_a_folder_holding_character_md_counts(tmp_path):
    shots = tmp_path / "kei-shots"
    root = shots / "heroes" / "walk"
    delivered(root)
    write(shots / "heroes", "CHARACTER.md", "## kei\nRig: r\n")
    growth(shots, "walk")
    assert p12(root) == []


def test_tidy_leaves_growth_md_where_it_is_and_the_gate_still_finds_it(tmp_path, capsys):
    from kei.cli import main
    shots = tmp_path / "kei-shots"
    delivered(shots / "walk", plan_for("kei_model"))
    growth(shots, "walk")
    assert p12(shots / "walk") == []
    assert main(["shots", "tidy", str(shots), "--apply"]) == 0
    assert (shots / "GROWTH.md").is_file() and not (shots / "kei_model" / "GROWTH.md").exists()
    assert p12(shots / "kei_model" / "walk") == []
