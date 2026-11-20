"""The shot folder's file list in every prompt folds long runs: frames, key stills and the agent's helper scripts."""
from kei.prompts import _artifacts


def test_frames_and_key_stills_fold_into_one_line_each(tmp_path):
    (tmp_path / "out_p3" / "frames").mkdir(parents=True)
    for f in range(30):
        (tmp_path / "out_p3" / "frames" / f"f{f:04d}.png").write_bytes(b"")
    for f in (0, 12, 24, 36, 48):
        (tmp_path / "out_p3" / f"key_f{f:04d}.png").write_bytes(b"")
    (tmp_path / "out_p3" / "shot.json").write_text("{}")
    (tmp_path / "PLAN.md").write_text("x")
    lines = _artifacts(tmp_path)
    assert "PLAN.md" in lines and "out_p3/shot.json" in lines
    assert "out_p3/frames/f*.png (30 files, f0000.png to f0029.png)" in lines
    assert "out_p3/key_f*.png (5 files, key_f0000.png to key_f0048.png)" in lines
    assert len(lines) == 4


def test_a_few_numbered_files_stay_listed(tmp_path):
    for n in ("p1", "p2"):
        (tmp_path / f"build_{n}.py").write_text("")
    assert sorted(_artifacts(tmp_path)) == ["build_p1.py", "build_p2.py"]


def test_many_helper_scripts_are_counted_not_listed(tmp_path):
    (tmp_path / "plan").mkdir()
    for n in ("grip", "stance", "sweep", "probe", "twin", "cover", "ext", "src", "cmp", "dump", "lag", "local", "pp"):
        (tmp_path / "plan" / f"{n}.py").write_text("")
    (tmp_path / "plan" / "plan.json").write_text("{}")
    assert _artifacts(tmp_path) == ["plan/plan.json", "plan/*.py (13 python helpers, not listed)"]
