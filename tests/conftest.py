"""Tests that talk to a fake Claireon do not wait for the editor tick."""
import pytest


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
