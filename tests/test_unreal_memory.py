"""The editor's memory is written down after each pass and bake, and never stops a shot."""
import json

from kei.apps import unreal_memory


def test_each_reading_is_a_row_in_unreal_memory_json(tmp_path):
    reads = iter([{"pid": 7, "private_gb": 17.0, "working_set_gb": 9.5}, {"pid": 7, "private_gb": 19.25, "working_set_gb": 10.0}])
    one = unreal_memory.record(tmp_path, "http://127.0.0.1:50000/mcp", "blocking: keyed", reader=lambda url: next(reads))
    unreal_memory.record(tmp_path, "http://127.0.0.1:50000/mcp", "p1: keyed", reader=lambda url: next(reads))
    rows = json.loads((tmp_path / "unreal" / "memory.json").read_text())
    assert [r["label"] for r in rows] == ["blocking: keyed", "p1: keyed"] and one["private_gb"] == 17.0
    assert rows[1]["private_gb"] - rows[0]["private_gb"] == 2.25


def test_an_unreadable_editor_writes_nothing_and_raises_nothing(tmp_path):
    assert unreal_memory.record(tmp_path, "http://127.0.0.1:1/mcp", "x", reader=lambda url: None) is None
    assert not (tmp_path / "unreal").exists()
    assert unreal_memory.editor_memory("") is None


def test_the_real_reader_finds_a_listening_process_on_windows():
    import socket
    import sys
    import pytest
    if sys.platform != "win32":
        pytest.skip("Windows only")
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    got = unreal_memory.editor_memory(f"http://127.0.0.1:{s.getsockname()[1]}/mcp")
    s.close()
    assert got and got["private_gb"] > 0 and got["pid"] > 0
