"""Kei's signature characters, Kei and Keira: data files of proportions and rigid shapes, one bone each.

A character file (kei/characters/<name>.json) holds:
  title         the display name
  summary       one line: the build, for the brief's list of characters
  height        metres, head top at rest (1.71 for both)
  proportions   rig proportion overrides (kei.rig.PROPORTIONS names), measured from the sheet
  rest          the rest pose channels (the bind pose of an export, the pose of a rest render)
  materials     {"body", "joint", "emission"}: "#rrggbb" each
  spine_beads   the spine bones whose head carries a visible bead
  measured      how the numbers were measured: source sheet, scale, method, notes, key widths
  shapes        rigid shapes, each on one bone

A shape: {"bone", "kind", "material", ...}. "bone" may hold {s}: the shape is written for the right side and the
left side is its mirror image. "space" is "bone" (the default: x, y, z on the bone's frame X, Y, Z, origin at the
bone's head, Y along the bone) or "rest" (the world at the rest pose: x the character's right, y up, z forward); a
rest-space shape is turned into its bone's frame when the file loads, so every shape below is in bone space.
  sphere      c [x, y, z], r
  ellipsoid   c, r [rx, ry, rz] along the axes, rot [a, b, c] (optional: radians about X, then Y, then Z)
  capsule     a, b (the two end centres), r [ra, rb] (a tapered capsule: radius ra at a, rb at b)
  block       c, r [rx, ry, rz], rot, power (optional, 2 to 8, default 4), taper [tx, tz] (optional): a rounded box,
              |x/rx|^power + |y/ry|^power + |z/rz|^power = 1 (2 is an ellipsoid, higher is flatter sides and
              squarer corners), its width scaled by 1 + tx * y/ry and its depth by 1 + tz * y/ry (|t| below 0.9),
              so a positive taper is wider at the top: a chest, a pelvis
  ring        c, axis [x, y, z], r [major, minor] (a torus around the axis)
  mark        c, size, depth: the angular C, size high and wide, depth thick, facing the bone's +Z with its
              opening toward the bone's -X (the character's left: the viewer's right in a front view); rot as an
              ellipsoid's (optional: a tilt about X lays it on the chest's slope)
Materials: body (ivory), joint (charcoal: only spheres, ellipsoids and rings centred on the bone's head, that is on
the joint), emission (the chest C; its glow has a strength from 0, off, to 1).

IMPORTED CHARACTERS (kei import) live outside the repository, one folder each in characters_dir() (KEI_CHARACTERS, or
~/.kei/characters): <name>/character.json and <name>/mesh.json. Their character.json has the fields above with no
shapes and no spine beads, plus mesh (the mesh file's name), confirmed (false until the person has looked at the fit
sheet and said yes), source (the model file it came from) and fit (the fit's report). mesh.json holds the bound parts
(kei.models.bind.BoundPart): bone, material, verts in the world at the rest pose, tris, and skin for a smooth part;
a textured part has uvs, and texture, the index of its image when the character has several (texture is then a list:
texture.rgb, texture_1.rgb, ...).
A folder may not take a built-in character's name.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from kei.rig import ALL_BONES, PoseError, check_channels, check_proportions, full_pose, skeleton

DATA = Path(__file__).resolve().parent
DEFAULT = "kei"
# The known characters are the files in this folder, the default first.
CHARACTERS = tuple(sorted((p.stem for p in DATA.glob("*.json")), key=lambda n: (n != DEFAULT, n)))
KINDS = ("sphere", "ellipsoid", "capsule", "ring", "mark", "block")
MATERIALS = ("body", "joint", "emission")
TOP_KEYS = ("name", "title", "summary", "height", "proportions", "rest", "materials", "spine_beads", "measured",
            "shapes")
IMPORTED_KEYS = ("mesh", "confirmed", "source", "fit", "import_id", "texture")   # an imported character's own fields
COMMON = ("bone", "kind", "material", "space", "note")
SHAPE_KEYS = {"sphere": ("c", "r"), "ellipsoid": ("c", "r", "rot"), "capsule": ("a", "b", "r"),
              "ring": ("c", "axis", "r"), "mark": ("c", "size", "depth", "rot"),
              "block": ("c", "r", "rot", "power", "taper")}
OPTIONAL = ("space", "note", "rot", "power", "taper")


class CharacterError(ValueError):
    """A character file is missing or wrong. The message names the field."""


Vec = tuple[float, float, float]


@dataclass(frozen=True)
class Shape:
    bone: str
    kind: str
    material: str
    c: Vec = (0.0, 0.0, 0.0)         # sphere, ellipsoid, ring, mark: the centre
    a: Vec = (0.0, 0.0, 0.0)         # capsule ends
    b: Vec = (0.0, 0.0, 0.0)
    r: tuple[float, ...] = ()        # sphere (r,), ellipsoid (rx, ry, rz), capsule (ra, rb), ring (major, minor)
    axes: tuple[Vec, Vec, Vec] = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))   # ellipsoid, ring, mark
    size: float = 0.0
    depth: float = 0.0
    note: str = ""
    power: float = 2.0               # block: the exponent of its sides
    taper: tuple[float, float] = (0.0, 0.0)   # block: width and depth scale per unit of y/ry


@dataclass
class Character:
    name: str
    title: str
    summary: str
    height: float
    proportions: dict
    rest: dict
    materials: dict
    spine_beads: list
    measured: dict
    shapes: list = field(default_factory=list)
    parts: list | None = None        # an imported character's bound parts (kei.models.bind.BoundPart as dicts)
    confirmed: bool = True           # an imported character is not confirmed until its fit is approved
    folder: Path | None = None       # an imported character's folder
    source: dict = field(default_factory=dict)
    fit: dict = field(default_factory=dict)
    import_id: str = ""              # new at every import: an approval names the import it approves
    texture: dict | None = None      # an imported character's base colour: {"file", "width", "height"} (raw RGB)
    textures: list = field(default_factory=list)   # every base colour image; texture is the first


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _vec(v, where: str, n: int = 3, positive: bool = False) -> tuple[float, ...]:
    if not (isinstance(v, list) and len(v) == n and all(map(_num, v))):
        raise CharacterError(f"{where}: needs a list of {n} finite numbers")
    if positive and not all(x > 0 for x in v):
        raise CharacterError(f"{where}: every number must be above 0")
    return tuple(float(x) for x in v)


def _positive(v, where: str) -> float:
    if not (_num(v) and v > 0):
        raise CharacterError(f"{where}: needs a finite number above 0")
    return float(v)


def _rot_xyz(rot) -> tuple[Vec, Vec, Vec]:
    """The three axes of a rotation by rot[0] about X, then rot[1] about Y, then rot[2] about Z."""
    def rx(v, a):
        return (v[0], v[1] * math.cos(a) - v[2] * math.sin(a), v[1] * math.sin(a) + v[2] * math.cos(a))

    def ry(v, a):
        return (v[0] * math.cos(a) + v[2] * math.sin(a), v[1], -v[0] * math.sin(a) + v[2] * math.cos(a))

    def rz(v, a):
        return (v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a), v[2])
    return tuple(rz(ry(rx(e, rot[0]), rot[1]), rot[2]) for e in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))


def _unit(v: Vec, where: str) -> Vec:
    n = math.hypot(*v)
    if n < 1e-9:
        raise CharacterError(f"{where}: the axis has no length")
    return (v[0] / n, v[1] / n, v[2] / n)


def _shape(d, i: int) -> dict:
    """One shape checked and read into plain values (not yet mirrored or moved to bone space)."""
    where = f"shape {i + 1}"
    if not isinstance(d, dict):
        raise CharacterError(f"{where}: needs an object")
    kind = d.get("kind")
    if kind not in KINDS:
        raise CharacterError(f"{where}: unknown kind {kind!r}: use one of {', '.join(KINDS)}")
    for k in d:
        if k not in COMMON + SHAPE_KEYS[kind]:
            raise CharacterError(f"{where}: unknown field {k!r} for a {kind}")
    for k in SHAPE_KEYS[kind]:
        if k not in d and k not in OPTIONAL:
            raise CharacterError(f"{where}: a {kind} needs {k!r}")
    bone = d.get("bone")
    names = [bone.replace("{s}", s) for s in "lr"] if isinstance(bone, str) else []
    if not names or any(n not in ALL_BONES for n in names):
        raise CharacterError(f"{where}: unknown bone {bone!r}")
    material = d.get("material")
    if material not in MATERIALS:
        raise CharacterError(f"{where}: unknown material {material!r}: use one of {', '.join(MATERIALS)}")
    space = d.get("space", "bone")
    if space not in ("bone", "rest"):
        raise CharacterError(f"{where}: space is 'bone' or 'rest', not {space!r}")
    note = d.get("note", "")
    if not isinstance(note, str):
        raise CharacterError(f"{where}: note needs a string")
    out = {"bone": bone, "kind": kind, "material": material, "space": space, "note": note}
    if kind == "sphere":
        out["c"], out["r"] = _vec(d["c"], f"{where} c"), (_positive(d["r"], f"{where} r"),)
    elif kind == "ellipsoid":
        out["c"], out["r"] = _vec(d["c"], f"{where} c"), _vec(d["r"], f"{where} r", positive=True)
        out["axes"] = _rot_xyz(_vec(d["rot"], f"{where} rot")) if "rot" in d else None
    elif kind == "block":
        out["c"], out["r"] = _vec(d["c"], f"{where} c"), _vec(d["r"], f"{where} r", positive=True)
        out["axes"] = _rot_xyz(_vec(d["rot"], f"{where} rot")) if "rot" in d else None
        power = d.get("power", 4)
        if not (_num(power) and 2 <= power <= 8):
            raise CharacterError(f"{where}: power needs a number from 2 to 8")
        taper = _vec(d.get("taper", [0, 0]), f"{where} taper", 2)
        if any(abs(t) >= 0.9 for t in taper):
            raise CharacterError(f"{where}: taper needs numbers between -0.9 and 0.9")
        out["power"], out["taper"] = float(power), taper
    elif kind == "capsule":
        out["a"], out["b"] = _vec(d["a"], f"{where} a"), _vec(d["b"], f"{where} b")
        out["r"] = _vec(d["r"], f"{where} r", 2, positive=True)
    elif kind == "ring":
        out["c"], out["r"] = _vec(d["c"], f"{where} c"), _vec(d["r"], f"{where} r", 2, positive=True)
        out["axis"] = _unit(_vec(d["axis"], f"{where} axis"), f"{where} axis")
    else:
        out["c"] = _vec(d["c"], f"{where} c")
        out["size"], out["depth"] = _positive(d["size"], f"{where} size"), _positive(d["depth"], f"{where} depth")
        out["axes"] = _rot_xyz(_vec(d["rot"], f"{where} rot")) if "rot" in d else None
    if material == "joint":
        if kind not in ("sphere", "ellipsoid", "ring"):
            raise CharacterError(f"{where}: a joint shape is a sphere, an ellipsoid or a ring, not a {kind}")
        if space != "bone" or math.hypot(*out["c"]) > 1e-6:
            raise CharacterError(f"{where}: a joint shape sits on the joint: c [0, 0, 0] in bone space")
    if material == "emission" and kind != "mark":
        raise CharacterError(f"{where}: the emission material is for the chest mark only")
    return out


def _perp(axis: Vec) -> tuple[Vec, Vec, Vec]:
    """Two unit vectors at right angles to axis, and axis: the frame of a ring."""
    h = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _unit((axis[1] * h[2] - axis[2] * h[1], axis[2] * h[0] - axis[0] * h[2], axis[0] * h[1] - axis[1] * h[0]),
              "ring axis")
    w = (axis[1] * u[2] - axis[2] * u[1], axis[2] * u[0] - axis[0] * u[2], axis[0] * u[1] - axis[1] * u[0])
    return u, axis, w


def _place(s: dict, side: str, rest_bones) -> Shape:
    """A read shape on one side, in its bone's frame. side is "l", "r" or "" (a centre bone)."""
    bone = s["bone"].replace("{s}", side) if side else s["bone"]
    mirror = side == "l"

    def m(v):
        return (-v[0], v[1], v[2]) if mirror else v

    axes = s.get("axes")
    if s["kind"] == "ring":
        axes = _perp(s["axis"])
    if s["space"] == "rest":       # world at the rest pose: mirror in the world, then into the bone's frame
        B = rest_bones[bone]
        X, Y, Z = B.frame

        def pt(p):
            p = m(p)
            d = (p[0] - B.head[0], p[1] - B.head[1], p[2] - B.head[2])
            return tuple(sum(d[i] * e[i] for i in range(3)) for e in (X, Y, Z))

        def vec(v):
            v = m(v)
            return tuple(sum(v[i] * e[i] for i in range(3)) for e in (X, Y, Z))
    else:                          # bone space: the left bone's frame is the right one mirrored with X negated
        pt = vec = m
    out = {"bone": bone, "kind": s["kind"], "material": s["material"], "note": s["note"], "r": s.get("r", ())}
    for k in ("c", "a", "b"):
        if k in s:
            out[k] = pt(s[k])
    if axes is not None:
        out["axes"] = tuple(vec(e) for e in axes)
    elif s["space"] == "rest":
        out["axes"] = tuple(vec(e) for e in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
    if s["kind"] == "mark":
        out["size"], out["depth"] = s["size"], s["depth"]
    if s["kind"] == "block":
        out["power"], out["taper"] = s["power"], s["taper"]
    return Shape(**out)


def _colour(v, where: str) -> str:
    if not (isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v)):
        raise CharacterError(f"{where}: needs a colour '#rrggbb'")
    return v


