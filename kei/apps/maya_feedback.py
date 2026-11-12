"""The animator's corrections, posed on a Maya animation layer named feedback (or feedback_<anything>), turned into the
author's note for the shot. Standard library only on Kei's side; the reading runs in Maya (kei_tools
read_feedback_layers), on a copy of the scene.

describe(offsets, rig) -> lines
  The corrections in Kei's channels where they map (knee bend, head roll, root height, foot target), sizes in degrees
  and centimetres, with the frames they touch; any other control is listed by its name.
collect(shot, scene) -> what the feedback layers hold, read in the background on a copy of the scene
render(collected, folder) -> Kei's pass before and after the corrections, four views, on that copy
save_pose(shot, n, collected, lines, renders) -> <shot>/feedback/<n>/pose.json (control, frame, value, offset)
record_note(...) -> the author's note through the kei note path, with the pose beside it

Rules this module keeps:
  - The animator's layer is never changed, muted, baked or deleted in the user's scene: Kei reads a copy.
  - The reason is one sentence from the animator, recorded verbatim. Kei asks for it and never writes it.
  - The pose alone is a note for this shot. It becomes a rule only when the author says "every shot", the same as
    notes (kei note --every-shot); the pose itself is never put in a lesson.
  - Nothing leaves the machine; the pose stays in the shot folder.
"""
from __future__ import annotations

import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from kei.apps.maya import find_mayapy, run_job
from kei.apps.maya_controls import POLE_M
from kei.apps.maya_session import HostError, call_host, load_target, locate
from kei.apps.maya_shot import view_videos
from kei.lessons import SCOPES      # this shot or every shot: the note model of kei note
from kei.sample import ShotError, read_json

RUN_ENV = "KEI_RUN"     # set by kei run for its seats: a feedback read inside a run asks the author through the shot
FOLDER = "feedback"     # <shot>/feedback/<n>/: pose.json, note.json, before/, after/
TAG = "[feedback:{n}]"  # names the feedback a question in QUESTIONS.md asks about

EPS = 1e-6
LEFT, RIGHT = "the character's left", "the character's right"


def _short(control: str) -> str:
    return control.split("|")[-1].rpartition(":")[2]


def _num(x: float, whole: bool) -> str:
    x = abs(x)
    return f"{x:.0f}" if whole and x >= 1 else f"{x:.1f}"


def _frames(fs: list[int], offs: list[float], start: int, end: int) -> str:
    """Where a correction acts: on every frame, at one frame, or over a span with the frame it is largest."""
    if fs == list(range(start, end + 1)) and max(offs) - min(offs) < 1e-3:
        return "on every frame"
    if len(fs) == 1:
        return f"at f{fs[0]}"
    peak = fs[max(range(len(fs)), key=lambda i: abs(offs[i]))]
    span = f"f{fs[0]} to f{fs[-1]}"
    return span if max(offs) - min(offs) < 1e-3 else f"{span}, most at f{peak}"


