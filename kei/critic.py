"""The critic: a separate reviewer seat that judges a stage from the shot's artifacts and answers pass or send back."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from kei.prompts import HERE as PROMPTS, _artifacts, stage_contract
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
    minor: tuple = ()         # small things the animator reads: never a send-back
    earlier: tuple = ()       # (note, "fixed" | "not fixed") for the stage's earlier send-back notes


class PanelNotes(list):
    """The panel's send-back notes (a list, empty when every critic passed), with the questions the critics asked the
    author, the checks they left for the author's sign-off and the records they want written."""

    def __init__(self, notes=(), questions=(), sign_off=(), records=(), minor=(), earlier=()):
        super().__init__(notes)
        self.questions = list(questions)
        self.sign_off = list(sign_off)
        self.records = list(records)
        self.minor = list(minor)
        self.earlier = list(earlier)


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


def _verdict_objects(output: str):
    """Every JSON verdict in the answer, last first: whole lines first, then objects spread over several lines or
    inside a code fence."""
    for line in reversed(output.splitlines()):
        data = _verdict_line(line)
        if data is not None:
            yield data
    text = re.sub(r"```(?:json)?", "", output)
    starts = [m.start() for m in re.finditer(r"\{", text)]
    dec = json.JSONDecoder()
    for i in reversed(starts):
        try:
            obj, _ = dec.raw_decode(text[i:])
        except ValueError:
            continue
        data = _verdict_line(json.dumps(obj)) if isinstance(obj, dict) else None
        if data is not None:
            yield data


def has_verdict(output: str) -> bool:
    return next(_verdict_objects(output), None) is not None


def parse_verdict(critic: str, output: str) -> Verdict:
    """Read the critic's last JSON verdict (one line, or an object over several lines). No verdict is a send-back
    here; panel_review asks once more and then pauses the stage as a machine fault instead."""
    for data in _verdict_objects(output):
        notes = [_label(critic, n) for n in data.get("notes", [])]
        raw_q = data.get("questions", [])
        questions = tuple(q for q in map(_question, raw_q if isinstance(raw_q, list) else []) if q)
        raw_s = data.get("sign_off", [])
        sign_off = tuple(s.strip() for s in (raw_s if isinstance(raw_s, list) else [])
                         if isinstance(s, str) and s.strip())
        raw_r = data.get("records", [])
        records = tuple(_label(critic, r.strip()) for r in (raw_r if isinstance(raw_r, list) else [])
                        if isinstance(r, str) and r.strip())
        raw_m = data.get("minor", [])
        minor = tuple(_label(critic, m.strip()) for m in (raw_m if isinstance(raw_m, list) else [])
                      if isinstance(m, str) and m.strip())
        raw_e = data.get("earlier", {})
        earlier = tuple((str(k).strip(), str(v).strip().lower()) for k, v in
                        (raw_e.items() if isinstance(raw_e, dict) else []) if str(k).strip())
        if data["verdict"] == "pass" or (not notes and (records or minor)):   # records and minor notes never send back
            return Verdict(True, notes if data["verdict"] == "pass" else [], questions, sign_off, records, minor,
                           earlier)
        return Verdict(False, notes or [_label(critic, "sent back with no reason")], questions, sign_off, records,
                       minor, earlier)
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


def passes_under_review(shot_dir: Path, stage_id: str, changed_plan: list[str] = ()) -> list[str]:
    """The passes a review judges: the one the stage made (blocking, or the newest p<N>) and any new pass after it."""
    from kei.pose_record import latest_pass
    made = latest_pass(shot_dir, stage_id)
    newer = [c[len("pass:"):] for c in changed_plan if c.startswith("pass:")]
    return list(dict.fromkeys(([made] if made else []) + newer))


