"""kei retarget: a pass made for a character's old proportions plays on its new ones (a re-imported model) with the
planted soles on the ground and the legs reaching, in a new pass folder; every other channel is copied unchanged."""
import json
import shutil
from pathlib import Path

import pytest

from kei.body_check import REACH, SOLE, measure
from kei.characters import load_character, on_character, parse_character, raw
from kei.cli import main
from kei.retarget import RetargetError, retarget_shot
from kei.rig import over_reach
from kei.sample import bake

WALK = Path(__file__).resolve().parent / "fixtures" / "walks" / "kei_p10_approved.json"
MOVED = ("root", "footL", "footR")
PLANTED = 0.006      # m: a sole point this low is on the ground (the toe tip stands toeH, 0.005, up)


def _kei_with(name: str, **proportions):
    data = raw("kei")
    return parse_character({**data, "proportions": {**data["proportions"], **proportions}}, name)


# kei_model's re-import on 2026-11-03, in kind: a taller ankle, shorter thigh and calf, a shorter heel, longer toes
TALLER_ANKLE = dict(ankleH=0.115, thigh=0.375, calf=0.395, heelBack=0.04, toeFwd=0.235)
# keira_model's, in kind: a shorter ankle and a longer calf
SHORTER_ANKLE = dict(ankleH=0.065, calf=0.437)


def _walk():
    return json.loads(WALK.read_text(encoding="utf-8"))


def _lowest(frames, s):
    return [min(fr["joints"][p.format(s=s)][1] for p in SOLE) for fr in frames]


@pytest.mark.parametrize("change", [TALLER_ANKLE, SHORTER_ANKLE], ids=["taller_ankle", "shorter_ankle"])
def test_a_planted_sole_stays_on_the_ground_and_the_leg_reaches_after_a_retarget(change):
    old = load_character("kei")
    new = _kei_with("kei", **change)
    shot = _walk()
    before = bake(on_character(shot, old), "spline")
    unfixed = bake(on_character(shot, new), "spline")
    out, report = retarget_shot(shot, old, new, source="kei.json (old)", when="2026-11-03")
    after = bake(on_character(out, new), "spline")
    for s in "lr":
        was, now, raw_ = _lowest(before, s), _lowest(after, s), _lowest(unfixed, s)
        planted = [i for i, y in enumerate(was) if y <= PLANTED]     # on the ground: not a swing frame near it
        assert planted, s
        assert max(abs(raw_[i] - was[i]) for i in planted) > 0.01, "the unretargeted walk is off the ground"
        assert max(abs(now[i] - was[i]) for i in planted) <= 0.002, (s, [round(now[i] - was[i], 4) for i in planted])
    assert max(over_reach(fr["pose"], new.proportions) for fr in after) <= REACH
    flags = measure(on_character(out, new), "spline", new.proportions, new.height)["flags"]
    assert not [f for f in flags if f["check"] in ("contacts", "hover") or "leg's reach" in f["what"]], flags
    assert report["ankle_shift_m"] == pytest.approx(change["ankleH"] - 0.09)


def test_every_channel_but_the_root_and_the_foot_heights_is_copied_byte_for_byte():
    shot = _walk()
    out, _ = retarget_shot(shot, load_character("kei"), _kei_with("kei", **TALLER_ANKLE),
                           source="kei.json (old)", when="2026-11-03")
    assert len(out["keys"]) == len(shot["keys"])
    for a, b in zip(shot["keys"], out["keys"]):
        assert list(a) == list(b)
        for c in a:
            if c in MOVED:
                assert a[c][0] == b[c][0] and a[c][2:] == b[c][2:], c       # only the height moves
            else:
                assert json.dumps(a[c]) == json.dumps(b[c]), c
    for k in shot:
        if k not in ("keys", "note", "character"):
            assert json.dumps(shot[k]) == json.dumps(out[k]), k
    assert "retargeted from kei.json (old)" in out["note"] and "2026-11-03" in out["note"]


def _shot_dir(tmp_path):
    shot = tmp_path / "walk"
    (shot / "out_p1").mkdir(parents=True)
    shutil.copy(WALK, shot / "out_p1" / "shot.json")
    old = tmp_path / "old_kei.json"
    data = raw("kei")
    old.write_text(json.dumps({**data, "proportions": {**data["proportions"], "ankleH": 0.07}}), encoding="utf-8")
    return shot, old


