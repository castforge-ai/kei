import pytest

from kei.state import ShotState, StateError, load_state, save_state


def test_missing_state_is_the_start(tmp_path):
    s = load_state(tmp_path)
    assert (s.stage, s.attempts, s.status) == ("brief", 0, "running")


def test_save_is_atomic_and_round_trips(tmp_path):
    s = ShotState(stage="plan", attempts=2, request="a heavy sprint stop",
                  history=[{"stage": "brief", "attempt": 1, "result": "pass", "misses": [],
                            "at": "2026-10-30T12:00:00"}])
    save_state(tmp_path, s)
    assert load_state(tmp_path) == s
    assert list((tmp_path / ".kei").glob("*.tmp")) == []


def test_corrupt_state_names_the_file(tmp_path):
    (tmp_path / ".kei").mkdir()
    (tmp_path / ".kei" / "state.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(StateError) as e:
        load_state(tmp_path)
    assert "state.json" in str(e.value)
