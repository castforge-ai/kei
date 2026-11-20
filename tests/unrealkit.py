"""A fake Unreal Editor behind a fake Claireon, for the Unreal adapter's tests. It models only what Kei asks: sequences
Kei made, the keys written to them, the dirty packages, the open sequence and a bone position function. No Unreal."""
from __future__ import annotations

from fakes.fake_claireon import FakeClaireon
from kei.apps.unreal import Claireon

MANNY = {"name": "Manny", "mesh": "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple",
         "control_rig": "/Game/Characters/Mannequins/Rigs/CR_Mannequin_Body"}

EULER = ["location.x", "location.y", "location.z", "rotation.x", "rotation.y", "rotation.z", "scale.x", "scale.y",
         "scale.z"]


def canned_rig() -> dict:
    """A small Control Rig read: two foot controls, a hip control, a float and a locked control."""
    def ctl(name, **kw):
        return {"name": name, "type": "euler_transform", "channels": EULER, "locked": False, "limited": False,
                "moves": {"location.z": ["foot_l"]}, **kw}
    return {"controls": [ctl("foot_l_ik_ctrl"), ctl("foot_r_ik_ctrl"), ctl("pelvis_ctrl"),
                         {"name": "hand_l_fk_ctrl", "type": "euler_transform", "channels": EULER, "locked": True,
                          "limited": False, "moves": {}},
                         {"name": "spine_blend", "type": "float", "channels": ["value"], "locked": False,
                          "limited": False, "moves": {}}],
            "bones": 161, "rest": {"thigh_l": [9.0, 0.0, 92.0], "thigh_r": [-9.0, 0.0, 92.0]}, "units": {"length": "cm", "angle": "deg", "up": "z"}, "probe": "done",
            "before": {"foot_l_ik_ctrl": [0, 0, 0, 0, 0, 0, 1, 1, 1, 1], "pelvis_ctrl": [0, 0, 90, 0, 0, 0, 1, 1, 1, 1]},
            "after": {"foot_l_ik_ctrl": [0, 0, 0, 0, 0, 0, 1, 1, 1, 1], "pelvis_ctrl": [0, 0, 90, 0, 0, 0, 1, 1, 1, 1]}}


