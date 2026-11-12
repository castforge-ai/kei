"""A delivered Unreal shot: Kei's folder in the editor keeps the delivered sequence on top, the rest by phase."""
import json

from kei.apps.unreal_rig import sequences
from kei.apps.unreal_tidy import plan_moves, tidy
from unrealkit import FakeEditor

F = "/Game/Kei/walk"
BOOK = {"rig": [f"{F}/LS_walk_rig_1"], "probe": [f"{F}/LS_walk_probe_1"],
        "blocking": [f"{F}/LS_walk_blocking_1", f"{F}/LS_walk_blocking_2"], "p1": [f"{F}/LS_walk_p1_1"],
        "p2": [f"{F}/LS_walk_p2_1"], "p3": [f"{F}/LS_walk_p3_1", f"{F}/LS_walk_p3_2"],
        "toeprobe": [f"{F}/LS_walk_toeprobe_1"]}
PHASES = {1: "4_breakdowns", 2: "5_spline", 3: "6_polish"}


def test_only_the_last_sequence_of_the_final_pass_stays_on_top(tmp_path):
    shot = tmp_path / "walk"
    moves = dict(plan_moves(shot, BOOK, PHASES, "p3"))
    assert f"{F}/LS_walk_p3_2" not in moves                                      # delivered: stays on top
    assert moves[f"{F}/LS_walk_p3_1"] == f"{F}/Production/6_Polish/LS_walk_p3_1"
    assert moves[f"{F}/LS_walk_blocking_2"] == f"{F}/Production/3_Blocking/LS_walk_blocking_2"
    assert moves[f"{F}/LS_walk_p1_1"] == f"{F}/Production/4_Breakdowns/LS_walk_p1_1"
    assert moves[f"{F}/LS_walk_rig_1"] == f"{F}/Production/1_Setup/LS_walk_rig_1"
    assert moves[f"{F}/LS_walk_toeprobe_1"] == f"{F}/Production/9_Probes/LS_walk_toeprobe_1"
    assert plan_moves(shot, {"p3": [f"{F}/Production/6_Polish/LS_walk_p3_1", f"{F}/LS_walk_p3_2"]}, PHASES,
                      "p3") == []                                                # already filed: nothing to do


def test_tidy_moves_them_in_the_editor_and_records_the_new_paths(tmp_path):
    shot = tmp_path / "walk"
    (shot / "unreal").mkdir(parents=True)
    for n in (1, 2, 3):
        (shot / f"out_p{n}").mkdir()
    (shot / "unreal" / "sequences.json").write_text(json.dumps(BOOK), encoding="utf-8")
    ed = FakeEditor()
    ed.sequences = {p: {} for v in BOOK.values() for p in v}
    with ed.server() as fake:
        r = tidy(ed.client(), shot)
        assert fake.scripts == ["organize"]
    assert r["failed"] == [] and r["kept"] == [f"{F}/LS_walk_p3_2"] and len(r["moved"]) == 8
    book = sequences(shot)
    assert book["p3"] == [f"{F}/Production/6_Polish/LS_walk_p3_1", f"{F}/LS_walk_p3_2"]
    assert set(ed.sequences) == {p for v in book.values() for p in v}


def test_a_copy_of_the_report_sits_beside_the_unreal_assets_and_points_back_at_the_shot(tmp_path):
    from kei.live.report import refresh, report_name, write_unreal_copy
    shot = tmp_path / "walk"
    (shot / "out_p1" / "frames").mkdir(parents=True)
    (shot / "out_p1" / "frames" / "f0000.png").write_bytes(b"\x89PNG")
    content = tmp_path / "Project" / "Content"
    dest = write_unreal_copy(shot, str(content), "/Game/Kei/walk")
    assert dest == content / "Kei" / "walk" / report_name(shot)
    html = dest.read_text(encoding="utf-8")
    assert "file:///" in html and "out_p1/frames/f0000.png" in html          # full paths back to the shot folder
    assert len(refresh(shot)) == 2                                           # the copy is kept up to date
