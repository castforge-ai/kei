"""kei retarget: a pass made for a character's old proportions, played on new ones (a re-imported model).

A pass's foot targets and root are absolute world positions, authored for the leg and foot of the character at the
time. When the character changes (a new ankle height, a shorter thigh, a longer toe), the same numbers put the soles
under or over the ground and the legs out of reach. retarget_shot moves, on every key:

  foot targets  the height by the change in ankle height (kei.rig: the sole is ankleH under the ankle target), so a
                foot on the ground lands on the ground and a lifted foot keeps its lift as authored.
  root          the height by the change in the standing root height, ankleH + calf + thigh + hipDrop (kei.rig: the
                hip is hipDrop under the root). Then, by default (keep "knees"), each key's root moves again so the
                knees bend as they did in the source pass on the source character: a diagonal leg (a heel strike)
                is not kept by the standing height alone and would snap straight. Per key, the offset is the one
                that best matches the two knee bends, the straighter knee and a planted leg weighted most, never
                leaving that leg's knee straighter than the source and never putting a foot out of reach.
                The offsets are then smoothed over time (KNEE_SMOOTH frames), never above that limit, so no bob or
                pop is added between keys. keep "standing-height" stops after the standing shift. A key whose
                foot target is still beyond the leg's reach after that has its root lowered only as far as the leg
                needs.

The foot targets do not move along the ground. In kei.rig the heel, ball and toe pivots of the foot roll are fixed
offsets from the ankle target, so a target held still through a contact keeps whichever pivot is down still, on the
old foot and on the new one. A target moved by the heel change on heel keys and by the ball change on ball keys would
make the planted foot slide when the roll passes from the heel to the ball. The heel and ball contacts therefore sit
where the new foot puts them about the same ankle: the report gives that distance.

Every other channel, key, frame, tangent and name is copied unchanged.
"""
from __future__ import annotations

import copy
import datetime
import json
import math
from pathlib import Path

from kei.body_check import REACH
from kei.characters import Character, CharacterError, load_character, on_character, parse_character
from kei.rig import PROPORTIONS, STAND, over_reach, solve
from kei.sample import _knee_flex, bake, check_shot, normalize_keys, read_json

KNEE_RANGE = 0.15     # m: the most a key's root moves, up or down, to match the knees
KNEE_SMOOTH = 1.0     # frames: the time scale (a Gaussian's sigma) the knee offsets are smoothed over
KNEE_PULL = 0.6       # each smoothing pass: this much the smoothed offset, the rest the key's own matching offset
KNEE_PASSES = 30
KEEPS = ("knees", "standing-height")
LOWER_MAX = 0.3        # m: the most a key's root is lowered to bring a foot target into reach


class RetargetError(ValueError):
    """The pass cannot be retargeted. The message names the file or the pass."""


def _p(ch: Character) -> dict:
    return {**PROPORTIONS, **ch.proportions}


def standing_root(ch: Character) -> float:
    """The root height of a straight, vertical leg on flat ground, as kei.rig builds the leg."""
    p = _p(ch)
    return p["ankleH"] + p["calf"] + p["thigh"] + p["hipDrop"]


def _r(v: float) -> float:
    return round(v, 6)


def _shift_y(key: dict, channel: str, dy: float) -> None:
    if channel not in key:
        return
    v = list(key[channel])
    v[1] = _r(v[1] + dy)
    key[channel] = v


def _pose(full_key: dict) -> dict:
    return {c: v for c, v in full_key.items() if c not in ("f", "name", "tangent")}


def _bends(pose: dict, proportions: dict) -> tuple[float, float]:
    j = solve(pose, proportions)
    return (math.degrees(_knee_flex(j, "l")), math.degrees(_knee_flex(j, "r")))


def _raised(pose: dict, dy: float) -> dict:
    return {**pose, "root": [pose["root"][0], pose["root"][1] + dy, pose["root"][2]]}


