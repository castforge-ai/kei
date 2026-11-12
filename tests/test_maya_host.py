"""Task 7 of plan 6: the Kei host that runs inside the user's Maya. These tests run the real Host on a free port with a
fake executor and fake tools, so they need no Maya."""
import contextlib
import json
import os
import threading
import time
import urllib.error
import urllib.request

import pytest

from kei.apps.maya_side.kei_host import Host
from kei.apps.maya_side.kei_tools import tool_entry

CALLS = []


def _seen(**kw):
    CALLS.append(kw)
    return {"got": kw}


def _boom():
    raise RuntimeError("the scene has no such node")


TOOLS = {"scene_info": tool_entry(lambda: {"scene": "C:/shots/a.ma", "unsaved": True}, "read"),
         "set_keys": tool_entry(_seen, "change", keys="list"),
         "boom": tool_entry(_boom, "read"),
         "playblast": tool_entry(_seen, "change", folder="str")}


@pytest.fixture
def host(tmp_path):
    CALLS.clear()
    undo = []

    @contextlib.contextmanager
    def chunk(name):
        undo.append(("open", name))
        yield
        undo.append(("close", name))

    h = Host(TOOLS, executor=lambda fn: fn(), session_dir=tmp_path / "sessions", undo=chunk,
             info=lambda: {"maya_version": "2027", "scene": "C:/shots/a.ma", "unsaved": True})
    h.start()
    yield h, undo
    h.stop()


