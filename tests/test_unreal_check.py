"""kei unreal check reads the project's files and asks the open editor, and compares both to the tested table."""
import json
import subprocess

from kei.apps import unreal_check, unreal_memory
from kei.apps.unreal import UnrealError
from kei.cli import main


def _project(tmp_path, engine="5.8", claireon="2.2.0", python=None, ignore=True, port=50123):
    p = tmp_path / "Proj"
    plugins = [{"Name": "PythonScriptPlugin", "Enabled": python}] if python is not None else []
    (p / "Plugins" / "Claireon").mkdir(parents=True)
    (p / "Proj.uproject").write_text(json.dumps({"EngineAssociation": engine, "Plugins": plugins}))
    (p / "Plugins" / "Claireon" / "Claireon.uplugin").write_text(json.dumps(
        {"VersionName": claireon, "Plugins": [{"Name": "PythonScriptPlugin", "Enabled": True}]}))
    if ignore is not None:
        (p / ".gitignore").write_text("Binaries/\n/Content/Kei/\n" if ignore else "Binaries/\n")
    if port:
        (p / "Saved" / "Claireon").mkdir(parents=True)
        (p / "Saved" / "Claireon" / "MCPServer.json").write_text(json.dumps({"port": port, "pid": 1}))
    return p


def _answers(info=None):
    info = info or {"server": "Claireon 2.2.0", "protocol_version": "2025-03-26", "tools": ["python_execute"]}
    return lambda url: info


def _rows(rows):
    return {what: (status, found) for status, what, found, _ in rows}


def test_the_tested_combination_is_all_ok(tmp_path):
    rows = _rows(unreal_check.checks(_project(tmp_path), None, probe=_answers()))
    assert rows["Unreal version"] == ("ok", "5.8") and rows["Claireon"] == ("ok", "2.2.0")
    assert rows["Python plugin"][0] == "ok" and "Claireon turns it on" in rows["Python plugin"][1]
    assert rows["port"] == ("ok", "http://127.0.0.1:50123/mcp")
    assert rows["editor answers"][0] == "ok" and rows["protocol"] == ("ok", "2025-03-26")
    assert rows["ignore line"][0] == "ok"
    assert not [r for r in rows.values() if r[0] == "fail"]


def test_an_untested_version_warns_and_never_fails(tmp_path):
    rows = _rows(unreal_check.checks(_project(tmp_path, engine="5.9", claireon="2.3.0"), None,
                                     probe=_answers({"server": "x", "protocol_version": "2026-07-28",
                                                     "tools": ["python_execute"]})))
    assert rows["Unreal version"] == ("warn", "5.9, not tested")
    assert rows["Claireon"] == ("warn", "2.3.0, not tested") and rows["protocol"][0] == "warn"
    assert not [r for r in rows.values() if r[0] == "fail"]


def test_a_source_build_says_it_cannot_read_the_version(tmp_path):
    rows = _rows(unreal_check.checks(_project(tmp_path, engine="{1234-ABCD}"), None, probe=_answers()))
    assert rows["Unreal version"][0] == "warn" and "source build" in rows["Unreal version"][1]


def test_no_claireon_and_a_python_plugin_turned_off_fail(tmp_path):
    p = _project(tmp_path, python=False)
    (p / "Plugins" / "Claireon" / "Claireon.uplugin").unlink()
    rows = _rows(unreal_check.checks(p, None, probe=_answers()))
    assert rows["Claireon"][0] == "fail" and rows["Python plugin"][0] == "fail"


def test_a_closed_editor_fails_the_answer_row_with_the_start_step(tmp_path):
    def closed(url):
        raise UnrealError("no editor answers")
    rows = unreal_check.checks(_project(tmp_path), None, probe=closed)
    row = next(r for r in rows if r[1] == "editor answers")
    assert row[0] == "fail" and "-StartMCPServer" in row[2] + row[3]


def test_no_port_file_and_no_url_stops_after_the_files(tmp_path):
    rows = _rows(unreal_check.checks(_project(tmp_path, port=None), None, probe=_answers()))
    assert rows["port"][0] == "fail" and "editor answers" not in rows


def test_a_missing_ignore_line_warns(tmp_path):
    rows = _rows(unreal_check.checks(_project(tmp_path, ignore=False), None, probe=_answers()))
    assert rows["ignore line"][0] == "warn"


def test_a_missing_tool_fails(tmp_path):
    rows = _rows(unreal_check.checks(_project(tmp_path), None,
                                     probe=_answers({"server": "x", "protocol_version": "2025-03-26", "tools": []})))
    assert rows["tools"] == ("fail", "missing python_execute")


def test_no_project_with_a_url_still_asks_the_editor():
    rows = _rows(unreal_check.checks(None, "http://127.0.0.1:50000/mcp", probe=_answers()))
    assert rows["project"][0] == "warn" and rows["editor answers"][0] == "ok"


def test_the_command_prints_the_table_and_exits_1_on_a_failure(tmp_path, capsys, monkeypatch):
    p = _project(tmp_path)
    monkeypatch.setattr(unreal_check, "probe_server", lambda url, timeout=5: (_ for _ in ()).throw(UnrealError("x")))
    monkeypatch.setattr(unreal_check.checks, "__defaults__", (unreal_check.probe_server,))
    code = main(["unreal", "check", "--project", str(p)])
    out = capsys.readouterr().out
    assert code == 1 and "Tested combinations:" in out and "5.8 | 2.2.0" in out


def test_the_memory_fallback_reads_lsof_and_ps():
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="4242\n" if cmd[0] == "lsof" else "  2097152\n")
    got = unreal_memory._posix_memory(50000, run=run)
    assert got == {"pid": 4242, "private_gb": None, "working_set_gb": 2.0}


def test_the_memory_fallback_returns_none_when_nothing_listens():
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="")
    assert unreal_memory._posix_memory(50000, run=run) is None
