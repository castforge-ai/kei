"""The character data: Kei and Keira load, validate, stand on the floor at 1.71 m and carry their measurements."""
import copy
import json
import math

import pytest

from kei.characters import (CHARACTERS, KINDS, MATERIALS, CharacterError, load_character, parse_character, raw,
                            rest_pose, rest_skeleton)
from kei.rig import ALL_BONES, BONES, PROPORTIONS, check_proportions, over_reach, skeleton, solve


@pytest.fixture(params=CHARACTERS)
def ch(request):
    return load_character(request.param)


def test_both_characters_exist():
    assert CHARACTERS == ("kei", "keira")


def test_unknown_character_is_refused():
    with pytest.raises(CharacterError, match="bob"):
        load_character("bob")


def test_proportions_are_valid_and_complete(ch):
    check_proportions(ch.proportions)
    assert set(ch.proportions) <= set(PROPORTIONS)


def test_every_shape_is_on_a_known_bone_with_a_known_kind_and_material(ch):
    assert ch.shapes
    for s in ch.shapes:
        assert s.bone in ALL_BONES
        assert s.kind in KINDS
        assert s.material in MATERIALS


def test_the_rest_pose_stands_on_the_floor_at_the_measured_height(ch):
    pose = rest_pose(ch)
    j = solve(pose, ch.proportions)
    assert over_reach(pose, ch.proportions) == 0
    assert abs(j["head_top"][1] - ch.height) < 0.01
    for s in "lr":
        assert abs(j[f"heel_{s}"][1]) < 1e-6 and abs(j[f"ball_{s}"][1]) < 1e-6
    assert ch.height == 1.71


def test_the_rig_takes_the_character_proportions(ch):
    j = solve(rest_pose(ch), ch.proportions)
    assert abs(math.dist(j["upperarm_l"], j["upperarm_r"]) - ch.measured["shoulder_joints"]) < 0.01
    assert abs(j["thigh_r"][1] - ch.measured["hip_joint_height"]) < 0.01


def test_every_side_shape_comes_in_a_mirrored_pair(ch):
    left = sorted((s.bone[:-2], s.kind, s.material) for s in ch.shapes if s.bone.endswith("_l"))
    right = sorted((s.bone[:-2], s.kind, s.material) for s in ch.shapes if s.bone.endswith("_r"))
    assert left == right and left


def test_the_rest_skeleton_mirrors_with_local_x_negated(ch):
    B = rest_skeleton(ch)
    for n in ALL_BONES:
        if not n.endswith("_r"):
            continue
        L, R = B[n[:-2] + "_l"], B[n]
        m = lambda v: (-v[0], v[1], v[2])
        assert math.dist(L.head, m(R.head)) < 1e-9, n
        XL, YL, ZL = L.frame
        XR, YR, ZR = R.frame
        assert math.dist(XL, tuple(-c for c in m(XR))) < 1e-9, n
        assert math.dist(YL, m(YR)) < 1e-9 and math.dist(ZL, m(ZR)) < 1e-9, n


def test_joint_shapes_sit_on_joint_centres(ch):
    for s in ch.shapes:
        if s.material == "joint":
            assert s.kind in ("sphere", "ellipsoid", "ring"), s
            assert math.dist(s.c, (0, 0, 0)) < 1e-6, s


def test_the_spine_beads_sit_on_spine_joints(ch):
    beads = {s.bone for s in ch.shapes if s.material == "joint" and s.bone.startswith("spine_")}
    assert len(beads) == 3 and beads == set(ch.spine_beads)


def test_one_emissive_chest_mark(ch):
    marks = [s for s in ch.shapes if s.material == "emission"]
    assert len(marks) == 1 and marks[0].kind == "mark" and marks[0].bone == "spine_05"


def test_hands_have_every_finger(ch):
    bones = {s.bone for s in ch.shapes}
    for s in "lr":
        for f in ("index", "middle", "ring", "pinky"):
            for k in ("01", "02", "03"):
                assert f"{f}_{k}_{s}" in bones
        for k in ("01", "02", "03"):
            assert f"thumb_{k}_{s}" in bones


def test_measurements_say_how_they_were_measured(ch):
    m = ch.measured
    assert m["source"].startswith("docs/characters/") and m["source"].endswith(".png")
    assert m["method"] and len(m["notes"]) >= 8
    for key in ("shoulder_joints", "hip_joint_height", "scale_mm_per_px"):
        assert isinstance(m[key], float)


def test_a_rest_space_shape_lands_where_it_was_written(ch):
    data = raw(ch.name)
    foot = next(s for s in data["shapes"] if s.get("space") == "rest" and s["bone"] == "foot_{s}")
    shape = next(s for s in ch.shapes if s.bone == "foot_r" and s.kind == foot["kind"] and s.note == foot.get("note"))
    B = rest_skeleton(ch)["foot_r"]
    X, Y, Z = B.frame
    world = tuple(B.head[i] + X[i] * shape.a[0] + Y[i] * shape.a[1] + Z[i] * shape.a[2] for i in range(3))
    assert math.dist(world, foot["a"]) < 1e-9
    left = next(s for s in ch.shapes if s.bone == "foot_l" and s.kind == foot["kind"] and s.note == foot.get("note"))
    BL = rest_skeleton(ch)["foot_l"]
    X, Y, Z = BL.frame
    world = tuple(BL.head[i] + X[i] * left.a[0] + Y[i] * left.a[1] + Z[i] * left.a[2] for i in range(3))
    assert math.dist(world, (-foot["a"][0], foot["a"][1], foot["a"][2])) < 1e-9


