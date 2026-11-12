"""The prompt each stage's agent gets: the request, the stage, its contract, what exists, and why the last try failed."""
from __future__ import annotations

from pathlib import Path

from kei.stages import Stage

HERE = Path(__file__).resolve().parent
SKIP_DIRS = {".kei", ".git", "__pycache__", "review"}   # review/: Kei's renders for the author; drawings are listed
QUESTION_RULE = ("To ask the author something only a person can settle (an unclear brief, a rig you cannot read, a "
                 "viewing at real rate), write the question in QUESTIONS.md, name the file to look at, and stop: "
                 "the shot waits for kei answer. No agent can watch video at real rate: never write that you did.")

SOURCE_RULE = ("Sources: cite only published research and recorded footage, by author and year, and say what a "
               "source shows in your own words. Describe the craft in your own words. Quote at most one sentence of "
               "any source. Mark every number you did not read in the source itself during this shot with "
               "(unchecked), right after the number. A name on the author's private list fails the stage.")


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


def _artifacts(shot_dir: Path) -> list[str]:
    out = []
    for p in sorted(Path(shot_dir).rglob("*")):
        rel = p.relative_to(shot_dir)
        if p.is_file() and not SKIP_DIRS.intersection(rel.parts):
            out.append(rel.as_posix())
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
    lines += ["", QUESTION_RULE, SOURCE_RULE]
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
