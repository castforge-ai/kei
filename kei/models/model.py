"""A model read from a file, in Kei's world: x the character's right, y up, z forward, metres.

Every reader (kei.models.fbx_read, kei.models.gltf_read) first brings the file into one common frame, the glTF one:
right-handed, y up, the model facing +z, its right on -x, metres. to_kei then mirrors x (x -> -x), as the exporters
do in reverse, and flips each triangle's winding so the triangles still wind counter-clockwise seen from outside.

Model
  meshes        [MeshData]
    name        the mesh's name in the file
    verts       [(x, y, z)] in Kei's world, at the file's rest (bind) pose
    tris        [(i, j, k)] counter-clockwise seen from outside
    colour      '#rrggbb', the material's diffuse colour (sRGB), or Kei's ivory when the file has none
    skin        None, or per vertex [(joint name, weight)] (the weights sum to 1)
    tri_uvs     None, or per triangle its corners' texture coordinates (u, v), v from the image's top
    texture     None, or the base colour image's path (a file inside the model's folder)
    parent_joint  None, or the joint the mesh hangs from in the file's hierarchy (a hat under the head joint): a
                mesh with no skin of its own follows that joint
  joints        [Joint] in parent-before-child order; empty for a model with no skeleton
    name, parent, head (the joint's position at the rest pose)
  source        the file it came from
  warnings      what the reader skipped or guessed (a sparse accessor, a pivot, a unit it could not use)
  temp_files    files the reader wrote for the import (a glTF's embedded images, one per image); the importer
                removes them once the textures are converted (remove_temp_files)
"""
from __future__ import annotations

from dataclasses import dataclass, field

Vec = tuple[float, float, float]
IVORY = "#E9DCC7"


class ModelError(ValueError):
    """A model file cannot be read, or holds something Kei cannot use. The message names the file."""


@dataclass
class MeshData:
    name: str
    verts: list
    tris: list
    colour: str = IVORY
    skin: list | None = None
    tri_uvs: list | None = None     # per triangle, its three corners' (u, v); v runs down from the image's top
    texture: str | None = None      # the base colour image's path, inside the model's folder
    parent_joint: str | None = None  # the nearest joint above the mesh in the file's hierarchy


@dataclass
class Joint:
    name: str
    parent: str | None
    head: Vec


@dataclass
class Model:
    meshes: list
    joints: list = field(default_factory=list)
    source: str = ""
    warnings: list = field(default_factory=list)   # what the reader skipped or guessed, for the person to see
    temp_files: list = field(default_factory=list)  # files the reader wrote (embedded images), removed after import

    @property
    def rigged(self) -> bool:
        return bool(self.joints) and any(m.skin for m in self.meshes)

    def all_verts(self) -> list:
        return [v for m in self.meshes for v in m.verts]


def remove_temp_files(model: Model) -> None:
    """Remove the files a reader wrote for the model (its embedded images)."""
    import os
    for f in model.temp_files:
        try:
            os.remove(f)
        except OSError:
            pass
    model.temp_files = []


def to_kei(p) -> Vec:
    """A point in the common frame (glTF axes, metres) in Kei's world."""
    return (-p[0], p[1], p[2])


def mirrors(m) -> bool:
    """Whether a 4x4 transform (rows) mirrors, its 3x3 part's determinant negative (a negative scale): it reverses a
    triangle's winding, so a reader flips the triangles it places."""
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])) < 0


def flip(tri) -> tuple[int, int, int]:
    """A triangle's winding reversed: the mirror x -> -x reverses it, this puts it back."""
    return (tri[0], tri[2], tri[1])


def finite_or_raise(values, what: str) -> None:
    """Raise ModelError when a number in values (points or UV corners, nested tuples) is NaN or infinite: a damaged
    or hostile file, refused here by name rather than as a traceback deep in the fit."""
    import math
    stack = [values]
    while stack:
        v = stack.pop()
        if isinstance(v, (list, tuple)):
            stack.extend(v)
        elif v is not None and not math.isfinite(v):
            raise ModelError(f"{what} is not a finite number ({v}); the file is damaged, export the model again")


def colour_hex(rgb) -> str:
    """Linear RGB factors (0..1) as an sRGB '#rrggbb'."""
    out = []
    for c in rgb[:3]:
        c = min(1.0, max(0.0, float(c)))
        s = c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
        out.append(round(s * 255))
    return "#" + "".join(f"{v:02X}" for v in out)


def texture_path(folder, name: str, warnings: list) -> str | None:
    """A texture file named by a model, resolved inside the model's folder only (the same checks as a glTF
    buffer: no scheme, no drive, no leading slash, no '..'). An absolute name is looked up by its file name in the
    folder and its .fbm folders. None, with a warning, when it is outside or missing."""
    from pathlib import Path, PureWindowsPath
    from kei.models.gltf_read import safe_relative
    folder = Path(folder).resolve()
    rel = safe_relative(name)
    candidates = [folder / rel] if rel else []
    if rel is None:
        base = PureWindowsPath(name.replace("/", "\\")).name
        if base and safe_relative(base):
            candidates = [folder / base] + [d / base for d in folder.glob("*.fbm")]
    for c in candidates:
        c = c.resolve()
        if folder in c.parents and c.is_file():
            return str(c)
    warnings.append(f"texture {name!r} is not a file inside the model's folder; the model is drawn untextured")
    return None


def read_model(path) -> Model:
    """A .glb, .gltf or binary .fbx file as a Model in Kei's world. Raises ModelError naming the file."""
    from pathlib import Path
    p = Path(path)
    try:
        blob = p.read_bytes()
    except OSError as e:
        raise ModelError(f"cannot read {p}: {e}") from e
    if blob[:4] == b"glTF" or p.suffix.lower() in (".glb", ".gltf"):
        from kei.models.gltf_read import read_gltf
        return read_gltf(blob, p)
    if blob[:20] == b"Kaydara FBX Binary  ":
        from kei.models.fbx_read import read_fbx_model
        return read_fbx_model(blob, p)
    if p.suffix.lower() == ".fbx":
        raise ModelError(f"{p}: an ASCII FBX file; save it as binary FBX (7.x) and import that")
    raise ModelError(f"{p}: not a model Kei reads; use .glb, .gltf or binary .fbx")
