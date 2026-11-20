"""Arcs as a person sees them: spacing pops and wobble, in the world and against the chest.

kei check's first arc rule only catches a turn over ARC_KINK within one frame, in world space, so a lumpy or zigzag
path passes, and a hand's path is mostly the root's travel. These measures add:

  spacing pop   a frame whose step is more than POP_RATIO times both neighbouring steps, while the part moves: the
                part jumps ahead for one frame (the snaps the critics kept finding: a wrist 19 cm in a frame).
  wobble        over WOBBLE_WINDOW frames, the path turns by more than WOBBLE_TURN degrees in all and changes the side
                it turns to at least WOBBLE_FLIPS times: a zigzag, not an arc (an arc keeps turning one way).

They run on the world paths of the parts below and on the hands and the head against the chest (spine_05), where the
body's travel no longer hides them. Spline passes only: a stepped pass jumps from key to key by design.
"""
from __future__ import annotations

import math

POP_RATIO = 2.5
POP_MIN = 0.006            # m per frame: a step this small is not a pop, whatever its ratio (scaled by height)
WOBBLE_WINDOW = 6
WOBBLE_TURN = 200.0        # degrees of turning, summed over the window
WOBBLE_FLIPS = 3           # times the turning changes side within the window: an arc keeps one side
MOVING = 0.004             # m per frame: slower steps are ignored (scaled by height)
WORLD_PARTS = ("head", "pelvis", "hand_l_tip", "hand_r_tip", "lowerarm_l", "lowerarm_r", "spine_05", "ball_l_tip",
               "ball_r_tip")
CHEST_PARTS = ("hand_l_tip", "hand_r_tip", "head")
CHEST = "spine_05"


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _len(v) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def _cross(u, v):
    return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])


def _dot(u, v) -> float:
    return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]


def _angle(u, v) -> float:
    lu, lv = _len(u), _len(v)
    if lu < 1e-12 or lv < 1e-12:
        return 0.0
    c = (u[0] * v[0] + u[1] * v[1] + u[2] * v[2]) / (lu * lv)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _paths(frames: list[dict]) -> dict[str, list[tuple[int, tuple]]]:
    out: dict[str, list] = {}
    for fr in frames:
        j = fr["joints"]
        for p in WORLD_PARTS:
            if p in j:
                out.setdefault(p, []).append((fr["f"], j[p]))
        if CHEST in j:
            c = j[CHEST]
            for p in CHEST_PARTS:
                if p in j:
                    out.setdefault(f"{p} against the chest", []).append((fr["f"], _sub(j[p], c)))
    return out


def arc_flags(frames: list[dict], k: float = 1.0) -> list[dict]:
    """The spacing-pop and wobble flags of a spline pass, in kei check's flag shape (soft: they carry a measure)."""
    flags = []
    pop_min, moving = POP_MIN * k, MOVING * k
    for part, path in _paths(frames).items():
        steps = [(path[i][0], _sub(path[i][1], path[i - 1][1])) for i in range(1, len(path))]
        for i in range(1, len(steps) - 1):
            f, s = steps[i]
            a, b, c = _len(steps[i - 1][1]), _len(s), _len(steps[i + 1][1])
            if b >= pop_min and b > POP_RATIO * max(a, c, 1e-9):
                flags.append({"check": "arcs", "part": part, "frames": [f, f], "measure": "spacing_pop_ratio",
                              "value": round(b / max(a, c, 1e-9), 1),
                              "what": f"the {part} jumps {b * 100:.1f} cm in one frame at f{f}, "
                                      f"{b / max(a, c, 1e-9):.1f} times the frames around it: a spacing pop"})
        moving_steps = [(f, s) for f, s in steps if _len(s) >= moving]
        i = 0
        while i + WOBBLE_WINDOW <= len(moving_steps):
            win = moving_steps[i:i + WOBBLE_WINDOW]
            if win[-1][0] - win[0][0] != WOBBLE_WINDOW - 1:   # only runs of consecutive moving frames
                i += 1
                continue
            turn = sum(_angle(win[n][1], win[n + 1][1]) for n in range(len(win) - 1))
            # an arc keeps turning the same way; a zigzag turns one way, then the other
            crosses = [_cross(win[n][1], win[n + 1][1]) for n in range(len(win) - 1)]
            flips = sum(1 for a, b in zip(crosses, crosses[1:]) if _dot(a, b) < 0)
            net = _angle(tuple(sum(s[1][c] for s in win) for c in range(3)), win[0][1])
            if turn > WOBBLE_TURN and flips >= WOBBLE_FLIPS:
                flags.append({"check": "arcs", "part": part, "frames": [win[0][0], win[-1][0]],
                              "measure": "arc_wobble_deg", "value": round(turn),
                              "what": f"the {part} path zigzags over f{win[0][0]}-{win[-1][0]}: it turns "
                                      f"{turn:.0f} deg in all, changing side {flips} times, and heads "
                                      f"{net:.0f} deg from where it started: a wobble, not an arc"})
                i += WOBBLE_WINDOW
                continue
            i += 1
    return flags
