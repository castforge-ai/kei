"""A shot that Kei animates in Blender, in the background (blender -b, no window). As with Maya, the conductor and its
twelve stages do not change; this module changes where the keys live and where the joints for the checks come from.

The shot folder holds:
  blender/scene.blend       the shot's base scene: Kei's character from Kei's own glTF (its skeleton with Kei's bone
                            names, the skinned mesh) and the leg IK an animator works with
  blender/character.glb     that glTF, as Kei wrote it
  rig/blender_rig.json      what setup made: the bones, each pole's angle and how far the knee sat from Kei's at rest
  out_<pass>/shot.json      the pass's keys, Kei's own channels ("rig": "v4"), written by the animator
  out_<pass>/scene.blend    the pass's scene, keyed: whole poses on Kei's key frames, the interpolation the pass asks
                            (blocking steps, spline passes ease), so the animator can open it and work on
  out_<pass>/joints.json    the joints Blender plays on every frame, in Kei's world and names ("source": "blender");
                            kei check measures these, so a foot that slides between keys in Blender is a flag
  out_<pass>/blender_report.json   the Blender version, the keys, and the channels Blender does not play

Blender plays Kei's key poses exactly; between keys it is Blender's own interpolation, with the feet on IK. Kei's
length scales (sq, legS, armS, neckS, bladeS) are not built into the Blender rig: a pass that uses them is keyed
without them and the report names them.
"""
from __future__ import annotations

import json
from pathlib import Path

from kei.apps.blender import BlenderError, find_blender, run_job
from kei.characters import DEFAULT as DEFAULT_CHARACTER
from kei.characters import load_character, on_character, rest_pose, shot_character
from kei.rig import ALL_BONES, BONES, com, skeleton
from kei.sample import ShotError, bake, bake_continuous, check_shot, normalize_keys, read_json

INTERPOLATION = {"step": "CONSTANT", "linear": "LINEAR", "spline": "BEZIER"}
SCALES = ("sq", "legSL", "legSR", "armSL", "armSR", "neckS", "bladeS")
POLE_M = 0.4
VIEWS = ("front", "three_quarter", "side", "back")
C = ((-1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0))     # Kei world -> Blender world (kei_blender.C)


def blender_dir(shot_dir: Path) -> Path:
    return Path(shot_dir) / "blender"


def scene_path(shot_dir: Path) -> Path:
    return blender_dir(shot_dir) / "scene.blend"


def is_blender_shot(shot_dir: Path) -> bool:
    return blender_dir(shot_dir).is_dir()


