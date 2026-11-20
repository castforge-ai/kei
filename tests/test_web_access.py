"""Web access is asked once, at kei init (or at the first kei run of an older kei.toml), and saved as seats.web.
The answer turns the web tools on or off on every seat: Claude Code through its tool lists, Codex through --search."""
import io
import tomllib

from kei.cli import main
from kei.config import SeatSpec, load_config
from kei.seats import with_web


def _web(path):
    return tomllib.loads(path.read_text(encoding="utf-8")).get("seats", {}).get("web")


def test_init_saves_the_flag_answer_and_the_seats_get_the_web(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--web", "off"]) == 0
    assert _web(tmp_path / "kei.toml") == "off"
    cfg = load_config(tmp_path / "kei.toml")
    assert cfg.web == "off" and cfg.web_asked
    assert "web access: off" in capsys.readouterr().out


def test_init_asks_at_a_terminal_and_no_means_off(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stdin = io.StringIO("n\n")
    stdin.isatty = lambda: True
    monkeypatch.setattr("sys.stdin", stdin)
    assert main(["init"]) == 0
    assert _web(tmp_path / "kei.toml") == "off"


def test_init_with_nobody_at_a_terminal_allows_the_web_by_default(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    stdin = io.StringIO("")
    stdin.isatty = lambda: False
    monkeypatch.setattr("sys.stdin", stdin)
    assert main(["init"]) == 0
    assert _web(tmp_path / "kei.toml") == "on"
    assert "the default" in capsys.readouterr().out


def test_an_older_kei_toml_reads_as_not_yet_asked(tmp_path):
    (tmp_path / "kei.toml").write_text('[animator]\ncmd = ["claude", "-p"]\n', encoding="utf-8")
    cfg = load_config(tmp_path / "kei.toml")
    assert cfg.web == "on" and not cfg.web_asked


def test_a_claude_seat_gains_or_refuses_the_web_tools():
    spec = SeatSpec("a", ["claude", "-p", "--allowedTools", "Bash(kei *),WebSearch"])
    on = with_web(spec, "on").cmd
    assert on[-1] == "Bash(kei *),WebSearch,WebFetch"
    off = with_web(spec, "off").cmd
    assert "Bash(kei *)" in off and "WebSearch" not in off[off.index("--allowedTools") + 1]
    assert off[off.index("--disallowedTools") + 1] == "WebSearch,WebFetch"
    bare = with_web(SeatSpec("c", ["claude", "-p", "--permission-mode", "plan"]), "on").cmd
    assert bare[-2:] == ["--allowedTools", "WebSearch,WebFetch"]


def test_a_codex_seat_gets_search_before_exec_and_other_clis_are_left_alone():
    spec = SeatSpec("g", ["codex", "exec", "--sandbox", "read-only", "-"])
    assert with_web(spec, "on").cmd[:3] == ["codex", "--search", "exec"]
    assert "--search" not in with_web(with_web(spec, "on"), "off").cmd
    other = SeatSpec("o", ["gemini", "-p"])
    assert with_web(other, "on").cmd == ["gemini", "-p"]
