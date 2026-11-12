"""Kei's own characters as a Maya job: plain JSON that the Maya side's load_character tool builds into joints, skinned
meshes and materials. One code path for every Kei character: Kei and Keira, and the characters made with kei import
(the general-rig characters later).

character_job(name, emission, texture_dir) -> dict, in the right-handed world the Maya side uses (x mirrored from
Kei's world, y up, metres; see kei_math):
  character, title, units "m"
  bones       [{name, parent, translate, orient}] in kei.rig.ALL_BONES order: translate is the head in the parent
              bone's space (the world for root), orient the rest local rotation as Maya joint-orient degrees (x, y, z,
              order xyz). A joint at rotate 0 sits in the rest pose.
  meshes      Kei's own characters: one per material, {name, material, points, normals, triangles, bone}; bone is
              the one bone index of each point (the rigid weights of the glTF and FBX exports).
              An imported character: one per texture and one per material for its untextured parts (mesh_groups),
              {name, material, points, normals, triangles, weights, uvs}; weights per point [[bone index, weight]]
              (a rigid part's points one bone at 1, a smooth part's its own weights), uvs per triangle
              [u0, v0, u1, v1, u2, v2] with v from the image's bottom, as Maya counts it (textured meshes only).
  materials   [{name, colour, emission, emission_strength}] as kei.export_scene gives them; an imported
              character's textures add {name "texture" (or "texture_<n>"), ..., texture: the PNG's path}.
  imported    true for an imported character
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

from kei.apps.maya_side import kei_math as km
from kei.characters import CharacterError, load_character
from kei.characters.texture import load_texture
from kei.export_scene import build_scene
from kei.rig import ALL_BONES


def _deg(R) -> list[float]:
    return [math.degrees(a) for a in km.matrix_euler(R, "xyz")]


def bone_table(scene) -> list[dict]:
    """The export scene's bones as Maya joints: local translate and joint orient, in the right-handed world."""
    world = {b.name: (km.mirror_frame(b.frame), km.mirror_point(b.head)) for b in scene.bones}
    out = []
    for b in scene.bones:
        R, p = world[b.name]
        if b.parent is None:
            t, L = p, R
        else:
            PR, Pp = world[b.parent]
            t, L = km.local(PR, Pp, R, p)
        out.append({"name": b.name, "parent": b.parent, "translate": list(t), "orient": _deg(L)})
    return out


def mesh_groups(ch) -> list[tuple[str, str, list[int]]]:
    """An imported character's parts in Maya meshes: [(mesh name, material name, [part indices])], one mesh per
    texture (the parts with uvs that read it) and one per material for the parts with no uvs, parts in file order."""
    groups: dict[tuple, list[int]] = {}
    for i, p in enumerate(ch.parts):
        if p.get("uvs") and ch.textures:
            key = ("tex", int(p.get("texture", 0)))
        else:
            key = ("mat", p.get("material", "body"))
        groups.setdefault(key, []).append(i)
    out = []
    for (kind, v), parts in sorted(groups.items(), key=lambda kv: (0, kv[0][1], "") if kv[0][0] == "tex"
                                   else (1, 0, kv[0][1])):
        mat = _texture_name(v) if kind == "tex" else v
        out.append((f"{ch.name}_{mat}", mat, parts))
    return out


def _texture_name(i: int) -> str:
    return "texture" if i == 0 else f"texture_{i}"


