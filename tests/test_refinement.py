"""Refinement depth: a pass that changes nothing, or that keys every frame, is a gate miss at the passes stage."""
import json
from pathlib import Path

from kei.refinement import measure, refinement_misses

ROOT = Path(__file__).resolve().parent.parent
WALK = json.loads((ROOT / "tests" / "fixtures" / "walks" / "kei_p10_approved.json").read_text(encoding="utf-8"))


def _write(root, name, shot):
    d = root / f"out_{name}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "shot.json").write_text(json.dumps(shot), encoding="utf-8")


def _walk(**kw):
    return {**WALK, "loop": False, **kw}


def test_a_copy_of_the_last_pass_is_not_a_pass(tmp_path):
    _write(tmp_path, "p1", _walk())
    _write(tmp_path, "p2", _walk())
    misses = refinement_misses(tmp_path)
    assert any("is the same motion as out_p1" in m for m in misses)
    rows = json.loads((tmp_path / "out_p2" / "refinement.json").read_text())["passes"]
    assert rows[-1]["max_mm"] == 0 and rows[-1]["from"] == "p1"


def test_a_long_pass_keyed_on_every_frame_is_sampled(tmp_path):
    keys = [{"f": f, "root": [0, 0.95 + 0.01 * (f % 3), 0.02 * f]} for f in range(121)]
    _write(tmp_path, "p1", _walk(frames=120, keys=keys))
    assert any("sampled, not animated" in m for m in refinement_misses(tmp_path))


def test_the_approved_walk_cycle_is_not_called_sampled(tmp_path):
    _write(tmp_path, "p1", _walk())
    assert not any("sampled" in m for m in refinement_misses(tmp_path))


def test_a_real_refinement_passes_and_is_measured(tmp_path):
    _write(tmp_path, "p1", _walk())
    moved = [dict(k, root=[k.get("root", [0, 0.95, 0])[0], k.get("root", [0, 0.95, 0])[1] - 0.02,
                          k.get("root", [0, 0.95, 0])[2]]) for k in WALK["keys"]]
    _write(tmp_path, "p2", _walk(keys=moved))
    assert refinement_misses(tmp_path) == []
    row = measure(tmp_path)[-1]
    assert row["mean_mm"] > 5 and row["frames_changed"] > 0
