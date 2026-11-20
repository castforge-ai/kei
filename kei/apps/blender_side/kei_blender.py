"""Kei's jobs inside Blender (run by kei.apps.blender: blender -b --factory-startup --python kei_blender.py -- job
result). Blender's own Python only: bpy and mathutils.

The job file is JSON {"tool": "setup" | "key" | "render", ...}; the result file gets JSON back, {"ok": true, ...} or
{"ok": false, "error": text}.

Axes. Kei's world (x the character's right, y up, z forward, metres) is left handed; Blender's is right handed, z up.
Kei's glTF puts a Kei point (x, y, z) at glTF (-x, y, z), and Blender's glTF import at (-x, -z, y): C below. A Kei
bone frame becomes a Blender rotation through its change from rest: delta = C (F_pose F_rest^T) C^T, which is a
proper rotation, so the bones Blender's importer made (whatever their roll) turn by the same amount as Kei's.

setup   imports Kei's glTF of the character (its own skeleton, Kei's bone names, skinned mesh), adds the leg IK an
        animator works with (ik_foot_l/r and pole_knee_l/r, not deforming: an IK constraint on each calf, the foot
        copying its IK control's rotation), finds each pole's angle by measuring the knee at rest, and saves the
        .blend.
key     opens the shot's .blend, keys whole poses at Kei's key frames (rotation on every bone, location where a bone
        moves, the IK controls where the feet are), sets the interpolation of every key (CONSTANT, LINEAR or
        BEZIER), saves the pass's .blend, and samples every frame: each bone's head and its turn from rest.
render  opens a pass's .blend and renders each view (front, side, three-quarter, back) as PNG frames.
"""
import json
import math
import sys

import bpy
from mathutils import Matrix, Vector

C = Matrix(((-1.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 1.0, 0.0)))   # Kei world -> Blender world
LEGS = {"l": ("thigh_l", "calf_l", "foot_l"), "r": ("thigh_r", "calf_r", "foot_r")}
POLE_M = 0.4


def to_bl(p):
    return C @ Vector(p)


def frame_matrix(axes):
    """A Kei bone frame (rows X, Y, Z in Kei's world) as a matrix with those columns."""
    return Matrix([[axes[c][r] for c in range(3)] for r in range(3)])


def armature():
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(arms) != 1:
        raise RuntimeError(f"the scene has {len(arms)} armatures; Kei's scene has one")
    return arms[0]


def update():
    bpy.context.view_layer.update()


# ---- setup ----------------------------------------------------------------------------------------------------------