def _knee_offsets(shot: dict, out: dict, po: dict, pn: dict) -> tuple[dict, dict]:
    """Per key frame: the root offset (m, on top of the standing shift) that keeps the source's knee bends, smoothed,
    and the upper limit of each key (the highest root with no knee straighter than the source and both feet in
    reach)."""
    src, now = normalize_keys(shot), normalize_keys(out)
    want, limit = {}, {}
    for sk, nk in zip(src, now):
        sp, np_ = _pose(sk), _pose(nk)
        goal = _bends(sp, po)
        j = solve(sp, po)
        # planted: the heel or the ball on the ground, and not rolling onto the toe tip to leave (roll past ballMax)
        planted = [min(j[f"{p}_{s}"][1] for p in ("heel", "ball")) <= 0.02
                   and sp[f"roll{s.upper()}"][0] <= max(0.0, sp[f"roll{s.upper()}"][2]) for s in "lr"]
        w = [(3.0 if planted[i] else 1.0) / (goal[i] + 5.0) ** 2 for i in range(2)]
        # never straighter than the source: the leg weighted most, the planted leg with the straighter knee (the
        # support). The other leg is only matched as well as it can be: a rear foot peeling off a shorter foot would
        # otherwise drag the whole body down for a frame or two and drop it back, a new bob.
        held = [0 if w[0] >= w[1] else 1]

        def ok(e):
            q = _raised(np_, e)
            b = _bends(q, pn)
            return over_reach(q, pn) <= 0 and all(b[i] >= goal[i] - 1e-3 for i in held)
        lo, hi = -KNEE_RANGE, KNEE_RANGE
        if ok(hi):
            top = hi
        elif not ok(lo):
            top = lo
        else:
            for _ in range(28):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if ok(mid) else (lo, mid)
            top = lo

        def err(e):
            b = _bends(_raised(np_, e), pn)
            return sum(w[i] * (b[i] - goal[i]) ** 2 for i in range(2))
        a, b = -KNEE_RANGE, top
        for _ in range(30):                    # golden section on the offset, under the limit
            m1, m2 = a + (b - a) * 0.382, a + (b - a) * 0.618
            if err(m1) < err(m2):
                b = m2
            else:
                a = m1
        want[sk["f"]] = min((a + b) / 2, top)
        limit[sk["f"]] = top
    n, loop = shot["frames"], bool(shot.get("loop"))

    def gap(f, g):
        d = abs(f - g)
        return min(d, n - d) if loop else d

    def kernel(f, g):
        return math.exp(-0.5 * (gap(f, g) / KNEE_SMOOTH) ** 2)
    e = dict(want)
    for _ in range(KNEE_PASSES):               # smooth over time, held to the matching offsets, never above a limit
        sm = {f: sum(v * kernel(f, g) for g, v in e.items()) / sum(kernel(f, g) for g in e) for f in e}
        e = {f: min(limit[f], KNEE_PULL * sm[f] + (1 - KNEE_PULL) * want[f]) for f in e}
    return e, limit


