"""The twelve stages of a shot. Every shot runs every stage, in this order. Nothing skips a stage."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    id: str
    title: str
    codes: tuple[str, ...]   # the gate codes this stage must clear (see kei/gates/pipeline.py)


STAGES: tuple[Stage, ...] = (
    Stage("brief", "Brief", ("P1",)),
    Stage("rig", "Rig evaluation", ("P2",)),
    Stage("weight", "Weight evaluation", ("P3",)),
    Stage("understanding", "Understanding score", ("P4",)),
    Stage("references", "Reference search", ("P5",)),
    Stage("study", "Study", ("P6",)),
    Stage("plan", "Plan", ("P7",)),
    Stage("blocking", "Blocking", ("P8",)),
    Stage("passes", "Breakdowns, spline and polish", ("P9", "ORDER")),
    Stage("checks", "All the checks", ("P10",)),
    Stage("self_review", "Self-review", ("P11",)),
    Stage("deliver", "Delivery", ("P12",)),
)

_INDEX = {s.id: i for i, s in enumerate(STAGES)}


def stage_by_id(stage_id: str) -> Stage:
    return STAGES[_INDEX[stage_id]]


def next_stage(stage_id: str) -> Stage | None:
    i = _INDEX[stage_id] + 1
    return STAGES[i] if i < len(STAGES) else None


def stages_through(stage_id: str) -> tuple[Stage, ...]:
    """This stage and every stage before it."""
    return STAGES[: _INDEX[stage_id] + 1]
