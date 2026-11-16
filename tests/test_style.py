"""A character's style range from their own clips, and the register the author sets: soft flags inside become notes."""
import json

from kei.apps.unreal_style import clip_joints, measure_clip, style_shot
from kei.characters import load_character
from kei.style import MARGIN, SOFT, apply, range_from_clips, register
from test_unreal_readback import standing
from unrealkit import FakeEditor

CLIP = "/Game/Char/Ren/Anim/as_ren_idle"


def leaning(f, lean_cm):
    """The standing mannequin with its upper body pushed forward by lean_cm: the mass ahead of the toes."""
    b = standing(0, last=12)
    for n in b:
        if n.startswith(("spine", "neck", "head", "clavicle", "upperarm", "lowerarm", "hand")):
            b[n][1] += lean_cm
    return b


def test_the_range_keeps_the_furthest_value_of_each_soft_measure_and_the_clip_that_shows_it():
    clips = [{"name": "idle", "flags": [{"measure": "balance_outside_m", "value": 0.04, "frames": [0, 9]},
                                        {"measure": "neck_bend_deg", "value": 50.0, "frames": [0, 9]}],
              "move_cm": {"head": 10.0}},
             {"name": "catch", "flags": [{"measure": "balance_outside_m", "value": 0.1, "frames": [3, 7]},
                                         {"check": "contacts", "frames": [0, 1]}],     # hard: no measure, not kept
              "move_cm": {"head": 30.0, "hand_r": 50.0}}]
    r = range_from_clips(clips)
    assert r["range"]["balance_outside_m"] == {"max": 0.1, "clip": "catch", "frames": [3, 7]}
    assert r["range"]["neck_bend_deg"]["clip"] == "idle" and set(r["range"]) <= set(SOFT)
    assert r["move_cm"] == {"head": 30.0, "hand_r": 50.0} and r["clips"] == ["idle", "catch"]


def test_a_soft_flag_inside_the_range_is_a_note_a_hard_flag_never_is_and_pushed_makes_every_soft_flag_a_note():
    style = {"range": {"balance_outside_m": {"max": 0.05, "clip": "idle", "frames": [0, 9]}}}

    def flags():
        return [{"check": "balance", "frames": [0, 9], "measure": "balance_outside_m", "value": 0.05 * (1 + MARGIN)},
                {"check": "balance", "frames": [0, 9], "measure": "balance_outside_m", "value": 0.08},
                {"check": "posing", "frames": [0, 9], "measure": "neck_bend_deg", "value": 40.0},
                {"check": "contacts", "frames": [0, 9]}]
    fl = flags()
    s = apply(fl, style, None)
    assert fl[0]["inside_style"] and fl[0]["note"] and fl[0]["style_clip"] == "idle"
    assert not fl[1].get("note") and not fl[2].get("note")
    assert fl[3]["rule"] == "hard" and not fl[3].get("note")
    assert s == {"register": "realistic (no Register line in PLAN.md)", "style_range": True, "notes": 1, "faults": 3}
    fl = flags()
    s = apply(fl, None, "pushed")
    assert [bool(f.get("note")) for f in fl] == [True, True, True, False] and s["faults"] == 1


def test_the_register_is_read_from_plan_md_and_an_unknown_word_or_no_line_is_none(tmp_path):
    assert register(tmp_path) is None
    (tmp_path / "PLAN.md").write_text("Idea sentence: she looks.\n- **Register:** Pushed\n", encoding="utf-8")
    assert register(tmp_path) == "pushed"
    (tmp_path / "PLAN.md").write_text("Register: loud\n", encoding="utf-8")
    assert register(tmp_path) is None


def test_a_clip_that_leans_past_its_toes_sets_a_balance_range_a_smaller_lean_falls_inside():
    ch = load_character("keira")
    clip, _ = clip_joints({str(f): leaning(f, 70) for f in range(12)}, None)
    shot, _ = clip_joints({str(f): leaning(f, 55) for f in range(12)}, None)
    st = range_from_clips([measure_clip("lean", clip, 30, ch.proportions, ch.height)])
    assert st["range"]["balance_outside_m"]["max"] > 0.05
    from kei.body_check import measure
    fl = measure({"fps": 30, "loop": False, "keys": []}, "spline", ch.proportions, ch.height, shot)["flags"]
    apply(fl, st, None)
    bal = [f for f in fl if f["check"] == "balance"]
    assert bal and all(f["inside_style"] for f in bal)


def test_kei_unreal_style_reads_each_clip_in_chunks_and_writes_rig_style_json(tmp_path):
    shot = tmp_path / "breaker_01"
    shot.mkdir()
    ed = FakeEditor()
    ed.baked = lambda f: leaning(f, 70)
    with ed.server() as fake:
        r = style_shot(ed.client(), shot, [CLIP], load_character("keira"), 30)
        assert set(fake.scripts) == {"read_bake"} and len(fake.scripts) > 2        # read only, a few frames a call
    written = json.loads((shot / "rig" / "style.json").read_text(encoding="utf-8"))
    assert written["clips"] == [CLIP] and written["range"]["balance_outside_m"]["clip"] == CLIP
    assert written["per_clip"][0]["frames"] == 99 and r["path"].endswith("style.json")
    assert "head" in written["move_cm"]
