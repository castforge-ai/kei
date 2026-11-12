"""The glTF export: a valid binary glTF 2.0 with the skeleton, rigidly skinned meshes, three materials and a clip."""
import json
import math
import struct

import pytest

from kei import hands
from kei.characters import CHARACTERS, load_character, rest_pose
from kei.characters.mesh import pose_mesh
from kei.export_gltf import COMPONENTS, TYPES, build_glb, read_glb, to_gltf
from kei.rig import ALL_BONES, PARENTS, skeleton
from kei.sample import bake

SHOT = {"rig": "v4", "fps": 24, "frames": 12,
        "keys": [{"f": 0, "root": [0, 0.915, 0], "footL": [-0.15, 0.09, 0], "footR": [0.15, 0.09, 0]},
                 {"f": 6, "root": [0.05, 0.86, 0.1], "spine": [0.6, 0.2, 0.3], "armR": [1.4, 0.3, 0.4],
                  "elbowR": [1.2, 0.5], "fingersR": hands.preset("fist"), "head": [0.3, 0, 0.6],
                  "footL": [-0.15, 0.09, 0], "footR": [0.2, 0.25, 0.25, 0.4, 0], "legSR": 1.05},
                 {"f": 12, "root": [0, 0.915, 0.2], "footL": [-0.15, 0.09, 0.2], "footR": [0.15, 0.09, 0.2]}]}


@pytest.fixture(scope="module", params=CHARACTERS)
def glb(request):
    ch = load_character(request.param)
    return ch, build_glb(ch, emission=1.0, shot=SHOT, mode="spline")


def data(doc, binary, i):
    """An accessor's values as a list of tuples, read with struct from the binary chunk."""
    acc = doc["accessors"][i]
    view = doc["bufferViews"][acc["bufferView"]]
    fmt, size = COMPONENTS[acc["componentType"]]
    n = TYPES[acc["type"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride", size * n)
    return [struct.unpack_from("<" + fmt * n, binary, start + k * stride) for k in range(acc["count"])]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def trs(t, q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w), t[0]],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w), t[1]],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y), t[2]],
            [0, 0, 0, 1]]


def globals_(doc, local):
    """{node index: 4x4 global matrix} from {node index: (translation, rotation)}."""
    parent = {c: i for i, n in enumerate(doc["nodes"]) for c in n.get("children", [])}
    out = {}

    def g(i):
        if i not in out:
            m = trs(*local[i])
            out[i] = mat_mul(g(parent[i]), m) if i in parent else m
        return out[i]
    for i in local:
        g(i)
    return out


def rest_locals(doc):
    return {i: (n.get("translation", [0, 0, 0]), n.get("rotation", [0, 0, 0, 1]))
            for i, n in enumerate(doc["nodes"]) if "mesh" not in n}


def mirror(p):
    return (-p[0], p[1], p[2])


def test_the_file_is_a_binary_gltf_2(glb):
    _, blob = glb
    magic, version, length = struct.unpack_from("<4sII", blob, 0)
    assert magic == b"glTF" and version == 2 and length == len(blob)
    jlen, jtype = struct.unpack_from("<II", blob, 12)
    assert jtype == 0x4E4F534A and jlen % 4 == 0
    blen, btype = struct.unpack_from("<II", blob, 20 + jlen)
    assert btype == 0x004E4942 and blen % 4 == 0
    assert 20 + jlen + 8 + blen == len(blob)
    doc = json.loads(blob[20:20 + jlen].decode("utf-8"))
    assert doc["asset"]["version"] == "2.0"
    assert doc["buffers"][0]["byteLength"] <= blen


def test_views_and_accessors_stay_inside_the_buffer(glb):
    _, blob = glb
    doc, binary = read_glb(blob)
    for v in doc["bufferViews"]:
        assert v.get("byteOffset", 0) % 4 == 0
        assert v.get("byteOffset", 0) + v["byteLength"] <= doc["buffers"][0]["byteLength"] <= len(binary)
    for i, a in enumerate(doc["accessors"]):
        v = doc["bufferViews"][a["bufferView"]]
        fmt, size = COMPONENTS[a["componentType"]]
        need = a.get("byteOffset", 0) + a["count"] * size * TYPES[a["type"]]
        assert need <= v["byteLength"], i
        vals = data(doc, binary, i)
        if "min" in a:
            for k in range(TYPES[a["type"]]):
                assert abs(min(x[k] for x in vals) - a["min"][k]) < 1e-6
                assert abs(max(x[k] for x in vals) - a["max"][k]) < 1e-6
        assert all(math.isfinite(x) for row in vals for x in row)