def parse_character(data, name: str) -> Character:
    """Check a character's data and build it, with every shape in its bone's frame. Raises CharacterError."""
    if not isinstance(data, dict):
        raise CharacterError(f"{name}: needs a JSON object")
    imported = "mesh" in data
    for k in data:
        if k not in TOP_KEYS and not (imported and k in IMPORTED_KEYS):
            raise CharacterError(f"{name}: unknown field {k!r}")
    for k in TOP_KEYS:
        if k not in data:
            raise CharacterError(f"{name}: missing field {k!r}")
    height = data["height"]
    if not (_num(height) and 1.0 < height < 2.5):
        raise CharacterError(f"{name}: height needs a number of metres between 1 and 2.5")
    try:
        check_proportions(data["proportions"], f"{name} proportions")
        check_channels(data["rest"], f"{name} rest")
    except PoseError as e:
        raise CharacterError(str(e)) from e
    mats = data["materials"]
    if not isinstance(mats, dict) or set(mats) != set(MATERIALS):
        raise CharacterError(f"{name}: materials needs exactly {', '.join(MATERIALS)}")
    mats = {k: _colour(v, f"{name} materials.{k}") for k, v in mats.items()}
    beads = data["spine_beads"]
    if not (isinstance(beads, list) and (beads or imported)
            and all(b in ALL_BONES and b.startswith("spine_") for b in beads)):
        raise CharacterError(f"{name}: spine_beads needs a list of spine bone names")
    measured = data["measured"]
    if not isinstance(measured, dict):
        raise CharacterError(f"{name}: measured needs an object")
    shapes = data["shapes"]
    if not isinstance(shapes, list) or not (shapes or imported):
        raise CharacterError(f"{name}: shapes needs a list of shapes")
    read = [_shape(d, i) for i, d in enumerate(shapes)]
    if not (isinstance(data["summary"], str) and data["summary"].strip() and "\n" not in data["summary"]):
        raise CharacterError(f"{name}: summary needs one line of text")
    ch = Character(name=name, title=str(data["title"]), summary=data["summary"].strip(), height=float(height), proportions=dict(data["proportions"]),
                   rest=dict(data["rest"]), materials=mats, spine_beads=list(beads), measured=dict(measured))
    if imported:
        ch.confirmed = data.get("confirmed") is True
        ch.source, ch.fit = dict(data.get("source") or {}), dict(data.get("fit") or {})
        ch.import_id = str(data.get("import_id") or "")
        tex = data.get("texture")
        if tex is not None:
            texs = tex if isinstance(tex, list) and tex else [tex]
            for i, t in enumerate(texs):
                want = "texture.rgb" if i == 0 else f"texture_{i}.rgb"
                if not (isinstance(t, dict) and t.get("file") == want and isinstance(t.get("width"), int)
                        and isinstance(t.get("height"), int)):
                    raise CharacterError(f"{name}: texture {i + 1} needs file {want}, width and height")
            ch.textures = [dict(t) for t in texs]
            ch.texture = ch.textures[0]
    rest_bones = rest_skeleton(ch)
    for s in read:
        sides = "lr" if "{s}" in s["bone"] else ("",)
        for side in sides:
            ch.shapes.append(_place(s, side, rest_bones))
    return ch