def test_kei_retarget_writes_a_new_pass_and_prints_what_changed(tmp_path, capsys):
    shot, old = _shot_dir(tmp_path)
    src = (shot / "out_p1" / "shot.json").read_bytes()
    assert main(["retarget", str(shot), "p1", "--from", str(old), "--to", "kei", "--out", "p2"]) == 0
    out = json.loads((shot / "out_p2" / "shot.json").read_text(encoding="utf-8"))
    assert out["character"] == "kei"
    assert (shot / "out_p1" / "shot.json").read_bytes() == src
    printed = capsys.readouterr().out
    assert "root" in printed and "foot" in printed and "+0.020" in printed, printed


def test_kei_retarget_refuses_to_overwrite_a_pass(tmp_path, capsys):
    shot, old = _shot_dir(tmp_path)
    (shot / "out_p2").mkdir()
    (shot / "out_p2" / "shot.json").write_text("{}", encoding="utf-8")
    assert main(["retarget", str(shot), "p1", "--from", str(old), "--to", "kei", "--out", "p2"]) != 0
    assert (shot / "out_p2" / "shot.json").read_text(encoding="utf-8") == "{}"
    assert "out_p2" in "".join(capsys.readouterr())
    with pytest.raises(RetargetError):
        from kei.retarget import retarget_pass
        retarget_pass(shot, "p1", str(old), "kei", "p1")


def test_a_diagonal_leg_still_out_of_reach_after_the_shift_lowers_the_root_only_as_far_as_needed():
    old = load_character("kei")
    new = _kei_with("kei", thigh=0.36, ankleH=0.12)        # the same standing leg, a shorter thigh
    stand = {"root": [0, 0.9, 0], "footL": [-0.12, 0.09, 0.0, 0, 0], "footR": [0.12, 0.09, 0.0, 0, 0]}
    # the left foot forward until the old leg is just straight: the shift keeps the height, not the diagonal
    lo, hi = 0.0, 1.0
    for _ in range(50):
        z = (lo + hi) / 2
        lo, hi = (z, hi) if over_reach({**stand, "footL": [-0.12, 0.09, z, 0, 0]}, old.proportions) <= 0 else (lo, z)
    stand["footL"] = [-0.12, 0.09, round(lo, 5), 0, 0]
    shot = {"rig": "v4", "fps": 24, "frames": 4, "keys": [{"f": 0, **stand}, {"f": 4, **stand}]}
    out, report = retarget_shot(shot, old, new, source="old", when="2026-11-03")
    assert set(report["lowered_for_reach"]) == {0, 4}, report
    for k in out["keys"]:
        assert over_reach(k, new.proportions) <= 1e-6
        assert 0 < report["lowered_for_reach"][k["f"]] < 0.05
    assert report["beyond_reach_frames"] == []


def _bends(frames, s):
    from kei.sample import _knee_flex
    import math
    return [math.degrees(_knee_flex(fr["joints"], s)) for fr in frames]


def _contact_keys(shot):
    """(frame, side) of the heel-strike keys: a planted foot target rolled onto the heel."""
    out = []
    for k in shot["keys"]:
        for s, S in (("l", "L"), ("r", "R")):
            if k.get(f"roll{S}", [0])[0] < 0 and k.get(f"foot{S}", [0, 1])[1] <= 0.0901:
                out.append((int(k["f"]), s))
    return out


@pytest.mark.parametrize("change", [TALLER_ANKLE, SHORTER_ANKLE], ids=["taller_ankle", "shorter_ankle"])
def test_a_retarget_keeps_the_knee_bend_at_contact_and_adds_no_knee_snap(change):
    from kei.body_check import knee_snaps
    old, new, shot = load_character("kei"), _kei_with("kei", **change), _walk()
    src = bake(on_character(shot, old), "spline")
    out, _ = retarget_shot(shot, old, new, source="old", when="2026-11-03")
    now = bake(on_character(out, new), "spline")
    contacts = _contact_keys(shot)
    assert contacts
    for f, s in contacts:
        was, got = _bends(src, s), _bends(now, s)
        for g in (f - 1, f, f + 1):
            assert abs(got[g] - was[g]) <= 2.0, (s, g, round(was[g], 1), round(got[g], 1))
    for s in "lr":
        assert knee_snaps(_bends(now, s), [fr["f"] for fr in now], True) == [], s
        assert min(g - w for g, w in zip(_bends(now, s), _bends(src, s))) > -2.0, s     # never straighter


def test_keep_standing_height_is_the_old_shift_of_the_root():
    old, new, shot = load_character("kei"), _kei_with("kei", **TALLER_ANKLE), _walk()
    out, report = retarget_shot(shot, old, new, source="old", when="2026-11-03", keep="standing-height")
    for a, b in zip(shot["keys"], out["keys"]):
        if "root" in a and b["f"] not in report["lowered_for_reach"]:
            assert b["root"][1] == pytest.approx(a["root"][1] + report["root_shift_m"], abs=1e-6)
