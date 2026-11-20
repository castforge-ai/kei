"""A declared principle flag stays declared when a re-key moves its first frame by a few frames."""
from kei.gates.pipeline import DECLARED_DRIFT, _declared, open_flags


def flag(fid):
    return {"id": fid, "frames": [int(fid.rsplit(".f", 1)[1]), 40]}


GATES = "# Gates\n\n## Declared\n- timing.hold.chest.f20: the hold is the acting beat\n\n## Notes\nnone\n"


def test_the_exact_id_is_declared():
    assert open_flags([flag("timing.hold.chest.f20")], GATES) == []


def test_a_flag_moved_by_a_few_frames_stays_declared():
    assert open_flags([flag("timing.hold.chest.f21")], GATES) == []
    assert open_flags([flag(f"timing.hold.chest.f{20 - DECLARED_DRIFT}")], GATES) == []


def test_a_flag_moved_further_or_on_another_part_is_open():
    far = flag(f"timing.hold.chest.f{20 + DECLARED_DRIFT + 1}")
    other = flag("timing.hold.head.f20")
    assert open_flags([far, other], GATES) == [far, other]


def test_one_declaration_covers_one_flag_the_exact_one_first():
    exact, near = flag("timing.hold.chest.f20"), flag("timing.hold.chest.f22")
    assert open_flags([near, exact], GATES) == [near]


def test_every_declared_section_counts():
    gates = GATES + "\n## Declared (passes)\n- arcs.kink.hand_l.f8: a snap on purpose\n"
    assert _declared(gates) == {"timing.hold.chest.f20", "arcs.kink.hand_l.f8"}
    assert open_flags([flag("arcs.kink.hand_l.f9")], gates) == []


def test_the_p10_gate_reads_kei_check_and_refuses_an_open_hard_flag(tmp_path):
    import json
    from kei.gates.pipeline import check
    p = tmp_path / "out_p1"
    (p / "body_check").mkdir(parents=True)
    (p / "shot.json").write_text("{}", encoding="utf-8")
    (p / "body_check" / "body_check.json").write_text(json.dumps({"flags": [
        {"check": "foot_slide", "frames": [40, 44], "what": "the planted left foot slides", "rule": "hard"},
        {"check": "balance", "frames": [3, 9], "what": "out of balance", "rule": "soft"}]}), encoding="utf-8")
    import os
    os.utime(p / "shot.json", (1_000_000, 1_000_000))                            # the check is newer than the keys
    (tmp_path / "PLAN.md").write_text("brief\nIdea sentence: a walk.\n", encoding="utf-8")
    p10 = lambda: [m for m in check(str(tmp_path))[0] if m.startswith("P10")]   # noqa: E731
    assert [m.split(" ")[1] for m in p10()] == ["foot_slide.body.f40"]          # the soft flag is the critics' call
    (tmp_path / "GATES.md").write_text("## Declared\n- foot_slide.body.f41: the foot pivots on purpose\n",
                                       encoding="utf-8")
    assert p10() == []                                                           # declared (a frame of drift is fine)
