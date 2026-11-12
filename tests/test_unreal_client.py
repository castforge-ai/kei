"""Task 2 of plan 7: the MCP client for Claireon, against a fake. No Unreal Editor."""
import pytest

from fakes.fake_claireon import FakeClaireon
from kei.apps.unreal import ALLOWED_TOOLS, Claireon, UnrealError


def test_the_handshake_keeps_the_server_version_and_the_tool_list():
    with FakeClaireon() as fake:
        c = Claireon(fake.url)
        info = c.initialize()
        assert info["protocol_version"] == "2025-03-26"      # what Claireon 2.2.0 answers: accepted
        assert info["server"] == "claireon-unreal-editor 1.0.0"
        assert "python_execute" in info["tools"] and "tool_search" in info["tools"]
        assert [r["method"] for r in fake.requests] == ["initialize", "tools/list"]


def test_a_missing_tool_the_adapter_needs_is_named():
    with FakeClaireon(tools=[{"name": "tool_search"}]) as fake:
        with pytest.raises(UnrealError, match="python_execute"):
            Claireon(fake.url).initialize()


def test_a_call_returns_the_result():
    with FakeClaireon() as fake:
        c = Claireon(fake.url)
        c.initialize()
        r = c.call("python_execute", {"code": "print(1)"})
        assert "<execute-result" in r["content"][0]["text"]


def test_the_allowlist_is_python_execute_only():
    assert ALLOWED_TOOLS == frozenset({"python_execute"})


def test_a_tool_off_the_allowlist_is_refused_before_any_request():      # Review Focus 4
    with FakeClaireon() as fake:
        c = Claireon(fake.url)
        c.initialize()
        before = len(fake.requests)
        with pytest.raises(UnrealError, match="level_sequence_set_control_keys"):
            c.call("level_sequence_set_control_keys", {})
        assert len(fake.requests) == before


@pytest.mark.parametrize("url", ["http://192.168.1.5:5000/mcp", "http://example.com/mcp", "https://0.0.0.0:1/mcp",
                                 "http://127.0.0.1.evil.test/mcp", "file:///etc/passwd", "127.0.0.1:5000"])
def test_a_url_that_is_not_local_is_refused(url):
    with pytest.raises(UnrealError, match="127.0.0.1"):
        Claireon(url)


def test_localhost_is_accepted():
    Claireon("http://localhost:5000/mcp")


def test_a_timeout_is_an_unreal_error_not_a_hang():
    with FakeClaireon(delay=1.0) as fake:
        with pytest.raises(UnrealError, match="did not answer"):
            Claireon(fake.url, timeout=0.2).initialize()


def test_a_closed_connection_is_an_unreal_error():
    with FakeClaireon() as fake:
        fake.stopped = True
        with pytest.raises(UnrealError, match="did not answer"):
            Claireon(fake.url, timeout=2).initialize()


def test_nothing_listening_says_how_to_start_the_server():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with pytest.raises(UnrealError, match="StartMCPServer"):
        Claireon(f"http://127.0.0.1:{port}/mcp", timeout=15).initialize()


def test_a_json_rpc_error_is_one_line():
    with FakeClaireon() as fake:
        c = Claireon(fake.url)
        c.initialize()
        fake.error = {"code": -32000, "message": "bad\nthing"}
        with pytest.raises(UnrealError) as e:
            c.call("python_execute", {"code": "x"})
        assert "\n" not in str(e.value) and "bad thing" in str(e.value)
