"""A sound track in the shot: its level, beats and phrases per frame, the sheets, and keys snapped to its beats."""
import json
import math
import struct
import wave

import pytest

from kei.cli import main
from kei.keys import KeysError, edit
from kei.sound import SoundError, add_sound, beats, phrases, read_levels, snap

RATE = 8000


def wav(path, hits, seconds=2.0, fps=24, silence_from=None):
    """Clicks at the given frames (a short loud burst), with a quiet hum between, and silence after silence_from."""
    n = int(RATE * seconds)
    per = RATE / fps
    samples = []
    for i in range(n):
        f = i / per
        v = 4000 * math.sin(i / 3)
        if silence_from is not None and f >= silence_from:
            v = 0
        for h in hits:
            if h <= f < h + 1:
                v = 20000 * math.sin(i)
        samples.append(int(v))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack(f"<{n}h", *samples))
    return path


def test_the_levels_have_one_value_per_frame_and_the_clicks_are_the_beats(tmp_path):
    lv = read_levels(wav(tmp_path / "a.wav", [6, 18, 30]), 24)
    assert len(lv) == 48 and max(lv) == 1.0
    assert beats(lv) == [6, 18, 30]


def test_phrases_split_on_silence_and_short_gaps_do_not_split():
    lv = [0.5] * 10 + [0.0] * 3 + [0.5] * 10 + [0.0] * 10 + [0.5] * 5
    assert phrases(lv) == [[0, 22], [33, 37]]


def test_add_sound_writes_the_track_the_sheets_and_the_words(tmp_path):
    shot = tmp_path / "shot"
    shot.mkdir()
    got = add_sound(shot, wav(tmp_path / "line.wav", [6, 30], silence_from=40), 24, frames=47, words=["hey you"])
    assert (shot / "sound" / "line.wav").is_file() and (shot / "sound" / "waveform.png").read_bytes()[:4] == b"\x89PNG"
    data = json.loads((shot / "sound" / "sound.json").read_text())
    assert data["beats"] == [6, 30] and data["frames"] == 48 and data["phrases"][0][2] == "hey you"
    xs = (shot / "sound" / "XSHEET.md").read_text()
    assert "| 6 | ########## | B | ... |" in xs and got["phrases"][0][0] == 0
    row0 = next(line for line in xs.splitlines() if line.startswith("| 0 | "))
    assert row0.endswith("| hey you |")


def test_an_offset_skips_the_start_of_the_track(tmp_path):
    got = add_sound(tmp_path, wav(tmp_path / "a.wav", [12]), 24, offset=6)
    assert got["beats"] == [6]


def test_a_file_kei_cannot_read_is_refused(tmp_path):
    bad = tmp_path / "x.wav"
    bad.write_bytes(b"not a wav")
    with pytest.raises(SoundError, match="not a PCM WAV"):
        add_sound(tmp_path, bad, 24)
    with pytest.raises(SoundError, match="no sound file"):
        add_sound(tmp_path, tmp_path / "missing.wav", 24)


SHOT = {"rig": "v4", "fps": 24, "frames": 40, "loop": False,
        "keys": [{"f": 0}, {"f": 9}, {"f": 15}, {"f": 25}, {"f": 40}]}


def test_snap_moves_keys_to_near_beats_in_order_and_never_onto_another_key():
    out, n = snap(SHOT, [0, 8, 11, 16, 30], within=2)
    assert [k["f"] for k in out["keys"]] == [0, 8, 16, 25, 40] and n == 2
    out, n = snap(SHOT, [13], within=5)
    assert [k["f"] for k in out["keys"]] == [0, 9, 13, 25, 40]


def test_snap_keeps_a_loops_last_key_and_respects_a_frame_range():
    loop = {**SHOT, "loop": True}
    out, _ = snap(loop, [39], within=2)
    assert out["keys"][-1]["f"] == 40
    out, n = snap(SHOT, [8, 16], within=2, frames=(10, 20))
    assert [k["f"] for k in out["keys"]] == [0, 9, 16, 25, 40] and n == 1


def test_kei_keys_snap_needs_the_sound_then_edits_with_history(tmp_path, capsys):
    shot = tmp_path / "s"
    (shot / "out_p1").mkdir(parents=True)
    (shot / "out_p1" / "shot.json").write_text(json.dumps(SHOT))
    with pytest.raises(KeysError, match="kei sound"):
        edit(SHOT, "snap", by="2")
    assert main(["sound", str(shot), str(wav(tmp_path / "b.wav", [8, 16]))]) == 0
    assert "2 beat(s) at f8, f16" in capsys.readouterr().out
    assert main(["keys", str(shot), "p1", "snap", "--by", "2"]) == 0
    keys = [k["f"] for k in json.loads((shot / "out_p1" / "shot.json").read_text())["keys"]]
    assert keys == [0, 8, 16, 25, 40]
    log = json.loads((shot / "out_p1" / "edits.json").read_text())
    assert log[-1]["op"] == "snap" and "beats" not in log[-1] and (shot / "out_p1" / "history" / "001.json").is_file()
