"""A small stand-in for maya.cmds, enough for the feedback layer tool: nodes with channels, animation layers (additive
or override, muted or not, with a weight) and their keys, locks and rotate limits. A channel's value at a frame is
Kei's pass (its base) with each unmuted layer on top, as Maya evaluates animation layers, at the current frame. As
in Maya 2027 (tests/maya/check_feedback.py), getAttr's time flag does not blend the layers, so the stand-in refuses it.
Adding a node to a layer adds every keyable channel of it, keyed or not (added=). The layer order, the selected and
preferred flags, moveLayerAfter, and an unflagged setKeyframe landing on the selected preferred layer as the
difference from what is under it, behave as tests/maya/check_feedback_layer.py shows in Maya 2027. No Maya needed."""
from __future__ import annotations

import sys
import types


def _at(keys: dict, f: float) -> float:
    """A layer curve's value at a frame: linear between keys, held before the first and after the last."""
    ts = sorted(keys)
    if f <= ts[0]:
        return keys[ts[0]]
    if f >= ts[-1]:
        return keys[ts[-1]]
    for a, b in zip(ts, ts[1:]):
        if a <= f <= b:
            return keys[a] + (keys[b] - keys[a]) * (f - a) / (b - a)
    raise AssertionError


class FakeCmds:
    def __init__(self, base: dict, units: str = "cm"):
        self.base = dict(base)                  # plug -> function of the frame (Kei's pass)
        self.layers: dict = {"BaseAnimation": {"mute": False, "override": False, "weight": 1.0, "keys": {},
                                               "added": [], "selected": False, "preferred": False}}
        self.selection: list = []
        self.locked: set = set()
        self.limits: dict = {}                  # plug -> (lo, hi) in degrees
        self.units = units
        self.time = 0.0
        self.edits: list = []                   # every edit= call, to see what a tool touched

    def add_layer(self, name, keys, override=False, mute=False, weight=1.0, added=()):
        """keys: {plug: {frame: value}}: an additive layer's values are offsets, an override layer's are values.
        added: channels on the layer with no key there (Maya adds a node's every channel)."""
        self.layers[name] = {"mute": mute, "override": override, "weight": weight, "keys": keys,
                             "added": list(added), "selected": False, "preferred": False}

    # ---- the cmds the tool calls ----
    def ls(self, *names, type=None, long=False):
        if type == "animLayer":
            return list(self.layers)
        return [n for n in names if n in self._nodes()]

    def _nodes(self):
        return {p.rsplit(".", 1)[0] for p in self.base}

    def objExists(self, name):
        return name in self.layers or name in self._nodes()

    def select(self, nodes=None, replace=False, clear=False):
        self.selection = [] if clear else list(nodes if isinstance(nodes, (list, tuple)) else [nodes])

    def animLayer(self, layer=None, q=False, edit=False, **kw):
        if not q and not edit:                  # make a layer: on top of the stack, additive unless override
            self.add_layer(layer, {}, override=bool(kw.get("override")))
            return layer
        lay = self.layers[layer]
        if edit:
            self.edits.append((layer, kw))
            if "mute" in kw:
                lay["mute"] = bool(kw["mute"])
            for flag in ("selected", "preferred"):
                if flag in kw:
                    lay[flag] = bool(kw[flag])
            if "moveLayerAfter" in kw:
                names = [n for n in self.layers if n != layer]
                names.insert(names.index(kw["moveLayerAfter"]) + 1, layer)
                self.layers = {n: self.layers[n] for n in names}
            if kw.get("addSelectedObjects"):
                lay["added"] += [p for p in self.base if p.rsplit(".", 1)[0] in self.selection
                                 and p not in lay["added"]]
            return None
        if kw.get("children"):
            return [n for n in self.layers if n != "BaseAnimation"]
        for flag in ("selected", "preferred"):
            if kw.get(flag):
                return lay[flag]
        if kw.get("mute"):
            return lay["mute"]
        if kw.get("override"):
            return lay["override"]
        if kw.get("weight"):
            return lay["weight"]
        if kw.get("attribute"):
            return list(dict.fromkeys(list(lay["added"]) + list(lay["keys"]))) or None
        if "findCurveForPlug" in kw:
            plug = kw["findCurveForPlug"]
            return [f"{layer}__{plug}"] if plug in lay["keys"] else None
        raise NotImplementedError(kw)

    def keyframe(self, curve, q=False, timeChange=False):
        layer, plug = curve.split("__", 1)
        return sorted(float(t) for t in self.layers[layer]["keys"][plug])

    def setKeyframe(self, node, attribute=None, time=None, value=None, animLayer=None):
        """An animator's key: on the layer named, else on the one selected and preferred layer, else the base. On an
        additive layer the key holds the difference from what is under it, as Maya keys it."""
        plug = f"{node}.{attribute}"
        target = animLayer or next((n for n, lay in self.layers.items() if lay["selected"] and lay["preferred"]),
                                   "BaseAnimation")
        f = self.time if time is None else float(time)
        below = self._value(plug, f, until=target)
        lay = self.layers[target]
        lay["keys"].setdefault(plug, {})[f] = value if lay["override"] else value - below

    def _value(self, plug, f, until=None):
        v = self.base[plug](f)
        for name, lay in self.layers.items():
            if name == until:
                break
            if lay["mute"] or plug not in lay["keys"]:
                continue
            x = _at(lay["keys"][plug], f)
            v = v + (x - v) * lay["weight"] if lay["override"] else v + x * lay["weight"]
        return v

    def getAttr(self, plug, time=None, lock=False):
        if lock:
            return plug in self.locked
        if time is not None:
            raise AssertionError("getAttr's time flag does not blend animation layers in Maya: read the frame made "
                                 "current")
        return self._value(plug, self.time)

    def currentTime(self, f=None, q=False, update=True):
        if q:
            return self.time
        self.time = float(f)
        return self.time

    def nodeType(self, node):
        return "transform"

    def transformLimits(self, node, q=False, **kw):
        flag = next(iter(kw))
        attr = {"rx": "rotateX", "ry": "rotateY", "rz": "rotateZ", "tx": "translateX", "ty": "translateY",
                "tz": "translateZ"}[flag.lstrip("e") if flag.startswith("e") and len(flag) == 3 else flag]
        lim = self.limits.get(f"{node}.{attr}")
        if flag.startswith("e") and len(flag) == 3:
            return [lim is not None, lim is not None]
        return list(lim) if lim else [0.0, 0.0]

    def currentUnit(self, q=False, linear=False, angle=False, **kw):
        return self.units if linear else "deg"

    def upAxis(self, q=False, axis=False):
        return "y"


def install(monkeypatch, cmds: FakeCmds) -> None:
    """Make `from maya import cmds` give the fake for the rest of the test."""
    maya = types.ModuleType("maya")
    maya.cmds = cmds
    monkeypatch.setitem(sys.modules, "maya", maya)
    monkeypatch.setitem(sys.modules, "maya.cmds", cmds)


def _undo(self, **kw):
    self.edits.append(("undo", kw))


FakeCmds.undoInfo = _undo
