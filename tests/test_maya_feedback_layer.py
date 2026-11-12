"""Plan 6d: Kei makes the feedback layer itself. When it keys pass N it adds an empty additive layer feedback_<pass>
directly above its own layer kei_<pass>, with the keyed controls on it, selected and preferred so the animator's next
key lands there. An existing feedback layer is never changed. The read takes the current pass's layer and the
animator's own feedback layers, and names a layer of an older pass without reading it. Maya is stood in for by
tests/fake_maya.py here; tests/maya/check_feedback_layer.py proves the same calls in real Maya."""
import json
from pathlib import Path

import pytest

import fake_maya
from kei.apps.maya_side import kei_tools

PV = "kei:l_leg_pv_ctl.translateX"
HEAD = "kei:c_head_fk_ctl.rotateZ"


def _scene(monkeypatch):
    cmds = fake_maya.FakeCmds({PV: lambda f: 10.0, HEAD: lambda f: 0.0})
    cmds.add_layer("kei_p23", {PV: {0: 1.0}}, override=True)
    cmds.add_layer("kei_p24", {PV: {0: 2.0}}, override=True)
    fake_maya.install(monkeypatch, cmds)
    return cmds


def _make(cmds, name="feedback_p24", above="kei_p24", controls=("kei:l_leg_pv_ctl", "kei:c_head_fk_ctl")):
    return kei_tools.make_feedback_layer(cmds, name, above, list(controls))