def _png(w: int, h: int, rgb: bytes) -> bytes:
    """An 8-bit RGB PNG of raw rows (top row first)."""
    stride = w * 3
    raw = b"".join(b"\x00" + rgb[y * stride:(y + 1) * stride] for y in range(h))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _imported_meshes(ch, scene, texture_dir) -> tuple[list[dict], list[dict]]:
    """The imported parts as Maya meshes (with per-vertex weights and, when textured, per-triangle uvs) and the
    texture materials, each image written as a PNG into texture_dir."""
    index = {n: i for i, n in enumerate(ALL_BONES)}
    meshes, materials = [], []
    groups = mesh_groups(ch)
    for i in sorted({int(ch.parts[g[2][0]].get("texture", 0)) for g in groups if g[1].startswith("texture")}):
        if texture_dir is None:
            raise CharacterError(f"{ch.name}: its texture needs a folder to be written to for Maya (texture_dir)")
        tex = load_texture(ch, i)
        if tex is None:
            raise CharacterError(f"{ch.name}: texture {i + 1} is named but cannot be read; import the model again")
        w, h, data = tex
        folder = Path(texture_dir)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{ch.name}_{_texture_name(i)}.png"
        path.write_bytes(_png(w, h, data))
        materials.append({"name": _texture_name(i), "colour": ch.materials["body"],
                          "emission": ch.materials["emission"], "emission_strength": 0.0,
                          "texture": str(path.resolve()).replace("\\", "/")})
    for name, mat, parts in groups:
        pts, nrm, tris, weights, uvs = [], [], [], [], []
        for i in parts:
            d, sm = ch.parts[i], scene.meshes[i]
            base = len(pts)
            pts += [list(km.mirror_point(v)) for v in sm.vertices]
            nrm += [list(km.mirror_point(v)) for v in sm.normals]
            if sm.weights:
                weights += [[[index[b], w] for b, w in vw] for vw in sm.weights]
            else:
                weights += [[[index[sm.bone], 1.0]]] * len(sm.vertices)
            tris += [[base + a, base + c, base + b] for a, b, c in sm.triangles]   # the mirror flips the winding
            if mat.startswith("texture"):
                uvs += [[u[0], 1 - u[1], u[4], 1 - u[5], u[2], 1 - u[3]] for u in d["uvs"]]
        meshes.append({"name": name, "material": mat, "points": pts, "normals": nrm, "triangles": tris,
                       "weights": weights, **({"uvs": uvs} if uvs else {})})
    return meshes, materials


def character_job(name: str, emission: float = 1.0, texture_dir=None) -> dict:
    """A Kei character as the load_character job. An unknown name is refused by kei.characters, with the name. An
    imported character (kei import) is built from its own files and must have its fit approved; its texture images
    are written as PNG files into texture_dir for Maya's file textures."""
    ch = load_character(name)
    if ch.parts is not None and not ch.confirmed:
        raise CharacterError(f"{name}: its fit is not approved yet, so Kei does not build it in Maya. Look at "
                             f"{ch.folder / 'fit.png'}, then approve it: kei import --confirm --name {name}")
    scene = build_scene(ch, emission)
    materials = [{"name": m.name, "colour": m.colour, "emission": m.emission,
                  "emission_strength": m.emission_strength} for m in scene.materials]
    if ch.parts is not None:
        meshes, more = _imported_meshes(ch, scene, texture_dir)
        return {"character": ch.name, "title": ch.title, "units": "m", "bones": bone_table(scene), "meshes": meshes,
                "materials": materials + more, "imported": True}
    index = {n: i for i, n in enumerate(ALL_BONES)}
    meshes = []
    for mat in ("body", "joint", "emission"):
        pts, nrm, tris, bone = [], [], [], []
        for m in scene.meshes:
            if m.material != mat:
                continue
            base = len(pts)
            pts += [list(km.mirror_point(v)) for v in m.vertices]
            nrm += [list(km.mirror_point(v)) for v in m.normals]
            bone += [index[m.bone]] * len(m.vertices)
            tris += [[base + a, base + c, base + b] for a, b, c in m.triangles]   # the mirror flips the winding
        meshes.append({"name": f"{ch.name}_{mat}", "material": mat, "points": pts, "normals": nrm,
                       "triangles": tris, "bone": bone})
    return {"character": ch.name, "title": ch.title, "units": "m", "bones": bone_table(scene), "meshes": meshes,
            "materials": materials}
