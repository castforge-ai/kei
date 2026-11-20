"""kei demo: Kei's tools on an approved walk, offline."""
from kei.cli import main


def test_the_demo_writes_every_artifact_it_names(tmp_path, capsys):
    assert main(["demo", str(tmp_path / "d")]) == 0
    out = capsys.readouterr().out
    for what in ("playback", "key sheet", "body checks", "pose records", "trails"):
        assert f"- {what}: " in out
    assert (tmp_path / "d" / "out_p1" / "poses" / "pose_sheet.png").is_file()