def _channel(ctl: str, attr: str, off: float, cm: float) -> tuple | None:
    """The correction in Kei's words as (what, size, which way, pole move in cm or None), or None when Kei has no
    words for that control."""
    side = ctl[0] if ctl[:2] in ("l_", "r_") else None
    if ctl.endswith("_leg_pv_ctl") and side:
        if attr == "translateX":        # Maya's +x is the character's left: outward for the left knee
            out = cm if side == "l" else -cm
            deg = math.degrees(math.atan2(abs(out), POLE_M * 100.0))
            return (f"knee_{side} bend turns", f"{_num(deg, True)} deg", "outward" if out > 0 else "inward", cm)
        word = {"translateY": ("up", "down"), "translateZ": ("forward", "back")}.get(attr)
        if word:
            return (f"knee_{side} pole moves", f"{_num(cm, False)} cm", word[0] if off > 0 else word[1], None)
    if ctl in ("c_body_ctl", "c_root_ctl") and attr == "translateY":
        return ("root height", f"{_num(cm, False)} cm", "higher" if off > 0 else "lower", None)
    if ctl.endswith("_foot_ik_ctl") and side and attr.startswith("translate"):
        a = attr[-1]
        if a == "Y":
            w = "higher" if off > 0 else "lower"
        elif a == "Z":
            w = "forward" if off > 0 else "back"
        else:
            w = "outward" if (off > 0) == (side == "l") else "inward"
        return (f"foot_{side} target", f"{_num(cm, False)} cm", w, None)
    for part, joint in (("calf", "knee"), ("lowerarm", "elbow")):
        if ctl == f"{side}_{part}_fk_ctl" and attr == "rotateX":
            return (f"{joint}_{side} bends", f"{_num(off, True)} deg", "more" if off > 0 else "less", None)
    if ctl == "c_head_fk_ctl":
        if attr == "rotateZ":
            return ("head rolls", f"{_num(off, True)} deg", f"toward {RIGHT if off > 0 else LEFT}", None)
        if attr == "rotateX":
            return ("head pitches", f"{_num(off, True)} deg", "down" if off > 0 else "up", None)
        if attr == "rotateY":
            return ("head turns", f"{_num(off, True)} deg", f"toward {LEFT if off > 0 else RIGHT}", None)
    return None


def _said(control: str, attr: str, off: float, f: float) -> tuple:
    """_channel's words, or the control's own name with a signed size in the scene's terms."""
    cm = off / f * 100.0
    said = _channel(_short(control), attr, off, cm)
    if said is not None:
        return said
    if attr.startswith("translate"):
        size = f"{cm:+.1f} cm"
    elif attr.startswith("rotate"):
        size = f"{off:+.1f} deg"
    else:
        size = f"{off:+.3g}"
    return (f"{_short(control) if ':' in control else control}.{attr}", size, "", None)


def _full(said: tuple) -> str:
    return " ".join(x for x in said[:3] if x)


def _pole(said: tuple, short: bool = False) -> str:
    if said[3] is None:
        return ""
    return f" ({_num(said[3], False)} cm)" if short else f" (the knee pole moves {_num(said[3], False)} cm)"


def _held_and_local(fs: list[int], offs: list[float], start: int, end: int):
    """A correction on every frame that holds one offset and changes it somewhere: the held offset and the frames
    and offsets of the change. None when the correction is only held, only local, or changes sign."""
    if fs != list(range(start, end + 1)) or max(offs) - min(offs) < 1e-3:
        return None
    held = min(offs, key=abs)
    if any(o * held <= 0 for o in offs):
        return None
    local = [(fr, o) for fr, o in zip(fs, offs) if abs(o - held) > 1e-3]
    return held, local


def describe(offsets: dict, rig: dict | None = None) -> list[str]:
    """One line per corrected channel of each feedback layer, in Kei's channels where they map, by control name where
    they do not. A held offset with a change on top says both: the held part on every frame, then the largest at its
    frame. offsets is what read_feedback_layers returned; rig (the control map, optional) gives the scene's unit when
    the offsets do not."""
    f = float(offsets.get("unit_per_m") or (rig or {}).get("unit_per_m") or 100.0)
    start, end = int(offsets.get("start", 0)), int(offsets.get("end", 0))
    layers = offsets.get("layers") or {}
    named = len(layers) > 1
    lines = []
    for layer, rows in layers.items():
        plugs: dict = {}
        for r in rows:
            if abs(r["offset"]) > EPS:
                plugs.setdefault((r["control"], r["attr"]), []).append(r)
        for (control, attr), rs in plugs.items():
            rs.sort(key=lambda r: r["frame"])
            fs, offs = [r["frame"] for r in rs], [r["offset"] for r in rs]
            peak = max(offs, key=abs)
            said = _said(control, attr, peak, f)
            both = _held_and_local(fs, offs, start, end)
            if both:
                held, local = both
                base = _said(control, attr, held, f)
                at = max(local, key=lambda x: abs(x[1]))[0]
                way = f" {said[2]}" if said[2] != base[2] else ""
                text = (f"{_full(base)} on every frame{_pole(base)}, and {said[1]}{way} at f{at}{_pole(said, True)}"
                        + (f" over f{local[0][0]} to f{local[-1][0]}" if len(local) > 1 else ""))
            else:
                text = f"{_full(said)} {_frames(fs, offs, start, end)}{_pole(said)}"
            if any(r.get("locked") for r in rs):
                text += " (locked on the rig: Kei cannot key it, so the next pass cannot match it)"
            held_by = next((r for r in rs if "reached" in r), None)
            if held_by:
                text += f" (a limit holds it: asked {held_by['asked']:.1f}, reached {held_by['reached']:.1f})"
            lines.append(f"{layer}: {text}" if named else text)
    return lines


