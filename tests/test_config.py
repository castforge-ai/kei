from pathlib import Path

import pytest

from kei.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parent.parent


def test_loads_the_example():
    c = load_config(ROOT / "kei.example.toml")
    assert c.animator.cmd[:4] == ["claude", "-p", "--output-format", "text"]
    assert [s.name for s in c.critics] == ["claude-critic", "codex"]
    assert c.max_attempts == 3
    assert c.max_send_backs == 3
    assert c.share == "ask"


def test_defaults_when_limits_and_share_are_missing(tmp_path):
    p = tmp_path / "kei.toml"
    p.write_text('[animator]\ncmd = ["x"]\n', encoding="utf-8")
    c = load_config(p)
    assert c.max_attempts == 3
    assert c.max_send_backs == 3
    assert c.share == "ask"
    assert c.critics == []
    assert c.animator.timeout_s == 1800


@pytest.mark.parametrize("body, key", [
    ('[animator]\ncmd = ["x"]\n[limits]\nmax_attempts = 0\n', "max_attempts"),
    ('[animator]\ncmd = ["x"]\n[limits]\nmax_send_backs = "3"\n', "max_send_backs"),
    ('[animator]\ncmd = ["x"]\n[share]\nmode = "sometimes"\n', "share.mode"),
    ('[animator]\ncmd = []\n', "animator.cmd"),
    ('[limits]\nmax_attempts = 3\n', "animator"),
])
def test_rejects_bad_values(tmp_path, body, key):
    p = tmp_path / "kei.toml"
    p.write_text(body, encoding="utf-8")
    with pytest.raises(ConfigError) as e:
        load_config(p)
    assert key in str(e.value)


def test_example_animator_can_write_files_in_the_shot_and_beside_it():
    c = load_config(ROOT / "kei.example.toml")
    cmd = c.animator.cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
    assert cmd[cmd.index("--add-dir") + 1] == ".."


def test_example_critics_are_read_only():
    c = load_config(ROOT / "kei.example.toml")
    by = {s.name: s.cmd for s in c.critics}
    claude, codex = by["claude-critic"], by["codex"]
    assert claude[claude.index("--permission-mode") + 1] == "plan"
    assert codex[codex.index("--sandbox") + 1] == "read-only"
    assert "--skip-git-repo-check" in codex   # a shot folder is usually not a git repository


def test_book_paths_resolve_against_the_config_folder(tmp_path):
    from kei.book import BUNDLED_BOOK
    p = tmp_path / "kei.toml"
    p.write_text('[animator]\ncmd = ["x"]\n', encoding="utf-8")
    c = load_config(p)
    assert (c.book, c.lessons, c.max_rule_chars) == (BUNDLED_BOOK, tmp_path / "lessons.local.md", 450000)
    p.write_text('[animator]\ncmd = ["x"]\n[book]\npath = "my/book.md"\nlessons = "l.md"\nmax_chars = 9\n',
                 encoding="utf-8")
    c = load_config(p)
    assert (c.book, c.lessons, c.max_rule_chars) == (tmp_path / "my/book.md", tmp_path / "l.md", 9)


def test_max_chars_must_be_positive(tmp_path):
    p = tmp_path / "kei.toml"
    p.write_text('[animator]\ncmd = ["x"]\n[book]\nmax_chars = 0\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="max_chars"):
        load_config(p)


def test_example_animator_may_run_the_commands_the_stages_need():
    cmd = load_config(ROOT / "kei.example.toml").animator.cmd
    allowed = ",".join(cmd[cmd.index("--allowedTools") + 1:]).replace(" ", "")
    for tool in ("Bash(kei*)", "Bash(python*)", "Bash(ffmpeg*)", "PowerShell(kei*)", "PowerShell(python*)"):
        assert tool in allowed, tool
    assert "Bash(*)" not in allowed and "Bash" not in allowed.split(",")   # scoped, never every command


ISOLATION = ("--safe-mode", "--strict-mcp-config", "--disable-slash-commands")


def test_example_claude_seats_load_none_of_the_users_setup():
    c = load_config(ROOT / "kei.example.toml")
    for seat in [c.animator] + [s for s in c.critics if s.cmd[0] == "claude"]:
        for flag in ISOLATION:
            assert flag in seat.cmd, (seat.name, flag)
        assert seat.cmd[seat.cmd.index("--setting-sources") + 1] == "project,local", seat.name   # never "user"


def test_example_codex_critic_skips_the_users_config_rules_and_history():
    codex = {s.name: s.cmd for s in load_config(ROOT / "kei.example.toml").critics}["codex"]
    for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral"):
        assert flag in codex, flag
    assert codex[-1] == "-"   # the prompt still comes on stdin


def test_example_codex_critic_runs_unelevated_on_windows():
    codex = {s.name: s.cmd for s in load_config(ROOT / "kei.example.toml").critics}["codex"]
    i = codex.index("-c")
    assert codex[i + 1] == 'windows.sandbox="unelevated"'
