"""Objects in a shot: Kei places them on every frame from their attach events, draws them and checks them."""
import pytest

from kei.objects import ObjectError, object_flags, object_parts, read_objects, track


def _frames(hand_l, hand_r, n=5):
    """n frames whose hands sit where hand_l(f) and hand_r(f) say (palm = the hand joint and its tip, together)."""
    out = []
    for f in range(n):
        j = {}
        for s, at in (("l", hand_l), ("r", hand_r)):
            p = at(f)
            j[f"hand_{s}"] = p
            j[f"hand_{s}_tip"] = p
        out.append({"f": f, "joints": j})
    return out


def crate(**kw):
    o = {"name": "crate", "shape": "box", "size": [0.4, 0.4, 0.4], "rest": [0.0, 0.2, 0.5],
         "attach": [{"f": 1, "to": "hands"}, {"f": 3, "to": "floor"}]}
    o.update(kw)
    return o


def lift(f):   # the hands at the crate's sides on frame 1, then up 0.1 m a frame, then still
    y = 0.2 + 0.1 * max(0, min(f, 3) - 1)
    return y


FRAMES = _frames(lambda f: (-0.2, lift(f), 0.5), lambda f: (0.2, lift(f), 0.5))


def test_a_held_object_follows_the_hands_and_stays_where_it_is_let_go():
    shot = {"frames": 4, "objects": [crate()]}
    t = track(read_objects(shot)[0], FRAMES)
    ys = [round(c[1], 3) for c, _ in t]
    assert ys == [0.2, 0.2, 0.3, 0.4, 0.4]
    assert [h for _, h in t] == [None, "hands", "hands", None, None]


def test_an_object_is_drawn_on_every_frame_with_its_own_material():
    shot = {"frames": 4, "objects": [crate(), crate(name="ball", shape="sphere", size=[0.2], attach=[])]}
    parts = object_parts(shot, FRAMES)
    assert len(parts) == 5 and all(len(p) == 2 for p in parts)
    assert {p.material for p in parts[0]} == {"object:crate", "object:ball"}
    top = max(v[1] for v in parts[2][0].verts)
    assert top == pytest.approx(0.5, abs=0.01)


@pytest.mark.parametrize("bad, words", [
    ({"shape": "cone"}, "shape"),
    ({"size": [0.4, 0.4]}, "size"),
    ({"attach": [{"f": 9, "to": "hands"}]}, "frame"),
    ({"attach": [{"f": 1, "to": "foot_l"}]}, "to"),
    ({"name": ""}, "name"),
])
def test_a_wrong_object_is_refused_with_its_reason(bad, words):
    with pytest.raises(ObjectError, match=words):
        read_objects({"frames": 4, "objects": [crate(**bad)]})


def test_two_objects_with_one_name_are_refused():
    with pytest.raises(ObjectError, match="twice"):
        read_objects({"frames": 4, "objects": [crate(), crate()]})


def test_no_objects_is_an_empty_list():
    assert read_objects({"frames": 4}) == []
    assert object_parts({"frames": 4}, FRAMES) == [[] for _ in FRAMES]


def test_an_object_under_the_floor_is_a_hard_flag():
    shot = {"frames": 4, "objects": [crate(rest=[0.0, 0.18, 0.5], attach=[])]}
    flags = object_flags(shot, FRAMES)
    assert [fl["frames"] for fl in flags] == [[0, 4]]
    assert "under the ground" in flags[0]["what"] and "measure" not in flags[0]


def test_an_object_let_go_in_the_air_floats():
    shot = {"frames": 4, "objects": [crate(attach=[{"f": 1, "to": "hands"}, {"f": 2, "to": "floor"}])]}
    flags = object_flags(shot, FRAMES)
    assert [fl["frames"] for fl in flags] == [[2, 4]]
    assert "nothing holds" in flags[0]["what"]


def test_a_grab_from_a_distance_is_flagged():
    far = _frames(lambda f: (-0.3, 0.2, 0.5), lambda f: (0.2, 0.2, 0.5))   # the left hand 0.1 m off the side
    shot = {"frames": 4, "objects": [crate(attach=[{"f": 1, "to": "hands"}])]}
    flags = object_flags(shot, far)
    assert [fl["frames"] for fl in flags] == [[1, 1]]
    assert "left hand" in flags[0]["what"] and "0.100" in flags[0]["what"]


