"""A delivered shot: the finished files on top, the work in production/<phase>/, and the working layout back on demand."""
import json

from kei import layout
from kei.cli import main
from kei.live.snapshot import snapshot
from kei.state import ShotState, load_state, save_state

GATES = """# Gates
## Blocking gate: pass
ok
## Breakdowns gate: pass
Keyed out_p1/shot.json.
## Spline gate: pass
The spline is out_p2.
## Polish gate: pass
Polish in out_p3.
## Polish gate: pass (p4, hands)
More polish.
"""


def delivered(tmp_path, status="done"):
    shot = tmp_path / "walk"
    for d in ("plan", "rig", "weight", "unreal", "out_blocking", "out_p1", "out_p2", "out_p3", "out_p4",
              "out_probe", "blocking_build", "checks_build", "video"):
        (shot / d).mkdir(parents=True, exist_ok=True)
    for n in range(1, 5):
        (shot / f"out_p{n}" / "shot.json").write_text(json.dumps({"pass": n}), encoding="utf-8")
    for f, text in (("PLAN.md", "Idea sentence: a walk."), ("REFS.md", "refs"), ("CHARACTER.md", "c"),
                    ("GATES.md", GATES), ("CHECKS.md", "x"), ("REVIEW.md", "## What I learned\n- a"),
                    ("GROWTH.md", "walk"), ("notes.txt", "loose")):
        (shot / f).write_text(text, encoding="utf-8")
    (shot / "plan" / "plan.json").write_text(json.dumps({"fps": 30, "frames": 34, "keys": []}), encoding="utf-8")
    (shot / "video" / "walk_01.mp4").write_bytes(b"mp4")
    save_state(shot, ShotState(stage="deliver", status=status, request="a walk"))
    return shot


def names(d):
    return sorted(p.name for p in d.iterdir())


def test_packing_keeps_only_the_delivery_on_top_and_files_the_work_by_phase(tmp_path):
    shot = delivered(tmp_path)
    m = layout.pack(shot)
    assert names(shot) == [".kei", "GROWTH.md", "REVIEW.md", "production", "walk_01.mp4", "walk_final.json"]
    prod = shot / "production"
    assert names(prod) == ["1_setup", "2_planning", "3_blocking", "4_breakdowns", "5_spline", "6_polish",
                           "7_checks", "9_probes", "other"]
    assert names(prod / "6_polish") == ["out_p3", "out_p4"] and names(prod / "4_breakdowns") == ["out_p1"]
    assert names(prod / "1_setup") == ["CHARACTER.md", "rig", "unreal", "weight"]
    assert json.loads((shot / "walk_final.json").read_text()) == {"pass": 4}       # the last pass, as delivered
    assert m["final_pass"] == "p4" and layout.where(shot, "plan/plan.json").is_file()


def test_unpacking_puts_every_file_back_exactly(tmp_path):
    shot = delivered(tmp_path)
    before = sorted(p.relative_to(shot).as_posix() for p in shot.rglob("*") if ".kei" not in p.parts)
    layout.pack(shot)
    layout.unpack(shot)
    after = sorted(p.relative_to(shot).as_posix() for p in shot.rglob("*") if ".kei" not in p.parts)
    assert after == before and not layout.is_packed(shot)


def test_kei_approve_packs_the_shot_in_every_app(tmp_path, capsys):
    shot = delivered(tmp_path, status="needs_approval")
    (shot / "maya").mkdir()
    assert main(["approve", str(shot)]) == 0
    assert layout.is_packed(shot) and (shot / "production" / "1_setup" / "maya").is_dir()
    assert "production" in capsys.readouterr().out


def test_a_command_on_a_delivered_shot_gets_the_working_layout_and_a_reopened_shot_stays_unpacked(tmp_path,
                                                                                                monkeypatch):
    monkeypatch.chdir(tmp_path)   # the note's lesson goes to this folder's lessons.local.md, never the repository's
    shot = delivered(tmp_path)
    layout.pack(shot)
    assert main(["status", str(shot)]) == 0 and layout.is_packed(shot)       # read as it is
    assert main(["note", str(shot), "--text", "the arms swing too wide"]) == 0
    assert load_state(shot).status != "done"
    assert not layout.is_packed(shot) and (shot / "PLAN.md").is_file() and (shot / "out_p4").is_dir()


def test_the_live_page_reads_a_delivered_shot(tmp_path):
    shot = delivered(tmp_path)
    layout.pack(shot)
    s = snapshot(shot)
    assert s["plan"]["frames"] == 34 and s["facts"] == {"Idea sentence": "a walk."}
    assert [p["name"] for p in s["passes"]][-1] in ("p4", "p3", "p2", "p1", "blocking", "probe")
    assert {"blocking", "p1", "p4"} <= {p["name"] for p in s["passes"]}


def test_approving_saves_the_live_page_as_one_report_file_on_top(tmp_path):
    from kei.live.report import report_name
    shot = delivered(tmp_path, status="needs_approval")
    (shot / "out_p4" / "frames").mkdir()
    (shot / "out_p4" / "frames" / "f0000.png").write_bytes(b"\x89PNG")
    assert main(["approve", str(shot)]) == 0
    report = shot / report_name(shot)
    html = report.read_text(encoding="utf-8")
    assert "window.KEI_STATIC" in html and "<style>" in html and 'src="/live.js"' not in html
    assert "http://" not in html and "https://" not in html                   # nothing from the network
    assert "production/6_polish/out_p4/frames/f0000.png" in html               # files by their path beside it
    layout.unpack(shot)
    layout.pack(shot)
    assert report.is_file()                                                     # it stays on top through a repack
