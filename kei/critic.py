"""The critic: a separate reviewer seat that judges a stage from the shot's artifacts and answers pass or send back."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from kei.prompts import HERE as PROMPTS, _artifacts
from kei.seats import Seat, SeatPaused, pause_kind
from kei.stages import Stage

VERDICTS = ("pass", "send_back")
REVIEWED_STAGES = ("plan", "blocking", "passes")
SEAT_ERROR_CHARS = 300
EARLIER_MAX = 6   # the latest send-backs of the stage a critic sees; older ones are counted, not listed


@dataclass(frozen=True)
class Verdict:
    passed: bool
    notes: list[str]
    questions: tuple = ()     # {"text", "look_at": [paths]}: what the critic asks the author
    sign_off: tuple = ()      # checks only the author can make, left for the sign-off
    records: tuple = ()       # records the critic wants written or brought up to date: a note, never a send-back


class PanelNotes(list):
    """The panel's send-back notes (a list, empty when every critic passed), with the questions the critics asked the
    author, the checks they left for the author's sign-off and the records they want written."""

    def __init__(self, notes=(), questions=(), sign_off=(), records=()):
        super().__init__(notes)
        self.questions = list(questions)
        self.sign_off = list(sign_off)
        self.records = list(records)


PATH = re.compile(r"[\w./\\-]+\.(?:mp4|gif|png|jpg|json|md|txt)\b")


def look_at_paths(text: str) -> list[str]:
    """The files a question names, in order, once each."""
    out = []
    for m in PATH.findall(text or ""):
        if m not in out:
            out.append(m)
    return out


def _question(q) -> dict | None:
    if isinstance(q, str) and q.strip():
        return {"text": q.strip(), "look_at": look_at_paths(q)}
    if isinstance(q, dict) and isinstance(q.get("text"), str) and q["text"].strip():
        look = q.get("look_at", [])
        if isinstance(look, str):
            look = [look]
        look = [x for x in look if isinstance(x, str)] if isinstance(look, list) else []
        return {"text": q["text"].strip(), "look_at": look or look_at_paths(q["text"])}
    return None


def _label(critic: str, note: str) -> str:
    prefix = f"critic {critic}: "
    return note if note.startswith(prefix) else prefix + note


def _verdict_line(line: str) -> dict | None:
    try:
        data = json.loads(line.strip())
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("verdict") not in VERDICTS:
        return None
    notes = data.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(n, str) for n in notes):
        return None
    return data


def parse_verdict(critic: str, output: str) -> Verdict:
    """Read the last line of the critic's answer that is a JSON verdict. No such line is a send-back."""
    for line in reversed(output.splitlines()):
        data = _verdict_line(line)
        if data is None:
            continue
        notes = [_label(critic, n) for n in data.get("notes", [])]
        raw_q = data.get("questions", [])
        questions = tuple(q for q in map(_question, raw_q if isinstance(raw_q, list) else []) if q)
        raw_s = data.get("sign_off", [])
        sign_off = tuple(s.strip() for s in (raw_s if isinstance(raw_s, list) else [])
                         if isinstance(s, str) and s.strip())
        raw_r = data.get("records", [])
        records = tuple(_label(critic, r.strip()) for r in (raw_r if isinstance(raw_r, list) else [])
                        if isinstance(r, str) and r.strip())
        if data["verdict"] == "pass" or (not notes and records):   # records alone are a note, not a send-back
            return Verdict(True, notes if data["verdict"] == "pass" else [], questions, sign_off, records)
        return Verdict(False, notes or [_label(critic, "sent back with no reason")], questions, sign_off, records)
    return Verdict(False, [_label(critic, "no verdict line")])


def answers_block(answers: list[dict]) -> list[str]:
    """The author's answers so far, as prompt lines (empty when there are none)."""
    if not answers:
        return []
    lines = ["The author's answers to the questions asked so far. A recorded viewing is the author's own:"]
    for a in answers:
        lines.append(f"- at {a.get('stage', '?')}: asked: {a.get('question', '').strip()}")
        lines.append(f"  answered: {a.get('answer', '').strip()}")
    return lines


def earlier_block(earlier: list[list[str]]) -> list[str]:
    """The stage's earlier send-backs, oldest first, the latest EARLIER_MAX of them."""
    if not earlier:
        return []
    shown = earlier[-EARLIER_MAX:]
    lines = ["Earlier send-backs of this stage, oldest first. Do not reverse an earlier note without saying so: if a "
             "note now asks the opposite of one below, name the earlier note and say why it changed."]
    if len(earlier) > len(shown):
        lines.append(f"({len(earlier) - len(shown)} older send-backs are not listed.)")
    for i, notes in enumerate(shown, len(earlier) - len(shown) + 1):
        lines.append(f"Send-back {i}:")
        lines += [f"- {n}" for n in notes]
    return lines


