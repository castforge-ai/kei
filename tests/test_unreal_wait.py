"""A busy editor gets time: Kei asks again every few seconds before it pauses the shot."""
import pytest

from kei.apps import unreal_stage
from kei.apps.unreal import UnrealError
from kei.apps.unreal_session import Editor


TARGET = {"kind": "open", "url": "http://127.0.0.1:1/mcp", "project": "game"}


def test_locate_waiting_asks_again_until_the_editor_answers(monkeypatch):
    monkeypatch.setenv("KEI_UNREAL_WAIT_S", "300")
    answers = [None, None, {"project": "game", "level": "L", "characters": []}]
    asked, slept = [], []
    got = unreal_stage.locate_waiting(TARGET, lambda url: (asked.append(url), answers.pop(0))[1], sleep=slept.append)
    assert isinstance(got, Editor) and len(asked) == 3 and slept == [unreal_stage.STEP_S] * 2


def test_locate_waiting_gives_up_after_the_patience(monkeypatch):
    monkeypatch.setenv("KEI_UNREAL_WAIT_S", "30")
    slept = []
    assert unreal_stage.locate_waiting(TARGET, lambda url: None, sleep=slept.append) is None
    assert slept == [15.0, 15.0]


def test_zero_patience_pauses_at_once(monkeypatch):
    monkeypatch.setenv("KEI_UNREAL_WAIT_S", "0")
    slept = []
    assert unreal_stage.locate_waiting(TARGET, lambda url: None, sleep=slept.append) is None and slept == []


def test_connect_waiting_retries_a_timeout_then_gives_up(monkeypatch):
    monkeypatch.setenv("KEI_UNREAL_WAIT_S", "45")
    calls = []

    def connect(url):
        calls.append(url)
        if len(calls) < 3:
            raise UnrealError("Claireon did not answer in 60 s")
        return "client"
    monkeypatch.setattr(unreal_stage, "_connect", connect)
    assert unreal_stage.connect_waiting("u", sleep=lambda s: None) == "client" and len(calls) == 3
    monkeypatch.setattr(unreal_stage, "_connect", lambda url: (_ for _ in ()).throw(UnrealError("no")))
    with pytest.raises(UnrealError):
        unreal_stage.connect_waiting("u", sleep=lambda s: None)
