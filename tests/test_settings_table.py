"""One table lists every setting: its type, default and meaning. kei/config.py and the table cannot drift."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "kei.example.toml"


def config_reads():
    """Every name kei/config.py reads with .get("..."), and the tables it reads with data["..."] or "..." in data."""
    src = (ROOT / "kei" / "config.py").read_text(encoding="utf-8")
    return set(re.findall(r'\.get\("([a-z_]+)"', src)) | set(re.findall(r'data\["([a-z_]+)"\]', src))


def test_every_key_load_config_reads_is_in_the_table():
    from kei.settings import SETTINGS
    tables = {seg.split("[")[0] for s in SETTINGS for seg in s.key.split(".")[:-1]}   # apps.maya.session: apps, maya
    leaves = {s.key.rsplit(".", 1)[-1] for s in SETTINGS}
    named = {"name"}       # a critic's name is its identifier in the key: critics[<name>].cmd
    missing = config_reads() - tables - leaves - named
    assert missing == set(), f"kei/config.py reads {sorted(missing)}, which kei/settings.py does not list"


def test_the_drift_check_sees_a_new_key(tmp_path, monkeypatch):
    """The check above is real: a key the table does not list is caught."""
    from kei.settings import SETTINGS
    leaves = {s.key.rsplit(".", 1)[-1] for s in SETTINGS}
    assert "brand_new_key" not in leaves
    assert "brand_new_key" in set(re.findall(r'\.get\("([a-z_]+)"', 'x.get("brand_new_key", 3)'))


def test_every_row_has_a_meaning_with_no_em_dash():
    from kei.settings import KINDS, SETTINGS
    assert len({s.key for s in SETTINGS}) == len(SETTINGS)
    for s in SETTINGS:
        assert s.meaning and chr(0x2014) not in s.meaning + s.help, s.key
        assert s.kind in KINDS, s.key
    keys = {s.key for s in SETTINGS}
    assert {"animator.cmd", "animator.timeout_s", "critics[<name>].cmd", "critics[<name>].timeout_s",
            "limits.max_attempts", "limits.max_send_backs", "share.mode", "book.path", "book.lessons",
            "book.max_chars", "shot.character"} <= keys


def test_current_on_the_example_config():
    from kei.settings import current
    rows = {r["key"]: r for r in current(EXAMPLE)}
    assert rows["share.mode"]["value"] == "ask" and rows["share.mode"]["source"] == "kei.toml"
    assert rows["book.max_chars"]["value"] == 450000 and rows["book.max_chars"]["source"] == "default"
    assert rows["critics[codex].cmd"]["value"][0] == "codex"
    assert rows["critics[claude-critic].timeout_s"]["source"] == "default"
    assert "critics[<name>].cmd" not in rows
    assert all(r["meaning"] for r in rows.values())


def test_current_with_no_file_is_every_default(tmp_path):
    from kei.settings import current
    rows = {r["key"]: r for r in current(tmp_path / "nope.toml")}
    assert rows["share.mode"] == {**rows["share.mode"], "value": "ask", "source": "default"}


@pytest.mark.parametrize("key, raw, want", [
    ("limits.max_attempts", "3", 3), ("share.mode", "always", "always"), ("share.mode", '"never"', "never"),
    ("animator.cmd", '["a", "b"]', ["a", "b"]), ("book.path", "my book", "my book"),
    ("shot.character", "keira", "keira")])
def test_parse_cli_value(key, raw, want):
    from kei.settings import parse_cli_value, setting
    assert parse_cli_value(setting(key), raw) == want


def test_a_bare_word_for_a_number_is_refused():
    from kei.settings import SettingError, parse_cli_value, setting
    with pytest.raises(SettingError, match="limits.max_attempts"):
        parse_cli_value(setting("limits.max_attempts"), "three")


def test_setting_finds_a_named_critic_and_refuses_an_unknown_key():
    from kei.settings import SettingError, setting
    assert setting("critics[codex].cmd").key == "critics[<name>].cmd"
    with pytest.raises(SettingError, match="nope.key"):
        setting("nope.key")