class FakeEditor:
    """Handlers for every one of Kei's scripts. Public knobs: leave_changed (a control the probe leaves moved),
    user_dirty (a package the keys make dirty), clip (a channel a limit holds back), bones (frame -> {bone: [x, y, z]}
    in Unreal centimetres), drop_after (stop answering after n python_execute calls, to model a lost editor)."""

    def __init__(self, characters=(MANNY,), bones=None):
        self.characters = list(characters)
        self.rig = canned_rig()
        self.sequences: dict[str, dict] = {}
        self.dirty: set[str] = set()
        self.saved: list[str] = []
        self.keys: list[dict] = []
        self.batches: list[int] = []       # key frames in each set_keys call
        self.unloads: list[list] = []      # the paths each unload_kei call was asked to unload
        self.unload_error = None
        self.captures: list[dict] = []     # capture_frame calls
        self.capture_shown = 0.31          # the fraction of each picture that is the character
        self.opened = None
        self.leave_changed = None
        self.user_dirty = None
        self.clip = None
        self.bones = bones or (lambda f: {})
        self.save_all_calls = 0
        self.fake: FakeClaireon | None = None
        self.baked = lambda frame: {}      # frame -> {bone: [x, y, z]} of the baked asset
        self.bake_error = None
        self.bakes: list[dict] = []
        self.content_dir = ""             # the project's Content folder on disk (organize.py reports it)
        self.pose_check = {"bones": 113, "mean_deg": 0.24, "worst_deg": [["spine_03", 7.33]],
                           "pelvis_relative_cm": {"head": 0.0, "hand_l": 0.0, "foot_l": 1.8}}
        self.poses: list[dict] = []
        self.missing_channels: set[str] = set()
        self.looks: list[dict] = []        # make_look calls
        self.performer_bones = {}          # performer -> (frame -> {bone: [x, y, z]}) in rig space
        self.levels: set[str] = set()      # levels Kei made (render_level)
        self.mesh_calls: list[dict] = []   # render_mesh calls
        self.mesh_written = None           # frames written per view by a render (None: every frame)
        self.mesh_error = None             # the render stage stops with this

    def handlers(self) -> dict:
        return {"probe": self.probe, "make_sequence": self.make_sequence, "read_rig": self.read_rig,
                "dirty": self.get_dirty, "set_keys": self.set_keys, "save_asset": self.save_asset,
                "open_sequence": self.open_sequence, "eval_rig": self.eval_rig, "bake": self.bake,
                "read_bake": self.read_bake, "organize": self.organize,
                "unload_kei": self.unload_kei, "capture_frame": self.capture_frame,
                "load_pose": self.load_pose, "layer_keys": self.layer_keys, "make_look": self.make_look,
                "render_level": self.render_level, "render_mesh": self.render_mesh}

    def render_level(self, inp):
        if not inp["level"].startswith("/Game/Kei/"):
            return {"error": "Kei makes levels only under /Game/Kei"}
        made = inp["level"] not in self.levels
        self.levels.add(inp["level"])
        return {"level": inp["level"], "made": made, "restored": "/Game/Maps/L_Gym" if made else ""}

    def render_mesh(self, inp):
        """Like Movie Render Queue, but at once: a small PNG per frame per view under out_dir/<view>/."""
        import os
        from kei.sheet import _Canvas
        self.mesh_calls.append(inp)
        if inp["stage"] == "open":
            self.opened = inp["sequence"]
            return {"stage": "open", "sequence": inp["sequence"]}
        if self.opened != inp["sequence"]:
            return {"error": "the sequence " + inp["sequence"] + " is not open in Sequencer"}
        if self.mesh_error:
            return {"error": self.mesh_error}
        count = int(inp["last"]) + 1 if self.mesh_written is None else self.mesh_written
        for v in inp["views"]:
            os.makedirs(os.path.join(inp["out_dir"], v), exist_ok=True)
            for f in range(count):
                cv = _Canvas(64, 36)
                cv.line(0, f % 36, 63, f % 36, (200, 30, 30))
                with open(os.path.join(inp["out_dir"], v, "f%04d.png" % f), "wb") as fh:
                    fh.write(cv.png())
        return {"stage": "render", "frames": int(inp["last"]) + 1, "travel_cm": 140.0, "warnings": [],
                "views": [{"name": v, "sequence": inp["views_folder"] + "/x_" + v, "position": [0, 0, 0],
                           "target": [0, 0, 80]} for v in inp["views"]]}

    def make_look(self, inp):
        """A performer's materials: one Kei instance per slot (three slots), under the shot's looks folder."""
        self.looks.append(inp)
        folder = inp["folder"] + "/looks/" + inp["performer"]
        if not folder.startswith("/Game/Kei/"):
            return {"error": "Kei writes only under /Game/Kei"}
        paths = [f"{folder}/MI_Kei_{inp['performer']}_{i}_MI_Slot{i}" for i in range(3)]
        return {"materials": paths, "set": {p: [s["name"] for s in inp["scalars"]] for p in paths}, "dirty": []}

    def server(self) -> FakeClaireon:
        self.fake = FakeClaireon(self.handlers())
        return self.fake

    def client(self) -> Claireon:
        c = Claireon(self.fake.url)
        c.initialize()
        return c

    def organize(self, inp):
        """Moves Kei's sequences inside its own folder, as organize.py does."""
        moved, failed = [], []
        for src, dst in inp["moves"]:
            if not (src.startswith(inp["folder"] + "/") and dst.startswith(inp["folder"] + "/")):
                failed.append([src, "outside Kei's folder for this shot"])
            elif src not in self.sequences:
                failed.append([src, "no such asset"])
            else:
                self.sequences[dst] = self.sequences.pop(src)
                moved.append([src, dst])
        return {"moved": moved, "failed": failed, "dirty": sorted(self.dirty), "content_dir": self.content_dir}

    def probe(self, inp):
        return {"project": "ThirdPersonTest", "level": "ThirdPersonMap", "engine": "5.8.3",
                "characters": self.characters}

    def make_sequence(self, inp):
        path = inp["folder"] + "/" + inp["name"]
        if not inp["folder"].startswith("/Game/Kei/"):
            return {"error": "Kei writes only under /Game/Kei"}
        if path in self.sequences:
            return {"error": "the asset " + path + " already exists: Kei never overwrites or deletes an asset"}
        self.sequences[path] = {"frames": inp["frames"], "fps": inp["fps"], "copy_from": inp.get("copy_from"),
                                "keys": [], "performers": {p["name"]: p for p in inp.get("performers") or []}}
        self.made_open = path              # make_sequence.py opens the sequence it made
        return {"path": path, "fps": int(inp["fps"]), "frames": inp["frames"], "facing": "yaw -90", "dirty": [],
                "performers": [p["name"] for p in inp.get("performers") or []],
                "placed": {"how": "the floor under the Player Start", "at_cm": [370.0, -20.0, 0.0], "level": "/Game/ThirdPerson/ThirdPersonMap"}}

    def read_rig(self, inp):
        out = dict(self.rig)
        out["after"] = {k: list(v) for k, v in out["after"].items()}
        if self.leave_changed:
            out["after"][self.leave_changed][2] += 0.5
        out["dirty"] = sorted(self.dirty)
        return out

    def get_dirty(self, inp):
        return {"dirty": sorted(self.dirty)}

    def set_keys(self, inp):
        """A batch of key frames in one call (inp["keys"]), or one frame given flat, as the editor script takes both."""
        seq = inp["sequence"]
        batch = inp["keys"] if "keys" in inp else [inp]
        self.batches.append(len(batch))
        keyed, clipped = 0, []
        for k in batch:
            who = inp.get("performer", "")
            if who and who not in self.sequences[seq]["performers"]:
                return {"error": "the sequence " + seq + " has no binding for the performer " + who}
            self.sequences[seq]["keys"].append({"f": k["frame"], "tangent": k["tangent"], "controls": k["controls"],
                                                **({"performer": who} if who else {})})
            self.keys.append({"sequence": seq, "performer": who,
                              **{n: k[n] for n in ("frame", "tangent", "controls", "types")}})
            self.dirty.add(seq)
            if self.user_dirty:
                self.dirty.add(self.user_dirty)
            if self.clip:
                ctl, ch, reached = self.clip
                if ctl in k["controls"] and ch in k["controls"][ctl]:
                    clipped.append({"control": ctl, "channel": ch, "asked": k["controls"][ctl][ch],
                                    "reached": reached, "f": k["frame"]})
            keyed += sum(len(v) for v in k["controls"].values())
        return {"keyed": keyed, "clipped": clipped}

    def layer_keys(self, inp):
        """The layer of a pass: recorded on the sequence; missing_channels names channels the section lacks."""
        missing = [n for n in inp["channels"] if n in self.missing_channels]
        if not missing:
            self.sequences[inp["sequence"]]["layer" + ("/" + inp["performer"] if inp.get("performer") else "")] =                 inp["channels"]
            self.dirty.add(inp["sequence"])
        return {"keyed": 0 if missing else sum(len(v) for v in inp["channels"].values()),
                "channels": len(inp["channels"]), "missing": missing, "collapsed": not missing, "sections": 1}

    def capture_frame(self, inp):
        self.captures.append(inp)
        if inp["stage"] == "pose":
            return {"stage": "pose", "frame": inp["frame"]}
        shown = self.capture_shown
        return {"stage": "shoot", "files": [inp["out_dir"] + "/" + v["name"] + ".png" for v in inp["views"]],
                "nonblack": {v["name"]: shown for v in inp["views"]}, "errors": [], "found": "the sequence's bound object"}

    def unload_kei(self, inp):
        self.unloads.append(list(inp["paths"]))
        if self.unload_error:
            return {"error": self.unload_error}
        return {"closed": True, "unloaded": len(inp["paths"]), "kept_dirty": [], "undo_cleared": True, "gc": True,
                "errors": []}

    def save_asset(self, inp):
        p = inp["path"]
        if not p.startswith("/Game/Kei/"):
            return {"error": "Kei saves only under /Game/Kei, not " + p}
        self.saved.append(p)
        self.dirty.discard(p)
        return {"saved": p}

    def open_sequence(self, inp):
        self.opened = inp["sequence"]
        return {"sequence": inp["sequence"], "reopened": True}

    def eval_rig(self, inp):
        """The bones in rig space on each frame asked for. Like the editor, it refuses a sequence that is not open."""
        if self.opened != inp["sequence"]:
            return {"error": "the sequence " + inp["sequence"] + " is not the one open in Sequencer"}
        bones = self.performer_bones.get(inp.get("performer") or "", self.bones)
        rows = {str(f): {b: p for b, p in bones(f).items() if b in inp["bones"]} for f in inp["frames"]}
        return {"frames": rows, "rest": {b: p for b, p in bones(0).items() if b in inp["bones"]},
                "controls": 107, "skipped": {"FLOAT": 6}, "missing": []}

    def bake(self, inp):
        if self.bake_error:
            return {"error": self.bake_error}
        if self.opened != inp["sequence"]:
            return {"error": "the sequence " + inp["sequence"] + " is not the one open in Sequencer"}
        if inp["asset"] in [b["asset"] for b in self.bakes]:
            return {"error": "the asset " + inp["asset"] + " already exists"}
        self.bakes.append(inp)
        self.saved.append(inp["asset"])
        return {"asset": inp["asset"], "frames": inp["end"] + 1, "ik_copy": "skeleton pose",
                "bones": 161, "skipped_bones": 185, "dirty": sorted(self.dirty)}

    def load_pose(self, inp):
        """The rig's backwards solve of one animation frame, read back. Like the editor, only on the open sequence."""
        if inp["sequence"] not in (self.opened, getattr(self, "made_open", None)):
            return {"error": "the sequence " + inp["sequence"] + " is not the one open in Sequencer"}
        if not inp["anim"].startswith("/Game/"):
            return {"error": "the animation " + inp["anim"] + " is not an animation sequence in the project"}
        self.poses.append(inp)
        self.dirty.add(inp["sequence"])
        if self.user_dirty:
            self.dirty.add(self.user_dirty)
        euler = {"location.x": 1.0, "location.y": 2.0, "location.z": 3.0, "rotation.x": 10.0, "rotation.y": 20.0,
                 "rotation.z": 30.0, "scale.x": 1.0, "scale.y": 1.0, "scale.z": 1.0}
        return {"sequence": inp["sequence"], "anim": inp["anim"], "frame": inp["frame"],
                "controls": {"foot_l_ik_ctrl": dict(euler), "pelvis_ctrl": dict(euler), "hand_l_fk_ctrl": dict(euler),
                             "spine_blend": {"value": 0.25}, "not_in_rig_ctrl": dict(euler)},
                "types": {}, "check": self.pose_check, "dirty": sorted(self.dirty)}

    def read_bake(self, inp):
        frames = {str(f): {b: v for b, v in self.baked(f).items() if b in inp["bones"]}
                  for f in range(inp["start"], inp["end"] + 1)}
        have = {b for row in frames.values() for b in row}
        return {"frames": frames, "missing": [b for b in inp["bones"] if b not in have], "total": 99}
