"""The critics answer at once, and a verdict already given survives a pause of another critic."""
import threading
import time

import pytest

from kei.critic import VERDICTS_DIR, panel_review
from kei.seats import FakeSeat, SeatPaused, SeatResult
from kei.stages import stage_by_id
from test_conductor import shot
from test_conductor_critic import PASS

SEND_BACK = '{"verdict": "send_back", "notes": ["the heel slides at f12"]}'


def test_critics_run_at_the_same_time_and_answer_in_their_order(tmp_path):
    both = threading.Barrier(2, timeout=5)   # each critic waits for the other: only a parallel panel gets past

    def act(answer):
        def run(prompt, root):
            both.wait()
            return SeatResult(0, answer)
        return run
    panel = panel_review(stage_by_id("blocking"), shot(tmp_path), "a box falls",
                         [FakeSeat("a", act(SEND_BACK)), FakeSeat("b", act(PASS))])
    assert list(panel) == ["critic a: the heel slides at f12"]


def test_a_verdict_given_before_a_pause_is_not_asked_again_on_resume(tmp_path):
    root = shot(tmp_path)
    calls = {"a": 0, "b": 0}
    limited = {"on": True}

    def a(prompt, r):
        calls["a"] += 1
        return SeatResult(0, PASS)

    def b(prompt, r):
        calls["b"] += 1
        time.sleep(0.05)
        if limited["on"]:
            return SeatResult(1, "Claude usage limit reached. Your limit resets at 3pm")
        return SeatResult(0, PASS)
    critics = [FakeSeat("a", a), FakeSeat("b", b)]
    with pytest.raises(SeatPaused):
        panel_review(stage_by_id("blocking"), root, "a box falls", critics)
    assert (root / VERDICTS_DIR / "blocking-a.json").is_file()
    limited["on"] = False
    assert list(panel_review(stage_by_id("blocking"), root, "a box falls", critics)) == []
    assert calls == {"a": 1, "b": 2}
    assert not list((root / VERDICTS_DIR).glob("*.json"))   # kept only until the whole panel answered


def test_a_kept_verdict_is_not_used_for_a_different_prompt(tmp_path):
    root = shot(tmp_path)
    calls = []
    seat = FakeSeat("a", lambda p, r: calls.append(1) or SeatResult(0, PASS))
    from kei.critic import _keep, _kept_path, Verdict
    _keep(_kept_path(root, "blocking", seat), "0" * 64, Verdict(False, ["stale"]), "")
    assert list(panel_review(stage_by_id("blocking"), root, "a box falls", [seat])) == []
    assert calls == [1]


def test_a_critic_at_its_usage_limit_hands_the_review_to_its_fallback(tmp_path, monkeypatch):
    from kei.config import SeatSpec
    from kei.seats import CliSeat
    asked = []

    def run(self, prompt, workdir):
        asked.append(self.name)
        if self.name == "c":
            return SeatResult(1, "Claude usage limit reached")
        return SeatResult(0, SEND_BACK)
    monkeypatch.setattr(CliSeat, "run", run)
    seat = CliSeat(SeatSpec(name="c", cmd=["claude", "-p"], fallback_cmd=("codex", "exec", "-")))
    panel = panel_review(stage_by_id("blocking"), shot(tmp_path), "a box falls", [seat])
    assert asked == ["c", "c-fallback"] and list(panel) == ["critic c-fallback: the heel slides at f12"]


def test_with_no_fallback_a_usage_limit_still_pauses(tmp_path, monkeypatch):
    from kei.config import SeatSpec
    from kei.seats import CliSeat
    monkeypatch.setattr(CliSeat, "run", lambda self, p, w: SeatResult(1, "usage limit reached"))
    with pytest.raises(SeatPaused):
        panel_review(stage_by_id("blocking"), shot(tmp_path), "a box falls", [CliSeat(SeatSpec(name="c", cmd=["x"]))])


def test_fallback_cmd_is_read_from_kei_toml(tmp_path):
    from kei.config import ConfigError, load_config
    p = tmp_path / "kei.toml"
    p.write_text('[animator]\ncmd = ["x"]\n[[critics]]\nname = "c"\ncmd = ["y"]\nfallback_cmd = ["z", "-"]\n',
                 encoding="utf-8")
    assert load_config(p).critics[0].fallback_cmd == ("z", "-")
    p.write_text('[animator]\ncmd = ["x"]\n[[critics]]\nname = "c"\ncmd = ["y"]\nfallback_cmd = "z"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)
