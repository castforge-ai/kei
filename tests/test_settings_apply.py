"""A settings change is validated the way a shot would read the file, then saved with a backup; a refused change
leaves kei.toml byte for byte."""
import hashlib
import shutil
from pathlib import Path

import pytest

from kei.config import load_config

EXAMPLE = Path(__file__).resolve().parent.parent / "kei.example.toml"


def which_all(name):
    return f"/usr/bin/{name}"


def which_none_of(*missing):
    return lambda name: None if name in missing else f"/usr/bin/{name}"


@pytest.fixture
def toml(tmp_path):
    p = tmp_path / "kei.toml"
    shutil.copy(EXAMPLE, p)
    return p


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_a_good_change_writes_the_backup_and_the_new_file(toml):
    from kei.settings import apply_change
    before = toml.read_bytes()
    out = apply_change(toml, {"share.mode": "always"}, which=which_all)
    assert out == [("share.mode", "ask", "always")]
    assert load_config(toml).share == "always"
    assert (toml.parent / "kei.toml.bak").read_bytes() == before
    assert toml.read_text(encoding="utf-8").count("\n") == before.decode().count("\n")


@pytest.mark.parametrize("key, value, why", [
    ("shot.character", "nobody", "nobody"),
    ("limits.max_attempts", 0, "max_attempts"),
    ("share.mode", "sometimes", "share.mode"),
    ("book.max_chars", "lots", "max_chars"),
    ("animator.cmd", [], "animator.cmd"),
])
def test_a_value_that_parses_but_breaks_a_shot_is_refused(toml, key, value, why):
    from kei.settings import SettingError, apply_change
    before = toml.read_bytes()
    with pytest.raises(SettingError, match=why):
        apply_change(toml, {key: value}, which=which_all)
    assert toml.read_bytes() == before and not (toml.parent / "kei.toml.bak").exists()


def test_the_last_critic_removed_is_refused(toml):
    from kei.settings import SettingError, remove_critic
    remove_critic(toml, "codex", which=which_all)
    before = toml.read_bytes()
    with pytest.raises(SettingError, match="a run with no critic does not start"):
        remove_critic(toml, "claude-critic", which=which_all)
    assert toml.read_bytes() == before


def test_a_missing_agent_cli_is_refused_naming_the_seat_and_the_program(toml):
    from kei.settings import SettingError, apply_change
    before = toml.read_bytes()
    with pytest.raises(SettingError, match=r"critic codex.*codex"):
        apply_change(toml, {"share.mode": "never"}, which=which_none_of("codex"))
    with pytest.raises(SettingError, match=r"animator.*nosuchagent"):
        apply_change(toml, {"animator.cmd": ["nosuchagent", "-p"]}, which=which_none_of("nosuchagent"))
    assert toml.read_bytes() == before


@pytest.mark.parametrize("value", [["claude", "--key", "sk-ant-api03-abcdefghijklmnop"],
                                   ["env", "ANTHROPIC_API_KEY=abc123", "claude"]])
def test_a_credential_looking_value_is_refused(toml, value):
    from kei.settings import SettingError, apply_change
    before = toml.read_bytes()
    with pytest.raises(SettingError, match="environment variable"):
        apply_change(toml, {"animator.cmd": value}, which=which_all)
    assert toml.read_bytes() == before


def test_a_book_path_that_does_not_exist_is_refused(toml):
    from kei.settings import SettingError, apply_change
    with pytest.raises(SettingError, match="book.path"):
        apply_change(toml, {"book.path": "no/such/book"}, which=which_all)


def test_a_critic_value_changes_that_critic_only(toml):
    from kei.settings import apply_change
    apply_change(toml, {"critics[codex].timeout_s": 60}, which=which_all)
    c = load_config(toml)
    assert [(s.name, s.timeout_s) for s in c.critics] == [("claude-critic", 1800), ("codex", 60)]


def test_unset_brings_the_default_back(toml):
    from kei.settings import apply_change
    out = apply_change(toml, {"limits.max_attempts": None}, which=which_all)
    assert out == [("limits.max_attempts", 3, 3)] and load_config(toml).max_attempts == 3
    assert "max_attempts" not in toml.read_text(encoding="utf-8").split("[limits]")[1].split("[")[0].split("#")[0]


def test_a_first_set_with_no_kei_toml_copies_the_example_with_its_comments(tmp_path):
    from kei.settings import apply_change
    p = tmp_path / "kei.toml"
    notes = []
    apply_change(p, {"share.mode": "never"}, which=which_all, notes=notes)
    text = p.read_text(encoding="utf-8")
    assert "# Critic seats" in text and load_config(p).share == "never"
    assert any("kei.example.toml" in n for n in notes)


def test_a_stale_hash_is_refused(toml):
    from kei.settings import SettingError, apply_change
    with pytest.raises(SettingError, match="kei.toml changed since you opened it: reload"):
        apply_change(toml, {"share.mode": "never"}, expect_sha256="0" * 64, which=which_all)
    apply_change(toml, {"share.mode": "never"}, expect_sha256=sha(toml), which=which_all)


def test_validate_text_shares_the_parser_with_load_config(toml):
    from kei.config import load_config_text
    c = load_config_text(toml.read_text(encoding="utf-8"), toml)
    assert c == load_config(toml)


def test_add_critic_from_a_preset_and_refuse_a_name_twice(toml):
    from kei.settings import SettingError, add_critic
    add_critic(toml, "second", "codex", which=which_all)
    assert [s.name for s in load_config(toml).critics] == ["claude-critic", "codex", "second"]
    with pytest.raises(SettingError, match="second"):
        add_critic(toml, "second", "claude", which=which_all)
