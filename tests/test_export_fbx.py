"""The FBX export: the export scene as binary FBX 7.4, read back with the test reader and checked against the scene
and against the glTF export (the same joints, within 1 mm, for a 90 deg bend on each axis of each bone)."""
import json
import math
import time

import pytest

from fbxread import read_fbx
from kei import hands
from kei.characters import CHARACTERS, load_character
from kei.export_fbx import KTIME, build_fbx, euler_xyz, fbx_from_scene
from kei.export_gltf import gltf_from_scene
from kei.export_scene import SceneAnimation, build_scene, quat_matrix
from kei.rig import ALL_BONES, PARENTS
from test_export_gltf import data, globals_, rest_locals

SHOT = {"rig": "v4", "fps": 24, "frames": 12,
        "keys": [{"f": 0, "root": [0, 0.915, 0], "footL": [-0.15, 0.09, 0], "footR": [0.15, 0.09, 0]},
                 {"f": 6, "root": [0.05, 0.86, 0.1], "spine": [0.6, 0.2, 0.3], "armR": [1.4, 0.3, 0.4],
                  "elbowR": [1.2, 0.5], "fingersR": hands.preset("fist"), "head": [0.3, 0, 0.6],
                  "footL": [-0.15, 0.09, 0], "footR": [0.2, 0.25, 0.25, 0.4, 0], "legSR": 1.05},
                 {"f": 12, "root": [0, 0.915, 0.2], "footL": [-0.15, 0.09, 0.2], "footR": [0.15, 0.09, 0.2]}]}


# ---- reading the scene back -------------------------------------------------------------------------------------

def _name(s: str) -> str:
    return s.split("\x00\x01")[0]


class Scene:
    """The parts of an FBX file the tests check: objects by id, connections, global settings."""

    def __init__(self, blob: bytes):
        self.version, top = read_fbx(blob)
        self.top = {n.name: n for n in top}
        self.objects = {o.props[0]: o for o in self.top["Objects"].children}
        self.links = [tuple(c.props) for c in self.top["Connections"].children]
        self.settings = {p.props[0]: p.props[4:] for p in self.top["GlobalSettings"].find("Properties70").children}

    def of(self, kind, sub=None):
        return [o for o in self.objects.values() if o.name == kind and (sub is None or o.props[2] == sub)]

    def parents(self, oid):
        return [c[2] for c in self.links if c[1] == oid]

    def children(self, oid, kind=None, prop=None):
        out = []
        for c in self.links:
            if c[2] == oid and (prop is None or (len(c) > 3 and c[3] == prop)):
                o = self.objects.get(c[1])
                if o is not None and (kind is None or o.name == kind):
                    out.append(o)
        return out

    def bones(self):
        """{name: (model, parent name or None)} of the LimbNode models."""
        models = {o.props[0]: o for o in self.of("Model", "LimbNode")}
        out = {}
        for oid, m in models.items():
            ps = [p for p in self.parents(oid) if p in models or p == 0]
            assert len(ps) == 1
            out[_name(m.props[1])] = (m, None if ps[0] == 0 else _name(models[ps[0]].props[1]))
        return out


def p70(node):
    return {p.props[0]: p.props[4:] for p in node.find("Properties70").children}


