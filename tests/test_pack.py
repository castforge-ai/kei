"""kei pack writes one file that shows the shot anywhere, and kei note --from-file brings the reviewer's notes back."""
import json

import pytest

from kei import pack as packmod
from kei.cli import main
from kei.notesign import signed
from kei.state import load_state
from test_cli import cfg
from test_signoff import waiting

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def _with_sheet(tmp_path):
    root = waiting(tmp_path)
    (root / "out_p1" / "poses").mkdir(parents=True)
    (root / "out_p1" / "poses" / "pose_sheet.png").write_bytes(PNG)
    (root / "out_p1" / "frames").mkdir()
    (root / "out_p1" / "frames" / "f0001.png").write_bytes(PNG)
    return root


def _notes_file(tmp_path, root, pack_id, notes, shot=None, reviewer="Sam"):
    f = tmp_path / "notes.json"
    f.write_text(json.dumps({"kei_notes": 1, "shot": shot or root.name, "pack": pack_id, "reviewer": reviewer,
                             "notes": notes}))
    return f


def test_the_pack_is_one_file_with_the_images_inside_and_no_frame_folders(tmp_path):
    root = _with_sheet(tmp_path)
    r = packmod.pack(root)
    html = r["path"].read_text(encoding="utf-8")
    assert r["path"] == root / f"{root.name}_pack.html"
    assert "data:image/png;base64," in html and "out_p1/poses/pose_sheet.png" not in html
    assert html.count("data:image/png;base64,") == r["files"] and r["files"] >= 1
    assert 'id="reviewer-notes"' in html and "window.KEI_PACK" in html and r["pack"] in html
    assert "src=\"/" not in html and "http://" not in html.split("<body>")[0]
    rec = json.loads((root / ".kei" / "packs.json").read_text())
    assert rec["packs"][0]["pack"] == r["pack"]


def test_a_tight_limit_leaves_files_out_and_says_so(tmp_path):
    root = _with_sheet(tmp_path)
    r = packmod.pack(root, max_mb=0.00001)
    assert r["files"] == 0 and r["skipped"] and "limit" in r["skipped"][0][1]


def test_no_shot_no_pack(tmp_path):
    with pytest.raises(packmod.PackError, match="not a Kei shot"):
        packmod.pack(tmp_path)


def test_notes_come_back_as_signed_notes_for_this_shot_with_the_reviewer(tmp_path, capsys):
    root = _with_sheet(tmp_path)
    r = packmod.pack(root)
    f = _notes_file(tmp_path, root, r["pack"], [{"text": "the left hand arc is off", "frames": "13-18"},
                                                 {"text": "the settle is too short", "frames": ""}])
    c = cfg(tmp_path, '[animator]\ncmd = ["x"]\n')
    assert main(["note", str(root), "--from-file", str(f), "--config", c]) == 0
    out = capsys.readouterr().out
    assert "noted from Sam: f13-18: the left hand arc is off" in out and "2 note(s) from Sam" in out
    notes = [h for h in load_state(root).history if h.get("result") == "note"]
    assert [n["misses"][0] for n in notes] == ["f13-18: the left hand arc is off", "the settle is too short"]
    assert all(n["reviewer"] == "Sam" and n["scope"] == "this shot" and signed(n) for n in notes)
    assert load_state(root).status == "running"
    assert main(["note", str(root), "--from-file", str(f), "--config", c]) == 1
    assert "already brought in" in capsys.readouterr().err


@pytest.mark.parametrize("change,said", [
    ({"shot": "other"}, "is for the shot"),
    ({"pack": "0000"}, "never made"),
    ({"notes": []}, "no notes"),
    ({"notes": [{"text": " "}]}, "no words"),
    ({"notes": [{"text": "x", "frames": "abc"}]}, "frames Kei cannot read"),
    ({"reviewer": ""}, "no reviewer"),
    ({"kei_notes": 2}, "not a notes file"),
])
def test_a_bad_notes_file_writes_nothing(tmp_path, change, said):
    root = _with_sheet(tmp_path)
    r = packmod.pack(root)
    data = {"kei_notes": 1, "shot": root.name, "pack": r["pack"], "reviewer": "Sam", "notes": [{"text": "ok"}]}
    data.update(change)
    f = tmp_path / "n.json"
    f.write_text(json.dumps(data))
    before = load_state(root).history
    with pytest.raises(packmod.PackError, match=said):
        packmod.read_notes(root, f)
    assert load_state(root).history == before


def test_from_file_refuses_text_too(tmp_path, capsys):
    root = _with_sheet(tmp_path)
    c = cfg(tmp_path, '[animator]\ncmd = ["x"]\n')
    assert main(["note", str(root), "--from-file", "x.json", "--text", "y", "--config", c]) == 1
    assert "takes no --text" in capsys.readouterr().err


def test_the_command_prints_where_and_how(tmp_path, capsys):
    root = _with_sheet(tmp_path)
    assert main(["pack", str(root), "--no-video"]) == 0
    out = capsys.readouterr().out
    assert "written:" in out and "--from-file" in out
