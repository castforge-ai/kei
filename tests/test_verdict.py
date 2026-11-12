from kei.critic import Verdict, parse_verdict


def test_pass_line():
    assert parse_verdict("codex", 'looks right\n{"verdict": "pass", "notes": []}') == Verdict(True, [])


def test_send_back_line_prefixes_notes():
    out = '{"verdict": "send_back", "notes": ["hips arc is straight f14-18"]}'
    assert parse_verdict("codex", out) == Verdict(False, ["critic codex: hips arc is straight f14-18"])


def test_last_verdict_line_wins():
    out = '{"verdict": "pass", "notes": []}\nthen I looked again\n{"verdict": "send_back", "notes": ["f3 pops"]}'
    assert parse_verdict("codex", out) == Verdict(False, ["critic codex: f3 pops"])


def test_prose_without_a_verdict_is_a_send_back():
    assert parse_verdict("codex", "All good!") == Verdict(False, ["critic codex: no verdict line"])


def test_send_back_without_notes_still_says_why():
    out = '{"verdict": "send_back", "notes": []}'
    assert parse_verdict("codex", out) == Verdict(False, ["critic codex: sent back with no reason"])
