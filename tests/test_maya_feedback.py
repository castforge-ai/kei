"""Plan 6c: an animator corrects Kei's pass by posing on an animation layer named feedback. Task 1: the Maya-side tool
reads the feedback layers as offsets from Kei's own pass, on a copy of the scene. It runs here on a stand-in for
maya.cmds (tests/fake_maya.py), so no Maya is needed."""
import pytest

import fake_maya
from kei.apps.maya_side import kei_tools

PV = "kei:l_leg_pv_ctl.translateX"
HEAD = "kei:c_head_fk_ctl.rotateZ"
BODY = "kei:c_body_ctl.translateY"


def _scene(monkeypatch):
    cmds = fake_maya.FakeCmds({PV: lambda f: 10.0, HEAD: lambda f: 0.5 * f, BODY: lambda f: 2.0,
                               "kei2:l_leg_pv_ctl.translateX": lambda f: 0.0})
    cmds.add_layer("kei_p1", {})
    fake_maya.install(monkeypatch, cmds)
    return cmds


def _read(**kw):
    return kei_tools.call("read_feedback_layers", {"rig": "kei", "start": 0, "end": 12, **kw})


def _rows(out, layer):
    return {(e["control"], e["attr"], e["frame"]): e for e in out["layers"][layer]}


def test_a_feedback_layer_with_two_keyed_controls_is_read_with_frames_and_offsets(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback", {PV: {4: 0.0, 6: 5.0, 8: 0.0}, HEAD: {0: -2.0}})
    out = _read()
    rows = _rows(out, "feedback")
    knee = rows[("kei:l_leg_pv_ctl", "translateX", 6)]
    assert knee["offset"] == pytest.approx(5.0) and knee["value"] == pytest.approx(15.0) and knee["key"] is True
    assert rows[("kei:l_leg_pv_ctl", "translateX", 5)]["offset"] == pytest.approx(2.5)     # between the keys
    assert rows[("kei:l_leg_pv_ctl", "translateX", 5)]["key"] is False
    assert ("kei:l_leg_pv_ctl", "translateX", 2) not in rows                               # nothing changed there
    head = [e for e in out["layers"]["feedback"] if e["attr"] == "rotateZ"]
    assert len(head) == 13 and all(e["offset"] == pytest.approx(-2.0) for e in head)       # one key: every frame
    assert out["modes"]["feedback"] == "additive" and out["units"] == "cm" and out["unit_per_m"] == 100.0


def test_a_channel_added_to_the_layer_but_never_keyed_there_is_not_read(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback", {PV: {6: 5.0}}, added=[BODY])
    out = _read()
    assert {e["control"] for e in out["layers"]["feedback"]} == {"kei:l_leg_pv_ctl"}


def test_the_read_puts_the_current_frame_back(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback", {PV: {6: 5.0}})
    cmds.time = 3.0
    _read()
    assert cmds.time == 3.0


def test_a_layer_not_named_feedback_is_ignored(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("fixes", {PV: {6: 5.0}})
    cmds.add_layer("kei_p2", {PV: {6: 5.0}})
    cmds.add_layer("feedback_knee", {PV: {6: 1.0}})
    out = _read()
    assert set(out["layers"]) == {"feedback_knee"}


def test_the_read_leaves_every_layer_and_its_mute_state_as_it_was(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback", {PV: {6: 5.0}})
    cmds.add_layer("feedback_b", {HEAD: {6: 1.0}}, mute=True)
    before = {n: dict(lay) for n, lay in cmds.layers.items()}
    _read()
    assert {n: dict(lay) for n, lay in cmds.layers.items()} == before


def test_the_tool_is_refused_in_the_open_session_so_it_only_reads_a_copy():
    assert "read_feedback_layers" in kei_tools.BACKGROUND_ONLY
    assert "set_feedback_mute" in kei_tools.BACKGROUND_ONLY


def test_an_override_layer_s_offset_is_its_value_less_kei_s(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback", {HEAD: {6: 9.0}}, override=True)
    rows = _rows(_read(), "feedback")
    e = rows[("kei:c_head_fk_ctl", "rotateZ", 6)]
    assert e["value"] == pytest.approx(9.0) and e["offset"] == pytest.approx(9.0 - 3.0)
    assert _read()["modes"]["feedback"] == "override"


def test_two_feedback_layers_are_each_read_against_kei_s_pass_alone(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback", {PV: {6: 5.0}})
    cmds.add_layer("feedback_2", {PV: {6: 1.0}})
    out = _read()
    assert _rows(out, "feedback")[("kei:l_leg_pv_ctl", "translateX", 6)]["offset"] == pytest.approx(5.0)
    assert _rows(out, "feedback_2")[("kei:l_leg_pv_ctl", "translateX", 6)]["offset"] == pytest.approx(1.0)


def test_keys_outside_the_pass_are_reported_and_not_wrapped(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback", {BODY: {6: -3.0, 30: -3.0}})
    out = _read()
    assert out["outside"] == [{"layer": "feedback", "control": "kei:c_body_ctl", "attr": "translateY", "frame": 30}]
    assert max(e["frame"] for e in out["layers"]["feedback"]) == 12


def test_a_control_on_another_rig_is_named(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback", {"kei2:l_leg_pv_ctl.translateX": {6: 5.0}})
    out = _read()
    assert out["other_rig"] == [{"layer": "feedback", "control": "kei2:l_leg_pv_ctl", "attr": "translateX"}]
    assert out["layers"]["feedback"] == []


def test_a_locked_channel_is_marked_and_a_limited_one_gives_the_asked_and_the_reached_value(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.locked.add(BODY)
    cmds.limits[HEAD] = (-30.0, 30.0)
    cmds.add_layer("feedback", {BODY: {6: 1.0}, HEAD: {6: 40.0}})
    rows = _rows(_read(), "feedback")
    assert rows[("kei:c_body_ctl", "translateY", 6)]["locked"] is True
    head = rows[("kei:c_head_fk_ctl", "rotateZ", 6)]
    assert head["asked"] == pytest.approx(43.0) and head["reached"] == pytest.approx(30.0)


def test_mute_switches_every_feedback_layer_and_nothing_else(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback", {PV: {6: 5.0}})
    cmds.add_layer("fixes", {PV: {6: 5.0}})
    out = kei_tools.call("set_feedback_mute", {"mute": True})
    assert out == {"layers": ["feedback"], "mute": True}
    assert cmds.layers["feedback"]["mute"] is True and cmds.layers["fixes"]["mute"] is False


# ---------------- Task 2: the offsets in plain words ----------------
def _offsets(rows, layer="feedback", start=0, end=12, unit_per_m=100.0):
    return {"layers": {layer: rows}, "start": start, "end": end, "unit_per_m": unit_per_m, "units": "cm",
            "outside": [], "other_rig": [], "modes": {layer: "additive"}}


def _row(control, attr, f, off, key=True):
    return {"control": control, "attr": attr, "frame": f, "value": off, "offset": off, "key": key}


def test_a_knee_pole_move_reads_as_a_knee_bend_change():
    from kei.apps.maya_feedback import describe
    lines = describe(_offsets([_row("kei:l_leg_pv_ctl", "translateX", 6, 5.0)]), None)
    assert len(lines) == 1
    assert lines[0].startswith("knee_l bend turns 7 deg outward at f6"), lines[0]
    assert "5.0 cm" in lines[0]
    right = describe(_offsets([_row("kei:r_leg_pv_ctl", "translateX", 6, 5.0)]), None)[0]
    assert "inward" in right


def test_a_constant_head_roll_reads_on_every_frame():
    from kei.apps.maya_feedback import describe
    rows = [_row("kei:c_head_fk_ctl", "rotateZ", f, -2.0, key=f == 0) for f in range(13)]
    assert describe(_offsets(rows), None) == ["head rolls 2 deg toward the character's left on every frame"]


def test_a_constant_offset_with_a_local_change_on_top_says_both():
    """The live check: the pole held 19.16 cm out on every frame, keyed up to 37.56 cm at f6 (keys f4, f6, f8)."""
    from kei.apps.maya_feedback import describe
    offs = {f: 19.16 for f in range(29)}
    offs.update({5: 28.36, 6: 37.56, 7: 28.36})
    rows = [_row("kei:l_leg_pv_ctl", "translateX", f, v, key=f in (4, 6, 8)) for f, v in offs.items()]
    assert describe(_offsets(rows, end=28), None) == [
        "knee_l bend turns 26 deg outward on every frame (the knee pole moves 19.2 cm), and 43 deg at f6 (37.6 cm) "
        "over f5 to f7"]
    one = {f: 2.0 for f in range(13)}
    one[6] = 5.0
    rows = [_row("kei:c_head_fk_ctl", "rotateZ", f, v) for f, v in one.items()]
    assert describe(_offsets(rows), None) == [
        "head rolls 2 deg toward the character's right on every frame, and 5 deg at f6"]


def test_root_height_foot_target_and_fk_knee_read_in_their_channels():
    from kei.apps.maya_feedback import describe
    rows = [_row("kei:c_body_ctl", "translateY", f, v) for f, v in ((4, -1.0), (5, -3.0), (6, -2.0))]
    rows += [_row("kei:l_foot_ik_ctl", "translateY", 10, 2.0), _row("kei:l_calf_fk_ctl", "rotateX", 6, 8.0)]
    lines = describe(_offsets(rows), None)
    assert "root height 3.0 cm lower f4 to f6, most at f5" in lines
    assert "foot_l target 2.0 cm higher at f10" in lines
    assert "knee_l bends 8 deg more at f6" in lines


def test_a_control_kei_does_not_map_is_listed_by_its_name_in_the_scene_s_unit():
    from kei.apps.maya_feedback import describe
    lines = describe(_offsets([_row("tail_03_ctl", "rotateY", 3, 12.5), _row("prop_ctl", "translateZ", 3, 4.0)],
                             unit_per_m=1.0), None)
    assert "tail_03_ctl.rotateY +12.5 deg at f3" in lines
    assert "prop_ctl.translateZ +400.0 cm at f3" in lines


def test_a_locked_or_limited_channel_says_so():
    from kei.apps.maya_feedback import describe
    locked = {**_row("kei:c_body_ctl", "translateY", 6, 1.0), "locked": True}
    held = {**_row("kei:c_head_fk_ctl", "rotateZ", 6, 40.0), "asked": 43.0, "reached": 30.0}
    lines = describe(_offsets([locked, held]), None)
    assert any("locked on the rig" in x and "root height" in x for x in lines)
    assert any("a limit holds it: asked 43.0, reached 30.0" in x for x in lines)


def test_two_layers_are_named_in_their_lines():
    from kei.apps.maya_feedback import describe
    off = _offsets([_row("kei:c_body_ctl", "translateY", 6, 1.0)])
    off["layers"]["feedback_head"] = [_row("kei:c_head_fk_ctl", "rotateZ", 6, 2.0)]
    lines = describe(off, None)
    assert lines == ["feedback: root height 1.0 cm higher at f6",
                     "feedback_head: head rolls 2 deg toward the character's right at f6"]


# ---------------- in Maya: the same read on real animation layers ----------------
@pytest.fixture(scope="module")
def maya_read():
    import mayakit
    return mayakit.run_script("check_feedback.py")


def _real(out, layer, attr, f):
    return next(e for e in out["read"]["layers"][layer] if e["attr"] == attr and e["frame"] == f)


@pytest.mark.maya
def test_in_maya_an_additive_layer_s_one_key_is_an_offset_on_every_frame(maya_read):
    rows = [e for e in maya_read["read"]["layers"]["feedback"] if e["attr"] == "translateX"]
    assert [e["frame"] for e in rows] == list(range(13))
    assert all(abs(e["offset"] - 5.0) < 1e-6 and abs(e["value"] - 15.0) < 1e-6 for e in rows)
    assert [e["frame"] for e in rows if e["key"]] == [6]
    assert maya_read["read"]["modes"] == {"feedback": "additive", "feedback_over": "override"}


@pytest.mark.maya
def test_in_maya_an_override_layer_s_offset_is_its_value_less_kei_s(maya_read):
    e = _real(maya_read, "feedback_over", "rotateZ", 6)
    assert abs(e["value"] - 9.0) < 1e-6 and abs(e["offset"] - (9.0 - 3.0)) < 1e-6
    e0 = _real(maya_read, "feedback_over", "rotateZ", 0)
    assert abs(e0["offset"] - 9.0) < 1e-6                 # one override key holds 9 deg on every frame


@pytest.mark.maya
def test_in_maya_the_read_leaves_the_layers_and_their_mute_states(maya_read):
    assert maya_read["after"] == maya_read["before"]
    assert maya_read["before"]["feedback_over"] is True and maya_read["before"]["feedback"] is False
    assert maya_read["read"]["other_rig"] == [] and maya_read["read"]["outside"] == []


@pytest.mark.maya
def test_in_maya_muting_the_feedback_layers_gives_kei_s_pass(maya_read):
    seen = maya_read["seen"]
    assert abs(seen["pole_f6_all_on"] - 15.0) < 1e-6
    assert abs(seen["pole_f6_muted"] - 10.0) < 1e-6 and abs(seen["head_f6_muted"] - 3.0) < 1e-6
    assert sorted(maya_read["muted"]["layers"]) == ["feedback", "feedback_over"]
    assert seen["time_after_read"] == 0                   # the current frame is put back


@pytest.mark.maya
def test_in_maya_an_additive_key_holds_the_difference_and_only_keyed_channels_are_read(maya_read):
    seen = maya_read["seen"]
    assert seen["layer_key"] == [5.0]           # setKeyframe's value is the value seen: the layer holds the offset
    # what Maya 2027 gives with getAttr's time flag under an additive layer: the value below it. The tool reads each
    # frame made current instead; this line says so if a later Maya changes it
    assert abs(seen["pole_f6_time_flag"] - 10.0) < 1e-6
    assert {e["attr"] for e in maya_read["read"]["layers"]["feedback"]} == {"translateX"}
