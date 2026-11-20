from pathlib import Path

import pytest

from kei.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parent.parent


def test_loads_the_example():
    c = load_config(ROOT / "kei.example.toml")
    assert c.animator.cmd[:4] == ["claude", "-p", "--output-format", "json"]   # json: Kei reads the token use
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


def test_with_the_example_config_lessons_go_to_the_folder_kei_runs_in(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = load_config(ROOT / "kei.example.toml")
    assert c.lessons == tmp_path / "lessons.local.md"   # never beside the shipped example, in the install folder


def test_max_chars_must_be_positive(tmp_path):
    p = tmp_path / "kei.toml"
    p.write_text('[animator]\ncmd = ["x"]\n[book]\nmax_chars = 0\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="max_chars"):
        load_config(p)


def test_example_animator_may_run_the_commands_the_stages_need():
    cmd = load_config(ROOT / "kei.example.toml").animator.cmd
    allowed = ",".join(cmd[cmd.index("--allowedTools") + 1:]).replace(" ", "")
    for tool in ("Bash(kei*)", "Bash(python.kei/scratch/*)", "Bash(ffmpeg*)", "PowerShell(kei*)",
                 "PowerShell(python.kei/scratch/*)"):
        assert tool in allowed, tool
    assert "Bash(python*)" not in allowed      # python runs the helpers in .kei/scratch/ only: no one-liners
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


def test_a_stage_can_have_its_own_limits(tmp_path):
    p = tmp_path / "kei.toml"
    p.write_text('[animator]\ncmd = ["x"]\n[limits]\nmax_attempts = 3\n[limits.passes]\nmax_attempts = 6\n'
                 'max_send_backs = 5\n', encoding="utf-8")
    c = load_config(p)
    assert (c.attempts_for("passes"), c.send_backs_for("passes")) == (6, 5)
    assert (c.attempts_for("plan"), c.send_backs_for("plan")) == (3, 3)
    for body in ('[limits.wings]\nmax_attempts = 2\n', '[limits.plan]\nmax_tries = 2\n', '[limits.plan]\nmax_attempts = 0\n'):
        p.write_text('[animator]\ncmd = ["x"]\n' + body, encoding="utf-8")
        with pytest.raises(ConfigError):
            load_config(p)


def test_model_and_effort_become_the_clis_own_flags(tmp_path):
    p = tmp_path / "kei.toml"
    p.write_text('[animator]\ncmd = ["claude", "-p"]\nmodel = "opus"\neffort = "high"\n'
                 '[[critics]]\nname = "c"\ncmd = ["codex", "exec", "-"]\nmodel = "gpt-6"\neffort = "xhigh"\n',
                 encoding="utf-8")
    c = load_config(p)
    assert c.animator.cmd == ["claude", "--model", "opus", "--effort", "high", "-p"]
    assert c.critics[0].cmd == ["codex", "exec", "-m", "gpt-6", "-c", 'model_reasoning_effort="xhigh"', "-"]
    p.write_text('[animator]\ncmd = ["gemini"]\nmodel = "x"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)
