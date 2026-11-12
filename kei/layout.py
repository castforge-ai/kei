"""A delivered shot's folder: the finished files on top, the work behind them in one folder per phase.

pack(shot) -> manifest
  At sign-off (kei approve), on every shot whatever app it was keyed in. The shot folder keeps on top only what was
  delivered: the delivery videos (from video/), REVIEW.md, GROWTH.md, any exported file (.glb, .fbx), and a copy of
  the approved pass's shot.json named <shot>_final.json. Everything else moves under production/, one folder per
  phase, in the order the work was done:

      production/1_setup        CHARACTER.md, rig/, weight/, and the app's folder (unreal/, maya/)
      production/2_planning     PLAN.md, REFS.md, EXTENT.md, QUESTIONS.md, plan/
      production/3_blocking     out_blocking/, blocking_build/
      production/4_breakdowns   the breakdowns pass (GATES.md names it; else out_p1/)
      production/5_spline       the spline pass (else out_p2/)
      production/6_polish       the polish passes (else out_p3/ and later), passes_build/
      production/7_checks       GATES.md, CHECKS.md, checks_build/
      production/8_review       review_build/, SELF_REVIEW*.md
      production/9_probes       every other out_*/ folder: rig probes and tests
      production/other          anything else

  Every move is recorded in .kei/layout.json, so it can be undone exactly.
unpack(shot)
  Puts every file back where the stages expect it. Kei calls it before any command that works on a packed shot (a
  note that reopens it, an export, a render), and packs again after when the shot is still approved.
is_packed(shot), where(shot, rel) -> the path of a file named by its working path (rel), packed or not.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

PRODUCTION = "production"
MANIFEST = ".kei/layout.json"
TOP_FILES = {"REVIEW.md", "GROWTH.md"}
TOP_SUFFIXES = {".glb", ".fbx", ".gltf"}
FIXED = {
    "1_setup": {"CHARACTER.md", "rig", "weight", "unreal", "maya"},
    "2_planning": {"PLAN.md", "REFS.md", "EXTENT.md", "QUESTIONS.md", "plan"},
    "3_blocking": {"out_blocking", "blocking_build"},
    "6_polish": {"passes_build"},
    "7_checks": {"GATES.md", "CHECKS.md", "checks_build"},
    "8_review": {"review_build"},
}
PASS_PHASES = (("Breakdowns", "4_breakdowns"), ("Spline", "5_spline"), ("Polish", "6_polish"))


def is_packed(shot: Path) -> bool:
    return (Path(shot) / MANIFEST).is_file()


def _manifest(shot: Path) -> dict:
    try:
        return json.loads((Path(shot) / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def where(shot: Path, rel: str) -> Path:
    """The file a working path names (such as "plan/plan.json"), wherever it is now."""
    shot = Path(shot)
    moved = _manifest(shot).get("moved", {})
    head, _, rest = rel.replace("\\", "/").partition("/")
    if head in moved:
        return shot / moved[head] / rest if rest else shot / moved[head]
    return shot / rel


def _passes(shot: Path) -> list[int]:
    return sorted(int(m.group(1)) for p in shot.iterdir() if (m := re.fullmatch(r"out_p(\d+)", p.name)) and p.is_dir())


def pass_phases(shot: Path) -> dict[int, str]:
    """Each refined pass's phase: from the gates in GATES.md that name it, else p1 breakdowns, p2 spline, the rest
    polish."""
    numbers = _passes(shot)
    gates = (shot / "GATES.md").read_text(encoding="utf-8", errors="replace") if (shot / "GATES.md").is_file() else ""
    named: dict[int, str] = {}
    for title, phase in PASS_PHASES:
        for m in re.finditer(rf"^## {title} gate[^\n]*\n(.*?)(?=^## |\Z)", gates, re.M | re.S):
            heading = m.group(0).splitlines()[0]
            found = re.search(r"\bp(\d+)\b", heading) or re.search(r"\bout_p(\d+)\b|\bp(\d+)\b", m.group(1))
            if found:
                n = int(next(g for g in found.groups() if g))
                named.setdefault(n, phase)
    out = {}
    for n in numbers:
        out[n] = named.get(n) or ("4_breakdowns" if n == 1 else "5_spline" if n == 2 else "6_polish")
    return out


def _phase(name: str, path: Path, phases: dict[int, str]) -> str | None:
    """The production folder of a top-level entry, or None when it stays on top."""
    if name == ".kei" or name == PRODUCTION or name in TOP_FILES or path.suffix.lower() in TOP_SUFFIXES             or name.endswith("_report.html"):
        return None
    for phase, names in FIXED.items():
        if name in names:
            return phase
    m = re.fullmatch(r"out_p(\d+)", name)
    if m and path.is_dir():
        return phases.get(int(m.group(1)), "6_polish")
    if name.startswith("out_") and path.is_dir():
        return "9_probes"
    if re.fullmatch(r"SELF_REVIEW.*\.md", name):
        return "8_review"
    return "other"


def pack(shot: Path) -> dict:
    shot = Path(shot)
    if is_packed(shot):
        return _manifest(shot)
    phases = pass_phases(shot)
    final = max(phases) if phases else None
    copied = []
    if final is not None and (shot / f"out_p{final}" / "shot.json").is_file():
        dst = shot / f"{shot.name}_final.json"
        shutil.copyfile(shot / f"out_p{final}" / "shot.json", dst)
        copied.append(dst.name)
    lifted = []
    video = shot / "video"
    if video.is_dir():
        for f in sorted(video.iterdir()):
            if f.is_file() and not (shot / f.name).exists():
                f.rename(shot / f.name)
                lifted.append(f.name)
        if not any(video.iterdir()):
            video.rmdir()
    moved = {}
    for p in sorted(shot.iterdir()):
        if p.name in copied or p.name in lifted:
            continue
        phase = _phase(p.name, p, phases)
        if phase is None:
            continue
        dst = shot / PRODUCTION / phase / p.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        p.rename(dst)
        moved[p.name] = dst.relative_to(shot).as_posix()
    manifest = {"moved": moved, "lifted_from_video": lifted, "copied": copied,
                "final_pass": f"p{final}" if final is not None else None}
    (shot / MANIFEST).parent.mkdir(parents=True, exist_ok=True)
    (shot / MANIFEST).write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def unpack(shot: Path) -> None:
    shot = Path(shot)
    if not is_packed(shot):
        return
    m = _manifest(shot)
    for name, rel in m.get("moved", {}).items():
        src = shot / rel
        if src.exists() and not (shot / name).exists():
            src.rename(shot / name)
    lifted = m.get("lifted_from_video", [])
    if lifted:
        (shot / "video").mkdir(exist_ok=True)
        for name in lifted:
            if (shot / name).exists():
                (shot / name).rename(shot / "video" / name)
    for name in m.get("copied", []):
        (shot / name).unlink(missing_ok=True)
    prod = shot / PRODUCTION
    if prod.is_dir():
        for d in sorted(prod.rglob("*"), key=lambda p: -len(p.parts)):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        if not any(prod.iterdir()):
            prod.rmdir()
    (shot / MANIFEST).unlink()