def test_the_skeleton_has_the_bone_names_and_hierarchy(glb):
    _, blob = glb
    doc, _ = read_glb(blob)
    skin = doc["skins"][0]
    names = [doc["nodes"][j]["name"] for j in skin["joints"]]
    assert names == list(ALL_BONES)
    index = {doc["nodes"][j]["name"]: j for j in skin["joints"]}
    parent = {c: i for i, n in enumerate(doc["nodes"]) for c in n.get("children", [])}
    for b in ALL_BONES:
        if PARENTS[b] is None:
            assert index[b] not in parent and skin["skeleton"] == index[b]
        else:
            assert parent[index[b]] == index[PARENTS[b]], b
    assert index["root"] in doc["scenes"][0]["nodes"]


def test_the_bind_pose_is_the_rest_pose_and_the_inverse_binds_invert_it(glb):
    ch, blob = glb
    doc, binary = read_glb(blob)
    skin = doc["skins"][0]
    G = globals_(doc, rest_locals(doc))
    ibm = data(doc, binary, skin["inverseBindMatrices"])
    B = skeleton(rest_pose(ch), ch.proportions)
    for j, m in zip(skin["joints"], ibm):
        inv = [[m[c * 4 + r] for c in range(4)] for r in range(4)]     # column-major
        ident = mat_mul(inv, G[j])
        assert all(abs(ident[r][c] - (r == c)) < 1e-6 for r in range(4) for c in range(4))
        name = doc["nodes"][j]["name"]
        head = tuple(G[j][r][3] for r in range(3))
        assert math.dist(head, mirror(B[name].head)) < 1e-6, name


def test_every_vertex_is_bound_to_one_joint_with_weight_one(glb):
    ch, blob = glb
    doc, binary = read_glb(blob)
    nj = len(doc["skins"][0]["joints"])
    total = 0
    for prim in doc["meshes"][0]["primitives"]:
        joints = data(doc, binary, prim["attributes"]["JOINTS_0"])
        weights = data(doc, binary, prim["attributes"]["WEIGHTS_0"])
        assert len(joints) == len(weights) == doc["accessors"][prim["attributes"]["POSITION"]]["count"]
        for j, w in zip(joints, weights):
            assert w == (1.0, 0.0, 0.0, 0.0) and 0 <= j[0] < nj
        idx = [i for (i,) in data(doc, binary, prim["indices"])]
        assert len(idx) % 3 == 0 and max(idx) < len(joints)
        total += len(joints)
    assert total == sum(len(p.verts) for p in pose_mesh(ch, rest_pose(ch)))


def test_the_mesh_stands_on_the_floor_facing_plus_z_with_its_right_at_minus_x(glb):
    ch, blob = glb
    doc, binary = read_glb(blob)
    prims = {doc["materials"][p["material"]]["name"]: p for p in doc["meshes"][0]["primitives"]}
    pos = [v for p in prims.values() for v in data(doc, binary, p["attributes"]["POSITION"])]
    assert abs(min(v[1] for v in pos)) < 0.002
    assert abs(max(v[1] for v in pos) - ch.height) < 0.03
    mark = data(doc, binary, prims["emission"]["attributes"]["POSITION"])
    assert sum(v[2] for v in mark) / len(mark) > 0.06    # the chest C is on the front, at +z (flush with a 0.07 m chest)
    G = globals_(doc, rest_locals(doc))
    hand_r = next(i for i, n in enumerate(doc["nodes"]) if n.get("name") == "hand_r")
    assert G[hand_r][0][3] < -0.2                                  # the right hand is at -x


def test_triangles_wind_outward(glb):
    _, blob = glb
    doc, binary = read_glb(blob)
    for p in doc["meshes"][0]["primitives"]:
        pos = data(doc, binary, p["attributes"]["POSITION"])
        nrm = data(doc, binary, p["attributes"]["NORMAL"])
        idx = [i for (i,) in data(doc, binary, p["indices"])]
        bad = 0
        for k in range(0, len(idx), 3):
            a, b, c = (pos[i] for i in idx[k:k + 3])
            e1, e2 = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
            f = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
            n = [sum(nrm[i][d] for i in idx[k:k + 3]) for d in range(3)]
            bad += sum(f[d] * n[d] for d in range(3)) < -1e-15
        assert bad == 0


