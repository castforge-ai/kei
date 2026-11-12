"""Write an imported character's folder (see kei.characters: IMPORTED CHARACTERS), and confirm its fit."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from kei.characters import CHARACTERS, CharacterError

NAME = re.compile(r"[a-z][a-z0-9_]{0,39}")
RESERVED = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
MATERIALS = {"body": "#E9DCC7", "joint": "#3B3530", "emission": "#FF8A2A"}   # Kei's own palette


def check_name(name: str) -> str:
    if not NAME.fullmatch(name or ""):
        raise CharacterError(f"character name {name!r}: use lower case letters, digits and _, starting with a letter")
    if name in RESERVED:
        raise CharacterError(f"{name!r} is a reserved device name on Windows; pick another, for example "
                             f"{name}_model")
    if name in CHARACTERS:
        raise CharacterError(f"{name!r} is a built-in character's name; give the imported one its own, for example "
                             f"{name}_model")
    return name


def _index(t) -> bool:
    """A part's texture index worth writing: the first texture (0) is the default."""
    return isinstance(t, int) and not isinstance(t, bool) and t > 0


def _r(v, n=6):
    return [round(float(c), n) for c in v]


def write_character(root, name: str, title: str, height: float, proportions: dict, rest: dict, parts,
                    source: dict, fit: dict, confirmed: bool = False, texture: dict | list | None = None,
                    folder=None) -> Path:
    """The folder root/name (or folder, an import's staging folder) with character.json and mesh.json; parts are
    kei.models.bind.BoundPart. texture: one texture ({"file", "width", "height"}), or a list of them when the parts
    have their own (a part's texture index)."""
    check_name(name)
    folder = Path(folder) if folder is not None else Path(root) / name
    folder.mkdir(parents=True, exist_ok=True)
    mesh = {"parts": [{"bone": p.bone, "material": p.material, "verts": [_r(v) for v in p.verts],
                       "tris": [list(t) for t in p.tris],
                       **({"uvs": [[round(float(c), 6) for uv in t for c in uv] for t in p.uvs]}
                          if getattr(p, "uvs", None) else {}),
                       **({"texture": p.texture} if getattr(p, "uvs", None) and _index(getattr(p, "texture", None))
                          else {}),
                       **({"skin": [[[n, round(w, 5)] for n, w in vw] for vw in p.skin]} if p.skin else {})}
                      for p in parts]}
    (folder / "mesh.json").write_text(json.dumps(mesh, separators=(",", ":")), encoding="utf-8")
    data = {"name": name, "title": title, "summary": f"{height:.2f} m, imported from {Path(source.get('file', '')).name}",
            "height": round(height, 4), "proportions": proportions, "rest": rest, "materials": dict(MATERIALS),
            "spine_beads": [], "measured": {"method": "kei import: fitted to the model's cross-sections"},
            "shapes": [], "mesh": "mesh.json", "confirmed": bool(confirmed), "source": source, "fit": fit,
            "import_id": uuid.uuid4().hex, **({"texture": texture} if texture else {})}
    (folder / "character.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    return folder


def confirm(folder) -> None:
    """Mark an imported character's fit as approved by the person."""
    path = Path(folder) / "character.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["confirmed"] = True
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