def setup(job):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=job["glb"])
    for o in [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("Icosphere")]:
        bpy.data.objects.remove(o)         # the importer's bone display shape
    scene = bpy.context.scene
    scene.render.fps = int(round(job.get("fps", 24)))
    scene.frame_start = 0
    arm = armature()
    arm.name = "kei_rig"
    for o in bpy.data.objects:            # dual quaternion skin when Kei renders that way (KEI_SKINNING)
        for mod in getattr(o, "modifiers", []):
            if mod.type == "ARMATURE":
                mod.use_deform_preserve_volume = job.get("skinning") == "dual_quaternion"
    bpy.context.view_layer.objects.active = arm
    for o in bpy.context.selected_objects:
        o.select_set(False)
    arm.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.data.edit_bones
    for s, (thigh, calf, foot) in LEGS.items():
        ik = eb.new(f"ik_foot_{s}")
        ik.head, ik.tail, ik.roll = eb[foot].head.copy(), eb[foot].tail.copy(), eb[foot].roll
        ik.use_deform = False
        knee = eb[calf].head
        pole = eb.new(f"pole_knee_{s}")
        forward = arm.matrix_world.inverted().to_3x3() @ to_bl((0.0, 0.0, 1.0))
        pole.head = knee + forward.normalized() * POLE_M
        pole.tail = pole.head + Vector((0.0, 0.0, 0.08))
        pole.use_deform = False
    bpy.ops.object.mode_set(mode="POSE")
    poles = {}
    for s, (thigh, calf, foot) in LEGS.items():
        pb = arm.pose.bones
        c = pb[calf].constraints.new("IK")
        c.target, c.subtarget = arm, f"ik_foot_{s}"
        c.pole_target, c.pole_subtarget = arm, f"pole_knee_{s}"
        c.chain_count = 2
        r = pb[foot].constraints.new("COPY_ROTATION")
        r.target, r.subtarget = arm, f"ik_foot_{s}"
        rest_knee = (arm.matrix_world @ arm.data.bones[calf].head_local).copy()
        rest_ankle = (arm.matrix_world @ arm.data.bones[foot].head_local).copy()

        def err(angle):
            c.pole_angle = math.radians(angle)
            update()
            return (arm.matrix_world @ pb[calf].head - rest_knee).length + \
                (arm.matrix_world @ pb[foot].head - rest_ankle).length

        best = min(range(-180, 180, 5), key=err)
        lo, hi = best - 5.0, best + 5.0
        for _ in range(30):                     # golden section on the coarse best
            a, b = lo + (hi - lo) * 0.382, lo + (hi - lo) * 0.618
            if err(a) < err(b):
                hi = b
            else:
                lo = a
        angle = (lo + hi) / 2
        poles[s] = {"angle_deg": round(angle, 3), "knee_error_m": round(err(angle), 6)}
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.wm.save_as_mainfile(filepath=job["out"])
    return {"armature": arm.name, "bones": [b.name for b in arm.data.bones], "poles": poles,
            "blender": bpy.app.version_string}


# ---- key ------------------------------------------------------------------------------------------------------------

def _world_targets(arm, rest, pose):
    """{bone: world matrix (Blender)} of every Kei bone in a Kei pose."""
    out = {}
    for name, b in pose.items():
        if name not in arm.data.bones or name not in rest:
            continue
        delta_kei = frame_matrix(b["frame"]) @ frame_matrix(rest[name]["frame"]).transposed()
        delta = C @ delta_kei @ C.transposed()
        rest_world = (arm.matrix_world @ arm.data.bones[name].matrix_local).to_3x3()
        m = (delta @ rest_world).to_4x4()
        m.translation = to_bl(b["head"])
        out[name] = m
    return out


def _bases(arm, world):
    """{bone: matrix_basis} that put each bone at its world matrix, parents first (the bone's own pose channels)."""
    A = arm.matrix_world.inverted()
    pose_arm = {n: A @ m for n, m in world.items()}
    out = {}
    for bone in sorted(arm.data.bones, key=lambda b: len(b.parent_recursive)):     # parents first
        n = bone.name
        if n not in pose_arm:
            continue
        if bone.parent is None:
            out[n] = bone.matrix_local.inverted() @ pose_arm[n]
            continue
        if bone.parent.name not in pose_arm:
            continue
        p = bone.parent
        space = pose_arm[p.name] @ p.matrix_local.inverted() @ bone.matrix_local
        out[n] = space.inverted() @ pose_arm[n]
    return out


