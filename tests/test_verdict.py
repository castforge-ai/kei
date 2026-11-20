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


def test_a_verdict_over_several_lines_or_in_a_fence_is_read():
    multi = 'Here it is:\n```json\n{\n  "verdict": "send_back",\n  "notes": ["f12: the heel slides"]\n}\n```\n'
    assert parse_verdict("codex", multi) == Verdict(False, ["critic codex: f12: the heel slides"])
    assert parse_verdict("codex", '{"verdict": "pass", "notes": []}\nthanks') == Verdict(True, [])


def test_minor_notes_never_send_back_and_earlier_notes_are_judged():
    v = parse_verdict("c", '{"verdict": "send_back", "notes": [], "minor": ["f40: a touch more overlap"], '
                           '"earlier": {"f9: the hips sink": "fixed"}}')
    assert v.passed and v.minor == ("critic c: f40: a touch more overlap",)
    assert v.earlier == (("f9: the hips sink", "fixed"),)
    v = parse_verdict("c", '{"verdict": "send_back", "notes": ["f12: the heel slides"], "minor": ["f40: overlap"]}')
    assert not v.passed and v.minor == ("critic c: f40: overlap",)