def euler_matrix(e):
    """FBX's XYZ order: rotate about X, then Y, then Z (M = Rz Ry Rx), degrees."""
    a, b, c = (math.radians(v) for v in e)
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    rx = [[1, 0, 0], [0, ca, -sa], [0, sa, ca]]
    ry = [[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]]
    rz = [[cc, -sc, 0], [sc, cc, 0], [0, 0, 1]]
    mul = lambda p, q: [[sum(p[i][k] * q[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(rz, mul(ry, rx))


def compose(bones, local):
    """{name: (rotation rows, position)} from {name: (translation, euler)} parent first, in FBX axes (cm)."""
    out = {}
    for name in ALL_BONES:
        t, e = local[name]
        m = euler_matrix(e)
        parent = bones[name][1]
        if parent is None:
            out[name] = (m, tuple(t))
        else:
            pm, pp = out[parent]
            r = [[sum(pm[i][k] * m[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
            out[name] = (r, tuple(pp[i] + sum(pm[i][k] * t[k] for k in range(3)) for i in range(3)))
    return out


def fbx_rest(sc):
    bones = sc.bones()
    local = {n: (p70(m)["Lcl Translation"], p70(m)["Lcl Rotation"]) for n, (m, _) in bones.items()}
    return bones, compose(bones, local)


def curves(sc, model, prop):
    """The three curves (X, Y, Z) on a model's property: [(times, values)] or None where not animated."""
    nodes = sc.children(model.props[0], "AnimationCurveNode", prop)
    if not nodes:
        return None
    out = []
    for axis in "XYZ":
        cs = sc.children(nodes[0].props[0], "AnimationCurve", "d|" + axis)
        assert len(cs) == 1
        out.append((cs[0].find("KeyTime").props[0], cs[0].find("KeyValueFloat").props[0]))
    return out


def fbx_frames(sc):
    """Per frame: {bone: (rotation, position)} composed from the curves (and the rest values where none)."""
    bones = sc.bones()
    tracks = {}
    for n, (m, _) in bones.items():
        props = p70(m)
        tracks[n] = (curves(sc, m, "Lcl Translation"), curves(sc, m, "Lcl Rotation"),
                     props["Lcl Translation"], props["Lcl Rotation"])
    count = len(tracks["root"][1][0][0])
    frames = []
    for k in range(count):
        local = {}
        for n, (tc, rc, t0, r0) in tracks.items():
            t = [c[1][k] for c in tc] if tc else t0
            r = [c[1][k] for c in rc] if rc else r0
            local[n] = (t, r)
        frames.append(compose(bones, local))
    return frames


def gltf_frames(doc, binary):
    """Per frame: {bone: position in cm} from the glTF animation channels."""
    names = {i: n["name"] for i, n in enumerate(doc["nodes"])}
    anim = doc["animations"][0]
    tracks = {}
    for ch in anim["channels"]:
        s = anim["samplers"][ch["sampler"]]
        tracks[(ch["target"]["node"], ch["target"]["path"])] = data(doc, binary, s["output"])
    count = len(next(iter(tracks.values())))
    out = []
    for k in range(count):
        local = rest_locals(doc)
        for i in local:
            local[i] = (tracks[(i, "translation")][k], tracks[(i, "rotation")][k])
        g = globals_(doc, local)
        out.append({names[i]: tuple(100 * g[i][r][3] for r in range(3)) for i in g})
    return out


@pytest.fixture(scope="module", params=CHARACTERS)
def animated(request):
    ch = load_character(request.param)
    scene = build_scene(ch, emission=1.0, shot=SHOT)
    return ch, scene, Scene(fbx_from_scene(scene))


# ---- the file -------------------------------------------------------------------------------------------------------

def test_the_file_is_fbx_7400_with_its_sections(animated):
    _, _, sc = animated
    assert sc.version == 7400
    for name in ("FBXHeaderExtension", "FileId", "CreationTime", "Creator", "GlobalSettings", "Documents",
                 "Definitions", "Objects", "Connections", "Takes"):
        assert name in sc.top, name


def test_global_settings_declare_y_up_centimetres_and_the_frame_rate(animated):
    _, scene, sc = animated
    s = sc.settings
    assert s["UpAxis"] == [1] and s["UpAxisSign"] == [1]
    assert s["FrontAxis"] == [2] and s["FrontAxisSign"] == [1]
    assert s["CoordAxis"] == [0] and s["CoordAxisSign"] == [1]
    assert s["UnitScaleFactor"] == [1.0]
    assert s["CustomFrameRate"] == [scene.animation.fps]
    assert s["TimeSpanStop"] == [round((len(scene.animation.rotations) - 1) * KTIME / scene.animation.fps)]


def test_definitions_count_the_objects(animated):
    _, _, sc = animated
    defs = {d.props[0]: d.find("Count").props[0] for d in sc.top["Definitions"].all("ObjectType")}
    for kind in ("Model", "NodeAttribute", "Geometry", "Material", "Deformer", "Pose", "AnimationStack",
                 "AnimationLayer", "AnimationCurveNode", "AnimationCurve"):
        assert defs[kind] == len(sc.of(kind)), kind
    assert sc.top["Definitions"].find("Count").props[0] == sum(defs.values())


def test_every_connection_names_objects_that_exist(animated):
    _, _, sc = animated
    for c in sc.links:
        assert c[0] in ("OO", "OP")
        assert c[1] in sc.objects
        assert c[2] == 0 or c[2] in sc.objects


# ---- the skeleton ---------------------------------------------------------------------------------------------------

def test_the_bones_have_the_scene_names_and_parents(animated):
    _, scene, sc = animated
    bones = sc.bones()
    assert set(bones) == set(ALL_BONES)
    for b in scene.bones:
        assert bones[b.name][1] == b.parent == PARENTS[b.name]
    for n, (m, _) in bones.items():
        attrs = sc.children(m.props[0], "NodeAttribute")
        assert len(attrs) == 1 and attrs[0].props[2] == "LimbNode"


def test_the_rest_pose_is_the_scene_rest_in_centimetres_mirrored(animated):
    _, scene, sc = animated
    _, rest = fbx_rest(sc)
    for b in scene.bones:
        want = (-100 * b.head[0], 100 * b.head[1], 100 * b.head[2])
        assert math.dist(rest[b.name][1], want) < 1e-6, b.name
        # the bone's Y axis (along the bone) is the mirrored world Y axis of its frame
        y = [rest[b.name][0][r][1] for r in range(3)]
        fy = b.frame[1]
        assert math.dist(y, (-fy[0], fy[1], fy[2])) < 1e-9, b.name


def test_the_bind_pose_matches_the_cluster_links(animated):
    _, scene, sc = animated
    _, rest = fbx_rest(sc)
    poses = sc.of("Pose", "BindPose")
    assert len(poses) == 1
    pose = {n.find("Node").props[0]: n.find("Matrix").props[0] for n in poses[0].all("PoseNode")}
    bones = sc.bones()
    assert poses[0].find("NbPoseNodes").props[0] == len(pose) == len(bones) + 1
    for name, (m, _) in bones.items():
        mat = pose[m.props[0]]
        r, t = rest[name]
        assert max(abs(mat[12 + i] - t[i]) for i in range(3)) < 1e-6
        assert max(abs(mat[4 * c + i] - r[i][c]) for i in range(3) for c in range(3)) < 1e-9
        cl = [sc.objects[p] for p in sc.parents(m.props[0]) if sc.objects.get(p) is not None
              and sc.objects[p].name == "Deformer"]
        assert len(cl) == 1
        assert cl[0].find("TransformLink").props[0] == pytest.approx(mat, abs=1e-9)


# ---- the mesh and its skin ------------------------------------------------------------------------------------------

def test_the_geometry_holds_every_vertex_and_triangle(animated):
    _, scene, sc = animated
    geos = sc.of("Geometry", "Mesh")
    assert len(geos) == 1
    g = geos[0]
    verts = g.find("Vertices").props[0]
    poly = g.find("PolygonVertexIndex").props[0]
    assert len(verts) == 3 * sum(len(m.vertices) for m in scene.meshes)
    assert len(poly) == 3 * sum(len(m.triangles) for m in scene.meshes)
    assert all(poly[k] < 0 for k in range(2, len(poly), 3))
    assert all(poly[k] >= 0 for k in range(len(poly)) if k % 3 != 2)
    assert len(g.find("LayerElementNormal").find("Normals").props[0]) == len(verts)
    mats = g.find("LayerElementMaterial").find("Materials").props[0]
    assert len(mats) == len(poly) // 3
    ys = verts[1::3]
    assert min(ys) == pytest.approx(0.0, abs=0.5)                       # standing on the floor
    assert max(ys) == pytest.approx(171.0, abs=1.0)                     # 1.71 m tall, in centimetres


def test_the_winding_faces_outward_after_the_mirror(animated):
    """Each triangle's normal (by its winding) agrees with its vertices' normals, as the glTF export's does."""
    _, _, sc = animated
    g = sc.of("Geometry", "Mesh")[0]
    v = g.find("Vertices").props[0]
    n = g.find("LayerElementNormal").find("Normals").props[0]
    poly = g.find("PolygonVertexIndex").props[0]
    agree = total = 0
    for k in range(0, len(poly), 3):
        i, j, l = poly[k], poly[k + 1], -poly[k + 2] - 1
        a, b, c = ([v[3 * x + d] for d in range(3)] for x in (i, j, l))
        u, w = [b[d] - a[d] for d in range(3)], [c[d] - a[d] for d in range(3)]
        cr = (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0])
        if math.hypot(*cr) < 1e-9:
            continue
        avg = [n[3 * i + d] + n[3 * j + d] + n[3 * l + d] for d in range(3)]
        total += 1
        agree += sum(cr[d] * avg[d] for d in range(3)) > 0
    assert agree / total > 0.99


def test_every_vertex_is_bound_to_its_mesh_bone_with_weight_1(animated):
    _, scene, sc = animated
    bones = sc.bones()
    skins = sc.of("Deformer", "Skin")
    assert len(skins) == 1
    geo = sc.of("Geometry", "Mesh")[0]
    assert geo.props[0] in sc.parents(skins[0].props[0])
    owner = {}
    for cl in sc.children(skins[0].props[0], "Deformer"):
        links = [o for o in sc.children(cl.props[0], "Model")]
        assert len(links) == 1
        bone = _name(links[0].props[1])
        idx = cl.find("Indexes").props[0] if cl.find("Indexes") else []
        w = cl.find("Weights").props[0] if cl.find("Weights") else []
        assert len(idx) == len(w) and all(x == 1.0 for x in w)
        for i in idx:
            assert i not in owner
            owner[i] = bone
    order = ("body", "joint", "emission")                 # the geometry groups the shapes by material
    want = [m.bone for name in order for m in scene.meshes if m.material == name for _ in m.vertices]
    assert [owner[i] for i in range(len(want))] == want
    assert {_name(c.props[1]) for c in sc.children(skins[0].props[0], "Deformer")} == set(bones)


def test_cluster_transform_is_the_inverse_of_its_link(animated):
    _, _, sc = animated
    for cl in sc.of("Deformer", "Cluster"):
        t, l = cl.find("Transform").props[0], cl.find("TransformLink").props[0]
        for i in range(4):
            for j in range(4):
                v = sum(t[4 * k + i] * l[4 * j + k] for k in range(4))       # column-major T * L
                assert v == pytest.approx(1.0 if i == j else 0.0, abs=1e-9)


# ---- materials ------------------------------------------------------------------------------------------------------

def test_three_materials_and_the_glow_only_when_on():
    ch = load_character("kei")
    for strength in (0.0, 0.6):
        sc = Scene(fbx_from_scene(build_scene(ch, emission=strength)))
        mats = {_name(m.props[1]): p70(m) for m in sc.of("Material")}
        assert set(mats) == {"body", "joint", "emission"}
        for name, props in mats.items():
            assert len(props["DiffuseColor"]) == 3
            glow = name == "emission" and strength > 0
            assert ("EmissiveColor" in props) == glow, (name, strength)
            if glow:
                assert props["EmissiveFactor"] == [strength]
        mesh = sc.of("Model", "Mesh")[0]
        assert [_name(m.props[1]) for m in sc.children(mesh.props[0], "Material")] == ["body", "joint", "emission"]


# ---- animation ------------------------------------------------------------------------------------------------------

def test_one_stack_one_layer_and_keys_on_every_frame(animated):
    _, scene, sc = animated
    stacks, layers = sc.of("AnimationStack"), sc.of("AnimationLayer")
    assert len(stacks) == 1 and len(layers) == 1
    assert layers[0].props[0] in [o.props[0] for o in sc.children(stacks[0].props[0])]
    n = len(scene.animation.rotations)
    for c in sc.of("AnimationCurve"):
        times = c.find("KeyTime").props[0]
        assert times == [round(k * KTIME / scene.animation.fps) for k in range(n)]
        assert len(c.find("KeyValueFloat").props[0]) == n
        assert c.find("KeyAttrRefCount").props[0] == [n]


def test_rotation_curves_on_every_bone_and_translation_where_it_moves(animated):
    _, scene, sc = animated
    a = scene.animation
    for i, b in enumerate(scene.bones):
        model = sc.bones()[b.name][0]
        assert curves(sc, model, "Lcl Rotation") is not None
        moves = any(math.dist(row[i], b.translation) > 1e-9 for row in a.translations)
        assert (curves(sc, model, "Lcl Translation") is not None) == moves, b.name
    assert curves(sc, sc.bones()["root"][0], "Lcl Translation") is not None


def test_the_keyed_joints_match_the_scene_animation(animated):
    _, scene, sc = animated
    frames = fbx_frames(sc)
    a = scene.animation
    assert len(frames) == len(a.rotations)
    from test_export_scene import compose as scene_compose
    for k, fr in enumerate(frames):
        want = scene_compose(scene, k)
        for n, p in want.items():
            assert math.dist(fr[n][1], (-100 * p[0], 100 * p[1], 100 * p[2])) < 0.01, (k, n)   # 0.1 mm


def test_a_90_degree_bend_on_each_axis_of_each_bone_matches_the_gltf_joints():
    """Review Focus 2: every bone bent 90 deg about its own X, Y and Z in turn, one frame each; the FBX joints (from
    the Euler curves) and the glTF joints (from the quaternions) agree within 1 mm."""
    scene = build_scene(load_character("kei"))
    rest_r = [b.rotation for b in scene.bones]
    rest_t = [b.translation for b in scene.bones]
    s = math.sqrt(0.5)
    turns = [(s, 0, 0, s), (0, s, 0, s), (0, 0, s, s)]
    rots = []
    for i in range(len(scene.bones)):
        for q in turns:
            row = list(rest_r)
            x1, y1, z1, w1 = rest_r[i]
            x2, y2, z2, w2 = q
            row[i] = (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                      w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)
            rots.append(row)
    scene.animation = SceneAnimation(24.0, rots, [list(rest_t) for _ in rots])
    fb = fbx_frames(Scene(fbx_from_scene(scene)))
    gl = gltf_frames(*gltf_from_scene(scene))
    worst = max(math.dist(fb[k][n][1], gl[k][n]) for k in range(len(rots)) for n in ALL_BONES)
    assert worst < 0.1, worst                                  # centimetres: 1 mm


def test_euler_xyz_round_trips_including_gimbal_lock():
    import random
    rnd = random.Random(3)
    cases = [(0, 90, 0), (30, 90, -20), (10, -90, 50), (180, 0, 0), (0, 0, 0)]
    cases += [tuple(rnd.uniform(-180, 180) for _ in range(3)) for _ in range(200)]
    for e in cases:
        m = euler_matrix(e)
        back = euler_matrix(euler_xyz(m))
        assert max(abs(m[i][j] - back[i][j]) for i in range(3) for j in range(3)) < 1e-9, e


def test_euler_xyz_picks_the_turn_nearest_the_previous_frame():
    m = euler_matrix((170, 10, 0))
    e = euler_xyz(m, near=(-185, 10, 0))
    assert e[0] == pytest.approx(-190) and e[1] == pytest.approx(10) and e[2] == pytest.approx(0, abs=1e-9)
    e = euler_xyz(euler_matrix((0, 80, 0)), near=(180, 100, 180))     # the equivalent triple (a+180, 180-b, c+180)
    assert e == pytest.approx((180, 100, 180))


def test_a_long_shot_writes_quickly_and_compressed():
    """Review Focus 3: 2,000 frames of every bone turning."""
    scene = build_scene(load_character("kei"))
    rest_r = [b.rotation for b in scene.bones]
    rest_t = [b.translation for b in scene.bones]
    rots = []
    for k in range(2000):
        a = 0.3 * math.sin(k / 20)
        h = (math.sin(a / 2), 0.0, 0.0, math.cos(a / 2))
        row = []
        for x1, y1, z1, w1 in rest_r:
            x2, y2, z2, w2 = h
            row.append((w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2))
        rots.append(row)
    trans = [[(rest_t[0][0], rest_t[0][1], rest_t[0][2] + k * 0.01)] + list(rest_t[1:]) for k in range(2000)]
    scene.animation = SceneAnimation(30.0, rots, trans)
    t0 = time.perf_counter()
    blob = fbx_from_scene(scene)
    spent = time.perf_counter() - t0
    assert spent < 20, spent
    raw_keys = (64 * 3 + 3) * 2000 * (8 + 4)                     # int64 times and float32 values, uncompressed
    still = len(fbx_from_scene(build_scene(load_character("kei"))))
    assert len(blob) - still < 0.7 * raw_keys, (len(blob), still)
    sc = Scene(blob)
    assert len(sc.of("AnimationCurve")) == 64 * 3 + 3
    root = sc.bones()["root"][0]
    tz = curves(sc, root, "Lcl Translation")[2][1]
    assert tz[-1] == pytest.approx(100 * (rest_t[0][2] + 19.99), abs=1e-3)


def test_a_still_scene_has_no_animation():
    sc = Scene(fbx_from_scene(build_scene(load_character("keira"))))
    assert not sc.of("AnimationStack") and not sc.of("AnimationCurve")
    assert sc.top["Takes"].find("Current").props == [""]


def test_build_fbx_is_build_scene_then_fbx_from_scene():
    ch = load_character("kei")
    assert build_fbx(ch, 0.5, SHOT) == fbx_from_scene(build_scene(ch, 0.5, SHOT))


# ---- the command ----------------------------------------------------------------------------------------------------

def test_kei_export_format_fbx(tmp_path, capsys):
    from kei.cli import main
    out = tmp_path / "kei.fbx"
    assert main(["export", "--character", "kei", "--format", "fbx", "--out", str(out)]) == 0
    Scene(out.read_bytes())
    assert str(out) in capsys.readouterr().out


def test_kei_export_takes_the_format_from_the_file_name(tmp_path):
    from kei.cli import main
    (tmp_path / "s" / "out_p1").mkdir(parents=True)
    (tmp_path / "s" / "out_p1" / "shot.json").write_text(json.dumps(SHOT), encoding="utf-8")
    out = tmp_path / "keira.FBX"
    assert main(["export", "--character", "keira", "--out", str(out), "--shot", str(tmp_path / "s"),
                 "--pass", "p1"]) == 0
    assert Scene(out.read_bytes()).of("AnimationStack")


def test_kei_export_default_name_follows_the_format(tmp_path, monkeypatch):
    from kei.cli import main
    monkeypatch.chdir(tmp_path)
    assert main(["export", "--character", "kei", "--format", "fbx"]) == 0
    assert (tmp_path / "kei.fbx").is_file()


def test_kei_export_refuses_a_format_the_file_name_contradicts(tmp_path, capsys):
    from kei.cli import main
    assert main(["export", "--character", "kei", "--format", "gltf", "--out", str(tmp_path / "x.fbx")]) == 1
    assert not (tmp_path / "x.fbx").exists()


def test_an_animated_property_is_flagged_animated_and_a_still_one_is_not(animated):
    """FBX marks a property that carries a curve with the flags 'A+' (animatable, animated); readers look for its
    curve only then."""
    _, scene, sc = animated
    a = scene.animation
    for i, b in enumerate(scene.bones):
        m = sc.bones()[b.name][0]
        flags = {p.props[0]: p.props[3] for p in m.find("Properties70").children}
        assert flags["Lcl Rotation"] == "A+"
        moves = any(math.dist(row[i], b.translation) > 1e-9 for row in a.translations)
        assert flags["Lcl Translation"] == ("A+" if moves else "A"), b.name
        assert flags["Lcl Scaling"] == "A"
    still = Scene(fbx_from_scene(build_scene(load_character("kei"))))
    for m, _ in still.bones().values():
        assert {p.props[3] for p in m.find("Properties70").children if p.props[0].startswith("Lcl")} == {"A"}


def test_the_mesh_has_one_uv_set_in_the_layer(animated):
    """A planar front projection (u from x, v from height), so importers do not invent a UV set and warn."""
    _, _, sc = animated
    g = sc.of("Geometry", "Mesh")[0]
    uv = g.find("LayerElementUV")
    assert uv.find("MappingInformationType").props == ["ByPolygonVertex"]
    assert uv.find("ReferenceInformationType").props == ["IndexToDirect"]
    coords, index = uv.find("UV").props[0], uv.find("UVIndex").props[0]
    poly = g.find("PolygonVertexIndex").props[0]
    assert len(index) == len(poly) and max(index) < len(coords) // 2
    assert all(0.0 <= c <= 1.0 for c in coords)
    types = [e.find("Type").props[0] for e in g.find("Layer").all("LayerElement")]
    assert "LayerElementUV" in types


def test_the_definitions_carry_the_animation_templates(animated):
    """A curve node's channels d|X, d|Y, d|Z are members of its compound property d, which the AnimationCurveNode
    template declares; without it a reader finds no channels and the curves are ignored (seen in Unreal)."""
    _, _, sc = animated
    types = {d.props[0]: d for d in sc.top["Definitions"].all("ObjectType")}
    t = types["AnimationCurveNode"].find("PropertyTemplate")
    assert t.props == ["FbxAnimCurveNode"]
    assert [p.props[:2] for p in t.find("Properties70").children] == [["d", "Compound"]]
    layer = {p.props[0]: p.props[4:] for p in types["AnimationLayer"].find("PropertyTemplate").find("Properties70").children}
    assert layer["Weight"] == [100.0]


def test_the_layer_record_carries_its_empty_child_list(animated):
    _, _, sc = animated
    layer = sc.of("AnimationLayer")[0]
    assert layer.listed and layer.children == []


def test_the_readme_names_fbx_as_an_export_format():
    from pathlib import Path
    text = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
    assert "FBX is planned" not in text
    assert "--format gltf|fbx" in text