def key(job):
    bpy.ops.wm.open_mainfile(filepath=job["blend"])
    scene = bpy.context.scene
    scene.render.fps = int(round(job.get("fps", 24)))
    scene.frame_start, scene.frame_end = 0, int(job["frames"])
    arm = armature()
    if arm.animation_data and arm.animation_data.action:
        arm.animation_data.action = None
    rest = job["rest"]
    A = arm.matrix_world.inverted()
    prev_q, moving = {}, set()
    plans = []
    for k in job["keys"]:
        world = _world_targets(arm, rest, k["bones"])
        bases = _bases(arm, world)
        for s, (_, _, foot) in LEGS.items():
            ik = arm.data.bones[f"ik_foot_{s}"]
            bases[ik.name] = ik.matrix_local.inverted() @ A @ world[foot]
            pole = arm.data.bones[f"pole_knee_{s}"]
            m = Matrix.Translation(A @ to_bl(k["poles"][s]))
            bases[pole.name] = pole.matrix_local.inverted() @ m
        plans.append((k["f"], bases))
        for n, m in bases.items():
            if m.translation.length > 1e-5:
                moving.add(n)
    for f, bases in plans:
        for n, m in bases.items():
            pb = arm.pose.bones[n]
            pb.rotation_mode = "QUATERNION"
            q = m.to_quaternion()
            if n in prev_q and prev_q[n].dot(q) < 0:
                q.negate()
            prev_q[n] = q
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=f)
            if n in moving or n.startswith(("ik_foot", "pole_knee")):
                pb.location = m.translation
                pb.keyframe_insert("location", frame=f)
    interp = job.get("interpolation", "BEZIER")
    action = arm.animation_data.action
    for fc in _fcurves(action):
        for kp in fc.keyframe_points:
            kp.interpolation = interp
            if interp == "BEZIER":
                kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
        fc.update()
    action.name = job.get("action", "kei_pass")
    bpy.ops.wm.save_as_mainfile(filepath=job["out"])
    frames = []
    names = job["sample"]
    for f in range(scene.frame_start, scene.frame_end + 1):
        scene.frame_set(f)
        pos, turn = {}, {}
        for n in names:
            pb = arm.pose.bones[n]
            w = arm.matrix_world @ pb.matrix
            r = arm.matrix_world.to_3x3() @ pb.bone.matrix_local.to_3x3()
            pos[n] = list(w.translation)
            d = w.to_3x3().normalized() @ r.normalized().inverted()
            turn[n] = [list(row) for row in d]
        frames.append({"f": f, "pos": pos, "turn": turn})
    return {"frames": frames, "keyed": len(plans), "blender": bpy.app.version_string}


def _fcurves(action):
    """Every F-curve of an action: the action's own list, or (Blender 4.4 and later) its layers' channelbags."""
    if hasattr(action, "fcurves") and len(getattr(action, "fcurves", [])):
        return list(action.fcurves)
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out += list(bag.fcurves)
    return out


# ---- render ---------------------------------------------------------------------------------------------------------

VIEWS = {"front": 0.0, "three_quarter": 45.0, "side": 90.0, "back": 180.0}


def render(job):
    bpy.ops.wm.open_mainfile(filepath=job["blend"])
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x, scene.render.resolution_y = job.get("width", 640), job.get("height", 360)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("kei_world") if scene.world is None else scene.world
    scene.world = world
    bpy.ops.mesh.primitive_plane_add(size=40.0, location=(0.0, 0.0, 0.0))   # the floor, so contact reads
    floor = bpy.context.active_object
    floor.name = "kei_floor"
    mat = bpy.data.materials.new("kei_floor")
    mat.diffuse_color = (0.32, 0.32, 0.34, 1.0)
    floor.data.materials.append(mat)
    target = Vector(job.get("target", (0.0, 0.0, 0.9)))
    cam_data = bpy.data.cameras.new("kei_cam")
    cam_data.lens = job.get("lens_mm", 50.0)
    cam = bpy.data.objects.new("kei_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    distance = job.get("distance_m", 6.0)
    out = {}
    for view in job.get("views", list(VIEWS)):
        a = math.radians(VIEWS[view])
        # the character faces Blender's -y: the front camera stands at -y looking toward +y
        cam.location = target + Vector((-math.sin(a) * distance, -math.cos(a) * distance, 0.0))   # side: its right
        direction = target - cam.location
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = job["out"].rstrip("/") + f"/{view}/f_"
        bpy.ops.render.render(animation=True)
        out[view] = job["out"].rstrip("/") + f"/{view}"
    return {"views": out, "frames": scene.frame_end - scene.frame_start + 1}


TOOLS = {"setup": setup, "key": key, "render": render}


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    job_path, result_path = args[0], args[1]
    job = json.loads(open(job_path, encoding="utf-8").read())
    try:
        result = {"ok": True, **TOOLS[job["tool"]](job)}
    except Exception as e:                 # every failure goes back to Kei as text, never a silent Blender exit
        import traceback
        result = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]}
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f)


main()
