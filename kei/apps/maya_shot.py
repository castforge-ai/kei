"""A shot that Kei animates in Maya, in the background (mayapy, no window). The conductor and its twelve stages do not
change; this module changes where the keys live and where the joints for the checks come from.

The shot folder holds:
  maya/scene.ma           the shot's base scene: Kei's character with its control rig, or a copy of the user's scene
                          (the user's own file is never written)
  rig/maya_controls.json  the control map of a Kei character (kei.apps.maya_controls)
  rig/maya_rig.json       what read_rig found: joints, controls, keyable channels, limits, what each control moves
  out_<pass>/shot.json    the pass's keys, written by the animator: Kei's own channels ("rig": "v4", turned into
                          control values here) or the rig's own controls ("rig": "maya", keys {"f", "tangent",
                          "<control>.<channel>": value})
  out_<pass>/scene.ma     the pass's scene, keyed (each pass keeps its own)
  out_<pass>/joints.json  the joints Maya gives back on every frame, in Kei's world and names ("source": "maya");
                          kei check measures these
  out_<pass>/maya_report.json   the Maya version, and each pose a limit clipped (asked versus reached)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from kei.apps.maya import MayaError, find_mayapy, run_job
from kei.apps.maya_controls import control_rig_job, joints_from_samples, shot_keys
from kei.apps.maya_scene import character_job
from kei.characters import DEFAULT as DEFAULT_CHARACTER
from kei.characters import shot_character
from kei.rig import ALL_BONES
from kei.sample import ShotError, check_shot, read_json

TANGENTS = ("step", "linear", "spline", "flat")


def scene_path(shot_dir: Path) -> Path:
    return Path(shot_dir) / "maya" / "scene.ma"


def is_maya_shot(shot_dir: Path) -> bool:
    return scene_path(shot_dir).is_file() or (Path(shot_dir) / "maya" / "target.json").is_file()


def _p(path: Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/")


def _write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return path


def setup_shot(shot_dir: Path, character: str | None = None, scene: Path | None = None, fps: float = 24,
               mayapy: Path | None = None) -> dict:
    """Make the shot's base scene: Kei's character with its control rig in a new centimetre scene, or a copy of the
    user's scene. The character is the one named, else the shot's (PLAN.md's Character line), else Kei; an imported
    one (kei import) is built from its own files, its texture written to maya/textures. Writes maya/scene.ma, rig/maya_rig.json and, for a Kei character, rig/maya_controls.json."""
    shot_dir = Path(shot_dir)
    dst = scene_path(shot_dir)
    dst.parent.mkdir(parents=True, exist_ok=True)
    mayapy = mayapy or find_mayapy()[0]
    if scene is not None:
        shutil.copyfile(scene, dst)
        res = run_job(mayapy, {"scene": _p(dst), "calls": [{"tool": "read_rig", "inputs": {}}]})
        _write(shot_dir / "rig" / "maya_rig.json", res["results"][0])
        return {"maya_version": res["maya_version"], "scene": dst, "character": None}
    name = shot_character(shot_dir, {"character": character} if character else None, DEFAULT_CHARACTER)
    job = character_job(name, texture_dir=dst.parent / "textures")
    calls = [{"tool": "set_time", "inputs": {"start": 0, "end": 24, "fps": fps}},
             {"tool": "load_character", "inputs": {"job": job}},
             {"tool": "build_control_rig", "inputs": {"job": control_rig_job(name)}},
             {"tool": "read_rig", "inputs": {"namespace": name}}]
    res = run_job(mayapy, {"units": "cm", "calls": calls, "save": _p(dst)})
    _write(shot_dir / "rig" / "maya_controls.json", res["results"][2])
    _write(shot_dir / "rig" / "maya_rig.json", res["results"][3])
    return {"maya_version": res["maya_version"], "scene": dst, "character": name}


def controls_map(shot_dir: Path) -> dict | None:
    p = Path(shot_dir) / "rig" / "maya_controls.json"
    return read_json(p, "control map") if p.is_file() else None


def keys_for(shot: dict, shot_dir: Path, mode: str) -> list[dict]:
    """The set_keys list for a pass: Kei's channels through the control map, or the rig's own controls as written."""
    if shot.get("rig") == "maya":
        out = []
        for i, k in enumerate(shot.get("keys") or []):
            if not isinstance(k, dict) or not isinstance(k.get("f"), (int, float)):
                raise ShotError(f'key {i + 1} needs a frame "f"')
            tangent = "step" if mode == "step" else k.get("tangent", "spline")
            if tangent not in TANGENTS:
                raise ShotError(f"key f {k['f']}: tangent is one of {', '.join(TANGENTS)}")
            chans = {c: v for c, v in k.items() if c not in ("f", "tangent", "name", "note", "function", "kind")}
            out.append({"f": k["f"], "tangent": tangent, "channels": chans})
        return out
    check_shot(shot)
    rig = controls_map(shot_dir)
    if rig is None:
        raise ShotError("a Kei-rig shot in Maya needs rig/maya_controls.json: set the shot up on a Kei character "
                        "(kei maya setup <shot> --character <name>), or key the rig's own controls (\"rig\": \"maya\")")
    return shot_keys(shot, rig, mode)


def feedback_layer(pass_name: str) -> str:
    """The animation layer Kei makes for the animator's corrections to a pass (kei maya feedback reads it)."""
    return f"feedback_{pass_name}"


def keyed_controls(keys: list[dict]) -> list[str]:
    """The controls a pass keys, each once: they go on the feedback layer, so the animator's key lands there."""
    return sorted({plug.rsplit(".", 1)[0] for k in keys for plug in k["channels"]})


def rig_controls(shot_dir: Path, keys: list[dict]) -> list[str]:
    """Every control of the shot's rig (rig/maya_rig.json), with the controls the keys name: the animator's
    corrections layer and the controls display layer hold all of them, keyed this pass or not."""
    p = Path(shot_dir) / "rig" / "maya_rig.json"
    known = [c["name"] for c in (read_json(p, "rig").get("controls") or [])] if p.is_file() else []
    return sorted(set(known) | set(keyed_controls(keys)))


def _frames_of(shot_dir: Path, pass_name: str) -> int:
    shot = read_json(Path(shot_dir) / f"out_{pass_name}" / "shot.json", "shot")
    return int(shot.get("frames") or max(k["f"] for k in shot["keys"]))


def timeline(shot: dict, frames: int) -> dict:
    """The set_time inputs that show a pass in Maya's time slider: the shot's frame rate, frames 0 to the end. A loop
    stops one frame short (frame <frames> repeats frame 0), so Maya's playback cycles without a doubled frame."""
    end = frames - 1 if shot.get("loop") and frames > 1 else frames
    return {"start": 0, "end": end, "fps": shot.get("fps") or 24}


def view_videos(views: dict, fps: float, folder: Path) -> dict:
    """With ffmpeg, a playback of each view's playblast frames ({view: {"folder", "frames"}}), the views side by side
    in folder/views.mp4, and the side by side played ten times. Without ffmpeg, no video and no error."""
    from kei.render import LOOPS, _mp4, _repeat
    videos = {}
    for v, info in views.items():
        d = Path(info["folder"])
        mp4 = d.parent / f"{d.name}.mp4"
        if _mp4(d, fps, mp4, info["frames"]):
            videos[v] = mp4
    side = None
    if len(videos) > 1 and shutil.which("ffmpeg"):
        import subprocess
        side = Path(folder) / "views.mp4"
        ins = []
        for p in videos.values():
            ins += ["-i", str(p)]
        cmd = [shutil.which("ffmpeg"), "-y", "-loglevel", "error", *ins, "-filter_complex",
               f"hstack=inputs={len(videos)}", "-pix_fmt", "yuv420p", str(side)]
        if subprocess.run(cmd, capture_output=True).returncode != 0:
            side = None
    loops = _repeat(side, LOOPS, Path(folder) / f"views_x{LOOPS}.mp4") if side else None
    return {"videos": videos, "side_by_side": side, "loops": loops}


def render_pass(shot_dir: Path, pass_name: str, views: list[str] | None = None, width: int = 640, height: int = 360,
                mayapy: Path | None = None) -> dict:
    """Maya playblasts of a keyed pass (out_<pass>/scene.ma, run on that file in the background): one folder of
    frames per view in out_<pass>/maya_views/, and with ffmpeg a playback per view, the views side by side, and the
    side by side played ten times. The pass records the renderer in maya_report.json."""
    shot_dir = Path(shot_dir)
    out = shot_dir / f"out_{pass_name}"
    scene = out / "scene.ma"
    if not scene.is_file():
        raise ShotError(f"no {scene}: key the pass in Maya first (kei maya key {shot_dir} {pass_name})")
    n = _frames_of(shot_dir, pass_name)
    fps = read_json(out / "shot.json", "shot").get("fps") or 24
    folder = out / "maya_views"
    res = run_job(mayapy or find_mayapy()[0], {"scene": _p(scene), "calls": [{"tool": "playblast", "inputs": {
        "folder": _p(folder), "start": 0, "end": n, "width": width, "height": height,
        **({"views": views} if views else {})}}]})
    pb = res["results"][0]
    made = view_videos(pb["views"], fps, folder)
    rep_path = out / "maya_report.json"
    rep = read_json(rep_path, "report") if rep_path.is_file() else {}
    rep["views"] = {"renderer": pb["renderer"], "maya_version": res["maya_version"],
                    "frames": {v: i["frames"] for v, i in pb["views"].items()}}
    _write(rep_path, rep)
    return {"folder": folder, **made, "renderer": pb["renderer"],
            "frames": {v: i["frames"] for v, i in pb["views"].items()}}


def export_pass(shot_dir: Path, pass_name: str, path: Path, mayapy: Path | None = None) -> dict:
    """FBX of a keyed pass from Maya: the controls baked onto the joints, the control rig removed, run on the pass's
    scene in the background and never saved over it."""
    shot_dir = Path(shot_dir)
    scene = shot_dir / f"out_{pass_name}" / "scene.ma"
    if not scene.is_file():
        raise ShotError(f"no {scene}: key the pass in Maya first (kei maya key {shot_dir} {pass_name})")
    rig = controls_map(shot_dir)
    res = run_job(mayapy or find_mayapy()[0], {"scene": _p(scene), "calls": [{"tool": "export_fbx", "inputs": {
        "path": _p(path), "start": 0, "end": _frames_of(shot_dir, pass_name),
        **({"namespace": rig["namespace"]} if rig else {})}}]})
    return res["results"][0]


def key_pass(shot_dir: Path, pass_name: str, mode: str | None = None, mayapy: Path | None = None) -> dict:
    """Key out_<pass>/shot.json on the shot's scene in the background, save out_<pass>/scene.ma, and read the joints
    back into out_<pass>/joints.json (Kei's world and names) with out_<pass>/maya_report.json."""
    shot_dir = Path(shot_dir)
    out = shot_dir / f"out_{pass_name}"
    shot = read_json(out / "shot.json", "shot")
    mode = mode or ("step" if pass_name == "blocking" else "spline")
    keys = keys_for(shot, shot_dir, mode)
    rig = controls_map(shot_dir)
    frames, fps = int(shot.get("frames") or max(k["f"] for k in keys)), shot.get("fps") or 24
    character = rig["character"] if rig else None
    joints = [f"{rig['namespace']}:{b}" for b in ALL_BONES] if rig else []
    from kei.apps.maya_session import load_target
    target = load_target(shot_dir) or {"kind": "background"}
    if target["kind"] == "open":
        return _key_open(shot_dir, pass_name, out, keys, frames, mode, rig, joints, target, mayapy,
                         timeline(shot, frames))
    calls = [{"tool": "set_time", "inputs": timeline(shot, frames)},
             {"tool": "set_keys", "inputs": {"keys": keys, "feedback": feedback_layer(pass_name),
                                             "feedback_controls": rig_controls(shot_dir, keys),
                                             "controls_layer": rig_controls(shot_dir, keys)}}]
    if joints:
        calls.append({"tool": "read_samples", "inputs": {"joints": joints, "start": 0, "end": frames}})
    res = run_job(mayapy or find_mayapy()[0], {"scene": _p(scene_path(shot_dir)), "calls": calls,
                                               "save": _p(out / "scene.ma")})
    report = {"maya_version": res["maya_version"], "mode": mode, "keys": res["results"][1]["keys"],
              "clipped": res["results"][1]["clipped"], "feedback": res["results"][1].get("feedback"),
              "controls_layer": res["results"][1].get("controls_layer")}
    _write(out / "maya_report.json", report)
    if joints:
        got = joints_from_samples(res["results"][2], character)
        _write(out / "joints.json", {"source": "maya", "fps": fps, "mode": mode, "character": character,
                                     "frames": [{"f": fr["f"], "joints": {n: [round(c, 6) for c in p]
                                                                          for n, p in fr["joints"].items()}}
                                                for fr in got]})
    return report


def _key_open(shot_dir: Path, pass_name: str, out: Path, keys: list, frames: int, mode: str, rig: dict | None,
              joints: list, target: dict, mayapy: Path | None, time: dict | None = None) -> dict:
    """Key a pass in the user's open Maya: the time slider set to the pass (its frame rate and range, so the user
    sees what Kei shows), the keys on the layer kei_<pass> (one undo removes the pass), then a copy of the open scene
    (unsaved changes included) for the heavy work in the background. The user's file is never saved.
    A host that stops answering stops the shot with paused_machine."""
    from kei.apps.maya_session import HostError, call_host, locate
    from kei.apps.maya_stage import stop_for_machine
    session = locate(target)
    try:
        if session is None:
            raise HostError(f"the open Maya (session {target.get('pid')}) is closed or its Kei host does not answer")
        layer = f"kei_{pass_name}"
        what = rig["namespace"] if rig else "the rig's controls"
        line = f"Kei keys {what} in the open Maya (session {session.pid}), frames 0 to {frames}, on layer {layer}"
        log = Path(shot_dir) / "maya" / "session.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        if time:
            call_host(session.port, session.token, "set_time", time, timeout=60)
        res = call_host(session.port, session.token, "set_keys", {
            "keys": keys, "layer": layer, "feedback": feedback_layer(pass_name),
            "feedback_controls": rig_controls(shot_dir, keys), "controls_layer": rig_controls(shot_dir, keys)},
            timeout=600)
        call_host(session.port, session.token, "save_temp_copy", {"path": _p(out / "scene.ma")}, timeout=600)
    except HostError as e:
        stop_for_machine(shot_dir, f"Maya stopped answering while keying {pass_name}: {e}")
        raise MayaError(str(e)) from e
    report = {"target": "open", "session": session.pid, "layer": layer, "said": line, "mode": mode,
              "keys": res["keys"], "clipped": res["clipped"], "muted": res.get("muted", []),
              "feedback": res.get("feedback"), "controls_layer": res.get("controls_layer")}
    if joints:
        got = run_job(mayapy or find_mayapy()[0], {"scene": _p(out / "scene.ma"), "calls": [
            {"tool": "read_samples", "inputs": {"joints": joints, "start": 0, "end": frames}}]})
        report["maya_version"] = got["maya_version"]
        fr = joints_from_samples(got["results"][0], rig["character"])
        _write(out / "joints.json", {"source": "maya", "fps": read_json(out / "shot.json", "shot").get("fps") or 24,
                                     "mode": mode, "character": rig["character"],
                                     "frames": [{"f": f["f"], "joints": {n: [round(c, 6) for c in p]
                                                                         for n, p in f["joints"].items()}}
                                                for f in fr]})
    _write(out / "maya_report.json", report)
    return report
