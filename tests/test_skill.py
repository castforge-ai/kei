"""The Kei skill (plan 4d, Task 5): skill/kei/SKILL.md names only kei commands and flags that exist, and the README's
first ten minutes says how to install it."""
import re
from pathlib import Path

import pytest

from kei.cli import main

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "kei" / "SKILL.md"
README = ROOT / "README.md"
REVIEW_COMMANDS = {"note", "fixed", "status", "approve", "drop", "park"}


def skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def kei_calls(text: str) -> list[list[str]]:
    """Each kei command the skill tells the agent to run: a code span or code line that starts with kei."""
    spans = re.findall(r"`(kei [^`]+)`", text)
    spans += [line.strip() for line in text.splitlines() if line.startswith("    kei ")]
    return [s.split() for s in spans]


def help_of(capsys, command: str) -> str:
    capsys.readouterr()
    with pytest.raises(SystemExit) as e:
        main([command, "--help"])
    assert e.value.code == 0, f"kei {command} is not a kei command"
    return capsys.readouterr().out


def test_the_skill_has_the_frontmatter_both_agents_read():
    text = skill_text()
    m = re.match(r"---\nname: kei\ndescription: (.+)\n---\n", text)
    assert m, "SKILL.md must start with name: kei and a one-line description"
    assert len(m.group(1)) <= 1024


def test_every_kei_command_in_the_skill_exists_with_its_flags(capsys):
    calls = kei_calls(skill_text())
    used = {c[1] for c in calls}
    assert REVIEW_COMMANDS <= used, f"the review section must use {sorted(REVIEW_COMMANDS - used)}"
    for call in calls:
        helptext = help_of(capsys, call[1])
        for flag in (t.split("=")[0] for t in call[2:] if t.startswith("--")):
            assert re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", helptext), \
                f"`{' '.join(call)}`: kei {call[1]} has no {flag}"


def test_the_skill_never_lets_the_agent_decide_for_the_author():
    text = skill_text()
    assert "Never sign off, drop or confirm without the author's answer in this chat" in text
    assert "--from chat" in text and "--undo" in text and "--mark-asked" in text
    assert "noted for this shot:" in text and "every shot too? (y/n)" in text
    assert "fixed? (all, or the numbers that are not)" in text


def test_the_skill_and_the_readme_have_no_em_dash():
    for p in (SKILL, README):
        assert chr(0x2014) not in p.read_text(encoding="utf-8"), p


def test_the_readme_says_how_to_install_the_skill_for_claude_code_and_codex():
    text = README.read_text(encoding="utf-8")
    start = text.index("## First ten minutes")
    part = text[start:text.index("\n## ", start + 1)]
    assert "skill/kei" in part
    assert ".claude/skills/kei" in part and ".agents/skills/kei" in part
    assert "Not built yet:\nthe skill entry point" not in text and "the skill entry point (First ten minutes)" \
        not in text