def test_a_clean_lift_and_set_down_has_no_flag():
    up_down = {0: 0.2, 1: 0.2, 2: 0.3, 3: 0.2, 4: 0.2}
    frames = _frames(lambda f: (-0.2, up_down[f], 0.5), lambda f: (0.2, up_down[f], 0.5))
    assert object_flags({"frames": 4, "objects": [crate()]}, frames) == []


def test_a_held_load_moves_the_centre_of_mass_toward_it():
    from kei.objects import with_loads
    frames = [{"f": f, "joints": {**fr["joints"], "com": (0.0, 1.0, 0.0)}} for f, fr in enumerate(FRAMES)]
    shot = {"frames": 4, "objects": [crate(mass_kg=30)]}
    out = with_loads(shot, frames, 70.0)
    assert out[0]["joints"]["com"] == (0.0, 1.0, 0.0), "not held yet"
    c = out[1]["joints"]["com"]
    assert c[2] == pytest.approx(0.5 * 30 / 100) and out[1]["joints"]["com_body"] == (0.0, 1.0, 0.0)


def test_a_grounded_object_the_palms_press_on_is_support():
    from kei.objects import with_loads
    frames = [{"f": 0, "joints": {**FRAMES[0]["joints"], "com": (0.0, 1.0, 0.3)}}]
    out = with_loads({"frames": 0, "objects": [crate(attach=[])]}, frames, 70.0)
    pts = out[0]["support_extra"]
    assert len(pts) == 4 and min(p[1] for p in pts) == pytest.approx(0.3) and max(p[1] for p in pts) == pytest.approx(0.7)


def test_the_body_mass_comes_from_character_md(tmp_path):
    from kei.objects import body_mass
    (tmp_path / "CHARACTER.md").write_text("## kei\nMass: 69.7 kg, weighed from the mesh\n", encoding="utf-8")
    assert body_mass(tmp_path, 1.71) == 69.7
    assert body_mass(None, 1.71) == pytest.approx(70.0)


def test_a_palm_that_slides_off_or_into_a_held_object_is_flagged():
    from kei.objects import grip_flags
    spread = {0: 0.2, 1: 0.2, 2: 0.28, 3: 0.28, 4: 0.2}   # the hands slide apart on f2-3, the box stays between them
    frames = _frames(lambda f: (-spread[f], 0.2, 0.5), lambda f: (spread[f], 0.2, 0.5))
    flags = grip_flags({"frames": 4, "objects": [crate(attach=[{"f": 1, "to": "hands"}])]}, frames)
    assert {(f["frames"][0], f["frames"][1]) for f in flags} == {(2, 3)} and len(flags) == 2
    assert all("drifts" in f["what"] for f in flags)
    press = {0: 0.2, 1: 0.2, 2: 0.15, 3: 0.2, 4: 0.2}
    frames = _frames(lambda f: (-press[f], 0.2, 0.5), lambda f: (press[f], 0.2, 0.5))
    flags = grip_flags({"frames": 4, "objects": [crate(attach=[{"f": 1, "to": "hands"}])]}, frames)
    assert flags and all("sinks" in f["what"] and f["frames"] == [2, 2] for f in flags)


def _swing(f):
    """The palms on the crate's sides; from frame 2 the line between them turns 90 degrees about the crate's centre."""
    if f < 2:
        return (-0.2, 0.2, 0.5), (0.2, 0.2, 0.5)
    return (0.0, 0.2, 0.7), (0.0, 0.2, 0.3)


SWING = _frames(lambda f: _swing(f)[0], lambda f: _swing(f)[1])


def test_an_object_that_turns_with_the_hands_follows_the_line_between_the_palms():
    import math
    from kei.objects import yaws
    o = read_objects({"frames": 4, "objects": [crate(turn="hands", yaw_deg=10)]})[0]
    ys = [round(math.degrees(y), 1) for y in yaws(o, SWING)]
    assert ys == [10.0, 10.0, 100.0, 100.0, 100.0]               # held from f1, turned 90 at f2, let go at f3
    still = read_objects({"frames": 4, "objects": [crate()]})[0]
    assert set(yaws(still, SWING)) == {0.0}                      # turn "none": it keeps its heading