def test_kei_makes_an_empty_additive_layer_directly_above_its_pass_with_the_controls_on_it(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("fixes", {})                                   # the animator's own layer, above Kei's pass
    out = _make(cmds)
    assert out == {"layer": "feedback_p24", "created": True, "controls": 2}
    assert cmds.animLayer("BaseAnimation", q=True, children=True) == ["kei_p23", "kei_p24", "feedback_p24", "fixes"]
    assert cmds.animLayer("feedback_p24", q=True, override=True) is False
    assert set(cmds.animLayer("feedback_p24", q=True, attribute=True)) == {PV, HEAD}
    assert cmds.layers["feedback_p24"]["keys"] == {}                       # empty: no key, no change to the pass


def test_the_new_layer_is_selected_and_preferred_so_the_animator_s_next_key_lands_on_it(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.layers["kei_p24"]["selected"] = True
    _make(cmds)
    sel = {n: cmds.animLayer(n, q=True, selected=True) for n in cmds.layers}
    assert [n for n, s in sel.items() if s] == ["feedback_p24"]
    assert cmds.animLayer("feedback_p24", q=True, preferred=True) is True
    cmds.currentTime(6)
    cmds.setKeyframe("kei:l_leg_pv_ctl", attribute="translateX", time=6, value=7.0)   # the animator, no layer named
    assert cmds.layers["feedback_p24"]["keys"] == {PV: {6.0: 5.0}}         # the difference from Kei's 2.0
    assert cmds.layers["kei_p24"]["keys"][PV] == {0: 2.0}


def test_an_existing_feedback_layer_is_left_exactly_as_it_is(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback_p24", {PV: {6: 5.0}}, mute=True, weight=0.5)
    before = json.dumps(cmds.layers, sort_keys=True, default=str)
    out = _make(cmds)
    assert out == {"layer": "feedback_p24", "created": False}
    assert json.dumps(cmds.layers, sort_keys=True, default=str) == before
    assert not [e for e in cmds.edits if e[0] == "feedback_p24"]


def _read(pass_name="p24"):
    return kei_tools.call("read_feedback_layers", {"rig": "kei", "start": 0, "end": 12, "pass_name": pass_name})


def test_the_read_takes_the_pass_s_layer_and_the_animator_s_own_and_names_an_older_pass_s(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback_p23", {PV: {6: 9.0}})
    cmds.add_layer("feedback_p24", {PV: {6: 5.0}})
    cmds.add_layer("feedback", {HEAD: {6: 1.0}})
    cmds.add_layer("feedback_knee", {HEAD: {6: 2.0}})
    cmds.add_layer("feedback_blocking", {HEAD: {6: 3.0}})
    out = _read()
    assert set(out["layers"]) == {"feedback_p24", "feedback", "feedback_knee"}
    assert out["other_pass"] == [{"layer": "feedback_p23", "pass": "p23"},
                                 {"layer": "feedback_blocking", "pass": "blocking"}]
    assert cmds.layers["feedback_p23"]["mute"] is False                    # named, never touched


def test_an_older_pass_s_layer_is_not_muted_for_before_and_after(monkeypatch):
    cmds = _scene(monkeypatch)
    cmds.add_layer("feedback_p23", {PV: {6: 9.0}})
    cmds.add_layer("feedback_p24", {PV: {6: 5.0}})
    out = kei_tools.call("set_feedback_mute", {"mute": True, "pass_name": "p24"})
    assert out["layers"] == ["feedback_p24"]
    assert cmds.layers["feedback_p23"]["mute"] is False and cmds.layers["feedback_p24"]["mute"] is True


def test_set_keys_takes_the_feedback_layer_to_make_in_the_same_call():
    spec = kei_tools.TOOLS["set_keys"]["inputs"]
    assert spec["feedback"] == ("str", None)


# ---------------- Kei's side: kei maya key and kei maya feedback ----------------
@pytest.fixture
def shot(tmp_path, monkeypatch):
    from kei.apps import maya_shot
    root = tmp_path / "walk"
    (root / "out_p24").mkdir(parents=True)
    (root / "out_p24" / "shot.json").write_text(json.dumps({"rig": "maya", "frames": 12, "keys": [
        {"f": 0, "kei:l_leg_pv_ctl.translateX": 10.0}, {"f": 12, "kei:l_leg_pv_ctl.translateX": 10.0,
                                                      "kei:c_head_fk_ctl.rotateZ": 1.0}]}))
    (root / "maya").mkdir()
    (root / "maya" / "scene.ma").write_text("//Maya ASCII\n")
    sent = []

    def run_job(py, job, **kw):
        sent.append(job)
        results = []
        for c in job["calls"]:
            if c["tool"] == "set_keys":
                fb = c["inputs"].get("feedback")
                results.append({"keys": 2, "channels": 2, "clipped": [], "muted": [],
                                "feedback": {"layer": fb, "created": True, "controls": 2} if fb else None})
            else:
                results.append({})
        return {"ok": True, "maya_version": "2027", "results": results}
    monkeypatch.setattr(maya_shot, "run_job", run_job)
    monkeypatch.setattr(maya_shot, "find_mayapy", lambda *a: (Path("mayapy"), "2027"))
    return root, sent


def test_kei_maya_key_makes_feedback_pass_with_the_keyed_controls_and_says_so(shot, capsys):
    from kei.cli import main
    root, sent = shot
    assert main(["maya", "key", str(root), "p24"]) == 0
    inputs = sent[0]["calls"][1]["inputs"]
    assert inputs["feedback"] == "feedback_p24"
    assert inputs["feedback_controls"] == ["kei:c_head_fk_ctl", "kei:l_leg_pv_ctl"]
    out = capsys.readouterr().out
    assert f"pose corrections on layer feedback_p24, then run: kei maya feedback {root}" in out
    rep = json.loads((root / "out_p24" / "maya_report.json").read_text())
    assert rep["feedback"] == {"layer": "feedback_p24", "created": True, "controls": 2}


def test_in_the_open_maya_the_feedback_layer_is_made_in_the_same_call_as_the_keys(shot, monkeypatch, capsys):
    from kei.apps import maya_session
    from kei.cli import main
    root, _ = shot
    (root / "maya" / "target.json").write_text(json.dumps({"kind": "open", "pid": 7, "start_time": 1.0}))
    calls = []

    class S:
        pid, port, token = 7, 1, "t"

    def call_host(port, token, tool, inputs=None, **kw):
        calls.append((tool, inputs))
        if tool == "set_keys":
            return {"keys": 2, "clipped": [], "muted": [], "feedback": {"layer": "feedback_p24", "created": False}}
        return {}
    monkeypatch.setattr(maya_session, "locate", lambda target: S)
    monkeypatch.setattr(maya_session, "call_host", call_host)
    assert main(["maya", "key", str(root), "p24"]) == 0
    assert [c[0] for c in calls][:2] == ["set_time", "set_keys"]      # the time slider first, then the keys
    tool, inputs = calls[1]
    assert tool == "set_keys" and inputs["layer"] == "kei_p24" and inputs["feedback"] == "feedback_p24"
    out = capsys.readouterr().out
    assert "feedback_p24 is already there and was left as it is" in out
    assert f"pose corrections on layer feedback_p24, then run: kei maya feedback {root}" in out


# ---------------- in Maya: the same calls on real animation layers ----------------
@pytest.fixture(scope="module")
def maya_layers():
    import mayakit
    return mayakit.run_script("check_feedback_layer.py")


@pytest.mark.maya
def test_in_maya_the_layer_is_made_additive_directly_above_kei_s_pass_with_the_controls(maya_layers):
    m = maya_layers
    assert m["p24"]["feedback"] == {"layer": "feedback_p24", "created": True, "controls": 2}
    assert m["order"] == ["kei_p23", "feedback_p23", "kei_p24", "feedback_p24", "fixes"]
    assert m["override"] is False and m["empty_keys"] is None
    assert {"kei:pole_ctl.translateX", "kei:head_ctl.rotateZ"} <= set(m["attributes"])


@pytest.mark.maya
def test_in_maya_it_is_the_one_selected_preferred_layer_and_the_animator_s_key_lands_on_it(maya_layers):
    m = maya_layers
    assert [n for n, f in m["flags"].items() if f["selected"] or f["preferred"]] == ["feedback_p24"]
    assert m["p23_key"] == [6.0, 3.0]                       # 4 cm seen, over Kei's 1: the layer holds 3
    assert m["p24_key"] == [6.0, 5.0] and m["kei_p24_keys"] == [0.0, 2.0, 12.0, 2.0]
    assert m["flags"]["feedback_p23"]["mute"] is False      # Kei mutes its own older pass, never a feedback layer


@pytest.mark.maya
def test_in_maya_keying_the_pass_again_leaves_the_feedback_layer_as_it_is(maya_layers):
    m = maya_layers
    assert m["again"]["feedback"] == {"layer": "feedback_p24", "created": False}
    assert m["again_key"] == [6.0, 5.0] and m["again_flags"]["feedback_p24"]["mute"] is True


@pytest.mark.maya
def test_in_maya_the_read_for_p24_names_feedback_p23_and_reads_only_feedback_p24(maya_layers):
    r = maya_layers["read"]
    assert r["other_pass"] == [{"layer": "feedback_p23", "pass": "p23"}]
    assert set(r["layers"]) == {"feedback_p24"}
    keyed = [(e["control"], e["attr"], e["frame"], round(e["offset"], 6)) for e in r["layers"]["feedback_p24"]
             if e["key"]]
    assert keyed == [("kei:pole_ctl", "translateX", 6, 5.0)]


def test_the_feedback_layer_and_the_controls_layer_hold_every_control_of_the_rig(shot):
    """Not only the controls this pass keys: the animator may correct any control on the corrections layer."""
    from kei.cli import main
    root, sent = shot
    (root / "rig").mkdir()
    (root / "rig" / "maya_rig.json").write_text(json.dumps({"controls": [
        {"name": "kei:c_body_ctl"}, {"name": "kei:c_head_fk_ctl"}, {"name": "kei:l_leg_pv_ctl"}]}))
    assert main(["maya", "key", str(root), "p24"]) == 0
    inputs = sent[0]["calls"][1]["inputs"]
    every = ["kei:c_body_ctl", "kei:c_head_fk_ctl", "kei:l_leg_pv_ctl"]
    assert inputs["feedback_controls"] == every and inputs["controls_layer"] == every


@pytest.fixture(scope="module")
def maya_controls_layer():
    import mayakit
    return mayakit.run_script("check_controls_layer.py")


@pytest.mark.maya
def test_in_maya_a_rig_with_no_controls_layer_gets_kei_controls_with_every_control(maya_controls_layer):
    m = maya_controls_layer
    assert m["made"] == {"layer": "kei_controls", "created": True, "added": 2, "kept_in_your_layers": []}
    assert m["made_members"] == ["kei:body_ctl", "kei:hand_ctl"]           # the mesh is not swept in
    assert m["again"] == {"layer": "kei_controls", "created": False, "added": 0}
    assert m["undo"] == "kei_set_keys"


@pytest.mark.maya
def test_in_maya_the_animator_s_own_layers_are_used_and_never_emptied(maya_controls_layer):
    m = maya_controls_layer
    assert m["theirs"] == {"layer": "anim_ctrls", "created": False, "added": 0} and m["no_kei_layer"]
    assert m["split"]["kept_in_your_layers"] == ["hands"] and m["split"]["added"] == 1
    assert m["split_members"] == {"kei_controls": ["kei:body_ctl"], "hands": ["kei:hand_ctl"]}
