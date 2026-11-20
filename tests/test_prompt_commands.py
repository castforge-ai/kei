"""Every kei command a stage prompt or the skill tells the agent to run exists: a removed or renamed command fails here."""
import re
from pathlib import Path

import pytest

from kei.cli import main

ROOT = Path(__file__).resolve().parent.parent
TEXTS = sorted((ROOT / "kei" / "prompts").glob("*.md")) + sorted((ROOT / "skill").rglob("*.md"))


def _named() -> set[str]:
    out = set()
    for p in TEXTS:
        out |= set(re.findall(r"`kei ([a-z]+)", p.read_text(encoding="utf-8")))
    return out


def test_the_prompts_name_the_new_tools():
    assert {"poses", "probe", "check", "render"} <= _named()


@pytest.mark.parametrize("cmd", sorted(_named()))
def test_a_command_the_agent_is_told_to_run_exists(cmd, capsys):
    with pytest.raises(SystemExit) as e:
        main([cmd, "--help"])
    assert e.value.code == 0, f"`kei {cmd}` is named in a prompt but is not a kei command"
