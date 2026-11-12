"""kei settings: list every setting with its meaning, show one, and set, unset, add or remove safely."""
import shutil
from pathlib import Path

import pytest

from kei.cli import main
from kei.config import load_config

EXAMPLE = Path(__file__).resolve().parent.parent / "kei.example.toml"


@pytest.fixture
def here(tmp_path, monkeypatch):
    """A folder with a copy of the example config, and every agent program found."""
    shutil.copy(EXAMPLE, tmp_path / "kei.toml")
    monkeypatch.chdir(tmp_path)
    import kei.settings
    monkeypatch.setattr(kei.settings.shutil, "which", lambda name: f"/usr/bin/{name}")
    return tmp_path


def run(capsys, *args):
    code = main(["settings", *args])
    out = capsys.readouterr().out
    assert "Traceback" not in out
    return code, out


def test_settings_lists_every_key_with_its_value_source_and_meaning(here, capsys):
    code, out = run(capsys)
    assert code == 0
    for key in ("animator.cmd", "critics[codex].cmd", "limits.max_attempts", "share.mode", "book.max_chars",
                "shot.character"):
        assert key in out
    line = next(ln for ln in out.splitlines() if ln.startswith("share.mode"))
    assert '"ask"' in line and "kei.toml" in line and "new lessons" in line
    assert "default" in next(ln for ln in out.splitlines() if ln.startswith("book.max_chars"))


def test_set_then_show_one(here, capsys):
    code, out = run(capsys, "set", "share.mode", "always")
    assert code == 0 and 'share.mode: "ask" -> "always"' in out and "applies from the next kei run" in out
    code, out = run(capsys, "share.mode")
    assert code == 0 and '"always"' in out and "ask: the review page offers" in out
    assert load_config(here / "kei.toml").share == "always"


def test_a_bad_value_exits_1_and_the_file_is_unchanged(here, capsys):
    before = (here / "kei.toml").read_bytes()
    code, out = run(capsys, "set", "limits.max_attempts", "0")
    assert code == 1 and "max_attempts" in out and len(out.strip().splitlines()) == 1
    assert (here / "kei.toml").read_bytes() == before


def test_unset_brings_the_default_back(here, capsys):
    run(capsys, "set", "limits.max_attempts", "5")
    code, out = run(capsys, "unset", "limits.max_attempts")
    assert code == 0 and "limits.max_attempts: 5 -> 3" in out
    assert load_config(here / "kei.toml").max_attempts == 3


def test_remove_critic_of_the_last_critic_exits_1(here, capsys):
    assert run(capsys, "remove-critic", "codex")[0] == 0
    before = (here / "kei.toml").read_bytes()
    code, out = run(capsys, "remove-critic", "claude-critic")
    assert code == 1 and "no critic" in out and (here / "kei.toml").read_bytes() == before


def test_add_critic_of_an_existing_name_exits_1(here, capsys):
    code, out = run(capsys, "add-critic", "codex", "--preset", "codex")
    assert code == 1 and "codex" in out
    code, out = run(capsys, "add-critic", "second", "--preset", "claude")
    assert code == 0 and [c.name for c in load_config(here / "kei.toml").critics][-1] == "second"


def test_an_unknown_key_exits_1(here, capsys):
    code, out = run(capsys, "set", "nope.key", "1")
    assert code == 1 and "nope.key" in out


def test_a_first_set_with_no_kei_toml_copies_the_example_here(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    import kei.settings
    monkeypatch.setattr(kei.settings.shutil, "which", lambda name: f"/usr/bin/{name}")
    example_before = EXAMPLE.read_bytes()
    code, out = run(capsys, "set", "share.mode", "never")
    assert code == 0 and "kei.example.toml" in out
    assert load_config(tmp_path / "kei.toml").share == "never" and EXAMPLE.read_bytes() == example_before


def test_the_diff_of_a_set_is_the_changed_line_only(here, capsys):
    before = (here / "kei.toml").read_text(encoding="utf-8").splitlines()
    run(capsys, "set", "critics[codex].timeout_s", "60")
    after = (here / "kei.toml").read_text(encoding="utf-8").splitlines()
    assert [ln for ln in after if ln not in before] == ["timeout_s = 60"]
    assert [ln for ln in before if ln not in after] == []