def characters_dir() -> Path:
    """The folder of imported characters: KEI_CHARACTERS, else ~/.kei/characters."""
    env = os.environ.get("KEI_CHARACTERS")
    return Path(env) if env else Path.home() / ".kei" / "characters"


def imported_characters() -> tuple[str, ...]:
    """The imported characters' names: the folders of characters_dir() with a character.json, built-in names left
    out."""
    root = characters_dir()
    if not root.is_dir():
        return ()
    return tuple(sorted(p.name for p in root.iterdir()
                        if (p / "character.json").is_file() and p.name not in CHARACTERS))


def known_characters() -> tuple[str, ...]:
    """Every character Kei can animate: the built-in ones (the default first), then the imported ones."""
    return CHARACTERS + imported_characters()


def _path(name: str) -> Path:
    if name in CHARACTERS:
        return DATA / f"{name}.json"
    if name in imported_characters():
        return characters_dir() / name / "character.json"
    raise CharacterError(f"no character {name!r}: use one of {', '.join(known_characters())}")


def raw(name: str) -> dict:
    """A character file as plain JSON."""
    path = _path(name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CharacterError(f"cannot read {path}: {e}") from e


def load_character(name: str) -> Character:
    """A character, checked, with every shape in its bone's frame; an imported one with its bound parts."""
    data = raw(name)
    return _loaded(data, name, _path(name).parent)


def load_imported(folder, name: str) -> Character:
    """An imported character read from a folder that is not (yet) its place in characters_dir(): an import's
    staging folder, so its fit sheet is drawn before it replaces the old import."""
    path = Path(folder) / "character.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise CharacterError(f"cannot read {path}: {e}") from e
    return _loaded(data, name, Path(folder))


def _loaded(data, name: str, folder: Path) -> Character:
    ch = parse_character(data, name)
    if "mesh" in data:
        ch.folder = folder
        if data["mesh"] != "mesh.json":
            raise CharacterError(f"{name}: an imported character's mesh is its folder's mesh.json, not "
                                 f"{data['mesh']!r}")
        mesh = ch.folder / "mesh.json"
        try:
            ch.parts = json.loads(mesh.read_text(encoding="utf-8"))["parts"]
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise CharacterError(f"cannot read the mesh of {name!r} ({mesh}): {e}") from e
        for i, p in enumerate(ch.parts):
            if not (isinstance(p, dict) and p.get("bone") in ALL_BONES and isinstance(p.get("verts"), list)
                    and isinstance(p.get("tris"), list)):
                raise CharacterError(f"{mesh}: part {i + 1} needs a known bone, verts and tris")
            n = len(p["verts"])
            if any(not (isinstance(t, list) and len(t) == 3 and all(isinstance(k, int) and 0 <= k < n for k in t))
                   for t in p["tris"]):
                raise CharacterError(f"{mesh}: part {i + 1} has a triangle that names a missing vertex")
            if p.get("uvs") is not None and not (isinstance(p["uvs"], list) and len(p["uvs"]) == len(p["tris"])
                                                 and all(isinstance(t, list) and len(t) == 6 for t in p["uvs"])):
                raise CharacterError(f"{mesh}: part {i + 1} needs six texture numbers per triangle")
            if "texture" in p and not (isinstance(p["texture"], int) and not isinstance(p["texture"], bool)
                                       and 0 <= p["texture"] < len(ch.textures)):
                raise CharacterError(f"{mesh}: part {i + 1} names texture {p['texture']!r}, which the character "
                                     "does not have")
            if p.get("skin") is not None:
                if not (isinstance(p["skin"], list) and len(p["skin"]) == n):
                    raise CharacterError(f"{mesh}: part {i + 1} needs one skin entry per vertex")
                skin = []
                for vw in p["skin"]:
                    pairs = []
                    for bw in vw:
                        if not (isinstance(bw, list) and len(bw) == 2 and bw[0] in ALL_BONES and _num(bw[1])
                                and bw[1] >= 0):
                            raise CharacterError(f"{mesh}: part {i + 1} weights a bone Kei does not have: {bw!r}")
                        pairs.append((bw[0], float(bw[1])))
                    total = sum(w for _, w in pairs)
                    if total <= 0:
                        raise CharacterError(f"{mesh}: part {i + 1} has a vertex with no weight")
                    skin.append([(b, w / total) for b, w in pairs])
                p["skin"] = skin
    return ch


# "Character: keira" at the start of a line, also as a bullet, in bold, or in lower case (as the Subjects line).
_LINE = re.compile(r"^[ \t>*+-]*\**character\**[ \t]*:[ \t]*\**(.*)$", re.I | re.M)


def plan_character(shot_dir) -> str | None:
    """The character PLAN.md names (the last Character line, in lower case), or None when it names none."""
    plan = Path(shot_dir) / "PLAN.md"
    if not plan.is_file():
        return None
    names = [m.replace("*", "").strip().lower() for m in _LINE.findall(plan.read_text(encoding="utf-8"))]
    names = [n for n in names if n]
    return names[-1] if names else None


def _unknown(name: str, where: str) -> str:
    return f"{where} names an unknown character {name!r}; use one of: {', '.join(known_characters())}"


def character_misses(shot_dir) -> list[str]:
    """A Character line in PLAN.md must name a known character. No line is fine: the config's default is used. With
    a line, the latest pass must not name another character in its shot.json (pass_character_misses)."""
    name = plan_character(shot_dir)
    if name is not None and name not in known_characters():
        return ["P1 " + _unknown(name, "PLAN.md Character")]
    return pass_character_misses(shot_dir, name) if name else []


def latest_pass(shot_dir):
    """out_p<highest n>/shot.json, else out_blocking/shot.json: the pass the next pass starts from (None if none)."""
    def order(p):
        m = re.fullmatch(r"out_p(\d+)", p.parent.name)
        return (2, int(m.group(1))) if m else (1, 0) if p.parent.name == "out_blocking" else (0, 0)
    passes = sorted((p for p in Path(shot_dir).glob("out_*/shot.json") if order(p)[0]), key=order)
    return passes[-1] if passes else None


def pass_character_misses(shot_dir, want: str) -> list[str]:
    """The latest pass (out_p<highest n>/shot.json, else out_blocking: the one the next pass starts from) must not
    name another character than the shot's own: its "character" would win over PLAN.md, and the pass would be made
    and judged on the other character without anyone being told. Older passes are history and are not read."""
    last = latest_pass(shot_dir)
    if last is None:
        return []
    try:
        named = json.loads(last.read_text(encoding="utf-8")).get("character")
    except (ValueError, AttributeError):
        return []
    if named is None or str(named).strip().lower() == want:
        return []
    rel = last.relative_to(shot_dir).as_posix()
    return [f"{rel} names the character {str(named).strip().lower()!r}, but PLAN.md's Character line names "
            f"{want!r}: set \"character\": \"{want}\" in it, or change the shot's character"]


def shot_character(shot_dir, shot: dict | None, default: str) -> str:
    """The shot's character: shot.json's "character", else the PLAN.md line, else the config's default."""
    field_ = shot.get("character") if isinstance(shot, dict) else None
    if field_ is not None:
        name, where = str(field_).strip().lower(), 'shot.json "character"'
    elif plan_character(shot_dir) is not None:
        name, where = plan_character(shot_dir), "PLAN.md Character"
    else:
        name, where = default, "the config's shot.character"
    if name not in known_characters():
        raise CharacterError(_unknown(name, where))
    return name


def on_character(shot: dict, ch: Character) -> dict:
    """The shot set up to play on the character: its proportions, and, when the shot names another character it was
    made for, match_knees (that character's proportions), so the root rides at the height where the knees bend as
    they did on the character the walk was made for (kei.sample; the feet stay where the shot puts them)."""
    props = shot.get("props") if isinstance(shot.get("props"), dict) else {}
    out = {**props, "proportions": ch.proportions}
    out.pop("match_knees", None)
    author = shot.get("character")
    name = author.strip().lower() if isinstance(author, str) else ""
    if name and name != ch.name and name in known_characters():
        out["match_knees"] = load_character(name).proportions
    return {**shot, "props": out}


def rest_pose(ch: Character) -> dict:
    """Every channel of the character's rest pose."""
    return full_pose(ch.rest)


def neutral_pose(ch: Character) -> dict:
    """The character's rest pose at a shot's neutral stance: spine, neck and head at 0 (Kei's own stance, trunk upright
    and head stacked over the shoulders). An imported character's rest spine and neck pitch are its sculpt's lean and
    head, bound in, so this is how a shot stands it."""
    return {**rest_pose(ch), "spine": [0.0, 0.0, 0.0], "neck": [0.0, 0.0, 0.0], "head": [0.0, 0.0, 0.0]}


def rest_skeleton(ch: Character):
    """The character's bones at rest (kei.rig.skeleton)."""
    return skeleton(rest_pose(ch), ch.proportions)
