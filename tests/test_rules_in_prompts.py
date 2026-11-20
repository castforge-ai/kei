import json
import sys
from dataclasses import replace

import pytest

from kei.book import BookError
from kei.cli import main
from kei.seats import FakeSeat
from test_conductor import CFG, Recorder, run_shot, shot, stage_of
from test_conductor_critic import always_pass, critic
from test_conductor_critic import run_shot as run_with_critics

BOOK = """### R1. Plan rule
stages: plan

Plan text.

### R2. Blocking rule
stages: blocking

Blocking text.
"""
LESSON = """### local.1. A lesson (provisional)
stages: plan

Lesson text.
"""


def config(tmp_path, **kw):
    book = tmp_path / "book.md"
    book.write_text(BOOK, encoding="utf-8")
    return replace(CFG, book=book, lessons=tmp_path / "lessons.local.md", **kw)


def prompts_for(rec, title):
    return [p for p in rec.prompts if stage_of(p) == title]


def test_stage_prompt_carries_only_its_rules(tmp_path):
    rec = Recorder()
    run_shot(shot(tmp_path), "a box falls", config(tmp_path), animator=FakeSeat("fake", rec))
    plan = prompts_for(rec, "Plan")[0]
    assert "### R1. Plan rule" in plan and "R2" not in plan
    assert "### R2. Blocking rule" in prompts_for(rec, "Blocking")[0]
    assert "Rules for this stage" not in prompts_for(rec, "Brief")[0]


def test_critic_prompt_carries_the_stage_rules(tmp_path):
    c = critic("c1", always_pass)
    run_with_critics(shot(tmp_path), "a box falls", config(tmp_path), animator=FakeSeat("fake", Recorder()),
                     critics=[c])
    plan = next(p for p in c.prompts if "Stage under review: Plan" in p)
    assert "- R1. Plan rule" in plan and "R2" not in plan, "the critic gets a checklist of the stage rules"


def test_local_lesson_follows_the_book(tmp_path):
    (tmp_path / "lessons.local.md").write_text(LESSON, encoding="utf-8")
    rec = Recorder()
    run_shot(shot(tmp_path), "a box falls", config(tmp_path), animator=FakeSeat("fake", rec))
    plan = prompts_for(rec, "Plan")[0]
    assert plan.index("R1. Plan rule") < plan.index("local.1. A lesson")


def test_rules_over_the_limit_stop_the_run(tmp_path):
    rec = Recorder()
    with pytest.raises(BookError) as e:
        run_shot(shot(tmp_path), "a box falls", config(tmp_path, max_rule_chars=10), animator=FakeSeat("fake", rec))
    assert "stage plan" in str(e.value) and "max_chars" in str(e.value)
    assert rec.prompts == []


def test_bad_book_is_one_line_and_exit_1(tmp_path, capsys):
    root = shot(tmp_path)
    (tmp_path / "book.md").write_text("### R1. No stages line\n\ntext\n", encoding="utf-8")
    cfg = tmp_path / "kei.toml"
    seat = json.dumps([sys.executable, "-c", "pass"])
    cfg.write_text(f'[animator]\ncmd = {seat}\n[[critics]]\nname = "c"\ncmd = {seat}\n[book]\npath = "book.md"\n',
                   encoding="utf-8")
    assert main(["run", str(root), "--request", "a box falls", "--config", str(cfg)]) == 1
    out = capsys.readouterr()
    assert "R1" in out.out + out.err and "Traceback" not in out.out + out.err


def test_missing_book_is_refused(tmp_path):
    cfg = replace(config(tmp_path), book=tmp_path / "my-bok.md")
    rec = Recorder()
    with pytest.raises(BookError) as e:
        run_shot(shot(tmp_path), "a box falls", cfg, animator=FakeSeat("fake", rec))
    assert "my-bok.md" in str(e.value) and rec.prompts == []
