"""A stage holds only when it AND every stage before it hold, so a later stage cannot quietly break an earlier one."""
from __future__ import annotations

from pathlib import Path

from kei.gates.pipeline import check
from kei.stages import Stage, stages_through


def stage_misses(shot_dir: Path, stage: Stage) -> list[str]:
    codes = {c for s in stages_through(stage.id) for c in s.codes}
    misses, _notes = check(str(shot_dir), deliver=(stage.id == "deliver"))
    return [m for m in misses if m.split(" ", 1)[0] in codes]