def retarget_shot(shot: dict, old: Character, new: Character, source: str, when: str | None = None,
                  label: str = "", keep: str = "knees") -> tuple[dict, dict]:
    """The shot moved from old's proportions to new's (see the module docstring), and a report of what moved."""
    when = when or datetime.date.today().isoformat()
    po, pn = _p(old), _p(new)
    ankle = pn["ankleH"] - po["ankleH"]
    root = standing_root(new) - standing_root(old)
    out = copy.deepcopy(shot)
    out["character"] = new.name
    keys = sorted(out["keys"], key=lambda k: k["f"])
    first = keys[0]
    for c in ("root", "footL", "footR"):       # a first key with no channel stands on the default: make it explicit
        if c not in first:
            first[c] = list(STAND[c])
    for k in out["keys"]:
        for c in ("footL", "footR"):
            _shift_y(k, c, ankle)
        _shift_y(k, "root", root)
    if keep not in KEEPS:
        raise RetargetError(f"keep is one of {', '.join(KEEPS)}, not {keep!r}")
    offsets = {}
    if keep == "knees":
        full = normalize_keys(out)
        offsets, _ = _knee_offsets(shot, out, po, pn)
        by_f = {k["f"]: k for k in out["keys"]}
        for i, fk in enumerate(full):
            key = by_f[fk["f"]]
            if "root" not in key:              # it carried the root over: the next key keeps the carried root
                nxt = full[i + 1] if i + 1 < len(full) else None
                if nxt is not None and "root" not in by_f[nxt["f"]]:
                    by_f[nxt["f"]]["root"] = list(nxt["root"])
                key["root"] = list(fk["root"])
        for k in out["keys"]:
            _shift_y(k, "root", offsets[k["f"]])

    # a key whose foot target is still out of reach: lower its root only as far as the leg needs
    lowered = {}
    full = normalize_keys(out)
    by_f = {k["f"]: k for k in out["keys"]}
    for i, fk in enumerate(full):
        pose = {c: v for c, v in fk.items() if c not in ("f", "name", "tangent")}
        if over_reach(pose, pn) <= 0:
            continue
        lo, hi = 0.0, LOWER_MAX
        for _ in range(50):
            mid = (lo + hi) / 2
            q = {**pose, "root": [pose["root"][0], pose["root"][1] - mid, pose["root"][2]]}
            if over_reach(q, pn) > 0:
                lo = mid
            else:
                hi = mid
        key = by_f[fk["f"]]
        if "root" not in key:                  # it carried the root over: the next key keeps the carried root
            nxt = full[i + 1] if i + 1 < len(full) else None
            if nxt is not None and "root" not in by_f[nxt["f"]]:
                by_f[nxt["f"]]["root"] = list(nxt["root"])
            key["root"] = list(fk["root"])
        key["root"] = [key["root"][0], _r(key["root"][1] - hi), key["root"][2]]
        lowered[fk["f"]] = hi
    check_shot(out)
    played = on_character(out, new)
    beyond = [fr["f"] for fr in bake(played, "spline") if over_reach(fr["pose"], pn) > REACH]

    def m(v: float) -> str:
        return f"{v:+.4f}"
    words = (f"retargeted from {source} to the character {new.name} on {when} (kei retarget): foot target heights "
             f"{m(ankle)} m (ankle height {po['ankleH']} -> {pn['ankleH']}), root height {m(root)} m (standing "
             f"root, ankle + calf + thigh + hip drop, {standing_root(old):.5f} -> {standing_root(new):.5f})")
    if offsets:
        words += (f", then {min(offsets.values()):+.4f} to {max(offsets.values()):+.4f} m per key, smoothed, so the "
                  f"knees bend as on the source")
    if lowered:
        words += ("; root lowered further for the leg's reach on keys "
                  + ", ".join(f"f{f:g} {v:.4f} m" for f, v in sorted(lowered.items())))
    words += ". Foot targets kept along the ground; every other channel unchanged."
    note = f"{label or 'Retarget'} ({words})"
    out["note"] = note + (" " + shot["note"] if isinstance(shot.get("note"), str) and shot["note"] else "")
    report = {"ankle_shift_m": ankle, "root_shift_m": root, "lowered_for_reach": lowered, "keep": keep,
              "knee_offsets_m": offsets,
              "beyond_reach_frames": beyond,
              "heel_moves_m": -(pn["heelBack"] - po["heelBack"]), "ball_moves_m": pn["ballFwd"] - po["ballFwd"],
              "toe_moves_m": pn["toeFwd"] - po["toeFwd"], "hip_width_change_m": pn["hipWidth"] - po["hipWidth"],
              "old_ankle": po["ankleH"], "new_ankle": pn["ankleH"],
              "old_standing_root": standing_root(old), "new_standing_root": standing_root(new)}
    return out, report


def _old_character(spec: str, name: str) -> tuple[Character, str]:
    """--from: a character.json path, else a character's name."""
    path = Path(spec)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise RetargetError(f"cannot read {path}: {e}") from e
        return parse_character(data, name), str(path)
    try:
        return load_character(spec), f"the character {spec}"
    except CharacterError as e:
        raise RetargetError(f"--from {spec!r} is neither a character.json file nor a character: {e}") from e


def retarget_pass(shot_dir, pass_name: str, from_spec: str, to: str | None, out_name: str,
                  when: str | None = None, keep: str = "knees") -> tuple[Path, dict]:
    """Write out_<out_name>/shot.json: out_<pass_name>/shot.json retargeted. Refuses an existing out_<out_name>."""
    shot_dir = Path(shot_dir)
    src = shot_dir / f"out_{pass_name}" / "shot.json"
    dst_dir = shot_dir / f"out_{out_name}"
    if dst_dir.exists():
        raise RetargetError(f"{dst_dir} exists: kei retarget never overwrites a pass; name a new one with --out")
    if not src.is_file():
        raise RetargetError(f"no {src}")
    shot = read_json(src, "shot")
    check_shot(shot)
    target = (to or shot.get("character") or "").strip().lower()
    if not target:
        raise RetargetError(f"{src} names no character: give --to")
    new = load_character(target)
    old, source = _old_character(from_spec, str(shot.get("character") or target).strip().lower())
    out, report = retarget_shot(shot, old, new, source, when, label=out_name.upper(), keep=keep)
    dst_dir.mkdir(parents=True)
    dst = dst_dir / "shot.json"
    dst.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return dst, report
