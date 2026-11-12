"""The sign-off checklist shows only the checks about the pass on screen, duplicates merged, in plain words first.
Every item stays in state.json; only what is shown changes. Nothing is ticked for the author."""
from kei.cli import main
from kei.state import ShotState, load_state, save_state

P = "author viewing at sign-off: "
KEIRA = [  # the shape of keira_walk_personality on 2026-11-03: 22 checks, most about passes long gone
    {"stage": "blocking", "from": "critic claude-critic",
     "check": P + "BLK42: play out_blocking/delivery/blocking_x10.mp4 at 24 fps, ten loops; confirm the seam"},
    {"stage": "blocking", "from": "critic codex",
     "check": P + "EXG2, EXG6: watch out_blocking/compare/turn_6_8_11_x10.mp4; confirm 8 degrees reads."},
    {"stage": "blocking", "from": "critic codex",
     "check": P + "WGT20: confirm the settle stays poised and balanced over each standing leg."},
    {"stage": "self_review", "from": "critic claude-critic",
     "check": P + "BLK42/LOC56/GAM6: watch out_p8/playback_x10.mp4 at 24 fps for rhythm and the seam"},
    {"stage": "self_review", "from": "critic codex",
     "check": P + "BLK42/TIM44: compare out_blocking/delivery/blocking_x10.mp4 and out_p8/delivery/playback_x10.mp4"},
    {"stage": "passes", "from": "critic claude-critic",
     "check": P + "BLK42/GAM6: watch the ten-loop playback at 24 fps for the seam, the steady straight head and the "
                  "deeper rear peel, in out_p35/playback_x10.mp4 and out_p35/delivery/playback_x10.mp4"},
    {"stage": "passes", "from": "critic claude-critic",
     "check": P + "POS12/HND40: f19-f24, near hand passing over the near thigh in the delivery camera (relaxed swing "
                  "or touching?), in out_p35/delivery/playback_x10.mp4"},
    {"stage": "passes", "from": "critic codex",
     "check": P + "HED6/HED12/local.5: watch out_p35/playback_x10.mp4; confirm the head reads straight and steady."},
    {"stage": "passes", "from": "critic codex",
     "check": P + "HND2/HND30: watch F19–F24 in out_p35/delivery/playback_x10.mp4; confirm the near hand reads as "
                  "swinging freely rather than resting on the thigh."},
]


def test_only_the_checks_about_the_pass_on_screen_are_shown():
    from kei.checklist import current_checks
    items = current_checks(KEIRA, "p35")
    shown = [c for i in items for c in i["checks"]]
    assert all("out_p8" not in c and "out_blocking" not in c for c in shown)
    assert KEIRA[2]["check"] in shown            # a blocking check that names no pass is still about the motion
    assert len(items) <= 5


def test_two_critics_asking_the_same_thing_become_one_item_naming_both():
    from kei.checklist import current_checks
    items = current_checks(KEIRA, "p35")
    hand = [i for i in items if "hand" in i["text"]]
    assert len(hand) == 1 and set(hand[0]["from"]) == {"critic claude-critic", "critic codex"}
    assert len(hand[0]["checks"]) == 2


def test_plain_words_first_ids_and_paths_set_apart():
    from kei.checklist import current_checks
    hand = next(i for i in current_checks(KEIRA, "p35") if "hand" in i["text"])
    assert not hand["text"].startswith("author viewing") and "POS12" not in hand["text"]
    assert "out_p35" not in hand["text"]
    assert {"POS12", "HND40", "HND2", "HND30"} <= set(hand["rules"])
    frames = [p["frame"] for p in hand["parts"] if "frame" in p]
    assert frames[0] == 19
    assert any(p.get("play") for p in hand["parts"])


def test_the_blocking_pass_keeps_its_own_checks():
    from kei.checklist import current_checks
    shown = [c for i in current_checks(KEIRA, "blocking") for c in i["checks"]]
    assert KEIRA[0]["check"] in shown and all("out_p35" not in c for c in shown)


def test_kei_status_shows_the_same_short_list_and_state_keeps_every_item(tmp_path, capsys):
    root = tmp_path / "keira"
    (root / "out_p35").mkdir(parents=True)
    (root / "out_p35" / "shot.json").write_text("{}", encoding="utf-8")
    save_state(root, ShotState(stage="deliver", status="needs_approval", sign_off=KEIRA))
    assert main(["status", str(root)]) == 0
    out = capsys.readouterr().out
    assert "out_p8" not in out and "out_blocking" not in out and "steady" in out
    assert sum(1 for line in out.splitlines() if line.startswith("- [ ]")) <= 5
    assert len(load_state(root).sign_off) == len(KEIRA)


def test_a_merged_item_has_each_button_once_and_a_frame_reference_keeps_its_case():
    from kei.checklist import current_checks
    hand = next(i for i in current_checks(KEIRA, "p35") if "hand" in i["text"])
    labels = [p.get("label") or p.get("play") for p in hand["parts"][1:]]
    assert len(labels) == len(set(labels))
    assert hand["text"].startswith("f19-f24")


def test_plain_worded_checks_merge_only_when_they_ask_the_same_thing_about_the_same_frames():
    from kei.checklist import current_checks
    items = current_checks([
        {"from": "critic a", "check": "Frame 3-6: the left foot plants flat"},
        {"from": "critic b", "check": "Frame 3-6: the left foot lands flat and stays planted"},
        {"from": "critic b", "check": "Frame 9-12: the head stays level"},
        {"from": "critic a", "check": "Frame 20-24: the left foot plants flat"}], "p1")
    assert [(i["range"], len(i["checks"])) for i in items] == [([3, 6], 2), ([9, 12], 1), ([20, 24], 1)]