def test_three_materials_and_the_emission_follows_the_strength():
    ch = load_character("kei")
    for strength in (0.0, 0.5, 1.0):
        doc, _ = read_glb(build_glb(ch, emission=strength))
        mats = {m["name"]: m for m in doc["materials"]}
        assert set(mats) == {"body", "joint", "emission"}
        e = mats["emission"].get("emissiveFactor", [0, 0, 0])
        if strength == 0:
            assert e == [0, 0, 0]
            assert all("emissiveFactor" not in m or m["emissiveFactor"] == [0, 0, 0] for m in mats.values())
        else:
            assert e[0] > 0.9 * strength and e[0] > e[1] > e[2]


def test_a_frame_of_the_animation_reproduces_the_rig_within_a_millimetre(glb):
    ch, blob = glb
    doc, binary = read_glb(blob)
    anim = doc["animations"][0]
    shot = {**SHOT, "props": {"proportions": ch.proportions}}
    frames = bake(shot, "spline")
    times = data(doc, binary, anim["samplers"][0]["input"])
    assert len(times) == len(frames) and abs(times[-1][0] - 12 / 24) < 1e-6
    for f in (0, 4, 6, 9, 12):
        local = rest_locals(doc)
        for ch_ in anim["channels"]:
            out = data(doc, binary, anim["samplers"][ch_["sampler"]]["output"])[f]
            node, path = ch_["target"]["node"], ch_["target"]["path"]
            t, q = local[node]
            local[node] = (list(out), q) if path == "translation" else (t, list(out))
        G = globals_(doc, local)
        B = skeleton(frames[f]["pose"], ch.proportions)
        worst = max(math.dist(tuple(G[i][r][3] for r in range(3)), mirror(B[n["name"]].head))
                    for i, n in enumerate(doc["nodes"]) if n.get("name") in B)
        assert worst < 0.001, f


def test_no_animation_without_a_shot():
    doc, _ = read_glb(build_glb(load_character("keira")))
    assert "animations" not in doc


def test_the_axes_convention_is_recorded():
    doc, _ = read_glb(build_glb(load_character("kei")))
    kei = doc["asset"]["extras"]
    assert "-x" in kei["kei_axes"] and kei["kei_units"] == "metres" and kei["kei_character"] == "kei"


def test_the_extras_are_flat_strings():
    """Unreal 5.8's glTF import reads asset.extras as strings: a nested object logs
    'LogJson: Error: Json Value of type 'Object' used as a 'String'' and fails a headless import's exit code."""
    doc, _ = read_glb(build_glb(load_character("kei")))
    assert doc["asset"]["extras"] and all(isinstance(v, str) for v in doc["asset"]["extras"].values())


def test_to_gltf_reflects_the_world():
    assert to_gltf((0.3, 1.0, 0.2)) == (-0.3, 1.0, 0.2)


def test_kei_export(tmp_path, capsys):
    from kei.cli import main
    out = tmp_path / "kei.glb"
    assert main(["export", "--character", "kei", "--out", str(out), "--emission", "0"]) == 0
    doc, _ = read_glb(out.read_bytes())
    assert doc["skins"][0]["joints"]
    assert str(out) in capsys.readouterr().out


def test_kei_export_with_a_shot(tmp_path):
    from kei.cli import main
    (tmp_path / "s" / "out_p1").mkdir(parents=True)
    (tmp_path / "s" / "out_p1" / "shot.json").write_text(json.dumps(SHOT), encoding="utf-8")
    out = tmp_path / "keira.glb"
    assert main(["export", "--character", "keira", "--out", str(out), "--shot", str(tmp_path / "s"),
                 "--pass", "p1"]) == 0
    doc, _ = read_glb(out.read_bytes())
    assert len(doc["animations"]) == 1


def test_a_truncated_file_is_refused():
    blob = build_glb(load_character("kei"))
    with pytest.raises(ValueError):
        read_glb(blob[:-10])
    with pytest.raises(ValueError):
        read_glb(b"glTX" + blob[4:])