def _post(h, body, token="mine"):
    tok = h.token if token == "mine" else token
    req = urllib.request.Request(f"http://127.0.0.1:{h.port}/call", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {tok}"} if tok else {}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_a_call_with_the_token_returns_the_tool_s_result(host):
    h, _ = host
    assert _post(h, {"tool": "scene_info", "inputs": {}}) == (200, {"ok": True, "result": {
        "scene": "C:/shots/a.ma", "unsaved": True}})


@pytest.mark.parametrize("token", [None, "wrong", "another-session-token"])
def test_no_token_or_a_wrong_one_is_refused_and_runs_nothing(host, token):
    h, _ = host
    status, _ = _post(h, {"tool": "set_keys", "inputs": {"keys": []}}, token=token)
    assert status == 401 and CALLS == []


def test_an_unknown_tool_and_a_wrong_input_are_refused_by_name(host):
    h, _ = host
    status, body = _post(h, {"tool": "run_python", "inputs": {"code": "x"}})
    assert status == 400 and "run_python" in body["error"]
    status, body = _post(h, {"tool": "set_keys", "inputs": {"keys": "all"}})
    assert status == 400 and "'keys'" in body["error"] and CALLS == []


def test_a_change_tool_runs_in_one_undo_chunk(host):
    h, undo = host
    assert _post(h, {"tool": "set_keys", "inputs": {"keys": [1]}})[0] == 200
    assert undo == [("open", "kei_set_keys"), ("close", "kei_set_keys")]
    _post(h, {"tool": "scene_info", "inputs": {}})
    assert len(undo) == 2                               # a read tool opens no chunk


def test_a_background_only_tool_is_refused_in_the_open_session(host):
    h, _ = host
    status, body = _post(h, {"tool": "playblast", "inputs": {"folder": "x"}})
    assert status == 403 and "copy" in body["error"] and CALLS == []


def test_a_failing_tool_answers_with_its_message(host):
    h, _ = host
    status, body = _post(h, {"tool": "boom", "inputs": {}})
    assert status == 500 and "no such node" in body["error"]


def test_the_session_file_holds_every_field_and_a_scene_event_refreshes_it(host):
    h, _ = host
    f = h.session_file
    data = json.loads(f.read_text())
    assert f.parent.name == str(os.getpid())
    assert set(data) == {"pid", "start_time", "port", "token", "maya_version", "scene", "unsaved"}
    assert data["pid"] == os.getpid() and data["port"] == h.port and data["token"] == h.token
    assert data["start_time"] and data["unsaved"] is True
    h.refresh({"scene": "C:/shots/b.ma", "unsaved": False})
    data = json.loads(f.read_text())
    assert data["scene"] == "C:/shots/b.ma" and data["unsaved"] is False


def test_the_server_answers_on_127_0_0_1_only(host):
    h, _ = host
    assert h.server.server_address[0] == "127.0.0.1"


def test_stopping_removes_the_session_folder(tmp_path):
    h = Host(TOOLS, executor=lambda fn: fn(), session_dir=tmp_path, info=lambda: {})
    h.start()
    folder = h.session_file.parent
    h.stop()
    assert not folder.exists()


def test_a_refused_request_with_a_body_still_gets_its_401(host):
    """The host drains a refused request (up to 64 KiB) before it answers; an unread body made Windows reset the
    connection."""
    h, _ = host
    big = {"tool": "set_keys", "inputs": {"keys": [{"f": i, "channels": {"a.tx": 1.0}} for i in range(1500)]}}
    for _ in range(5):
        status, _ = _post(h, big, token="wrong")
        assert status == 401
    assert CALLS == []


def _raw(h, head: bytes, body: bytes = b"") -> bytes:
    import socket
    s = socket.create_connection(("127.0.0.1", h.port), timeout=5)
    s.sendall(head + body)
    out = b""
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            out += chunk
    except OSError:
        pass
    s.close()
    return out


def test_a_negative_or_missing_length_is_refused_before_any_read(host):
    h, _ = host
    auth = f"Authorization: Bearer {h.token}\r\n".encode()
    neg = _raw(h, b"POST /call HTTP/1.1\r\nHost: x\r\n" + auth + b"Content-Length: -1\r\n\r\n")
    assert neg.startswith(b"HTTP/1.0 400") or neg.startswith(b"HTTP/1.1 400")
    none = _raw(h, b"POST /call HTTP/1.1\r\nHost: x\r\n" + auth + b"Connection: close\r\n\r\n")
    assert b" 411 " in none.split(b"\r\n")[0]


def test_a_bad_token_is_refused_from_the_headers_and_its_body_is_not_read_past_64_kib(host):
    h, _ = host
    head = b"POST /call HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer nope\r\nContent-Length: 999999999\r\n\r\n"
    t = time.time()
    out = _raw(h, head, b"x" * 70000)
    assert b" 401 " in out.split(b"\r\n")[0] and time.time() - t < 5 and CALLS == []


def test_an_announced_body_over_64_mib_is_refused_even_with_the_token(host):
    h, _ = host
    head = (f"POST /call HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {h.token}\r\n"
            f"Content-Length: {65 * 1024 * 1024}\r\n\r\n").encode()
    assert b" 413 " in _raw(h, head).split(b"\r\n")[0]


def test_stop_returns_with_an_idle_connection_open(tmp_path):
    import socket
    h = Host(TOOLS, executor=lambda fn: fn(), session_dir=tmp_path, info=lambda: {})
    h.start()
    idle = socket.create_connection(("127.0.0.1", h.port))
    done = threading.Event()
    threading.Thread(target=lambda: (h.stop(), done.set()), daemon=True).start()
    assert done.wait(5), "stop() hung on an idle connection"
    idle.close()


def test_stop_returns_while_a_call_waits_for_the_main_thread(tmp_path):
    """Maya quits while a call is in flight: the handler waits for the main thread, which is in stop()."""
    gate = threading.Event()

    def main_thread(fn):
        gate.wait(10)       # the main thread is busy quitting
        return fn()
    h = Host(TOOLS, executor=main_thread, session_dir=tmp_path, info=lambda: {})
    h.start()
    threading.Thread(target=lambda: _post(h, {"tool": "scene_info", "inputs": {}}), daemon=True).start()
    time.sleep(0.3)
    done = threading.Event()
    threading.Thread(target=lambda: (h.stop(), done.set()), daemon=True).start()
    ok = done.wait(5)
    gate.set()
    assert ok, "stop() waited for the call in flight"


def test_the_scene_refresh_after_a_call_runs_on_the_main_thread(tmp_path):
    where = []
    main = threading.local()

    def executor(fn):
        main.on = True
        try:
            return fn()
        finally:
            main.on = False

    def info():
        where.append(getattr(main, "on", False))
        return {"scene": "a.ma", "unsaved": False}
    h = Host(TOOLS, executor=executor, session_dir=tmp_path, info=info)
    h.start()
    try:
        where.clear()
        assert _post(h, {"tool": "scene_info", "inputs": {}})[0] == 200
        assert where and all(where), where
    finally:
        h.stop()


def test_read_rig_is_refused_in_the_open_session(tmp_path):
    from kei.apps.maya_side import kei_tools
    tools = {"read_rig": kei_tools.TOOLS["read_rig"]}
    h = Host(tools, executor=lambda fn: fn(), session_dir=tmp_path, info=lambda: {})
    h.start()
    try:
        status, body = _post(h, {"tool": "read_rig", "inputs": {}})
        assert status == 403 and "copy" in body["error"]
    finally:
        h.stop()


def test_a_second_start_rewrites_a_session_file_that_was_removed(tmp_path, monkeypatch):
    from kei.apps.maya_side import kei_host
    h = Host(TOOLS, executor=lambda fn: fn(), session_dir=tmp_path, info=lambda: {"scene": "a.ma"})
    h.start()
    monkeypatch.setattr(kei_host, "HOST", h)
    try:
        import shutil
        shutil.rmtree(h.session_file.parent)
        kei_host.start()
        assert h.session_file.is_file()
    finally:
        h.stop()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions; Windows keeps LOCALAPPDATA private to the account")
def test_the_session_folder_and_file_are_private_on_posix(tmp_path):
    import stat
    h = Host(TOOLS, executor=lambda fn: fn(), session_dir=tmp_path / "s", info=lambda: {})
    h.start()
    try:
        assert stat.S_IMODE(h.session_file.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(h.session_file.stat().st_mode) == 0o600
    finally:
        h.stop()