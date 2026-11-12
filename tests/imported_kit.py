"""A small synthetic imported character for the tests, so no test reads the author's own ~/.kei folder.

make_imported(root, name) writes root/name/character.json, mesh.json and texture.rgb as kei import would: Keira's
proportions with a sculpt's lean in the rest pose (spine and neck pitch), her shapes as bound parts in the world at
rest, the lower legs and the forearms smooth (each vertex near the knee or the elbow weighted between the two bones),
every part textured (a 4 x 2 image) except the head, which stays untextured."""
from __future__ import annotations

import json
import math

from kei.characters import load_character, rest_pose
from kei.characters.imported import confirm, write_character
from kei.characters.mesh import pose_mesh
from kei.models.bind import BoundPart
from kei.rig import PARENTS, skeleton

SMOOTH = ("calf_l", "calf_r", "lowerarm_l", "lowerarm_r")
BLEND_M = 0.08           # vertices within this distance of a smooth bone's head blend with its parent bone
TEXTURE = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0,
                 0, 255, 255, 255, 0, 255, 128, 128, 128, 30, 60, 90])   # 4 x 2 texels


def make_imported(root, name: str = "synth", confirmed: bool = True):
    keira = load_character("keira")
    rest = {**keira.rest, "spine": [0.047, 0, 0], "neck": [-0.14, 0, 0]}
    pose = {**rest_pose(keira), **rest}
    B = skeleton(pose, keira.proportions)
    parts = []
    for p in pose_mesh(keira, pose, B):
        tris = [tuple(t) for t in p.tris]
        uvs = None if p.bone == "head" else [
            [((p.verts[i][0] + 1.0) % 1.0, min(1.0, max(0.0, 1.0 - p.verts[i][1] / 1.8))) for i in t] for t in tris]
        skin = None
        if p.bone in SMOOTH:
            head, parent = B[p.bone].head, PARENTS[p.bone]
            skin = []
            for v in p.verts:
                w = min(1.0, math.dist(v, head) / BLEND_M)
                skin.append([(p.bone, 0.5 + 0.5 * w), (parent, 0.5 - 0.5 * w)] if w < 1.0 else [(p.bone, 1.0)])
        parts.append(BoundPart(p.bone, p.material, list(p.verts), tris, skin, uvs))
    folder = write_character(root, name, name.title(), keira.height, dict(keira.proportions), rest, parts,
                             {"file": f"{name}.fbx", "skeleton": "fitted to the mesh"}, {"note": "test"},
                             texture={"file": "texture.rgb", "width": 4, "height": 2})
    (folder / "texture.rgb").write_bytes(TEXTURE)
    if confirmed:
        confirm(folder)
    return folder


def unconfirm(folder) -> None:
    path = folder / "character.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["confirmed"] = False
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
