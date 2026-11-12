"""A delivered Unreal shot's folder in the editor, filed like the shot folder (kei.layout): Kei's folder for the shot,
/Game/Kei/<shot>/, keeps on top only the delivered sequence (the last one of the final pass) and the baked animation;
every other sequence Kei made moves to Production/<phase>/ in the same folder, in the phase order of production/.

plan_moves(shot_dir, book, phases, final) -> [[from, to]]
tidy(client, shot_dir) -> {"moved", "failed"}: runs the moves through organize.py and records the new paths in
  unreal/sequences.json, so every later command (an export, a reopened shot) finds each sequence where it is.
"""
from __future__ import annotations

from pathlib import Path

from kei import layout
from kei.apps.unreal import Claireon, run_script
from kei.apps.unreal_rig import _write, kei_folder, sequences, sequences_path

FOLDERS = {"1_setup": "1_Setup", "2_planning": "2_Planning", "3_blocking": "3_Blocking",
           "4_breakdowns": "4_Breakdowns", "5_spline": "5_Spline", "6_polish": "6_Polish", "9_probes": "9_Probes"}


def _phase(pass_name: str, phases: dict[int, str]) -> str:
    if pass_name in ("rig", "probe"):
        return "1_setup"
    if pass_name == "blocking":
        return "3_blocking"
    if pass_name.startswith("p") and pass_name[1:].isdigit():
        return phases.get(int(pass_name[1:]), "6_polish")
    return "9_probes"


def plan_moves(shot_dir: Path, book: dict, phases: dict[int, str], final: str | None) -> list[list[str]]:
    folder = kei_folder(shot_dir)
    keep = book.get(final, [])[-1:] if final else []
    moves = []
    for pass_name, paths in book.items():
        sub = f"{folder}/Production/{FOLDERS[_phase(pass_name, phases)]}"
        for p in paths:
            if p in keep or not p.startswith(folder + "/") or "/Production/" in p:
                continue
            moves.append([p, f"{sub}/{p.rsplit('/', 1)[-1]}"])
    return moves


def tidy(client: Claireon, shot_dir: Path) -> dict:
    shot_dir = Path(shot_dir)
    phases = layout.pass_phases(shot_dir)
    final = f"p{max(phases)}" if phases else None
    book = sequences(shot_dir)
    moves = plan_moves(shot_dir, book, phases, final)
    out = run_script(client, "organize.py", {"folder": kei_folder(shot_dir), "moves": moves})
    where = dict(out.get("moved", []))
    _write(sequences_path(shot_dir), {k: [where.get(p, p) for p in v] for k, v in book.items()})
    return {"moved": out.get("moved", []), "failed": out.get("failed", []),
            "kept": book.get(final, [])[-1:] if final else [], "content_dir": out.get("content_dir")}
