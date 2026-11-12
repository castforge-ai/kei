"""The TOML value editor: one value changes, every comment and every other byte stays."""
import tomllib
from pathlib import Path

import pytest

EXAMPLE = (Path(__file__).resolve().parent.parent / "kei.example.toml").read_text(encoding="utf-8")


def comments(text):
    return [line for line in text.splitlines() if line.lstrip().startswith("#")]


def changed_lines(a, b):
    la, lb = a.splitlines(), b.splitlines()
    return [x for x in lb if x not in la], [x for x in la if x not in lb]


def test_find_value_of_a_simple_key():
    from kei.toml_edit import find_value
    start, end = find_value(EXAMPLE, "share", "mode")
    assert EXAMPLE[start:end] == '"ask"'


def test_multiline_array_replaced_whole():
    from kei.toml_edit import find_value, set_value
    start, end = find_value(EXAMPLE, "animator", "cmd")
    assert EXAMPLE[start:end].startswith('["claude"') and EXAMPLE[start:end].endswith('"]')
    assert EXAMPLE[start:end].count("\n") == 3
    new = set_value(EXAMPLE, "animator", "cmd", '["claude", "-p"]')
    data = tomllib.loads(new)
    assert data["animator"]["cmd"] == ["claude", "-p"] and data["animator"]["timeout_s"] == 1800
    added, removed = changed_lines(EXAMPLE, new)
    assert added == ['cmd = ["claude", "-p"]'] and len(removed) == 4
    assert comments(new) == comments(EXAMPLE)


def test_a_hash_inside_a_quoted_value_is_not_a_comment():
    from kei.toml_edit import find_value, set_value
    text = set_value(EXAMPLE, "share", "mode", '"a#b"')
    start, end = find_value(text, "share", "mode")
    assert text[start:end] == '"a#b"'
    assert tomllib.loads(text)["share"]["mode"] == "a#b"
    assert "# ask | always | never | auto: what Kei does" in text   # the comment after the value stays
    again = set_value(text, "share", "mode", '"always"')
    assert tomllib.loads(again)["share"]["mode"] == "always" and comments(again) == comments(EXAMPLE)


def test_literal_and_multiline_strings_are_read_whole():
    from kei.toml_edit import find_value
    text = "[t]\na = 'x # y'  # c\nb = \"\"\"one\n# not a comment\ntwo\"\"\"\nc = [\n  'p', # inner\n  \"q\",\n]\nd = 1\n"
    for key, want in (("a", "'x # y'"), ("b", '"""one\n# not a comment\ntwo"""'), ("c", "[\n  'p', # inner\n  \"q\",\n]"),
                      ("d", "1")):
        s, e = find_value(text, "t", key)
        assert text[s:e] == want, key


def test_two_array_tables_change_one():
    from kei.toml_edit import set_value
    new = set_value(EXAMPLE, "critics", "timeout_s", "60", index=1)
    data = tomllib.loads(new)
    assert data["critics"][1]["timeout_s"] == 60 and "timeout_s" not in data["critics"][0]
    new = set_value(EXAMPLE, "critics", "cmd", '["codex", "exec", "-"]', index=1)
    data = tomllib.loads(new)
    assert data["critics"][1]["cmd"] == ["codex", "exec", "-"]
    assert data["critics"][0]["cmd"][0] == "claude"
    assert comments(new) == comments(EXAMPLE)


def test_a_commented_key_under_a_commented_header_is_uncommented_with_it():
    from kei.toml_edit import set_value
    new = set_value(EXAMPLE, "book", "max_chars", "500000")
    data = tomllib.loads(new)
    assert data["book"] == {"max_chars": 500000}
    added, removed = changed_lines(EXAMPLE, new)
    assert added == ["[book]", "max_chars = 500000             # the most rule text one stage may get; over it, the "
                                "shot stops for a person"]
    assert removed == ["# [book]", "# max_chars = 450000             # the most rule text one stage may get; over it, "
                                   "the shot stops for a person"]


def test_a_key_with_no_line_is_added_at_the_end_of_its_table():
    from kei.toml_edit import set_value
    new = set_value(EXAMPLE, "limits", "extra", "2")
    assert tomllib.loads(new)["limits"] == {"max_attempts": 3, "max_send_backs": 3, "extra": 2}
    lines = new.splitlines()
    i = lines.index("extra = 2")
    assert lines[i - 1].startswith("max_send_backs")


def test_a_new_table_goes_at_the_end_of_the_file():
    from kei.toml_edit import set_value
    new = set_value(EXAMPLE, "extra", "name", '"x"')
    assert tomllib.loads(new)["extra"] == {"name": "x"}
    assert new.startswith(EXAMPLE.rstrip("\n")) and new.endswith('[extra]\nname = "x"\n')


def test_unset_removes_the_line_and_keeps_every_comment():
    from kei.toml_edit import set_value, unset_value
    new = unset_value(EXAMPLE, "animator", "timeout_s")
    assert "timeout_s" not in tomllib.loads(new)["animator"]
    assert comments(new) == comments(EXAMPLE)
    new = unset_value(EXAMPLE, "animator", "cmd")
    assert "cmd" not in tomllib.loads(new)["animator"] and comments(new) == comments(EXAMPLE)


@pytest.mark.parametrize("table, key, value, index", [
    ("share", "mode", '"never"', None), ("limits", "max_attempts", "5", None), ("animator", "timeout_s", "60", None),
    ("animator", "cmd", '["x"]', None), ("shot", "character", '"keira"', None), ("critics", "timeout_s", "9", 0)])
def test_set_then_unset_keeps_every_comment_line(table, key, value, index):
    from kei.toml_edit import set_value, unset_value
    new = unset_value(set_value(EXAMPLE, table, key, value, index=index), table, key, index=index)
    assert comments(new) == comments(EXAMPLE)
    tomllib.loads(new)


def test_crlf_files_keep_crlf_on_the_changed_line_too():
    from kei.toml_edit import set_value
    crlf = EXAMPLE.replace("\n", "\r\n")
    for table, key, value in (("share", "mode", '"never"'), ("animator", "cmd", '["a", "b"]'),
                              ("book", "max_chars", "9"), ("limits", "extra", "1"), ("apps", "app", '"x"')):
        new = set_value(crlf, table, key, value)
        assert "\n" not in new.replace("\r\n", ""), (table, key)
        tomllib.loads(new)


def test_add_and_remove_an_array_table():
    from kei.toml_edit import add_table, remove_array_table
    new = add_table(EXAMPLE, '[[critics]]\nname = "third"\ncmd = ["x"]\n')
    assert [c["name"] for c in tomllib.loads(new)["critics"]] == ["claude-critic", "codex", "third"]
    gone = remove_array_table(new, "critics", 1)
    data = tomllib.loads(gone)
    assert [c["name"] for c in data["critics"]] == ["claude-critic", "third"]
    assert data["limits"]["max_attempts"] == 3
    assert "# [book]" in gone and "# Critic seats" in gone


def test_format_value():
    from kei.toml_edit import format_value
    assert format_value(3) == "3" and format_value(True) == "true" and format_value("a\"b") == '"a\\"b"'
    assert tomllib.loads("v = " + format_value(["claude", "-p", 'x="y"']))["v"] == ["claude", "-p", 'x="y"']
    assert tomllib.loads("v = " + format_value("é\n#"))["v"] == "é\n#"


def test_a_missing_index_is_refused():
    from kei.toml_edit import TomlEditError, set_value
    with pytest.raises(TomlEditError):
        set_value(EXAMPLE, "critics", "cmd", '["x"]', index=5)
