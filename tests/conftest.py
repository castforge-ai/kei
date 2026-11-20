"""Tests that talk to a fake Claireon do not wait for the editor tick."""
from pathlib import Path

import pytest

_REPO_LESSONS = Path(__file__).resolve().parent.parent / "lessons.local.md"


def _lessons_text():
    return _REPO_LESSONS.read_bytes() if _REPO_LESSONS.is_file() else None


@pytest.fixture(autouse=True, scope="session")
def _repo_lessons_untouched():
    """No test writes the repository's own lessons file (a test's lesson belongs in its tmp folder)."""
    before = _lessons_text()
    yield
    assert _lessons_text() == before, f"a test changed {_REPO_LESSONS}: run that test's kei note in its tmp folder"


@pytest.fixture(autouse=True)
def _own_kei_home(tmp_path_factory, monkeypatch):
    """The note signing key of a test lives in a tmp folder, never in the user's ~/.kei."""
    monkeypatch.setenv("KEI_HOME", str(tmp_path_factory.mktemp("kei_home")))


@pytest.fixture(autouse=True)
def _one_render_process(monkeypatch):
    """The suite runs in parallel already: a render draws in one process unless a test asks for workers."""
    monkeypatch.setenv("KEI_RENDER_WORKERS", "1")


@pytest.fixture(autouse=True)
def _no_editor_tick(monkeypatch):
    monkeypatch.setattr("kei.apps.unreal.TICK_SECONDS", 0)


@pytest.fixture(autouse=True)
def _no_live_page(monkeypatch):
    """kei run starts a live page in its own process; tests never do (test_live.py turns it back on by hand)."""
    monkeypatch.setenv("KEI_NO_LIVE", "1")


@pytest.fixture(autouse=True)
def _no_editor_wait(monkeypatch):
    """A test whose editor does not answer pauses at once; test_unreal_wait.py sets its own patience."""
    monkeypatch.setenv("KEI_UNREAL_WAIT_S", "0")