@pytest.mark.parametrize("change, message", [
    (lambda d: d["shapes"][0].update(bone="tail_01"), "tail_01"),
    (lambda d: d["shapes"][0].update(kind="cube"), "cube"),
    (lambda d: d["shapes"][0].update(material="gold"), "gold"),
    (lambda d: d["shapes"][0].update(colour="red"), "colour"),
    (lambda d: d["proportions"].update(thigh=-0.4), "thigh"),
    (lambda d: d["proportions"].update(tail=0.4), "tail"),
    (lambda d: d["rest"].update(wings=[1]), "wings"),
    (lambda d: d.update(height="tall"), "height"),
    (lambda d: d.pop("shapes"), "shapes"),
])
def test_bad_data_is_refused_and_named(change, message):
    data = copy.deepcopy(raw("kei"))
    change(data)
    with pytest.raises(CharacterError, match=message):
        parse_character(data, "kei")


def test_bad_numbers_in_a_shape_are_refused():
    for bad in (float("nan"), float("inf"), -0.01, 0, "1", True):
        data = copy.deepcopy(raw("kei"))
        s = next(s for s in data["shapes"] if s["kind"] == "sphere")
        s["r"] = bad
        with pytest.raises(CharacterError, match="r"):
            parse_character(data, "kei")
    data = copy.deepcopy(raw("kei"))
    s = next(s for s in data["shapes"] if s["kind"] == "capsule")
    s["a"] = [0, float("nan"), 0]
    with pytest.raises(CharacterError, match="a"):
        parse_character(data, "kei")


def test_the_files_are_plain_json_without_em_dashes():
    from kei.characters import DATA
    for name in CHARACTERS:
        text = (DATA / f"{name}.json").read_text(encoding="utf-8")
        json.loads(text)
        assert chr(0x2014) not in text


def test_the_chest_mark_may_tilt_to_follow_the_chest():
    """A mark takes rot like an ellipsoid: turned about X, its front faces up the chest's slope."""
    data = copy.deepcopy(raw("kei"))
    mark = next(s for s in data["shapes"] if s["kind"] == "mark")
    mark["rot"] = [-0.4, 0, 0]
    ch = parse_character(data, "kei")
    X, Y, Z = next(s for s in ch.shapes if s.kind == "mark").axes
    assert Z[1] == pytest.approx(math.sin(0.4)) and Z[2] == pytest.approx(math.cos(0.4))
    assert X == pytest.approx((1.0, 0.0, 0.0))


def _with_block(**extra):
    data = copy.deepcopy(raw("kei"))
    block = {"bone": "spine_05", "kind": "block", "material": "body", "c": [0, 0, 0], "r": [0.2, 0.15, 0.12]}
    block.update(extra)
    data["shapes"].append(block)
    return data


def test_a_block_is_a_rounded_box_that_may_taper():
    """A block: an ellipsoid's box of r, its sides as flat as power makes them (2 is an ellipsoid), its width and
    depth scaled by 1 + taper at the top and 1 - taper at the bottom."""
    from kei.characters.mesh import shape_mesh
    ch = parse_character(_with_block(power=4, taper=[0.2, 0.0]), "kei")
    s = ch.shapes[-1]
    assert (s.power, s.taper) == (4.0, (0.2, 0.0))
    v, n, t = shape_mesh(s)
    assert max(p[1] for p in v) == pytest.approx(0.15, abs=1e-6)
    assert max(p[2] for p in v) == pytest.approx(0.12, abs=1e-6)
    # flat sides: near the middle height the width is close to the full 0.2 (an ellipsoid would round it off)
    mid = [abs(p[0]) for p in v if abs(p[1]) < 0.03 and abs(p[2]) < 0.03]
    assert max(mid) > 0.19
    # the taper: wider above the middle than below it
    up = max(abs(p[0]) for p in v if 0.06 < p[1] < 0.08)
    down = max(abs(p[0]) for p in v if -0.08 < p[1] < -0.06)
    assert up > down * 1.1


@pytest.mark.parametrize("extra, message", [
    ({"power": 1.5}, "power"), ({"power": 9}, "power"), ({"taper": [0.95, 0]}, "taper"), ({"taper": [0.1]}, "taper"),
    ({"material": "joint", "c": [0, 0, 0]}, "joint"),
])
def test_bad_blocks_are_refused(extra, message):
    with pytest.raises(CharacterError, match=message):
        parse_character(_with_block(**extra), "kei")


def test_a_mirrored_turned_block_is_not_inside_out():
    """A side block with rot: the left copy's axes are mirrored (left-handed); its mesh must still enclose a positive
    volume, or the renderer culls its outside and Unreal draws it inverted."""
    from kei.characters.mesh import shape_mesh
    data = copy.deepcopy(raw("kei"))
    data["shapes"].append({"bone": "thigh_{s}", "kind": "block", "material": "body", "c": [0, 0.2, 0],
                           "r": [0.05, 0.08, 0.05], "rot": [0.3, 0.2, 0.1]})
    ch = parse_character(data, "kei")
    for s in ch.shapes[-2:]:
        v, _, t = shape_mesh(s)
        vol = sum(sum(a * b for a, b in zip(v[i], cross(v[j], v[k]))) for i, j, k in t) / 6
        assert vol > 0, s.bone


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
