"""Plan 6b: an approved walk keyed in Maya on an imported character plays as Kei's own bake of the same pass on the
same character: the joints within 1 mm on the keys and 2 mm on every frame, the loop seam included, and a sample of
the skinned vertices (rigid and smooth parts) within 2 mm on every frame. The character is the small synthetic import
of imported_kit, so the suite never reads the author's own characters."""
import json
import math
import os
import tempfile
from pathlib import Path

import pytest

from kei.apps.maya import run_job
from kei.apps.maya_scene import mesh_groups
from kei.apps.maya_shot import key_pass, setup_shot
from kei.apps.maya_side import kei_math as km
from kei.characters import load_character, on_character
from kei.characters.mesh import pose_mesh
from kei.rig import skeleton
from kei.sample import bake_continuous

import mayakit
from imported_kit import make_imported

FIX = Path(__file__).resolve().parent / "fixtures" / "walks" / "keira_walk_personality_p8.json"
EVERY = 23            # one vertex in EVERY of each mesh is read back
pytestmark = pytest.mark.maya


def maya_vs_kei(shot_dir: Path, name: str, pass_name: str, py, every: int = EVERY) -> dict:
    """Joints and sampled vertices of a keyed pass in Maya against Kei's own bake of it on the same character."""
    shot = json.loads((shot_dir / f"out_{pass_name}" / "shot.json").read_text(encoding="utf-8"))
    ch = load_character(name)
    kei = bake_continuous(on_character(shot, ch))
    maya = json.loads((shot_dir / f"out_{pass_name}" / "joints.json").read_text())["frames"]
    keys = {int(k["f"]) for k in shot["keys"]}
    joint_errs = [(max(abs(a - b) for a, b in zip(m["joints"][n], k["joints"][n])), m["f"], n)
                  for m, k in zip(maya, kei) for n in k["joints"]]
    groups = mesh_groups(ch)
    picks = {}
    for mesh, _, parts in groups:
        count = sum(len(ch.parts[i]["verts"]) for i in parts)
        picks[f"{name}:{mesh}"] = list(range(0, count, every))
    os.environ.setdefault("KEI_MAYA_APP_DIR", str(Path(tempfile.gettempdir()) / "kei_test_maya_app"))
    got = run_job(py, {"args": {"scene": str(shot_dir / f"out_{pass_name}" / "scene.ma").replace("\\", "/"),
                                "meshes": picks, "start": 0, "end": shot["frames"]}},
                  timeout=900, script=mayakit.SCRIPTS / "check_points.py")["data"]["frames"]
    vert_errs = []
    for fr, k in zip(got, kei):
        parts = pose_mesh(ch, k["pose"], skeleton(k["pose"], ch.proportions))
        for mesh, _, idx in groups:
            pts = [km.mirror_point(v) for i in idx for v in parts[i].verts]
            for j, p in zip(picks[f"{name}:{mesh}"], fr["points"][f"{name}:{mesh}"]):
                vert_errs.append((math.dist(p, pts[j]), fr["f"], mesh, j))
    return {"frames": len(maya), "joints_keys": max(e for e in joint_errs if e[1] in keys),
            "joints_all": max(joint_errs), "verts_all": max(vert_errs), "verts_count": len(vert_errs) // len(got)}


@pytest.fixture(scope="module")
def walked(tmp_path_factory):
    py = mayakit.mayapy()
    root = tmp_path_factory.mktemp("imported_walk")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("KEI_CHARACTERS", str(root / "characters"))
        make_imported(root / "characters")
        shot = {**json.loads(FIX.read_text(encoding="utf-8")), "character": "synth"}
        d = root / "shot"
        d.mkdir()
        (d / "PLAN.md").write_text("# a walk\n\nCharacter: synth\n", encoding="utf-8")
        setup_shot(d, fps=shot.get("fps") or 24, mayapy=py)
        (d / "out_p1").mkdir()
        (d / "out_p1" / "shot.json").write_text(json.dumps(shot), encoding="utf-8")
        key_pass(d, "p1", mode="spline", mayapy=py)
        yield shot, maya_vs_kei(d, "synth", "p1", py), d, py


def test_the_walk_plays_on_the_imported_character_in_maya_as_kei_s_own_bake(walked):
    shot, r, _, _ = walked
    print("parity on the synthetic import:", r)
    assert r["frames"] == shot["frames"] + 1
    assert r["joints_keys"][0] < 0.001, r["joints_keys"]
    assert r["joints_all"][0] < 0.002, r["joints_all"]


def test_the_skinned_vertices_play_as_kei_s_own_skinning(walked):
    _, r, _, _ = walked
    assert r["verts_count"] > 300
    assert r["verts_all"][0] < 0.002, r["verts_all"]


def test_the_fbx_of_a_maya_pass_on_an_imported_character_carries_its_mesh_and_skin(walked, tmp_path):
    from kei.apps.maya_shot import export_pass
    from kei.models.model import read_model
    _, _, d, py = walked
    ch = load_character("synth")
    r = export_pass(d, "p1", tmp_path / "walk.fbx", mayapy=py)
    m = read_model(tmp_path / "walk.fbx")
    assert sum(len(x.verts) for x in m.meshes) == sum(len(p["verts"]) for p in ch.parts), r
    skins = [w for x in m.meshes for w in x.skin]
    assert len(skins) == sum(len(p["verts"]) for p in ch.parts)
    blended = [w for w in skins if len(w) == 2]
    assert blended and all(abs(sum(x for _, x in w) - 1) < 1e-4 for w in skins)
    assert {n for w in skins for n, _ in w} >= {"calf_l", "thigh_l", "lowerarm_r", "upperarm_r", "head"}
    textured = [x for x in m.meshes if x.tri_uvs]
    assert len(textured) == 1 and len(textured[0].tri_uvs) == len(textured[0].tris)
    png = (d / "maya" / "textures" / "synth_texture.png").read_bytes()
    assert png in (tmp_path / "walk.fbx").read_bytes(), "the texture travels inside the FBX, not only as a path"