def test_a_turned_box_measures_the_palm_gap_in_its_own_axes():
    from kei.objects import surface_gap
    import math
    o = read_objects({"frames": 4, "objects": [crate(size=[0.8, 0.4, 0.2])]})[0]
    c = (0.0, 0.2, 0.0)
    assert surface_gap(o, c, (0.0, 0.2, 0.3)) > 0.1                       # 0.3 m in front: outside the thin box
    assert surface_gap(o, c, (0.0, 0.2, 0.3), math.radians(90)) == 0.0    # turned, its long side reaches there


def test_wrong_turn_settings_are_refused():
    for bad in ({"turn": "spin"}, {"yaw_deg": "left"}):
        with pytest.raises(ObjectError):
            read_objects({"frames": 4, "objects": [crate(**bad)]})


def test_the_stick_render_draws_objects_as_outlines():
    from kei.objects import object_edges
    edges = object_edges({"frames": 4, "objects": [crate(colour="#ff0000")]}, FRAMES)
    assert len(edges) == 5 and len(edges[0]) == 12 and edges[0][0][2] == (255, 0, 0)


def test_a_body_part_inside_an_object_is_flagged_and_one_clear_of_it_is_not():
    import time
    from kei.characters import load_character
    from kei.objects import mesh_flags
    from kei.sample import bake
    stand = {"root": [0, 0.915, 0], "footL": [-0.12, 0.09, 0, 0, 0], "footR": [0.12, 0.09, 0, 0, 0]}
    base = {"rig": "v4", "fps": 24, "frames": 4, "keys": [{"f": 0, **stand}, {"f": 4, **stand}]}
    ch = load_character("kei")
    inside = {**base, "objects": [{"name": "crate", "shape": "box", "size": [0.3, 0.3, 0.3], "rest": [0.0, 1.1, 0.0]}]}
    t0 = time.perf_counter()
    flags = mesh_flags(inside, bake(inside), ch)
    assert flags and all(f["measure"] == "mesh_depth_m" and f["value"] > 0.02 for f in flags)
    assert time.perf_counter() - t0 < 30
    clear = {**base, "objects": [{"name": "crate", "shape": "box", "size": [0.3, 0.3, 0.3], "rest": [0.0, 0.15, 0.9]}]}
    assert mesh_flags(clear, bake(clear), ch) == []


def test_an_object_with_a_path_carries_the_hands_on_its_grip_points():
    import math
    from kei.objects import grip_targets
    from kei.sample import bake
    stand = {"root": [0, 0.915, 0], "footL": [-0.12, 0.09, 0, 0, 0], "footR": [0.12, 0.09, 0, 0, 0]}
    shot = {"rig": "v4", "fps": 24, "frames": 12, "keys": [{"f": 0, **stand}, {"f": 12, **stand}],
            "objects": [{"name": "crate", "shape": "box", "size": [0.36, 0.3, 0.3], "rest": [0, 1.0, 0.3],
                         "path": [{"f": 0, "pos": [0, 1.0, 0.3]}, {"f": 12, "pos": [0, 1.15, 0.3], "yaw_deg": 20}],
                         "grip": {"l": [-0.18, 0, 0], "r": [0.18, 0, 0]}, "attach": [{"f": 0, "to": "hands"}]}]}
    frames = bake(shot)
    for fr in frames:
        t = grip_targets(shot, fr["f"])
        for s, ch in (("l", "ikL"), ("r", "ikR")):
            assert math.dist(fr["joints"][f"hand_{s}"], t[ch][:3]) < 0.01, (fr["f"], s)
    o = read_objects(shot)[0]
    assert [round(c[1], 3) for c, _ in track(o, frames)][::12] == [1.0, 1.15]       # it moves on its own keys


def test_a_wrong_path_or_grip_is_refused():
    for bad in ({"path": [{"f": 0}]}, {"grip": {"x": [0, 0, 0]}}):
        with pytest.raises(ObjectError):
            read_objects({"frames": 4, "objects": [crate(**bad)]})
