"""Character folders: one folder per character, its rig and weight evaluated once, its shots inside.

    kei-shots/
      kei_model/            the character folder, named after the character
        CHARACTER.md        one "## <character>" section: Fingerprint:, Evaluated:, Rig:, Mass:, Class:
        rig_eval/ weight_eval/   the evidence of that evaluation
        walk_personality/   a shot inside the character folder

A shot is inside a character folder when its parent folder is named after a character the shot uses, or holds a
CHARACTER.md with that character's section. The saved section is reused while its fingerprint (a hash of the
character's own files: the rig and the mesh) still matches; a re-import or a refit makes it stale, and the next shot
evaluates again and replaces it. A shot outside a character folder evaluates in the shot, as before.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from kei.characters import CHARACTERS, DATA, characters_dir, known_characters

SHEET = "CHARACTER.md"
EVIDENCE = ("rig_eval", "weight_eval")
_SECTION = re.compile(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", re.M | re.S)
_CHAR_LINE = re.compile(r"^[ \t>*+-]*\**character\**[ \t]*:[ \t]*\**(.*)$", re.I | re.M)
_CLASSES = ("light", "average", "heavy", "massive")
_PROVENANCE = re.compile(r"^(Fingerprint|Evaluated):[^\n]*\n?", re.M)


def _read(path: Path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def shot_characters(shot_dir, default: str) -> list[str]:
    """Every known character a Character line of PLAN.md names (a line may name several, comma separated), else the
    default."""
    plan = _read(Path(shot_dir) / "PLAN.md") or ""
    names = []
    for line in _CHAR_LINE.findall(plan):
        for n in re.split(r",|\band\b", line.replace("*", "")):
            n = n.strip().lower()
            if n in known_characters():
                names.append(n)
    return list(dict.fromkeys(names)) or [default]


def sections(text: str) -> dict[str, str]:
    """The "## <name>" sections of a CHARACTER.md, by lower-case name (spaces folded): each its whole text, heading
    included."""
    return {" ".join(m.group(1).lower().split()): m.group(0) for m in _SECTION.finditer(text or "")}


def aliases(name: str) -> list[str]:
    """The headings a CHARACTER.md section may name the character by, in lower case: its name, the name without a
    trailing _model (## kei for kei_model), and its display name (character.json "title")."""
    name = name.lower()
    out = [name, name[: -len("_model")] if name.endswith("_model") else name]
    try:
        from kei.characters import raw
        title = raw(name).get("title")
    except Exception:   # an unknown or unreadable character has only its own names
        title = None
    if isinstance(title, str) and title.strip():
        out.append(" ".join(title.lower().split()))
    return list(dict.fromkeys(out))


def section_for(text: str, name: str) -> str | None:
    """The character's section of a CHARACTER.md, heading included, matched by any of its aliases; the full name
    first."""
    have = sections(text)
    for a in aliases(name):
        if a in have:
            return have[a]
    return None


def character_folder(shot_dir, names) -> Path | None:
    """The character folder the shot is in, or None."""
    parent = Path(shot_dir).resolve().parent
    names = [n.lower() for n in names if n]
    if parent.name.lower() in names:
        return parent
    text = _read(parent / SHEET) or ""
    return parent if any(section_for(text, n) is not None for n in names) else None


def character_files(name: str) -> list[Path]:
    """The character's own files: its character.json (the rig) and, for an imported character, its mesh."""
    if name in CHARACTERS:
        return [DATA / f"{name}.json"]
    folder = characters_dir() / name
    files = [folder / "character.json"]
    try:
        mesh = json.loads(files[0].read_text(encoding="utf-8")).get("mesh")
    except (OSError, ValueError, AttributeError):
        mesh = None
    if isinstance(mesh, str) and mesh:
        files.append(folder / mesh)
    return files


def fingerprint(name: str) -> str:
    """A hash of the character's own files. The fit approval (character.json "confirmed") is left out: approving a
    fit changes neither the rig nor the mesh."""
    h = hashlib.sha256()
    for f in character_files(name):
        data = f.read_bytes() if f.is_file() else b""
        if f.name == "character.json" and data:
            try:
                d = json.loads(data.decode("utf-8"))
                d.pop("confirmed", None)
                data = json.dumps(d, sort_keys=True).encode("utf-8")
            except ValueError:
                pass
        h.update(f.name.encode("utf-8") + b"\0" + data + b"\0")
    return h.hexdigest()[:16]


def complete(section: str) -> bool:
    """A section with Rig:, Mass: and a Class: the weight gate accepts."""
    m = re.search(r"^\s*-?\s*Class:\s*(\w+)", section, re.M)
    return bool(re.search(r"^\s*-?\s*Rig:\s*\S", section, re.M) and re.search(r"^\s*-?\s*Mass:\s*\S", section, re.M)
                and m and m.group(1).lower() in _CLASSES)


@dataclass(frozen=True)
class Saved:
    name: str
    text: str           # the section, heading included
    fingerprint: str
    date: str


def saved_evaluation(folder, name: str) -> Saved | None:
    """The character's section in the character folder's CHARACTER.md, or None."""
    sec = section_for(_read(Path(folder) / SHEET) or "", name)
    if sec is None:
        return None
    fp = re.search(r"^Fingerprint:\s*(\S+)", sec, re.M)
    ev = re.search(r"^Evaluated:\s*(\S+)", sec, re.M)
    return Saved(name.lower(), sec, fp.group(1) if fp else "", ev.group(1) if ev else "")


def fresh(folder, name: str) -> Saved | None:
    """The saved evaluation when it can be reused: complete, and its fingerprint still the character's."""
    s = saved_evaluation(folder, name)
    if s is None or not complete(s.text):
        return None
    try:
        return s if s.fingerprint == fingerprint(name) else None
    except OSError:
        return None


def put_section(path: Path, name: str, section: str) -> None:
    """Replace the character's section in a CHARACTER.md (found by any of its aliases), or add it at the end."""
    path = Path(path)
    text = _read(path) or ""
    section = section.rstrip("\n") + "\n"
    old = section_for(text, name)
    if old is not None:
        text = text.replace(old, section + ("\n" if old.endswith("\n\n") else ""), 1)
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + section
    path.write_text(text, encoding="utf-8")


def _copy_tree(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)


@dataclass
class Reuse:
    folder: Path
    saved: dict          # name -> Saved, the characters reused
    others: list         # the characters the stage still evaluates

    @property
    def whole(self) -> bool:
        return bool(self.saved) and not self.others

    def messages(self) -> list[str]:
        return [f"reused {self.folder.name}/{SHEET} from {s.date} ({n})" for n, s in self.saved.items()]


def plan_reuse(shot_dir, default: str) -> Reuse | None:
    """What the rig and weight stages can reuse from the shot's character folder, or None (no folder, or nothing
    fresh in it)."""
    names = shot_characters(shot_dir, default)
    folder = character_folder(shot_dir, names)
    if folder is None:
        return None
    saved = {n: s for n in names if (s := fresh(folder, n)) is not None}
    if not saved:
        return None
    return Reuse(folder, saved, [n for n in names if n not in saved])


def apply_reuse(shot_dir, reuse: Reuse) -> None:
    """Write the reused sections into the shot's CHARACTER.md and copy their evidence the shot does not have yet."""
    shot_dir = Path(shot_dir)
    sheet = shot_dir / SHEET
    if not sheet.is_file():
        sheet.write_text(f"# CHARACTER: {shot_dir.name}\n\n", encoding="utf-8")
    for n, s in reuse.saved.items():
        put_section(sheet, n, s.text)
    for d in EVIDENCE:
        if not (shot_dir / d).exists():
            _copy_tree(reuse.folder / d, shot_dir / d)


def reuse_notes(reuse: Reuse) -> list[str]:
    """What the animator is told when some characters are reused and the others are evaluated in this stage."""
    names = ", ".join(reuse.saved)
    return [*(m + ": its section is already in CHARACTER.md" for m in reuse.messages()),
            f"Keep the sections of {names} exactly as they are. Evaluate only: {', '.join(reuse.others)}."]


def save_evaluations(shot_dir, default: str, today: str | None = None) -> list[str]:
    """After the weight stage passes in a character folder: save each character's complete section to the folder's
    CHARACTER.md with its fingerprint and date, unless a fresh one is there already (it was reused). A stale section
    is replaced. The shot's evidence folders are copied with it. Returns the names saved."""
    shot_dir = Path(shot_dir)
    names = shot_characters(shot_dir, default)
    folder = character_folder(shot_dir, names)
    if folder is None:
        return []
    have = _read(shot_dir / SHEET) or ""
    when = today or date.today().isoformat()
    out = []
    for n in names:
        sec = section_for(have, n)
        if sec is None or not complete(sec) or fresh(folder, n) is not None:
            continue
        body = _PROVENANCE.sub("", sec.partition("\n")[2])
        text = f"## {n}\nFingerprint: {fingerprint(n)}\nEvaluated: {when} in {shot_dir.name}\n{body}"
        put_section(folder / SHEET, n, text)
        out.append(n)
    if out:
        for d in EVIDENCE:
            if (shot_dir / d).is_dir():
                if (folder / d).exists():
                    shutil.rmtree(folder / d)
                _copy_tree(shot_dir / d, folder / d)
    return out


# A new shot of an action the character already has starts from that shot's vetted references, as a draft.
ACTIONS = ("walk", "run", "jog", "sprint", "jump", "hop", "leap", "skip", "idle", "stand", "sit", "turn", "fall",
           "climb", "crawl", "roll", "dance", "wave", "point", "kick", "punch", "throw", "catch", "lift", "carry",
           "push", "pull", "swing", "sneak", "dodge", "attack", "land", "slide", "spin", "bow", "nod", "reach")
_ACTION_LINE = re.compile(r"^Action:\s*(\S+)", re.M | re.I)
_REFS_LINE = re.compile(r"^Refs:\s*(.+)$", re.M)


def _stem(word: str) -> str:
    """walks, walking, walked -> walk; runs, running -> run; falls -> fall."""
    for end in ("ning", "ping", "ing", "ed", "s"):
        if word.endswith(end) and word[: -len(end)] in ACTIONS:
            return word[: -len(end)]
    return word


def _first_action(text: str) -> str | None:
    for w in re.findall(r"[a-z]+", (text or "").lower()):
        if _stem(w) in ACTIONS:
            return _stem(w)
    return None


def shot_action(shot_dir, request: str | None = None) -> str | None:
    """The shot's action word: PLAN.md's "Action:" line, else the first action word of the request, else of
    PLAN.md."""
    plan = _read(Path(shot_dir) / "PLAN.md") or ""
    m = _ACTION_LINE.search(plan)
    if m:
        return _stem(m.group(1).strip(" .,").lower())
    if request is None:
        from kei.state import StateError, load_state
        try:
            request = load_state(Path(shot_dir)).request
        except (StateError, OSError, ValueError):
            request = ""
    return _first_action(request) or _first_action(plan)


def shot_refs(shot_dir) -> list[Path]:
    """The REFS.md files a shot vetted: those its PLAN.md Refs lines name that exist, else its REFS.md."""
    shot_dir = Path(shot_dir)
    plan = _read(shot_dir / "PLAN.md") or ""
    out = []
    for line in _REFS_LINE.findall(plan):
        for r in re.findall(r"[\w./\-]*REFS\.md", line):
            p = (shot_dir / r).resolve()
            if p.is_file() and p not in out:
                out.append(p)
    if not out and (shot_dir / "REFS.md").is_file():
        out.append((shot_dir / "REFS.md").resolve())
    return out


def draft_refs(shot_dir, request: str | None = None, default: str = "") -> list[Path]:
    """The REFS.md files of the other shots in the shot's character folder with the same action. With no Character
    line in PLAN.md the shot's character is the default, as for the run."""
    shot_dir = Path(shot_dir).resolve()
    folder = character_folder(shot_dir, shot_characters(shot_dir, default))
    action = shot_action(shot_dir, request)
    if folder is None or action is None:
        return []
    out = []
    for d in sorted(p for p in folder.iterdir() if p.is_dir() and p != shot_dir):
        if (d / "PLAN.md").is_file() and shot_action(d) == action:
            out += [r for r in shot_refs(d) if r not in out]
    return out


def draft_notes(paths) -> list[str]:
    """What the references stage is told about the drafts."""
    return [f"{p} holds the vetted references of another shot of the same action on this character. Use it as a "
            "draft only: re-vet every row for this shot (its tier, our checks, its verdict) and measure the clips "
            "again; never copy it blind." for p in paths]


# kei shots tidy: put each shot under a folder named after its character.

@dataclass(frozen=True)
class Move:
    shot: Path
    dest: Path
    refused: str = ""    # why the shot is not moved, or "" when it can be


def _is_shot(d: Path) -> bool:
    return any((d / f).exists() for f in ("PLAN.md", "kei.toml", ".kei"))


def _toml_character(shot: Path) -> str | None:
    import tomllib
    try:
        data = tomllib.loads((shot / "kei.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    name = data.get("shot", {}).get("character") if isinstance(data.get("shot"), dict) else None
    return name.strip().lower() if isinstance(name, str) and name.strip() else None


def tidy_moves(root) -> list[Move]:
    """The moves that put each shot directly in root under root/<its character>/: the character PLAN.md names, else
    the shot's kei.toml [shot] character. A shot already in its character folder is left out; a running shot, or one
    whose place is taken, is listed as refused."""
    from kei.characters import plan_character
    from kei.state import StateError, load_state, state_path
    root = Path(root)
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and _is_shot(p)):
        name = plan_character(d) or _toml_character(d)
        if not name or name == d.name.lower():
            continue
        dest = root / name / d.name
        try:   # a shot never run has no state file, and is not running
            status = load_state(d).status if state_path(d).is_file() else ""
        except StateError as e:
            status, why = "", f"its state cannot be read: {e}"
        else:
            why = ""
        if status == "running":
            why = "it is running (status running); move it when it stops"
        elif dest.exists():
            why = f"{name}/{d.name} exists already"
        out.append(Move(d, dest, why))
    return out


def apply_moves(moves) -> list[Move]:
    """Move every shot that is not refused. Returns the moves made."""
    done = []
    for m in moves:
        if m.refused:
            continue
        m.dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(m.shot), str(m.dest))
        done.append(m)
    return done
