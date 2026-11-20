"""kei check --explain: one flag in plain lines, read from the reports kei check wrote for the pass.

A principle flag is named by its id (principle.kind.part.f<first frame>). A body check flag has no id of its own, so
it is named the same way: check.part.f<first frame>, with "body" for a flag on no one part. A name may be the start of
an id ("balance", "arcs.hand_r_tip", "solid_drawing.twin_pose"), and a principle id whose first frame moved by a few
frames since it was copied still finds its flag.
"""
from __future__ import annotations

import json
from pathlib import Path

from kei.gates.pipeline import DECLARED_DRIFT, _FLAG_ID


def body_id(flag: dict) -> str:
    return f"{flag['check']}.{flag.get('part') or 'body'}.f{flag['frames'][0]}"


def _read(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except ValueError:
        return None


def _matches(fid: str, ref: str) -> bool:
    return fid == ref or fid.startswith(ref + ".")


def _near(fid: str, ref: str) -> bool:
    a, b = _FLAG_ID.match(fid), _FLAG_ID.match(ref)
    return bool(a and b and a.group(1) == b.group(1) and abs(int(a.group(2)) - int(b.group(2))) <= DECLARED_DRIFT)


def _pick(flags: list[tuple[str, dict]], ref: str) -> list[tuple[str, dict]]:
    hits = [(i, f) for i, f in flags if _matches(i, ref)]
    return hits or [(i, f) for i, f in flags if _near(i, ref)]


def _limit_lines(names, thresholds: dict, scale: float | None) -> list[str]:
    out = []
    for n in names:
        if n in thresholds:
            v = thresholds[n]
            out.append(f"  limit {n} = {v}" + (f" (scaled by the character's height x{scale})"
                                               if scale not in (None, 1, 1.0) else ""))
    return out


def explain(out_dir: Path, ref: str) -> list[str]:
    """The lines that explain every flag of out_<pass> that ref names. Empty when none does."""
    from kei.principles import LIMITS_OF
    out_dir = Path(out_dir)
    ref = ref.strip().strip("`")
    lines: list[str] = []
    body = _read(out_dir / "body_check" / "body_check.json") or {}
    for fid, f in _pick([(body_id(f), f) for f in body.get("flags", [])], ref):
        lines.append(f"{fid} (body check {f['check']}), frames {f['frames'][0]}-{f['frames'][1]}")
        lines.append(f"  {f['what']}")
        if "measure" in f:
            lines.append(f"  measured {f['measure']} = {f.get('value')}")
        stem = str(f.get("measure") or f["check"]).split("_")[0]
        for k, t in (body.get("thresholds") or {}).items():
            if k.split("_")[0] == stem:
                v, src = (t.get("value"), t.get("source")) if isinstance(t, dict) else (t, None)
                lines.append(f"  limit {k} = {v}" + (f" ({src})" if src else ""))
        kind = "a hard fault" if f.get("rule") == "hard" else "a soft flag"
        why = (" inside her style range" if f.get("inside_style") else
               " the register is pushed" if f.get("note") else "")
        lines.append(f"  {kind}" + (f", shown as a note:{why}" if why else ""))
    pr = _read(out_dir / "principles" / "principles.json") or {}
    flags = [(f["id"], f) for f in pr.get("flags", [])] or [
        (f["id"], f) for s in (pr.get("principles") or {}).values() for f in s.get("flags", [])]
    for fid, f in _pick(flags, ref):
        principle, kind = fid.split(".")[:2]
        lines.append(f"{fid} (principle {principle}), frames {f['frames'][0]}-{f['frames'][1]}, rule {f.get('rule')}")
        lines.append(f"  {f['what']}")
        measured = ((pr.get("principles") or {}).get(principle) or {}).get("measured") or {}
        for k, v in measured.items():
            if f.get("part") and (k == f["part"] or k.startswith(f["part"])):
                lines.append(f"  measured {k} = {json.dumps(v)}")
        lines += _limit_lines(LIMITS_OF.get(kind, ()), pr.get("thresholds") or {}, pr.get("scale"))
        lines.append(f"  fix it at a key, or declare it in GATES.md under \"## Declared\" as \"- {fid}: <reason>\"")
    return lines
