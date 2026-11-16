"""A pass as a layer on the one before it: only what changed is written, as deltas, then merged down.

From the second spline pass on, most of a pass is the pass before it. Rewriting every control on every frame drifts
what was already right and costs the editor a full write and read each time. So when a pass can be expressed as a
change of the previous one, Kei:

  1. copies the previous pass's sequence (make_sequence.py with copy_from): the new pass starts exactly where the
     last one ended, and the previous sequence stays as it was, for before and after;
  2. writes, on a new additive section of the Control Rig track, the difference new minus previous for each channel
     that changed, on every frame from one before its first change to one after its last, so the layer is zero
     outside the frames it bears on (an additive key holds its value before the first key and after the last);
  3. collapses the layers into one section (ControlRigSequencerLibrary.collapse_control_rig_anim_layers, the
     editor's own merge down), so the readback and every check measure the full result, as with any pass.

layer_plan(prev, new, types, frames) -> {"channels", "controls", "keys"} or {"full": <why>}
  prev, new: parse_keys() output of the two passes. It needs both passes keyed on every frame 0..frames with the same
  tangent on each frame, and no bool channel changing: then the delta on each frame is exact. Anything else, and the
  pass is keyed whole, as before.
"""
from __future__ import annotations

EPS = 1e-4          # rig units (cm, degrees): a smaller change is no change
_ROTATOR = {"x": "Roll", "y": "Pitch", "z": "Yaw"}


def section_channel(control: str, channel: str, kind: str) -> str | None:
    """The name of a Kei channel on the Control Rig section, as the editor lists it; None for a bool."""
    if kind == "float":
        return control
    if kind == "bool":
        return None
    group, axis = channel.split(".")
    if kind == "rotator":
        return f"{control}.Rotation.{_ROTATOR[axis]}"
    return f"{control}.{group.capitalize()}.{axis.upper()}"


def _dense(keys: list[dict], frames: int) -> dict | None:
    by_f = {k["f"]: k for k in keys}
    return by_f if set(by_f) == set(range(frames + 1)) else None


def layer_plan(prev: list[dict], new: list[dict], types: dict, frames: int) -> dict:
    a, b = _dense(prev, frames), _dense(new, frames)
    if a is None or b is None:
        return {"full": "a pass that does not key every frame cannot be written as a layer of the previous one"}
    if any(a[f]["tangent"] != b[f]["tangent"] for f in a):
        return {"full": "the tangents changed"}
    changed: dict[tuple[str, str], dict[int, float]] = {}
    for f in range(frames + 1):
        pa, pb = a[f]["controls"], b[f]["controls"]
        for ctl in set(pa) | set(pb):
            for ch in set(pa.get(ctl, {})) | set(pb.get(ctl, {})):
                if ch not in pa.get(ctl, {}) or ch not in pb.get(ctl, {}):
                    return {"full": f"{ctl}.{ch} is keyed on f{f} in one pass and not in the other"}
                va, vb = pa[ctl][ch], pb[ctl][ch]
                if types[ctl] == "bool":
                    if bool(va) != bool(vb):
                        return {"full": f"the switch {ctl} changed"}
                    continue
                d = float(vb) - float(va)
                changed.setdefault((ctl, ch), {})[f] = d
    channels: dict[str, list[list[float]]] = {}
    controls: dict[str, list[int]] = {}
    for (ctl, ch), by_f in changed.items():
        moved = [f for f, d in by_f.items() if abs(d) > EPS]
        if not moved:
            continue
        lo, hi = max(0, min(moved) - 1), min(frames, max(moved) + 1)
        name = section_channel(ctl, ch, types[ctl])
        channels[name] = [[f, round(by_f[f], 6) if abs(by_f[f]) > EPS else 0.0] for f in range(lo, hi + 1)]
        span = controls.setdefault(ctl, [lo, hi])
        span[0], span[1] = min(span[0], lo), max(span[1], hi)
    return {"channels": channels, "controls": controls, "keys": sum(len(v) for v in channels.values())}
