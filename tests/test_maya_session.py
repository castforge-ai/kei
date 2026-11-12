"""Task 8 of plan 6: finding open Maya sessions and asking where to animate. Real session files in a temp folder and a
real Kei host on a free port (fake executor, fake scene), so no Maya is needed."""
import json
import os

import pytest

from kei.apps.maya_session import Question, Target, answer_choice, choose_target, find_sessions, ping
from kei.apps.maya_side.kei_host import Host
from kei.apps.maya_side.kei_tools import tool_entry


def _host(root, scene="C:/shots/walk.ma", unsaved=False, rigs=("kei:kei_rig",)):
    info = {"maya_version": "2027", "scene": scene, "unsaved": unsaved, "rigs": list(rigs)}
    h = Host({"scene_info": tool_entry(lambda: info, "read")}, executor=lambda fn: fn(), session_dir=root,
             info=lambda: info)
    h.start()
    return h


def _fake_session(root, pid, start, port=1, token="t"):
    d = root / str(pid)
    d.mkdir(parents=True)
    (d / "session.json").write_text(json.dumps({"pid": pid, "start_time": start, "port": port, "token": token}))
    return d


def _alive_self(pid):
    from kei.apps.maya_side.kei_proc import start_time
    return start_time(pid)


@pytest.fixture
def root(tmp_path):
    return tmp_path / "sessions"


def test_no_session_and_no_maya_works_in_the_background_without_asking(root):
    sessions, hostless = find_sessions(root, maya_pids=lambda: [])
    assert choose_target(sessions, hostless) == Target("background")


def test_one_live_session_gives_a_question_naming_its_scene_rig_and_unsaved_changes(root):
    h = _host(root, unsaved=True)
    try:
        sessions, hostless = find_sessions(root, alive=_alive_self, maya_pids=lambda: [])
        q = choose_target(sessions, hostless)
        assert isinstance(q, Question)
        assert f"session {os.getpid()}" in q.text and "C:/shots/walk.ma" in q.text and "rig kei" in q.text
        assert "unsaved changes" in q.text
        assert [c["kind"] for c in q.choices] == ["open", "background"]
    finally:
        h.stop()


def test_two_sessions_give_both_and_the_background(root):
    h = _host(root)
    try:
        sessions, _ = find_sessions(root, alive=_alive_self, maya_pids=lambda: [])
        twin = sessions[0].__class__(**{**sessions[0].__dict__, "pid": 4242, "scene": "C:/other.ma"})
        q = choose_target(sessions + [twin], [])
        assert [c["kind"] for c in q.choices] == ["open", "open", "background"]
        assert "C:/other.ma" in q.text
    finally:
        h.stop()


def test_a_dead_pid_s_file_is_removed(root):
    d = _fake_session(root, 999999, 1.0)
    assert find_sessions(root, alive=lambda pid: None, maya_pids=lambda: []) == ([], [])
    assert not d.exists()


def test_a_reused_pid_with_another_start_time_is_ignored_and_its_file_removed(root):
    d = _fake_session(root, 1234, 100.0)
    called = []
    sessions, _ = find_sessions(root, alive=lambda pid: 500.0, ping=lambda p, t: called.append(p) or {},
                                maya_pids=lambda: [])
    assert sessions == [] and not d.exists() and called == []


def test_a_live_maya_whose_host_does_not_answer_is_kept_and_reported_busy(root):
    """A modal dialog or a long evaluation keeps Maya from answering; its session is alive, so its file stays."""
    d = _fake_session(root, os.getpid(), _alive_self(os.getpid()), port=9)
    sessions, hostless = find_sessions(root, alive=_alive_self, ping=ping, maya_pids=lambda: [])
    assert d.exists() and len(sessions) == 1 and sessions[0].busy
    q = choose_target(sessions, hostless)
    assert "busy" in q.text and [c["kind"] for c in q.choices] == ["background"]
    assert choose_target(sessions, hostless, "open") != Target("open", sessions[0])


def test_a_session_file_missing_its_port_or_token_is_removed_and_the_scan_goes_on(root):
    bad = root / "11"
    bad.mkdir(parents=True)
    (bad / "session.json").write_text(json.dumps({"pid": 11, "start_time": 1.0}))
    h = _host(root)
    try:
        sessions, _ = find_sessions(root, alive=lambda pid: _alive_self(os.getpid()) if pid == os.getpid() else 1.0,
                                    maya_pids=lambda: [])
        assert [s.pid for s in sessions] == [os.getpid()] and not bad.exists()
    finally:
        h.stop()


def test_a_session_started_after_the_first_scan_is_found_at_the_next(root):
    assert find_sessions(root, alive=_alive_self, maya_pids=lambda: [])[0] == []
    h = _host(root)
    try:
        assert len(find_sessions(root, alive=_alive_self, maya_pids=lambda: [])[0]) == 1
    finally:
        h.stop()


def test_a_maya_with_no_host_gives_the_shelf_step_and_the_background_choice(root):
    sessions, hostless = find_sessions(root, maya_pids=lambda: [5150])
    q = choose_target(sessions, hostless)
    assert isinstance(q, Question) and "process 5150" in q.text and "kei maya shelf" in q.text
    assert [c["kind"] for c in q.choices] == ["background"]


def test_each_setting(root):
    h = _host(root)
    try:
        sessions, hostless = find_sessions(root, alive=_alive_self, maya_pids=lambda: [])
        assert choose_target(sessions, hostless, "background") == Target("background")
        t = choose_target(sessions, hostless, "open")
        assert t.kind == "open" and t.session.pid == os.getpid()
        assert isinstance(choose_target(sessions, hostless, "ask"), Question)
        assert isinstance(choose_target(sessions * 2, hostless, "open"), Question)   # which one? it asks
        with pytest.raises(ValueError, match="ask, open, background"):
            choose_target(sessions, hostless, "sometimes")
    finally:
        h.stop()


def test_an_answer_picks_by_number_and_a_number_out_of_range_is_refused():
    q = choose_target([], [7], "ask")
    assert answer_choice(q.choices, "1")["kind"] == "background"
    with pytest.raises(ValueError, match="from 1 to 1"):
        answer_choice(q.choices, "2")
    with pytest.raises(ValueError, match="from 1 to 1"):
        answer_choice(q.choices, "the open one")