def critic_prompt(stage: Stage, shot_dir: Path, request: str, changed_plan: list[str], rules: str = "",
                  answers: list[dict] = (), earlier: list[list[str]] = (), author_notes: list[str] = ()) -> str:
    """What a critic sees: its instructions, the request and the shot's files. Never the animator's conversation."""
    lines = [
        (PROMPTS / "critic.md").read_text(encoding="utf-8").strip(),
        "",
        f"Request: {request}",
        f"Stage under review: {stage.title}",
        "",
    ]
    if rules:
        lines += [rules, ""]
    if answers:
        lines += [*answers_block(answers), ""]
    if author_notes:
        lines += ["The author's notes for this stage, oldest first. Judge the work against them too:",
                  *[f"- {n}" for n in author_notes], ""]
    if earlier:
        lines += [*earlier_block(list(earlier)), ""]
    lines += ["In the shot folder:"]
    lines += [f"- {a}" for a in _artifacts(shot_dir)] or ["- (nothing yet)"]
    if changed_plan:
        lines += ["", f"The plan changed since it was approved: {', '.join(changed_plan)}. Judge the change first: "
                  "was it needed, and does the work now follow the new plan? The approved copy is in .kei/approved_plan/."]
    return "\n".join(lines) + "\n"


def _badly_worded(checks) -> list[tuple[str, str]]:
    from kei.checklist import check_wording
    return [(c, why) for c in checks if (why := check_wording(c))]


def _rewording(bad: list[tuple[str, str]]) -> str:
    from kei.checklist import WORDING
    lines = ["", "Kei did not take your sign-off checks: the author answers each one by eye, so each must read "
             f"{WORDING}.", "Not taken:"]
    lines += [f"- {c} ({why})" for c, why in bad]
    lines += ["Answer again with the same verdict and notes, and the sign-off checks rewritten."]
    return "\n".join(lines) + "\n"


def panel_review(stage: Stage, shot_dir: Path, request: str, critics: list[Seat],
                 changed_plan: list[str] | None = None, rules: str = "", answers: list[dict] = (),
                 earlier: list[list[str]] = (), author_notes: list[str] = ()) -> PanelNotes:
    """Run every critic on the stage. Any send-back wins; a critic that cannot answer counts as a send-back, except
    one that hit a usage limit or could not start: that raises SeatPaused, and the stage pauses."""
    changed = list(changed_plan or []) if stage.id != "plan" else []
    if stage.id not in REVIEWED_STAGES and not changed:
        return PanelNotes()
    prompt = critic_prompt(stage, shot_dir, request, changed, rules, answers, earlier, author_notes)
    notes: list[str] = []
    questions: list[dict] = []
    sign_off: list[dict] = []
    records: list[str] = []
    for seat in critics:
        result = seat.run(prompt, Path(shot_dir))
        kind = pause_kind(result)
        if kind:
            raise SeatPaused(kind, seat.name, result.output.strip()[:SEAT_ERROR_CHARS])
        if result.exit_code != 0:
            why = result.output.strip()[:SEAT_ERROR_CHARS] or f"the seat exited with code {result.exit_code}"
            notes.append(_label(seat.name, why))
            continue
        verdict = parse_verdict(seat.name, result.output)
        bad = _badly_worded(verdict.sign_off)
        if bad:   # asked once more, with the reasons; the stage's work is not the question here
            again = seat.run(prompt + _rewording(bad), Path(shot_dir))
            kind = pause_kind(again)
            if kind:
                raise SeatPaused(kind, seat.name, again.output.strip()[:SEAT_ERROR_CHARS])
            if again.exit_code == 0:
                verdict = parse_verdict(seat.name, again.output)
            bad = _badly_worded(verdict.sign_off)
            if bad:
                notes.append(_label(seat.name, "its sign-off checks are not in the author's wording after two tries: "
                                    + "; ".join(f"{c!r} ({why})" for c, why in bad)))
                verdict = Verdict(verdict.passed, verdict.notes, verdict.questions, (), verdict.records)
        if not verdict.passed:
            notes += verdict.notes
        questions += [{**q, "from": f"critic {seat.name}"} for q in verdict.questions]
        sign_off += [{"from": f"critic {seat.name}", "check": s} for s in verdict.sign_off]
        records += verdict.records
    return PanelNotes(notes, questions, sign_off, records)
