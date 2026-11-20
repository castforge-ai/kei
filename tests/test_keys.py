"""kei keys: edit a pass's keys with named edits, every version kept."""
import json
from pathlib import Path

import pytest

from kei.cli import main
from kei.keys import KeysError, edit

ROOT = Path(__file__).resolve().parent.parent
WALK = {**json.loads((ROOT / "tests" / "fixtures" / "walks" / "kei_p10_approved.json").read_text(encoding="utf-8")),
        "loop": False}
SHOT = {"rig": "v4", "fps": 24, "frames": 20, "loop": False, "keys": [
    {"f": 0, "root": [0, 0.95, 0]}, {"f": 10, "root": [0, 0.90, 0.2]}, {"f": 20, "root": [0, 0.95, 0.4]}],
    "objects": [{"name": "box", "shape": "box", "size": [0.4, 0.4, 0.4], "rest": [0, 0.2, 0.5],
                 "attach": [{"f": 12, "to": "hands"}]}]}


def test_set_offset_insert_copy_delete():
    s, said = edit(SHOT, "set", frame=10, channel="root", value="0,0.88,0.2")
    assert s["keys"][1]["root"] == [0.0, 0.88, 0.2] and SHOT["keys"][1]["root"] == [0, 0.90, 0.2], "input unchanged"
    s, _ = edit(SHOT, "offset", frames="5-20", channel="root", by="0,-0.02,0")
    assert [round(k["root"][1], 3) for k in s["keys"]] == [0.95, 0.88, 0.93]
    s, _ = edit(SHOT, "insert", frame=5)
    assert [k["f"] for k in s["keys"]] == [0, 5, 10, 20] and 0.9 < s["keys"][1]["root"][1] < 0.95
    s, _ = edit(SHOT, "copy", src=0, frame=15)
    assert next(k for k in s["keys"] if k["f"] == 15)["root"] == [0, 0.95, 0]
    s, _ = edit(SHOT, "delete", frame=10)
    assert [k["f"] for k in s["keys"]] == [0, 20]


def test_shift_retimes_the_keys_and_the_objects_attach_frames():
    s, said = edit(SHOT, "shift", src=10, by="4")
    assert [k["f"] for k in s["keys"]] == [0, 14, 24] and s["frames"] == 24
    assert s["objects"][0]["attach"][0]["f"] == 16
    with pytest.raises(KeysError, match="past the keys"):
        edit(SHOT, "shift", src=10, by="-10")


@pytest.mark.parametrize("kw, words", [
    ({"op": "set", "frame": 10, "channel": "wing", "value": "1"}, "no channel"),
    ({"op": "set", "frame": 10, "channel": "root", "value": "1,2"}, "3 number"),
    ({"op": "offset", "frames": "3-4", "channel": "root", "by": "0,0,0"}, "no key in"),
    ({"op": "insert", "frame": 10}, "already has a key"),
    ({"op": "delete", "frame": 3}, "has no key"),
])
def test_a_bad_edit_says_why(kw, words):
    with pytest.raises(KeysError, match=words):
        edit(SHOT, **kw)


def test_the_cli_keeps_every_version_and_logs_each_edit(tmp_path, capsys):
    d = tmp_path / "out_p1"
    d.mkdir()
    (d / "shot.json").write_text(json.dumps(WALK), encoding="utf-8")
    assert main(["keys", str(tmp_path), "p1", "offset", "--frames", "0-28", "--channel", "root",
                 "--by", "0,-0.01,0"]) == 0
    assert (d / "history" / "001.json").is_file()
    log = json.loads((d / "edits.json").read_text())
    assert log[0]["op"] == "offset" and log[0]["did"].startswith("offset root")
    assert main(["keys", str(tmp_path), "p1", "copy", "--from", "0", "--frame", "28", "--to", "p2"]) == 0
    assert (tmp_path / "out_p2" / "shot.json").is_file()
    assert main(["keys", str(tmp_path), "p1", "delete", "--frame", "99"]) != 0
