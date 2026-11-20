"""Matched IK and FK switching: at a frame, key the other mode so it gives the same pose, and switch with no snap.

match(pose, proportions, limb, to) -> (channels, report)
  limb is armL, armR, legL or legR; to is "ik" or "fk". The pose is the full pose on that frame. Kei solves it as it
  plays now, then finds the other mode's channels that put the same joints in the same place:
    arm to ik   ik<s> = the wrist where the arm is, weight 1; pole<s> = a point out past the elbow, weight 1.
    arm to fk   ik<s> weight 0, and arm<s> (pitch, roll, twist) and elbow<s> (flex, pron) fitted so the elbow, the
                wrist and the hand's tip land where they were.
    leg to fk   legFK<s> fitted so the knee and the ankle land where they were, weight 1.
    leg to ik   legFK<s> weight 0, and foot<s> (its x, y, z) and knee<s> fitted so the knee and the ankle stay.
  report gives the largest joint gap after the fit (metres): a match is good under MATCH_TOL.
The fit is a small damped least squares on the channels named above; nothing else in the pose changes.
"""
from __future__ import annotations

import copy
import math

from kei.rig import full_pose, solve

MATCH_TOL = 0.002      # metres: a matched switch moves no joint more than this
LIMBS = ("armL", "armR", "legL", "legR")


class MatchError(ValueError):
    pass


def _targets(limb: str) -> list[str]:
    s = limb[-1].lower()
    if limb.startswith("arm"):
        return [f"lowerarm_{s}", f"hand_{s}", f"hand_{s}_tip"]
    return [f"calf_{s}", f"foot_{s}"]


def _gap(j: dict, want: dict) -> float:
    return max(math.dist(j[n], want[n]) for n in want)


def _fit(pose: dict, proportions, slots: list[tuple[str, int]], want: dict, iters: int = 60) -> dict:
    """Damped Gauss-Newton on the channel slots (channel, index) so the named joints reach want."""
    p = copy.deepcopy(pose)

    def resid(q):
        j = solve(q, proportions)
        return [c for n in want for c in (j[n][0] - want[n][0], j[n][1] - want[n][1], j[n][2] - want[n][2])]

    lam, h = 1e-3, 1e-5
    r = resid(p)
    cost = sum(x * x for x in r)
    for _ in range(iters):
        if cost < 1e-12:
            break
        cols = []
        for ch, i in slots:
            q = copy.deepcopy(p)
            _bump(q, ch, i, h)
            cols.append([(a - b) / h for a, b in zip(resid(q), r)])
        n = len(slots)
        jtj = [[sum(cols[a][k] * cols[b][k] for k in range(len(r))) for b in range(n)] for a in range(n)]
        jtr = [sum(cols[a][k] * r[k] for k in range(len(r))) for a in range(n)]
        while True:
            m = [[jtj[a][b] + (lam * (jtj[a][a] + 1e-9) if a == b else 0.0) for b in range(n)] for a in range(n)]
            step = _solve_lin(m, [-x for x in jtr])
            q = copy.deepcopy(p)
            for (ch, i), d in zip(slots, step):
                _bump(q, ch, i, d)
            rq = resid(q)
            cq = sum(x * x for x in rq)
            if cq < cost:
                p, r, cost, lam = q, rq, cq, max(lam / 3, 1e-9)
                break
            lam *= 4
            if lam > 1e6:
                return p
    return p


def _bump(q: dict, ch: str, i: int | None, d: float) -> None:
    if i is None:
        q[ch] += d
    else:
        q[ch][i] += d


def _solve_lin(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        if abs(m[c][c]) < 1e-15:
            continue
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [x - f * y for x, y in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-15 else 0.0 for i in range(n)]


def match(pose: dict, proportions: dict | None, limb: str, to: str) -> tuple[dict, dict]:
    if limb not in LIMBS:
        raise MatchError(f"the limb is one of {', '.join(LIMBS)}, not {limb!r}")
    if to not in ("ik", "fk"):
        raise MatchError(f"switch to ik or fk, not {to!r}")
    side = limb[-1]
    s = side.lower()
    p = full_pose(pose)
    p = {k: (list(v) if isinstance(v, (list, tuple)) else v) for k, v in p.items()}
    now = solve(p, proportions)
    want = {n: now[n] for n in _targets(limb)}
    q = copy.deepcopy(p)
    if limb.startswith("arm") and to == "ik":
        wrist, elbow, sh = now[f"hand_{s}"], now[f"lowerarm_{s}"], now[f"upperarm_{s}"]
        mid = tuple((a + b) / 2 for a, b in zip(sh, wrist))
        out = tuple(e - m for e, m in zip(elbow, mid))
        n = math.sqrt(sum(c * c for c in out)) or 1.0
        q[f"ik{side}"] = [*wrist, 1.0]
        q[f"pole{side}"] = [*(e + 0.3 * c / n for e, c in zip(elbow, out)), 1.0]
        changed = [f"ik{side}", f"pole{side}"]
    elif limb.startswith("arm"):
        q[f"ik{side}"] = [*q[f"ik{side}"][:3], 0.0]
        q[f"pole{side}"] = [*q[f"pole{side}"][:3], 0.0]
        q = _fit(q, proportions, [(f"arm{side}", 0), (f"arm{side}", 1), (f"arm{side}", 2), (f"elbow{side}", 0),
                                  (f"elbow{side}", 1)], want)
        changed = [f"ik{side}", f"pole{side}", f"arm{side}", f"elbow{side}"]
    elif to == "fk":
        start = q[f"legFK{side}"]
        q[f"legFK{side}"] = [*start[:4], 1.0]
        if not any(start[:4]):
            q[f"legFK{side}"][3] = 0.2     # a little knee bend to start the fit from
        q = _fit(q, proportions, [(f"legFK{side}", i) for i in range(4)], want)
        changed = [f"legFK{side}"]
    else:
        q[f"legFK{side}"] = [*q[f"legFK{side}"][:4], 0.0]
        q = _fit(q, proportions, [(f"foot{side}", 0), (f"foot{side}", 1), (f"foot{side}", 2), (f"knee{side}", None)],
                 want)
        changed = [f"legFK{side}", f"foot{side}", f"knee{side}"]
    gap = _gap(solve(q, proportions), want)
    return {c: q[c] for c in changed}, {"limb": limb, "to": to, "gap_m": round(gap, 5), "matched": gap <= MATCH_TOL}
