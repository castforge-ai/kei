"""The author's banned-names list: a stage whose files name a banned source fails, and the miss never repeats the name."""
import json
import sys
from pathlib import Path

from kei.config import load_config_text
from kei.gates.sources import load_banned, source_misses
from kei.prompts import SOURCE_RULE, stage_prompt
from kei.stages import STAGES

SEAT = json.dumps([sys.executable, "-c", "pass"])
BASE = f'[animator]\ncmd = {SEAT}\n[[critics]]\nname = "c"\ncmd = {SEAT}\n'
NAME = "Zorblax Primer"          # a made-up title: no real name appears in Kei's tests


def banned(tmp_path, text=f"# my list\n\\bzorblax\\b\n(unclosed\n"):
    p = tmp_path / "kei.banned.txt"
    p.write_text(text, encoding="utf-8")
    return p


def test_the_list_reads_patterns_and_keeps_a_broken_one_as_plain_text(tmp_path):
    pats = load_banned(banned(tmp_path))
    assert [n for n, _ in pats] == [2, 3]
    assert pats[0][1].search("the ZORBLAX primer") and pats[1][1].search("x (unclosed y")
    assert load_banned(None) == [] and load_banned(tmp_path / "none.txt") == []


def test_a_banned_name_in_a_shot_file_is_a_miss_that_names_the_file_and_line_not_the_name(tmp_path):
    shot = tmp_path / "shot"
    (shot / "plan").mkdir(parents=True)
    (shot / "REFS.md").write_text(f"| 1. Gait study, 2010 | R |\n| 2. {NAME} | B |\n", encoding="utf-8")
    (shot / "plan" / "plan.json").write_text(json.dumps({"note": "clean"}), encoding="utf-8")
    misses = source_misses(shot, banned(tmp_path))
    assert misses == [misses[0]] and misses[0].startswith("SRC REFS.md line 2 ")
    assert "its line 2" in misses[0] and "zorblax" not in misses[0].lower()


def test_hidden_folders_and_frames_are_not_read_and_no_list_means_no_check(tmp_path):
    shot = tmp_path / "shot"
    (shot / ".kei").mkdir(parents=True)
    (shot / ".kei" / "state.json").write_text(json.dumps({"request": NAME}), encoding="utf-8")
    assert source_misses(shot, banned(tmp_path)) == []
    (shot / "PLAN.md").write_text(NAME, encoding="utf-8")
    assert source_misses(shot, None) == []
    assert len(source_misses(shot, banned(tmp_path))) == 1


def test_the_list_next_to_kei_toml_is_read_without_a_setting_and_a_setting_wins(tmp_path):
    cfg = tmp_path / "kei.toml"
    assert load_config_text(BASE, cfg).banned_names is None
    banned(tmp_path)
    assert load_config_text(BASE, cfg).banned_names == tmp_path / "kei.banned.txt"
    other = tmp_path / "lists" / "names.txt"
    other.parent.mkdir()
    other.write_text("x\n", encoding="utf-8")
    c = load_config_text(BASE + '[book]\nbanned_names = "lists/names.txt"\n', cfg)
    assert Path(c.banned_names) == other


def test_every_stage_prompt_carries_the_citing_rule(tmp_path):
    for stage in STAGES:
        assert SOURCE_RULE in stage_prompt(stage, tmp_path, "a walk", [])
    refs = (Path(__file__).resolve().parents[1] / "kei" / "prompts" / "references.md").read_text(encoding="utf-8")
    assert "never named" in refs and "one sentence" in refs and "(unchecked)" in refs
    assert "(unchecked)" in SOURCE_RULE


def test_a_loop_is_in_place_unless_the_author_asks_for_root_motion():
    prompts = Path(__file__).resolve().parents[1] / "kei" / "prompts"
    for name in ("plan.md", "blocking.md"):
        text = (prompts / name).read_text(encoding="utf-8")
        assert "IN PLACE unless the author asked for root motion" in text and '"in_place"' in text, name