def critic_prompt(stage: Stage, shot_dir: Path, request: str, changed_plan: list[str], rules: str = "",
                  answers: list[dict] = (), earlier: list[list[str]] = (), author_notes: list[str] = (),
                  fixed: list[str] = ()) -> str:
    """What a critic sees: its instructions, the request and the shot's files. Never the animator's conversation."""
    lines = [
        (PROMPTS / "critic.md").read_text(encoding="utf-8").strip(),
        "",
        f"Request: {request}",
        f"Stage under review: {stage.title}",
        "",
        "The stage's contract: what the animator was asked to leave. Judge every file it names:",
        stage_contract(stage),
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
    if fixed:
        lines += [*fixed, ""]
    from kei.unchecked import critic_lines
    marks = critic_lines(shot_dir)
    if marks:
        lines += [*marks, ""]
    plan_files = [c for c in changed_plan if not c.startswith("pass:")]
    new_passes = [c[len("pass:"):] for c in changed_plan if c.startswith("pass:")]
    from kei.apps.unreal_mesh import mesh_lines
    mesh = mesh_lines(shot_dir, passes_under_review(shot_dir, stage.id, changed_plan))
    if mesh:
        lines += [*mesh, ""]
    lines += ["In the shot folder:"]
    lines += [f"- {a}" for a in _artifacts(shot_dir)] or ["- (nothing yet)"]
    if plan_files:
        lines += ["", f"The plan changed since it was approved: {', '.join(plan_files)}. Judge the change first: "
                  "was it needed, and does the work now follow the new plan? The approved copy is in .kei/approved_plan/."]
    if new_passes:
        lines += ["", f"A new pass was made after the passes review: {', '.join(new_passes)}. Judge that pass as you "
                  "would at the passes stage, against the plan sheet and the earlier passes: it is the motion that "
                  "will be delivered."]
    lines += ["", VERDICT_REMINDER]
    return "\n".join(lines) + "\n"


VERDICT_REMINDER = ('Your answer ends with ONE line of JSON, in the format given at the top: {"verdict": "pass" | '
                    '"send_back", "notes": [blocking notes], "minor": [small things]}, with the optional keys. '
                    "send_back only for a blocking note.")


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


VERDICT_ONLY = ("\nYour last answer had no verdict line. Answer again with only the one JSON verdict line, as the "
                "format above says.\n")


def _answer(seat: Seat, prompt: str, workdir: Path):
    """A critic's answer with a verdict in it. A crash, a timeout or an answer with no verdict is asked once more; a
    second failure pauses the stage as a machine fault (SeatPaused "machine"), never a send-back: a critic that cannot
    answer has not judged the work. A usage limit or a seat that cannot start pauses at once."""
    import time
    from kei.seats import keep_run
    last = None
    for attempt in range(2):
        asked = prompt if attempt == 0 or last is None or last.exit_code != 0 else prompt + VERDICT_ONLY
        t0 = time.time()
        result = seat.run(asked, workdir)
        keep_run(workdir, f"critic-{seat.name}", asked, result, time.time() - t0)
        kind = pause_kind(result)
        if kind:
            raise SeatPaused(kind, seat.name, result.output.strip()[:SEAT_ERROR_CHARS])
        if result.exit_code == 0 and has_verdict(result.output):
            return result
        last = result
    why = (last.output.strip()[:SEAT_ERROR_CHARS] or f"exit code {last.exit_code}") if last.exit_code != 0         else "no verdict line, twice"
    raise SeatPaused("machine", seat.name, f"the critic could not give a verdict: {why}")


VERDICTS_DIR = Path(".kei") / "verdicts"


def _kept_path(shot_dir: Path, stage_id: str, seat: Seat) -> Path:
    safe = re.sub(r"[^\w.-]", "_", seat.name)
    return Path(shot_dir) / VERDICTS_DIR / f"{stage_id}-{safe}.json"


def _kept(path: Path, sha: str) -> tuple[Verdict, str] | None:
    """A verdict this critic already gave on this very prompt, before a pause."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("prompt_sha") != sha:
        return None
    v = data["verdict"]
    return Verdict(v["passed"], list(v["notes"]), tuple(v["questions"]), tuple(v["sign_off"]), tuple(v["records"]),
                   tuple(v["minor"]), tuple(tuple(e) for e in v["earlier"])), data.get("wording", "")


def _keep(path: Path, sha: str, verdict: Verdict, wording: str) -> None:
    from dataclasses import asdict
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"prompt_sha": sha, "verdict": asdict(verdict), "wording": wording}), encoding="utf-8")


REWORD = ("You reviewed this shot already; Kei did not take some of your sign-off checks. Reword them only: the "
          "verdict and notes you gave stand. Answer with one JSON line: {\"sign_off\": [\"...\", ...]}, every check "
          "of your verdict, rewritten where needed.\n")


def _sign_off_line(output: str) -> tuple | None:
    text = re.sub(r"```(?:json)?", "", output or "")
    dec = json.JSONDecoder()
    for i in reversed([m.start() for m in re.finditer(r"\{", text)]):
        try:
            obj, _ = dec.raw_decode(text[i:])
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("sign_off"), list):
            return tuple(s.strip() for s in obj["sign_off"] if isinstance(s, str) and s.strip())
    return None


def _one_critic(seat: Seat, prompt: str, shot_dir: Path, title: str) -> tuple[Verdict, str]:
    """One critic's verdict, and a send-back note when its sign-off checks stay badly worded after a second ask.
    The second ask is a short call with only the checks: it never sends the stage's rules again."""
    result = _answer(seat, prompt, shot_dir)
    verdict = parse_verdict(seat.name, result.output)
    bad = _badly_worded(verdict.sign_off)
    if not bad:
        return verdict, ""
    ask = f"Stage under review: {title}" + chr(10) + REWORD + "Your checks:\n" + "\n".join(f"- {c}" for c in verdict.sign_off) + _rewording(bad)
    again = seat.run(ask, shot_dir)
    kind = pause_kind(again)
    if kind:
        raise SeatPaused(kind, seat.name, again.output.strip()[:SEAT_ERROR_CHARS])
    checks = _sign_off_line(again.output) if again.exit_code == 0 else None
    if checks is not None:
        verdict = Verdict(verdict.passed, verdict.notes, verdict.questions, checks, verdict.records, verdict.minor,
                          verdict.earlier)
    bad = _badly_worded(verdict.sign_off)
    if not bad:
        return verdict, ""
    wording = _label(seat.name, "its sign-off checks are not in the author's wording after two tries: "
                     + "; ".join(f"{c!r} ({why})" for c, why in bad))
    return Verdict(verdict.passed, verdict.notes, verdict.questions, (), verdict.records, verdict.minor,
                   verdict.earlier), wording


def _fallback(seat: Seat):
    """The critic's stand-in (fallback_cmd in kei.toml), as a seat of its own, or None."""
    spec = getattr(seat, "spec", None)
    if spec is None or not getattr(spec, "fallback_cmd", ()):
        return None
    from dataclasses import replace
    from kei.seats import CliSeat
    return CliSeat(replace(spec, name=f"{spec.name}-fallback", cmd=list(spec.fallback_cmd), fallback_cmd=()))


def _panel(stage: Stage, prompt: str, shot_dir: Path, critics: list[Seat]) -> list[tuple[Verdict, str]]:
    """Every critic at once, each in its own thread. A verdict is kept in .kei/verdicts until the whole panel has
    answered, so when one critic pauses (a usage limit, a fault), the others are not asked again on resume as long
    as the prompt is the same. Results come back in the critics' order; the first pause is raised after all finish."""
    import hashlib
    from concurrent.futures import ThreadPoolExecutor
    sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    paths = [_kept_path(shot_dir, stage.id, s) for s in critics]

    def job(i):
        held = _kept(paths[i], sha)
        if held is not None:
            return held
        try:
            got = _one_critic(critics[i], prompt, shot_dir, stage.title)
        except SeatPaused as e:
            stand_in = _fallback(critics[i])
            if e.kind != "usage" or stand_in is None:
                raise
            got = _one_critic(stand_in, prompt, shot_dir, stage.title)   # its own limit pauses the stage as usual
        _keep(paths[i], sha, *got)
        return got
    results: list = [None] * len(critics)
    errors: list = [None] * len(critics)
    with ThreadPoolExecutor(max_workers=max(1, len(critics))) as pool:
        futures = [pool.submit(job, i) for i in range(len(critics))]
        for i, f in enumerate(futures):
            try:
                results[i] = f.result()
            except BaseException as e:   # noqa: BLE001  raised below, after every critic finished
                errors[i] = e
    first = next((e for e in errors if e is not None), None)
    if first is not None:
        raise first
    for p in paths:
        p.unlink(missing_ok=True)
    return results


def panel_review(stage: Stage, shot_dir: Path, request: str, critics: list[Seat],
                 changed_plan: list[str] | None = None, rules: str = "", answers: list[dict] = (),
                 earlier: list[list[str]] = (), author_notes: list[str] = (), fixed: list[str] = (),
                 primary: str | None = None) -> PanelNotes:
    """Run every critic on the stage. Any send-back wins. A critic that cannot answer (a crash, a timeout, no verdict)
    is asked once more, then the stage pauses as a machine fault: it never costs a send-back. A usage limit or a seat
    that cannot start raises SeatPaused at once."""
    changed = list(changed_plan or []) if stage.id != "plan" else []
    if stage.id not in REVIEWED_STAGES and not changed:
        return PanelNotes()
    prompt = critic_prompt(stage, shot_dir, request, changed, rules, answers, earlier, author_notes, fixed)
    notes: list[str] = []
    questions: list[dict] = []
    sign_off: list[dict] = []
    records: list[str] = []
    minor: list[str] = []
    earlier_status: list[tuple] = []
    verdicts = _panel(stage, prompt, Path(shot_dir), critics)
    for seat, (verdict, wording) in zip(critics, verdicts):
        if wording:
            notes.append(wording)
        if not verdict.passed:
            notes += verdict.notes
        questions += [{**q, "from": f"critic {seat.name}"} for q in verdict.questions]
        sign_off += [{"from": f"critic {seat.name}", "check": s} for s in verdict.sign_off]
        records += verdict.records
        minor += verdict.minor
        earlier_status += [(seat.name, n, s) for n, s in verdict.earlier]
    from kei.merge_notes import merge
    notes, disputes = merge(notes, primary)      # one note per fault; opposite notes become a question
    return PanelNotes(notes, questions + disputes, sign_off, records, minor, earlier_status)
