"""The reference library: a folder of footage the seats may read, named in every stage's prompt."""
import json
import sys

import pytest

from kei.config import ConfigError, SeatSpec, load_config_text
from kei.prompts import stage_prompt
from kei.seats import with_dirs
from kei.stages import STAGES

SEAT = json.dumps([sys.executable, "-c", "pass"])
BASE = f'[animator]\ncmd = {SEAT}\n[[critics]]\nname = "c"\ncmd = {SEAT}\n'


def test_no_library_unless_a_folder_is_there_or_named(tmp_path):
    cfg = tmp_path / "kei.toml"
    assert load_config_text(BASE, cfg).refs_library is None
    (tmp_path / "kei-refs").mkdir()
    assert load_config_text(BASE, cfg).refs_library == tmp_path / "kei-refs"
    (tmp_path / "footage").mkdir()
    assert load_config_text(BASE + '[refs]\nlibrary = "footage"\n', cfg).refs_library == tmp_path / "footage"


def test_a_named_library_that_is_not_a_folder_is_refused(tmp_path):
    with pytest.raises(ConfigError, match="refs.library"):
        load_config_text(BASE + '[refs]\nlibrary = "nowhere"\n', tmp_path / "kei.toml")


def test_a_claude_seat_gets_read_access_and_another_cli_is_left_alone(tmp_path):
    claude = SeatSpec("a", ["claude", "-p", "--add-dir", ".."])
    got = with_dirs(claude, [tmp_path])
    assert got.cmd[:3] == ["claude", "--add-dir", str(tmp_path.resolve())] and got.cmd[3:] == claude.cmd[1:]
    assert with_dirs(got, [tmp_path]).cmd == got.cmd                       # never twice
    assert with_dirs(claude, [None]) is claude
    codex = SeatSpec("c", ["codex", "exec", "-"])
    assert with_dirs(codex, [tmp_path]) is codex


def test_the_prompt_names_the_library_and_how_to_use_it(tmp_path):
    lib = tmp_path / "kei-refs"
    lib.mkdir()
    shot = tmp_path / "shot"
    shot.mkdir()
    stage = next(s for s in STAGES if s.id == "references")
    text = stage_prompt(stage, shot, "a walk", [], refs_library=lib)
    assert lib.resolve().as_posix() in text and "INDEX.md" in text and "never trace" in text
    assert ".kei/look/" in text
    assert "Reference library" not in stage_prompt(stage, shot, "a walk", [])
