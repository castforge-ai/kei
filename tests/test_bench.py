"""kei bench: one brief, several seats, a blind comparison with a sealed key."""
import json
import random

import pytest

from kei.bench import BenchError, read_bench, run_bench
from kei.state import ShotState, save_state


def bench(tmp_path):
    (tmp_path / "bench.toml").write_text('brief = "a crate lifted"\n[[seat]]\nname = "claude"\nconfig = "a.toml"\n'
                                         '[[seat]]\nname = "gpt"\nconfig = "b.toml"\n', encoding="utf-8")
    for n in ("a.toml", "b.toml"):
        (tmp_path / n).write_text('[animator]\ncmd = ["x"]\n', encoding="utf-8")
    return tmp_path


def fake_run(shot, brief, config, answers):
    (shot / "out_p1").mkdir(exist_ok=True)
    (shot / "out_p1" / "shot.json").write_text("{}", encoding="utf-8")
    save_state(shot, ShotState(stage="deliver", status="needs_approval", request=brief,
                               history=[{"stage": "passes", "result": "send_back"}, {"stage": "passes", "result": "pass",
                                                                                   "scripts": 3}]))


def fake_render(shot, pass_name):
    v = shot / f"out_{pass_name}" / "playback.mp4"
    v.write_bytes(shot.name.encode())
    return v


def test_each_seat_runs_and_the_videos_go_blind_with_a_sealed_key(tmp_path):
    r = run_bench(bench(tmp_path), run=fake_run, render=fake_render, rng=random.Random(1))
    assert r["blind"] == ["A.mp4", "B.mp4"]
    key = json.loads((tmp_path / "blind" / "key.json").read_text(encoding="utf-8"))
    assert sorted(key.values()) == ["claude", "gpt"]
    assert (tmp_path / "blind" / "A.mp4").read_bytes() == key["A"].encode()
    runs = (tmp_path / "RUNS.md").read_text(encoding="utf-8")
    assert r["seal"] in runs and "claude" in runs and "| 3 | p1 |" in runs


def test_a_bench_needs_a_brief_and_two_seats(tmp_path):
    (tmp_path / "bench.toml").write_text('brief = "x"\n[[seat]]\nname = "a"\nconfig = "a.toml"\n', encoding="utf-8")
    with pytest.raises(BenchError):
        read_bench(tmp_path)