def _p(path: Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/")


def _frames(B: dict) -> dict:
    return {n: {"head": list(B[n].head), "frame": [list(a) for a in B[n].frame]} for n in ALL_BONES}


def setup_shot(shot_dir: Path, character: str | None = None, fps: float = 24, blender: Path | None = None) -> dict:
    """Make blender/scene.blend: Kei's glTF of the character imported, with leg IK. The character is the one named,
    else the shot's (PLAN.md's Character line), else Kei."""
    from kei.export_gltf import export_glb
    shot_dir = Path(shot_dir)
    name = character or shot_character(shot_dir, None, DEFAULT_CHARACTER)
    ch = load_character(name)
    folder = blender_dir(shot_dir)
    folder.mkdir(parents=True, exist_ok=True)
    glb = export_glb(ch, folder / "character.glb", 1.0)
    blender = blender or find_blender()[0]
    from kei.characters import mesh
    r = run_job(blender, {"tool": "setup", "glb": _p(glb), "out": _p(scene_path(shot_dir)), "fps": fps,
                          "skinning": mesh.SKINNING})
    worst = max(p["knee_error_m"] for p in r["poles"].values())
    rig = {"character": ch.name, "blender": r["blender"], "armature": r["armature"], "bones": r["bones"],
           "poles": r["poles"], "ik": {"legs": ["ik_foot_l", "ik_foot_r", "pole_knee_l", "pole_knee_r"]}}
    (shot_dir / "rig").mkdir(parents=True, exist_ok=True)
    (shot_dir / "rig" / "blender_rig.json").write_text(json.dumps(rig, indent=1), encoding="utf-8")
    if worst > 0.005:
        raise BlenderError(f"the leg IK in Blender puts a knee {worst * 100:.1f} cm from Kei's at rest: the pole "
                           "angle could not be found; see rig/blender_rig.json")
    return rig


def pole(B: dict, side: str) -> list:
    """Where a knee's pole control goes: POLE_M in front of the knee, along the leg's bend (away from the line hip to
    ankle), or straight ahead of the pelvis when the leg is straight."""
    hip, knee, ankle = B[f"thigh_{side}"].head, B[f"calf_{side}"].head, B[f"foot_{side}"].head
    line = [ankle[i] - hip[i] for i in range(3)]
    ll = sum(c * c for c in line) or 1.0
    t = sum((knee[i] - hip[i]) * line[i] for i in range(3)) / ll
    off = [knee[i] - (hip[i] + t * line[i]) for i in range(3)]
    n = sum(c * c for c in off) ** 0.5
    if n < 1e-4:                                     # straight: the pelvis's forward (its frame's Z)
        off, n = list(B["pelvis"].frame[2]), 1.0
        fwd = B["pelvis"].frame[2]
        if fwd[2] < 0:
            off = [-c for c in off]
    return [knee[i] + POLE_M * off[i] / n for i in range(3)]


def key_job(shot: dict, ch, mode: str, rest_B: dict | None = None) -> dict:
    """The key job for a pass: Kei's whole pose (every bone's head and frame) on each key frame, the knee poles, and
    the interpolation of the pass. Kei's own channels only."""
    shot = on_character(shot, ch)
    # a loop keys its last frame one cycle of travel on from the first (bake_continuous), so Blender plays the walk
    # forward into the next cycle instead of sliding back to the start
    frames = bake_continuous(shot) if shot.get("loop") else bake(shot, mode)
    by_f = {fr["f"]: fr for fr in frames}
    keyed = sorted({k["f"] for k in normalize_keys(shot) if 0 <= k["f"] <= shot["frames"]} | {0, shot["frames"]})
    keys = []
    for f in keyed:
        B = skeleton(by_f[f]["pose"], ch.proportions)
        keys.append({"f": f, "bones": _frames(B), "poles": {s: pole(B, s) for s in "lr"}})
    rest_B = rest_B or skeleton(rest_pose(ch), ch.proportions)
    return {"tool": "key", "fps": shot.get("fps") or 24, "frames": shot["frames"],
            "interpolation": INTERPOLATION[mode], "rest": _frames(rest_B), "keys": keys,
            "sample": sorted(set(BONES) | {"clavicle_l"})}


def _mul(m, v):
    return tuple(sum(m[r][c] * v[c] for c in range(3)) for r in range(3))


def _t(m):
    return tuple(tuple(m[c][r] for c in range(3)) for r in range(3))


def _mm(a, b):
    return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(3)) for c in range(3)) for r in range(3))


def joints_from_blender(samples: list, ch) -> list[dict]:
    """Blender's sampled frames as Kei's joints per frame (the names kei.rig.solve gives: tips, heels, sternum, nose
    and the centre of mass included), in Kei's world."""
    from kei.apps.maya_controls import extra_offsets
    offs = extra_offsets(ch.name)
    rest = skeleton(rest_pose(ch), ch.proportions)
    Ct = _t(C)
    out = []
    for fr in samples:
        j = {n: _mul(Ct, fr["pos"][n]) for n in BONES}
        for point, (bone, o) in offs.items():
            turn = _mm(Ct, _mm(fr["turn"][bone], C))          # the bone's turn from rest, in Kei's world
            F = [_mul(turn, rest[bone].frame[a]) for a in range(3)]
            head = j[bone] if bone in j else _mul(Ct, fr["pos"][bone])
            j[point] = tuple(head[i] + sum(o[a] * F[a][i] for a in range(3)) for i in range(3))
        j["com"] = com(j)
        out.append({"f": fr["f"], "joints": {n: [round(c, 5) for c in p] for n, p in j.items()}})
    return out


