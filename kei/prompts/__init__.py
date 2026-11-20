"""The prompt each stage's agent gets: the request, the stage, its contract, what exists, and why the last try failed."""
from __future__ import annotations

from pathlib import Path

from kei.stages import Stage

HERE = Path(__file__).resolve().parent
SKIP_DIRS = {".kei", ".git", "__pycache__", "review"}   # review/: Kei's renders for the author; drawings are listed
QUESTION_RULE = ("To ask the author something only a person can settle (an unclear brief, a rig you cannot read, a "
                 "viewing at real rate), write the question in QUESTIONS.md, name the file to look at, and stop: "
                 "the shot waits for kei answer. No agent can watch video at real rate: never write that you did.")

RECORD_RULE = ("Kei keeps the shot's bookkeeping in KEI_RECORD.md (stage, tries, each pass's hash and flag counts, "
               "file pointers) and writes it before each review: do not keep stage, version or hash lines in PLAN.md "
               "or GATES.md, and never edit KEI_RECORD.md.")
SCRATCH_RULE = ("Your own helpers (a measuring script, a probe, a temporary render) go in .kei/scratch/, Kei's "
                "folder, and run as python .kei/scratch/<name>.py: python runs nothing else, no one-liners. "
                "They stay in Kei's "
                "folder, never delivered. Use kei probe, kei keys, kei try, kei sweep, kei poses and kei check "
                "(--explain) before you write one.")

SOURCE_RULE = ("Sources: cite only published research and recorded footage, by author and year, and say what a "
               "source shows in your own words. Describe the craft in your own words. Quote at most one sentence of "
               "any source. Mark (unchecked) right after a number that states a fact about the real world (a speed, an angle, "
               "a mass, a timing taken from research or footage) when you did not read it in the source itself "
               "during this shot. Never mark the shot's own numbers: frames, key values, the timings you chose, "
               "or what kei check, probe or poses measured. Kei counts the marks itself and shows them to the "
               "author and the critics. A name on the author's private list fails the stage.")


def library_rule(library: Path) -> str:
    return (f"Reference library: {Path(library).resolve().as_posix()} (read INDEX.md first). It holds public-domain "
            "and openly licensed footage of real people, each with a SOURCE.md giving its creator, year, licence, "
            "frame rate and view. Take the short look there: pull frames with ffmpeg into the shot's .kei/look/ "
            "folder (Kei's own, never delivered), open them, measure with python, and write your measurements in "
            "REFS.md. Cite each clip by creator "
            "and year as its SOURCE.md says. Measure, never trace; never copy a library file into the shot. A "
            "number you measured in a clip carries no (unchecked) mark.")


def stage_contract(stage: Stage) -> str:
    return (HERE / f"{stage.id}.md").read_text(encoding="utf-8").strip()


SERIES_MIN = 5    # files of one numbered series in a folder (f0000.png, key_f0012.png...) listed as one line
SCRIPTS_MIN = 12  # python files in one folder listed as one line: the agent's own helpers, not the shot's artifacts


def _series(name: str) -> str | None:
    """'key_f0012.png' -> 'key_f*.png'; None for a name with no number."""
    import re
    m = re.match(r"^(.*?)(\d+)(\D*)$", name)
    return f"{m.group(1)}*{m.group(3)}" if m else None


def _artifacts(shot_dir: Path) -> list[str]:
    """What is already in the shot folder, one line per file, with long runs folded: a numbered series of five files
    or more in a folder (each frame of a render, each key still) is one line with its count, and a folder with many
    python helpers is one line too. A late stage would otherwise list thousands of frames in every prompt."""
    shot_dir = Path(shot_dir)
    by_dir: dict[Path, list[str]] = {}
    for p in sorted(shot_dir.rglob("*")):
        rel = p.relative_to(shot_dir)
        if p.is_file() and not SKIP_DIRS.intersection(rel.parts):
            by_dir.setdefault(rel.parent, []).append(rel.name)
    out = []
    for folder, names in by_dir.items():
        prefix = "" if str(folder) == "." else folder.as_posix() + "/"
        groups: dict[str, list[str]] = {}
        for n in names:
            key = _series(n)
            if key:
                groups.setdefault(key, []).append(n)
        folded = {n for key, ns in groups.items() if len(ns) >= SERIES_MIN for n in ns}
        scripts = [n for n in names if n.endswith(".py") and n not in folded]
        if len(scripts) >= SCRIPTS_MIN:
            folded |= set(scripts)
        shown_series = set()
        for n in names:
            if n not in folded:
                out.append(prefix + n)
                continue
            key = _series(n)
            if key and key in groups and len(groups[key]) >= SERIES_MIN:
                if key not in shown_series:
                    shown_series.add(key)
                    ns = groups[key]
                    out.append(f"{prefix}{key} ({len(ns)} files, {ns[0]} to {ns[-1]})")
        if len(scripts) >= SCRIPTS_MIN:
            out.append(f"{prefix}*.py ({len(scripts)} python helpers, not listed)")
    return out


def stage_prompt(stage: Stage, shot_dir: Path, request: str, misses: list[str], rules: str = "",
                 critic_notes: list[str] = (), author_notes: list[str] = (), questions: list[dict] = (),
                 answers: list[dict] = (), character: str | None = None, look_at: list[str] = (),
                 kei_notes: list[str] = (), refs_library: Path | None = None) -> str:
    lines = [
        "You are Kei, an animator who keys every motion by hand, working in the shot folder you are started in.",
        "",
        f"Request: {request}",
        f"Stage: {stage.title}",
        *([f"Character: {character} (every pass's shot.json names it as \"character\"; kei render, check and "
           f"bake use it)"] if character else []),
        "",
        "Do this stage only. Leave its artifact in the shot folder; the next stage starts from it.",
        "",
        stage_contract(stage),
        "",
    ]
    if rules:
        lines += [rules, ""]
    if kei_notes:
        lines += ["From the shot's character folder:"]
        lines += [f"- {m}" for m in kei_notes]
        lines += [""]
    lines += ["Already in the shot folder:"]
    lines += [f"- {a}" for a in _artifacts(shot_dir)] or ["- (nothing yet)"]
    lines += ["", QUESTION_RULE, SOURCE_RULE, SCRATCH_RULE, RECORD_RULE]
    if refs_library:
        lines += ["", library_rule(refs_library)]
    if answers:
        from kei.critic import answers_block
        lines += ["", *answers_block(answers)]
    if author_notes:
        lines += ["", "The author's notes for this stage. They come first:"]
        lines += [f"- {m}" for m in author_notes]
    if look_at:
        lines += ["", "The author drew on the review frames. Open each file before you change anything:"]
        lines += [f"- Look at: {p}" for p in look_at]
    if misses:
        lines += ["", "The gate refused the last attempt. Fix these before anything else:"]
        lines += [f"- {m}" for m in misses]
    if critic_notes:
        lines += ["", "The critics sent the last reviewed try back. Fix every note; never undo one without saying why:"]
        lines += [f"- {m}" for m in critic_notes]
    return "\n".join(lines) + "\n"
