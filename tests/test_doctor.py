"""kei doctor: every check says ok, warn or fail, with the fix."""
from kei.cli import main
from kei.config import example_config
from kei.doctor import FAIL, checks, report


def test_a_missing_seat_program_is_a_failure_with_its_fix(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PATH", str(tmp_path))
    rows = checks(example_config())
    seats = [r for r in rows if r[1].endswith("seat")]
    assert seats and all(r[0] == FAIL and "not on the PATH" in r[2] and "install" in r[3] for r in seats)
    text, fails = report(rows)
    assert fails == len(seats) and "to fix" in text.splitlines()[-1]
    assert main(["doctor"]) == 1 and "rule book" in capsys.readouterr().out


def test_a_broken_config_stops_the_checks_with_its_reason(tmp_path):
    bad = tmp_path / "kei.toml"
    bad.write_text("[limits]\nmax_attempts = 0\n", encoding="utf-8")
    rows = checks(bad)
    assert rows[-1][0] == FAIL and rows[-1][1] == "config"