def key_pass(shot_dir: Path, pass_name: str, mode: str | None = None, blender: Path | None = None) -> dict:
    """Key out_<pass>/shot.json into the shot's Blender scene: out_<pass>/scene.blend, joints.json (what Blender
    plays) and blender_report.json."""
    shot_dir = Path(shot_dir)
    out = shot_dir / f"out_{pass_name}"
    src = out / "shot.json"
    if not src.is_file():
        raise ShotError(f"no {src}: write the pass's keys there first")
    if not scene_path(shot_dir).is_file():
        raise ShotError(f"{shot_dir} has no Blender scene yet: kei blender setup {shot_dir}")
    shot = read_json(src, "shot")
    check_shot(shot)
    rig = json.loads((shot_dir / "rig" / "blender_rig.json").read_text(encoding="utf-8"))
    ch = load_character(shot.get("character") or rig["character"])
    if ch.name != rig["character"]:
        raise ShotError(f"the pass is on {ch.name}, the Blender scene holds {rig['character']}: set the shot up again "
                        f"with kei blender setup {shot_dir} --character {ch.name}")
    mode = mode or ("step" if pass_name == "blocking" else "spline")
    job = key_job(shot, ch, mode)
    job.update(blend=_p(scene_path(shot_dir)), out=_p(out / "scene.blend"),
               action=f"{shot_dir.resolve().name}_{pass_name}")
    r = run_job(blender or find_blender()[0], job)
    unplayed = sorted({c for k in normalize_keys(shot) for c in SCALES if c in k and k[c] not in (1, 1.0, None)})
    frames = joints_from_blender(r["frames"], ch)
    (out / "joints.json").write_text(json.dumps({"fps": shot.get("fps") or 24, "mode": mode, "character": ch.name,
                                                 "source": "blender", "frames": frames}), encoding="utf-8")
    report = {"blender": r["blender"], "keys": r["keyed"], "frames": len(frames), "mode": mode,
              "interpolation": INTERPOLATION[mode], "not_played": unplayed}
    (out / "blender_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def render_pass(shot_dir: Path, pass_name: str, views: list | None = None, width: int = 640, height: int = 360,
                blender: Path | None = None) -> dict:
    """Render the pass's Blender scene from each view into out_<pass>/blender_render/<view>.mp4 (Blender's Workbench
    engine, PNG frames turned into a video by ffmpeg)."""
    import shutil
    import subprocess
    shot_dir = Path(shot_dir)
    out = shot_dir / f"out_{pass_name}"
    blend = out / "scene.blend"
    if not blend.is_file():
        raise ShotError(f"no {blend}: key the pass first (kei blender key {shot_dir} {pass_name})")
    fps = (read_json(out / "shot.json", "shot").get("fps") or 24) if (out / "shot.json").is_file() else 24
    dst = out / "blender_render"
    job = {"tool": "render", "blend": _p(blend), "out": _p(dst), "views": list(views or VIEWS), "width": width,
           "height": height}
    if (out / "joints.json").is_file():       # aim at the middle of the travel, far enough to hold all of it
        pel = [fr["joints"]["pelvis"] for fr in read_json(out / "joints.json", "joints")["frames"]]
        mid = [sum(p[i] for p in pel) / len(pel) for i in range(3)]
        reach = max(max(abs(p[i] - mid[i]) for p in pel) for i in (0, 2))
        job["target"] = list(_mul(C, (mid[0], 0.9, mid[2])))
        job["distance_m"] = 6.0 + 2.5 * reach
    r = run_job(blender or find_blender()[0], job)
    ffmpeg = shutil.which("ffmpeg")
    videos = {}
    for view, folder in r["views"].items():
        if ffmpeg is None:
            videos[view] = folder
            continue
        mp4 = dst / f"{view}.mp4"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps), "-start_number", "0",
                        "-i", str(Path(folder) / "f_%04d.png"), "-pix_fmt", "yuv420p", "-vf",
                        "pad=ceil(iw/2)*2:ceil(ih/2)*2", str(mp4)], check=True)
        videos[view] = str(mp4)
    return {"views": videos, "frames": r["frames"]}
