"""kei demo: Kei's tools on a finished walk, offline, with no agent and no subscription.

  kei demo [folder]    (default: ./kei-demo)

It copies an approved walk cycle into <folder>/out_p1/shot.json and runs, in order: the render (a still per key, a key
sheet and a playback), kei check (the body checks and the twelve principles), kei poses (the pose records and sheet),
kei trails (the hands' and head's paths) and, with ffmpeg, the clean four-view video. A first look at what every agent
shot produces, in about a minute. A real shot, with agents, takes 30 to 90 minutes or more.
"""
from __future__ import annotations

import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_demo(folder: Path, size: int = 180) -> list[tuple[str, Path]]:
    from kei.body_check import check_pass
    from kei.pose_record import write_records
    from kei.render import render_post, render_shot
    from kei.trails import draw_trails
    folder = Path(folder)
    out = folder / "out_p1"
    out.mkdir(parents=True, exist_ok=True)
    src = out / "shot.json"
    shutil.copyfile(HERE / "walk.json", src)
    made = []
    r = render_shot(src, out, "spline", size=size, character="kei")
    made += [("playback", r["playback"]), ("key sheet", r["keys"])]
    made.append(("body checks", check_pass(folder, "p1", "kei", "spline")))
    made.append(("pose records", write_records(folder, "p1", "kei", sheet=True).parent / "pose_sheet.png"))
    made.append(("trails", draw_trails(folder, ["p1"], ["hand_l_tip", "hand_r_tip", "head"], None, "kei")))
    if shutil.which("ffmpeg"):
        post = render_post(src, out / "post", "spline", "kei", height=2 * size, name="kei_walk")
        if post.get("video"):
            made.append(("four-view video", post["video"]))
    return made
