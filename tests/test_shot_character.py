"""The shot's character: named in PLAN.md, defaulted by the config, checked at the brief, used by render and bake."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from kei import render
from kei.characters import CHARACTERS, DATA, character_misses, load_character, plan_character, shot_character
from kei.cli import EXAMPLE_CONFIG, main
from kei.config import ConfigError, load_config
from kei.prompts import HERE as PROMPTS
from kei.seats import FakeSeat
from shotkit import STAGE_WRITERS
from test_conductor import CFG, Recorder, run_shot, shot
from test_conductor_critic import always_pass, critic
from test_conductor_critic import run_shot as run_with_critics

STAND = {"rig": "v4", "fps": 12, "frames": 2,
         "keys": [{"f": 0, "root": [0, 0.915, 0], "footL": [-0.15, 0.09, 0], "footR": [0.15, 0.09, 0]},
                  {"f": 2, "root": [0, 0.9, 0.02], "footL": [-0.15, 0.09, 0], "footR": [0.15, 0.09, 0]}]}


def plan(root, line):
    root.mkdir(parents=True, exist_ok=True)
    (root / "PLAN.md").write_text(f"# Brief\n\nIdea sentence: a stand.\n{line}\n", encoding="utf-8")


def shot_folder(tmp_path, shot=STAND, line=None):
    root = tmp_path / "stand"
    (root / "out_p1").mkdir(parents=True)
    (root / "out_p1" / "shot.json").write_text(json.dumps(shot), encoding="utf-8")
    if line is not None:
        plan(root, line)
    return root


def config_file(tmp_path, character=None):
    text = EXAMPLE_CONFIG.read_text(encoding="utf-8")
    if character is not None:
        text = text.replace('character = "kei"', f'character = "{character}"')
    p = tmp_path / "kei.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_the_known_characters_are_the_files():
    assert set(CHARACTERS) == {p.stem for p in DATA.glob("*.json")}
    assert CHARACTERS[0] == "kei"


@pytest.mark.parametrize("line", ["Character: Keira", "- Character: keira", "**Character:** keira",
                                  "character: KEIRA", "* **Character**: keira"])
def test_the_character_line_is_read(tmp_path, line):
    plan(tmp_path, line)
    assert plan_character(tmp_path) == "keira"


def test_no_line_means_no_choice(tmp_path):
    plan(tmp_path, "Subjects: all")
    assert plan_character(tmp_path) is None
    assert plan_character(tmp_path / "nowhere") is None


def test_the_config_default_is_kei_and_can_be_keira(tmp_path):
    assert load_config(EXAMPLE_CONFIG).character == "kei"
    assert "[shot]" in EXAMPLE_CONFIG.read_text(encoding="utf-8")
    assert load_config(config_file(tmp_path, "keira")).character == "keira"
    with pytest.raises(ConfigError, match="bob.*kei, keira"):
        load_config(config_file(tmp_path, "bob"))


def test_the_order_is_shot_json_then_plan_then_config(tmp_path):
    plan(tmp_path, "Character: keira")
    assert shot_character(tmp_path, {"character": "kei"}, "kei") == "kei"
    assert shot_character(tmp_path, {}, "kei") == "keira"
    (tmp_path / "PLAN.md").write_text("no line\n", encoding="utf-8")
    assert shot_character(tmp_path, {}, "keira") == "keira"
    with pytest.raises(Exception, match="bob"):
        shot_character(tmp_path, {"character": "bob"}, "kei")


def test_an_unknown_name_is_refused_with_the_known_ones(tmp_path):
    plan(tmp_path, "Character: bob")
    misses = character_misses(tmp_path)
    assert len(misses) == 1 and "bob" in misses[0] and "kei, keira" in misses[0]
    plan(tmp_path, "Character: keira")
    assert character_misses(tmp_path) == []
    plan(tmp_path, "Subjects: all")
    assert character_misses(tmp_path) == []


def brief_with(line):
    def fault(sid, n, r):
        if sid == "brief":
            STAGE_WRITERS["brief"](r)
            p = r / "PLAN.md"
            p.write_text(p.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")
            return True
        return False
    return fault


def test_the_brief_gate_refuses_an_unknown_character(tmp_path):
    rec = Recorder(brief_with("Character: bob"))
    state = run_shot(shot(tmp_path), "a stand", CFG, animator=FakeSeat("fake", rec))
    assert (state.stage, state.status) == ("brief", "needs_human")
    miss = " ".join(state.history[-1]["misses"])
    assert "bob" in miss and "kei, keira" in miss


def test_the_brief_gate_accepts_a_known_character(tmp_path):
    rec = Recorder(brief_with("Character: keira"))
    state = run_shot(shot(tmp_path), "a stand", CFG, animator=FakeSeat("fake", rec))
    assert state.status == "needs_approval"


def test_the_brief_prompt_lists_every_character_and_the_default():
    text = (PROMPTS / "brief.md").read_text(encoding="utf-8")
    assert "Character:" in text
    for name in CHARACTERS:
        ch = load_character(name)
        line = next(l for l in text.splitlines() if l.lstrip("- ").startswith(f"{name}:"))
        assert ch.summary in line
    assert "default" in text and "Keira" in text and "build" in text


def test_a_later_change_of_character_is_reviewed_as_a_plan_change(tmp_path):
    def fault(sid, n, r):
        if sid == "brief":
            return brief_with("Character: kei")(sid, n, r)
        if sid == "blocking" and n == 1:
            STAGE_WRITERS["blocking"](r)
            p = r / "PLAN.md"
            p.write_text(p.read_text(encoding="utf-8").replace("Character: kei", "Character: keira"),
                         encoding="utf-8")
            return True
        return False

    c = critic("c1", always_pass)
    run_with_critics(shot(tmp_path), "a stand", CFG, animator=FakeSeat("fake", Recorder(fault)), critics=[c])
    reviewed = next(p for p in c.prompts if "Stage under review: Blocking" in p)
    assert "The plan changed since it was approved: PLAN.md" in reviewed


def test_render_uses_the_plan_character_and_labels_it(tmp_path, monkeypatch, capsys):
    labels = []
    real = render._character_panel

    def spy(cv, ox, oy, view, ch, parts, bounds, size, label, *a, **k):
        labels.append((ch.name, label))
        return real(cv, ox, oy, view, ch, parts, bounds, size, label, *a, **k)
    monkeypatch.setattr(render, "_character_panel", spy)
    root = shot_folder(tmp_path, line="Character: keira")
    assert main(["render", str(root), "p1", "--size", "80", "--config", str(config_file(tmp_path))]) == 0
    assert labels and all(n == "keira" and "keira" in l for n, l in labels)
    assert "keira" in capsys.readouterr().out


def test_the_shot_json_field_wins_and_an_unknown_one_exits_1(tmp_path, capsys):
    root = shot_folder(tmp_path, {**STAND, "character": "kei"}, line="Character: keira")
    cfg = str(config_file(tmp_path, "keira"))
    assert main(["bake", str(root), "p1", "--config", cfg]) == 0
    data = json.loads((root / "out_p1" / "joints.json").read_text(encoding="utf-8"))
    assert data["character"] == "kei"
    root2 = shot_folder(tmp_path / "b", {**STAND, "character": "bob"})
    capsys.readouterr()
    assert main(["render", str(root2), "p1", "--config", cfg]) == 1
    assert "bob" in "".join(capsys.readouterr())


def test_bake_uses_the_character_proportions(tmp_path):
    root = shot_folder(tmp_path)
    assert main(["bake", str(root), "p1", "--config", str(config_file(tmp_path, "keira"))]) == 0
    data = json.loads((root / "out_p1" / "joints.json").read_text(encoding="utf-8"))
    j = data["frames"][0]["joints"]
    import math
    keira = load_character("keira")
    assert data["character"] == "keira"
    assert abs(math.dist(j["thigh_l"], j["calf_l"]) - keira.proportions["thigh"]) < 1e-5


def test_the_stick_style_is_still_there(tmp_path):
    from test_sheet import decode
    root = shot_folder(tmp_path, line="Character: kei")
    assert main(["render", str(root), "p1", "--style", "stick", "--size", "100",
                 "--config", str(config_file(tmp_path))]) == 0
    w, h, _ = decode((root / "out_p1" / "frames" / "f0000.png").read_bytes())
    assert (w, h) == (200, 200)
    assert main(["render", str(root), "p1", "--size", "100", "--config", str(config_file(tmp_path))]) == 0
    w, h, _ = decode((root / "out_p1" / "frames" / "f0000.png").read_bytes())
    assert (w, h) == (500, 100)


def _passes_naming(root, plan_line, pass_character):
    plan(root, plan_line)
    (root / "out_p1").mkdir(parents=True, exist_ok=True)
    (root / "out_p1" / "shot.json").write_text(json.dumps({**STAND, "character": pass_character}), encoding="utf-8")


def test_a_pass_that_names_another_character_stops_the_shot_before_any_stage(tmp_path):
    # 2026-11-02: PLAN.md and kei.toml named kei_model, the walk's shot.json still named kei, so a whole pass was
    # made and reviewed on the old rig without anyone being told.
    from kei.characters import CharacterError
    root = shot(tmp_path)
    _passes_naming(root, "Character: keira", "kei")
    rec = Recorder()
    with pytest.raises(CharacterError) as e:
        run_shot(root, "a stand", CFG, animator=FakeSeat("fake", rec))
    assert "out_p1/shot.json" in str(e.value) and "'kei'" in str(e.value) and "'keira'" in str(e.value)
    assert rec.prompts == []


def test_a_stage_that_leaves_a_pass_for_another_character_is_refused_by_its_gate(tmp_path):
    root = shot(tmp_path)
    plan(root, "Character: keira")
    assert not character_misses(root)
    (root / "out_p2").mkdir()
    (root / "out_p2" / "shot.json").write_text(json.dumps({**STAND, "character": "kei"}), encoding="utf-8")
    miss = " ".join(character_misses(root))
    assert "out_p2/shot.json" in miss and "keira" in miss


def test_the_animator_prompt_names_the_shot_s_character(tmp_path):
    root = shot(tmp_path)
    plan(root, "Character: keira")
    rec = Recorder()
    run_shot(root, "a stand", CFG, animator=FakeSeat("fake", rec))
    assert "Character: keira" in rec.prompts[0], rec.prompts[0][:400]


def test_the_pass_read_is_the_highest_numbered_one_not_the_last_touched(tmp_path):
    import os, time
    root = shot(tmp_path)
    plan(root, "Character: keira")
    for n, ch in ((2, "kei"), (3, "keira")):
        (root / f"out_p{n}").mkdir()
        (root / f"out_p{n}" / "shot.json").write_text(json.dumps({**STAND, "character": ch}), encoding="utf-8")
    later = time.time() + 60
    os.utime(root / "out_p2" / "shot.json", (later, later))     # an old pass touched after the latest one
    assert not character_misses(root)
