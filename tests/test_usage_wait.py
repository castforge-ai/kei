"""A usage limit: Kei reads when it resets, records it, and kei run --wait-on-limit waits for it."""
from datetime import datetime

from kei.seats import SeatResult, pause_kind, reset_at

NOW = datetime(2026, 11, 19, 14, 0)


def test_the_reset_time_is_read_from_the_message():
    assert reset_at("You've hit your usage limit. It resets 2026-11-24 10:46.", NOW) == datetime(2026, 11, 24, 10, 46)
    assert reset_at("Rate limit reached, try again in 2h 30m", NOW) == datetime(2026, 11, 19, 16, 30)
    assert reset_at("limit reached; resets at 3pm", NOW) == datetime(2026, 11, 19, 15, 0)
    assert reset_at("limit reached; resets at 1pm", NOW) == datetime(2026, 11, 20, 13, 0)
    assert reset_at("usage limit reached", NOW) is None


def test_a_bare_429_in_a_failed_run_is_not_a_usage_limit():
    assert pause_kind(SeatResult(1, "Traceback: frame 429 out of range")) is None
    assert pause_kind(SeatResult(1, "API Error: 429 Too Many Requests")) == "usage"
    assert pause_kind(SeatResult(1, "HTTP 429")) == "usage"
