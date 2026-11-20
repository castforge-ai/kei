# kei_script: read_rig
# Reads the Control Rig on Kei's own sequence (never a user's): every control with its type, its keyable channels and
# whether it is locked, then probes each transform control by moving it a small step and noting which bones move,
# then puts every control back. Kei compares "before" and "after" (within 1e-4) and stops if any differs.
# Input: sequence, step_cm (default 1.0), step_deg (default 1.0). Units out: centimetres, degrees, Z up.
EULER = ["location.x", "location.y", "location.z", "rotation.x", "rotation.y", "rotation.z", "scale.x", "scale.y",
         "scale.z"]


def _channels(ctype):
    name = str(ctype).split(".")[-1].upper()
    if "EULER" in name:
        return "euler_transform", EULER
    if "FLOAT" in name:
        return "float", ["value"]
    if "BOOL" in name:
        return "bool", ["value"]
    if "ROTATOR" in name:
        return "rotator", ["rotation.x", "rotation.y", "rotation.z"]
    return None, []


def _flat(t):
    q = t.rotation
    return [round(v, 6) for v in (t.translation.x, t.translation.y, t.translation.z, q.x, q.y, q.z, q.w,
                                  t.scale3d.x, t.scale3d.y, t.scale3d.z)]


def _main(inp):
    seq = load_sequence(inp["sequence"])
    rig = control_rig_of(seq)
    h = rig.get_hierarchy()
    controls, keys = [], {}
    for el in h.get_controls():
        key = el.get_key() if hasattr(el, "get_key") else el    # 5.8 returns RigElementKey itself
        name = str(key.name)
        settings = h.get_control_settings(key)
        kind, channels = _channels(settings.control_type)
        animatable = "ANIMATION_CONTROL" in str(settings.animation_type).upper()
        # a limb's IK/FK switch is an animation channel (on the mannequin rig, a bool under global_ctrl)
        switch = (kind == "bool" and "ANIMATION_CHANNEL" in str(settings.animation_type).upper()
                  and name.endswith("_fk_ik_switch"))
        if kind is None or not (animatable or switch):
            continue
        keys[name] = (key, kind)
        controls.append({"name": name, "type": kind, "channels": channels, "locked": False,
                         "limited": any(bool(x) for x in (getattr(settings, "limit_enabled", None) or [])),
                         **({"switch": True} if switch else {})})
    bones = [b for b in h.get_bones()]
    rest = {}       # the legs at rest, in rig space: Kei derives which way the character faces from them
    for b in bones:
        if str(b.name) in ("thigh_l", "thigh_r"):
            t = h.get_global_transform(b).translation
            rest[str(b.name)] = [round(t.x, 3), round(t.y, 3), round(t.z, 3)]
    originals = {n: h.get_local_transform(k) for n, (k, kind) in keys.items() if kind == "euler_transform"}
    before = {n: _flat(t) for n, t in originals.items()}
    moves, probe = {}, "done"
    step, deg = float(inp.get("step_cm") or 1.0), float(inp.get("step_deg") or 1.0)
    try:
        def pose():
            try:
                rig.execute(unreal.Name("Forwards Solve"))
            except Exception:
                pass
            return {str(b.name): h.get_global_transform(b).translation for b in bones}
        base = pose()
        for n, (k, kind) in keys.items():
            if kind != "euler_transform":
                continue
            start = h.get_local_transform(k)
            found = {}
            for ch, (dx, dy, dz, rx, ry, rz) in (("location.x", (step, 0, 0, 0, 0, 0)), ("location.y", (0, step, 0, 0, 0, 0)),
                                                 ("location.z", (0, 0, step, 0, 0, 0)), ("rotation.x", (0, 0, 0, deg, 0, 0)),
                                                 ("rotation.y", (0, 0, 0, 0, deg, 0)), ("rotation.z", (0, 0, 0, 0, 0, deg))):
                moved = unreal.Transform(
                    location=[start.translation.x + dx, start.translation.y + dy, start.translation.z + dz],
                    rotation=unreal.MathLibrary.compose_rotators(start.rotation.rotator(), unreal.Rotator(rx, ry, rz)),
                    scale=[start.scale3d.x, start.scale3d.y, start.scale3d.z])
                h.set_local_transform(k, moved)
                now = pose()
                for b, p in now.items():
                    d = (p.x - base[b].x, p.y - base[b].y, p.z - base[b].z)
                    if max(abs(d[0]), abs(d[1]), abs(d[2])) > 1e-3:
                        if len(found.setdefault(ch, [])) < 8:     # results stay small: Claireon truncates long output
                            found[ch].append(b)
                h.set_local_transform(k, start)
            moves[n] = found
        pose()
    except Exception as e:
        probe = "skipped: " + str(e)[:200]
    finally:
        for n, (k, kind) in keys.items():
            if kind == "euler_transform" and n in originals:
                h.set_local_transform(k, originals[n])
    after = {n: _flat(h.get_local_transform(k)) for n, (k, kind) in keys.items() if kind == "euler_transform"}
    for c in controls:
        c["moves"] = moves.get(c["name"], {})
    return {"controls": controls, "bones": len(bones), "units": {"length": "cm", "angle": "deg", "up": "z"},
            "probe": probe, "rest": rest, "before": before, "after": after, "dirty": dirty_packages()}


kei_run(_main)