class FeedbackError(ShotError):
    """Kei cannot take this feedback: no feedback layer, a layer on another rig, a shot with no keyed pass. It says
    what to do, in plain words."""


def maya_pass(shot: Path) -> str:
    """The pass the feedback corrects: the latest pass keyed in Maya (out_<pass>/scene.ma)."""
    from kei.characters import latest_pass
    last = latest_pass(shot)
    if last is None or not (last.parent / "scene.ma").is_file():
        raise FeedbackError(f"no pass keyed in Maya in {shot}: Kei compares feedback with a pass it keyed "
                            f"(kei maya key {shot} <pass>)")
    return last.parent.name[len("out_"):]


def _p(path: Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/")


def copy_path(shot: Path) -> Path:
    return Path(shot) / "maya" / "feedback_copy.ma"


def take_copy(shot: Path, pass_name: str, scene: Path | None = None) -> tuple[Path, str]:
    """A copy of the scene that holds the feedback layer, and where it came from: the open Maya the shot works in
    (its host exports the scene, unsaved changes included, and changes nothing), else the scene given, else the
    pass's own scene. The source file is only read."""
    shot = Path(shot)
    dst = copy_path(shot)
    dst.parent.mkdir(parents=True, exist_ok=True)
    target = load_target(shot) or {"kind": "background"}
    if scene is None and target["kind"] == "open":
        session = locate(target)
        if session is not None:
            try:
                call_host(session.port, session.token, "save_temp_copy", {"path": _p(dst)}, timeout=600)
            except HostError as e:
                raise FeedbackError(f"the open Maya did not give Kei a copy of its scene: {e}") from e
            return dst, f"the open Maya (session {session.pid})"
    src = Path(scene) if scene is not None else shot / f"out_{pass_name}" / "scene.ma"
    if not src.is_file():
        raise FeedbackError(f"no scene at {src}")
    shutil.copyfile(src, dst)
    return dst, str(src)


def _pass_frames(shot: Path, pass_name: str) -> tuple[int, float]:
    data = read_json(Path(shot) / f"out_{pass_name}" / "shot.json", "shot")
    n = int(data.get("frames") or max(k["f"] for k in data["keys"]))
    return n, float(data.get("fps") or 24)


def rig_namespace(shot: Path) -> str | None:
    """The namespace of the pass's Kei rig (rig/maya_controls.json), or None for a rig of the user's own."""
    p = Path(shot) / "rig" / "maya_controls.json"
    return read_json(p, "control map").get("namespace") if p.is_file() else None


def collect(shot: Path, scene: Path | None = None, mayapy: Path | None = None) -> dict:
    """Read the feedback layers on a copy, in the background. Returns the pass, the copy, where it came from, the rig
    and what read_feedback_layers found. A layer keyed on another rig is refused by name."""
    shot = Path(shot)
    pass_name = maya_pass(shot)
    copy, source = take_copy(shot, pass_name, scene)
    frames, fps = _pass_frames(shot, pass_name)
    rig = rig_namespace(shot)
    mayapy = mayapy or find_mayapy()[0]
    res = run_job(mayapy, {"scene": _p(copy), "calls": [{"tool": "read_feedback_layers", "inputs": {
        "rig": rig, "start": 0, "end": frames, "pass_name": pass_name}}]})
    found = res["results"][0]
    if found["other_rig"]:
        names = ", ".join(f"{o['control']}.{o['attr']} (layer {o['layer']})" for o in found["other_rig"])
        raise FeedbackError(f"the feedback is keyed on another rig than the pass's: {names}. Pass {pass_name} is "
                            f"keyed on rig {rig}: key the corrections on its controls, then run this again")
    return {"pass": pass_name, "copy": copy, "source": source, "rig": rig, "frames": frames, "fps": fps,
            "mayapy": mayapy, "found": found}


def has_feedback(found: dict) -> bool:
    return any(rows for rows in found["layers"].values())


def outside_lines(found: dict) -> list[str]:
    return [f"{o['control']}.{o['attr']} at f{o['frame']} (layer {o['layer']}) is outside the pass (frames "
            f"{found['start']} to {found['end']}): not wrapped into it, and not part of the note"
            for o in found.get("outside", [])]


def other_pass_lines(found: dict) -> list[str]:
    return [f"{o['layer']} belongs to pass {o['pass']}, not read" for o in found.get("other_pass", [])]


def next_number(shot: Path) -> int:
    """The next feedback number. A number that holds a note, or a question about one, is never used again."""
    used = [int(d.name) for d in (Path(shot) / FOLDER).glob("*") if d.name.isdigit()
            and ((d / "note.json").is_file() or (d / "question.json").is_file())]
    return max(used, default=0) + 1


def render(c: dict, folder: Path) -> dict:
    """Kei's pass (every feedback layer muted), then with the corrections on, four views each, on the copy."""
    calls = [{"tool": "set_feedback_mute", "inputs": {"mute": True, "pass_name": c["pass"]}},
             {"tool": "playblast", "inputs": {"folder": _p(folder / "before"), "start": 0, "end": c["frames"]}},
             {"tool": "set_feedback_mute", "inputs": {"mute": False, "pass_name": c["pass"]}},
             {"tool": "playblast", "inputs": {"folder": _p(folder / "after"), "start": 0, "end": c["frames"]}}]
    res = run_job(c["mayapy"], {"scene": _p(c["copy"]), "calls": calls})
    out = {}
    for name, pb in (("before", res["results"][1]), ("after", res["results"][3])):
        out[name] = {"views": pb["views"], **view_videos(pb["views"], c["fps"], folder / name)}
    return out


def targets(poses: list[dict]) -> list[dict]:
    """What the next pass must reach: each keyed frame of each correction (control, attr, frame, value). A locked
    channel is left out: Kei cannot key it."""
    return [{"control": r["control"], "attr": r["attr"], "frame": r["frame"], "value": r["value"]}
            for r in poses if r.get("key") and not r.get("locked")]


def _rel(shot: Path, p) -> str:
    try:
        return Path(p).resolve().relative_to(Path(shot).resolve()).as_posix()
    except ValueError:
        return str(p)


def save_pose(shot: Path, n: int, c: dict, lines: list[str], renders: dict | None) -> str:
    """<shot>/feedback/<n>/pose.json. Returns its path relative to the shot."""
    folder = Path(shot) / FOLDER / str(n)
    folder.mkdir(parents=True, exist_ok=True)
    found = c["found"]
    poses = [{"layer": layer, **r} for layer, rows in found["layers"].items() for r in rows]
    data = {"pass": c["pass"], "rig": c["rig"], "source": c["source"], "units": found["units"],
            "unit_per_m": found["unit_per_m"], "frames": [found["start"], found["end"]], "modes": found["modes"],
            "description": lines, "poses": poses, "targets": targets(poses), "outside": found.get("outside", [])}
    if renders:
        data["before"], data["after"] = f"{FOLDER}/{n}/before", f"{FOLDER}/{n}/after"
        data["videos"] = {k: {v: _rel(shot, p) for v, p in r["videos"].items()} for k, r in renders.items()}
    (folder / "pose.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    return f"{FOLDER}/{n}/pose.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_note(shot: Path, n: int, sentence: str, scope: str, stage: str) -> None:
    (Path(shot) / FOLDER / str(n) / "note.json").write_text(json.dumps(
        {"sentence": sentence, "scope": scope, "stage": stage, "at": _now()}, indent=1), encoding="utf-8")


def record_note(shot: Path, text: str, scope: str, stage: str, lessons: Path, pose: str):
    """The author's note through the kei note path (note_shot), the sentence verbatim, with its scope: this shot or
    every shot (a rule), as kei note gives it. The pose file goes on the note's history entry, where the next pass
    reads it as targets."""
    from kei.signoff import note_shot
    from kei.state import save_state
    state, lesson = note_shot(shot, text, stage, lessons, scope=scope)
    state.history[-1]["pose"] = pose
    save_state(shot, state)
    return state, lesson


def ask_in_run(shot: Path, n: int, lines: list[str], renders: dict | None) -> Path:
    """Inside kei run no one is at the keyboard: the question goes to the author through QUESTIONS.md (the shot stops
    for kei answer), and the pose waits in feedback/<n>/ for the answer."""
    folder = Path(shot) / FOLDER / str(n)
    (folder / "question.json").write_text(json.dumps({"description": lines, "at": _now()}, indent=1),
                                          encoding="utf-8")
    text = [f"{TAG.format(n=n)} The animator posed a correction on a feedback layer:"]
    text += [f"- {x}" for x in lines]
    if renders:
        text.append(f"Look at: {FOLDER}/{n}/before and {FOLDER}/{n}/after (Kei's pass, then with the correction)")
    text += ["Why? Answer in one sentence; Kei keeps it word for word and never writes it for you:",
             f'kei answer {shot} --text "..."',
             "Add --every-shot when it applies to every shot (a rule); without it, it is for this shot."]
    q = Path(shot) / "QUESTIONS.md"
    q.write_text("\n".join(text) + "\n", encoding="utf-8")
    return q


def asked_feedback(questions: list[str]) -> int | None:
    """The feedback number an open question asks about, if any."""
    for q in questions:
        m = re.search(r"\[feedback:(\d+)\]", q or "")
        if m:
            return int(m.group(1))
    return None


def answer_note(shot: Path, n: int, text: str, scope: str, stage: str, attempt: int, lessons: Path) -> dict:
    """The author's answer to a feedback question asked inside kei run: the note for the stage running, the sentence
    verbatim, kept as a local lesson with its scope (this shot or every shot). Returns the note's history entry, the
    same shape note_shot records (result note, lesson, scope, round), so one rule decides what may be shared; the
    pose stays on the entry, never in the lesson."""
    from kei.lessons import add_lesson
    from kei.signoff import latest_round
    write_note(shot, n, text, scope, stage)
    entry = {"stage": stage, "attempt": attempt, "result": "note", "lesson": add_lesson(lessons, text, stage, scope),
             "misses": [text], "at": _now(), "scope": scope, "pose": f"{FOLDER}/{n}/pose.json"}
    round_id = latest_round(shot)
    if round_id:
        entry["round"] = round_id     # the failing case of a rule, as note_shot records it
    return entry


# ---------------- the next pass matches the pose ----------------
DEG_TOL = 1.0       # degrees: how near a rotation must come to the animator's pose
CM_TOL = 0.5        # centimetres: how near a move must come


def _pose(shot: Path, rel: str) -> dict | None:
    p = Path(shot) / rel
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tolerance(attr: str, value: float, unit_per_m: float) -> tuple[float, str]:
    """How near a pass must come to a target, and the words for it."""
    if attr.startswith("translate"):
        return CM_TOL / 100.0 * unit_per_m, f"{CM_TOL} cm"
    if attr.startswith("rotate"):
        return DEG_TOL, f"{DEG_TOL:g} deg"
    tol = 0.01 * max(1.0, abs(value))
    return tol, f"{tol:g}"


def target_lines(shot: Path, poses: list[str]) -> list[str]:
    """One note line per pose file: the controls to key, their values and frames, in the scene's unit and degrees."""
    out = []
    for rel in poses:
        data = _pose(shot, rel)
        if not data or not data.get("targets"):
            continue
        f = float(data.get("unit_per_m") or 100.0)
        items = "; ".join(f"{t['control']}.{t['attr']} {t['value']:.3f} at f{t['frame']}" for t in data["targets"])
        out.append(f"The animator posed this correction on pass {data.get('pass')} ({rel}). Key the next pass so each "
                   f"control reaches its value at its frame (degrees and the scene's unit, {data.get('units', 'cm')}; "
                   f"within {DEG_TOL:g} deg or {CM_TOL} cm, {CM_TOL / 100.0 * f:g} in the scene's unit): {items}")
    return out


def _value_at(keys: list[dict], plug: str, frame: float) -> float | None:
    """A channel's value at a frame from the pass's keys: the key's value, else a straight line between the keys
    around it, held before the first and after the last. None when the pass never keys it."""
    def same(a: str, b: str) -> bool:
        return a == b or a.rpartition(":")[2] == b.rpartition(":")[2] and (":" not in a or ":" not in b)
    pts = sorted((k["f"], v) for k in keys for c, v in k["channels"].items() if same(c, plug))
    if not pts:
        return None
    if frame <= pts[0][0]:
        return pts[0][1]
    if frame >= pts[-1][0]:
        return pts[-1][1]
    for (fa, va), (fb, vb) in zip(pts, pts[1:]):
        if fa <= frame <= fb:
            return va if fb == fa else va + (vb - va) * (frame - fa) / (fb - fa)
    return None


def target_misses(shot: Path, poses: list[str]) -> list[str]:
    """What the newest pass misses of the author's feedback poses: one line per target it does not reach, naming the
    control, the frame, the value it keys and the target. Between keys the pass is read as straight lines (the
    pass's own curves are Maya's to draw)."""
    if not poses:
        return []
    from kei.apps.maya_shot import keys_for
    from kei.characters import latest_pass
    shot = Path(shot)
    last = latest_pass(shot)
    out = []
    for rel in poses:
        data = _pose(shot, rel)
        if not data or not data.get("targets"):
            continue
        name = last.parent.name[len("out_"):] if last else None
        if name is None or name == data.get("pass"):
            out.append(f"no new pass after the author's feedback pose ({rel}, on pass {data.get('pass')}): write the "
                       "next pass so it reaches the pose")
            continue
        try:
            shot_data = read_json(last, "shot")
            keys = keys_for(shot_data, shot, "step" if name == "blocking" else "spline")
        except (ShotError, ValueError) as e:
            out.append(f"pass {name} cannot be read against the feedback pose ({rel}): {e}")
            continue
        f = float(data.get("unit_per_m") or 100.0)
        for t in data["targets"]:
            plug = f"{t['control']}.{t['attr']}"
            got = _value_at(keys, plug, t["frame"])
            tol, words = tolerance(t["attr"], t["value"], f)
            if got is None:
                out.append(f"pass {name} does not key {plug}: the author's feedback pose ({rel}) has it at "
                           f"{t['value']:.3f} at f{t['frame']}")
            elif abs(got - t["value"]) > tol + 1e-9:
                out.append(f"pass {name} misses the author's feedback pose ({rel}): {plug} is {got:.3f} at "
                           f"f{t['frame']}, the pose is {t['value']:.3f} (within {words})")
    return out
