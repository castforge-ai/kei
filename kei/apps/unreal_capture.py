"""Drawing the real mesh from the editor: a test of one frame (kei unreal capture-test), before it is part of a review.

capture_test(client, shot_dir, pass_name, frame=None, size=(640, 720)) -> dict
  Opens the pass's sequence, sets the time to a frame (the middle key frame unless one is given), waits one editor tick,
  and has the editor draw the character from the front, the side and the three quarter view into
  out_<pass>/mesh_test/ (kei_ue script capture_frame). Returns {"files", "nonblack", "found", "errors", "frame",
  "looks_drawn"}; looks_drawn is True when every view shows more than MIN_SHOWN of the picture as not background. A
  failure is returned in words, never hidden: the review does not use these pictures until a person has seen them.
"""
from __future__ import annotations

from pathlib import Path

from kei.apps.unreal import Claireon, run_script, tick
from kei.apps.unreal_rig import sequences
from kei.sample import ShotError, read_json

VIEWS = [{"name": "front", "yaw": 180.0}, {"name": "side", "yaw": 90.0}, {"name": "three_quarter", "yaw": 135.0}]
MIN_SHOWN = 0.02      # of the picture: a view with less than this is empty or black


def middle_key_frame(shot: dict) -> int:
    frames = sorted({int(k["f"]) for k in shot.get("keys") or [] if isinstance(k, dict) and "f" in k})
    return frames[len(frames) // 2] if frames else int(shot.get("frames") or 0) // 2


def capture_test(client: Claireon, shot_dir: Path, pass_name: str, frame: int | None = None,
                 size: tuple[int, int] = (640, 720)) -> dict:
    shot_dir = Path(shot_dir)
    made = sequences(shot_dir).get(pass_name) or []
    if not made:
        raise ShotError(f"no Unreal sequence for {pass_name} in {shot_dir}: key the pass first (kei unreal key)")
    seq = made[-1]
    shot = read_json(shot_dir / f"out_{pass_name}" / "shot.json", "shot")
    frame = middle_key_frame(shot) if frame is None else int(frame)
    out_dir = shot_dir / f"out_{pass_name}" / "mesh_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_script(client, "capture_frame.py", {"stage": "pose", "sequence": seq, "frame": frame})
    tick()          # the pose appears one editor tick after the time is set
    tick()
    got = run_script(client, "capture_frame.py", {"stage": "shoot", "sequence": seq, "frame": frame, "views": VIEWS,
                                                  "out_dir": str(out_dir), "size": list(size)})
    shown = got.get("nonblack") or {}
    return {"frame": frame, "sequence": seq, "files": got.get("files", []), "nonblack": shown,
            "found": got.get("found", ""), "errors": got.get("errors", []),
            "looks_drawn": bool(shown) and all(v > MIN_SHOWN for v in shown.values())}
