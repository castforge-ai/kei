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

    def handlers(self) -> dict:
        return {"probe": self.probe, "make_sequence": self.make_sequence, "read_rig": self.read_rig,
                "dirty": self.get_dirty, "set_keys": self.set_keys, "save_asset": self.save_asset,
                "open_sequence": self.open_sequence, "eval_rig": self.eval_rig, "bake": self.bake,
                "read_bake": self.read_bake, "organize": self.organize}

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
                                "keys": []}
        return {"path": path, "fps": int(inp["fps"]), "frames": inp["frames"], "facing": "yaw -90", "dirty": []}

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
        seq = inp["sequence"]
        self.sequences[seq]["keys"].append({"f": inp["frame"], "tangent": inp["tangent"], "controls": inp["controls"]})
        self.keys.append(inp)
        self.dirty.add(seq)
        if self.user_dirty:
            self.dirty.add(self.user_dirty)
        clipped = []
        if self.clip:
            ctl, ch, reached = self.clip
            if ctl in inp["controls"] and ch in inp["controls"][ctl]:
                clipped.append({"control": ctl, "channel": ch, "asked": inp["controls"][ctl][ch], "reached": reached})
        return {"keyed": sum(len(v) for v in inp["controls"].values()), "clipped": clipped}

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
        rows = {str(f): {b: p for b, p in self.bones(f).items() if b in inp["bones"]} for f in inp["frames"]}
        return {"frames": rows, "rest": {b: p for b, p in self.bones(0).items() if b in inp["bones"]},
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

    def read_bake(self, inp):
        frames = {str(f): {b: v for b, v in self.baked(f).items() if b in inp["bones"]}
                  for f in range(inp["start"], inp["end"] + 1)}
        have = {b for row in frames.values() for b in row}
        return {"frames": frames, "missing": [b for b in inp["bones"] if b not in have], "total": 99}
