"""kei skill install: put the Kei skill where your agent reads skills, from the installed package.

  kei skill install                    Claude Code, for every project: ~/.claude/skills/kei
  kei skill install --agent codex      Codex, for every project: ~/.agents/skills/kei
  kei skill install --project          inside this folder: .claude/skills/kei (or .agents/skills/kei)

The skill ships inside the package (kei/skill/kei, from the repository's skill/kei), so a pipx or uv install has it
too. An existing copy is replaced only with --force, and a copy you changed is never replaced silently.
"""
from __future__ import annotations

import shutil
from pathlib import Path

FOLDERS = {"claude": ".claude/skills/kei", "codex": ".agents/skills/kei"}


class SkillError(ValueError):
    pass


def source() -> Path:
    """The skill folder: inside the installed package, else the repository's skill/kei (a source checkout)."""
    here = Path(__file__).resolve().parent
    for p in (here / "skill" / "kei", here.parent / "skill" / "kei"):
        if (p / "SKILL.md").is_file():
            return p
    raise SkillError("the Kei skill is not in this installation (no kei/skill/kei/SKILL.md)")


def install(agent: str = "claude", project: bool = False, force: bool = False, home: Path | None = None,
            cwd: Path | None = None) -> Path:
    if agent not in FOLDERS:
        raise SkillError(f"agent is one of {', '.join(FOLDERS)}")
    base = (cwd or Path.cwd()) if project else (home or Path.home())
    dst = base / FOLDERS[agent]
    src = source()
    if dst.exists():
        same = all((dst / f.relative_to(src)).is_file() and (dst / f.relative_to(src)).read_bytes() == f.read_bytes()
                   for f in src.rglob("*") if f.is_file())
        if same:
            return dst
        if not force:
            raise SkillError(f"{dst} exists and differs from this version's skill: kei skill install --force "
                             f"replaces it")
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    return dst
