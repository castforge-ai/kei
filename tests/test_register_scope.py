"""A pushed register can be scoped to beats, and it never turns an arc break into a note."""
from kei.style import apply, pushed_ranges


def _flags():
    return [{"check": "balance", "frames": [5, 9], "measure": "balance_outside_m", "value": 0.2},
            {"check": "balance", "frames": [70, 80], "measure": "balance_outside_m", "value": 0.3},
            {"check": "arcs", "frames": [75, 75], "measure": "arc_kink_deg", "value": 120},
            {"check": "contacts", "frames": [3, 4]}]


def _plan(tmp_path, line):
    (tmp_path / "PLAN.md").write_text(f"# Plan\n{line}\n", encoding="utf-8")
    return pushed_ranges(tmp_path)


def test_pushed_beats_are_read_from_the_register_line(tmp_path):
    assert _plan(tmp_path, "Register: pushed f61-120, f150 to f167") == [(61, 120), (150, 167)]
    assert _plan(tmp_path, "Register: pushed") is None
    assert _plan(tmp_path, "Register: realistic f1-20") is None


def test_only_flags_in_a_pushed_beat_become_notes(tmp_path):
    flags = _flags()
    out = apply(flags, None, "pushed", [(61, 120)])
    assert [bool(f.get("note")) for f in flags] == [False, True, True, False]
    assert out["faults"] == 2 and out["notes"] == 2 and "f61-120" in out["register"]


def test_pushed_keeps_pops_wobble_and_jolts_as_faults_but_relaxes_kinks():
    flags = _flags() + [{"check": "arcs", "frames": [75, 75], "measure": "spacing_pop_ratio", "value": 3.0},
                        {"check": "jolt", "frames": [75, 75], "measure": "jolt_g", "value": 6.0}]
    apply(flags, None, "pushed")
    assert [bool(f.get("note")) for f in flags] == [True, True, True, False, False, False]


def test_a_style_range_can_still_allow_a_spacing_pop():
    flags = [{"check": "arcs", "frames": [75, 75], "measure": "spacing_pop_ratio", "value": 3.0}]
    apply(flags, {"range": {"spacing_pop_ratio": {"max": 3.2, "clip": "idle_03"}}}, "pushed")
    assert flags[0].get("inside_style") and flags[0].get("note")
