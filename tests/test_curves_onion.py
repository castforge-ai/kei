"""kei curves draws a curve image per channel; kei render --onion draws the frames around each frame."""
import json

from kei.cli import main
from kei.render import read_png, render_shot
from test_pose_record import WALK, _shot
from test_render import SHOTS, write_shot

FULL = json.loads(WALK.read_text(encoding="utf-8"))["frames"]


def test_kei_curves_writes_one_image_per_channel(tmp_path, capsys):
    _shot(tmp_path, frames=FULL)
    assert main(["curves", str(tmp_path), "p1", "--channels", "spine,root"]) == 0
    for c in ("spine", "root"):
        img = read_png((tmp_path / "out_p1" / "curves" / f"{c}.png").read_bytes())
        assert img is not None and img.w == 900
    assert "written:" in capsys.readouterr().out


def test_kei_curves_refuses_an_unknown_channel(tmp_path, capsys):
    _shot(tmp_path, frames=FULL)
    assert main(["curves", str(tmp_path), "p1", "--channels", "wings"]) == 1
    assert "no channel" in capsys.readouterr().err


def test_an_onion_skin_adds_pale_figures_and_needs_the_stick_style(tmp_path):
    shot = {**SHOTS["sway"], "frames": 8, "loop": False,
            "keys": [{"f": 0, "yaw": 0.4}, {"f": 4, "yaw": -0.4}, {"f": 8, "yaw": 0.4}]}
    src = write_shot(tmp_path, shot)
    plain = render_shot(src, tmp_path / "a", "spline", size=80)["frames"][4].read_bytes()
    onion = render_shot(src, tmp_path / "b", "spline", size=80, onion=2)["frames"][4].read_bytes()
    a, b = read_png(plain), read_png(onion)
    from kei.render import PERFORMER
    pale = bytes(PERFORMER)
    count = lambda cv: sum(bytes(cv.px[i:i + 3]) == pale for i in range(0, len(cv.px), 3))   # noqa: E731
    assert count(a) == 0 and count(b) > 50      # the frames around f4 are drawn as pale figures


def test_a_long_pose_sheet_is_split_into_pages_of_ten_keys(tmp_path):
    from kei.pose_record import write_records
    shot = json.loads(WALK.read_text(encoding="utf-8"))
    keys = [{**shot["keys"][0], "f": f} for f in range(0, 24, 2)]          # twelve keys
    (tmp_path / "out_p1").mkdir()
    (tmp_path / "out_p1" / "shot.json").write_text(json.dumps({**shot, "frames": 24, "loop": False, "keys": keys}),
                                                   encoding="utf-8")
    write_records(tmp_path, "p1", "kei", sheet=True)
    pages = sorted(p.name for p in (tmp_path / "out_p1" / "poses").glob("pose_sheet*.png"))
    assert pages == ["pose_sheet.png", "pose_sheet_2.png"]


def test_render_json_pins_a_stages_settings_and_the_command_line_wins(tmp_path, monkeypatch):
    import kei.cli as cli
    seen = {}

    def fake(src, out, mode, **kw):
        seen.update(kw, out=out)
        raise SystemExit(0)
    monkeypatch.setattr(cli, "render_shot", fake)
    _shot(tmp_path, frames=FULL)
    (tmp_path / "render.json").write_text(json.dumps({"all": {"size": 200}, "passes": {"style": "stick", "onion": 1},
                                                      "p1": {"size": 150}}), encoding="utf-8")
    try:
        main(["render", str(tmp_path), "p1", "--character", "kei"])
    except SystemExit:
        pass
    assert seen["size"] == 150 and seen["onion"] == 1 and "proportions" in seen          # stick, from the stage
    seen.clear()
    try:
        main(["render", str(tmp_path), "p1", "--character", "kei", "--size", "90"])
    except SystemExit:
        pass
    assert seen["size"] == 90


def test_render_json_with_an_unknown_setting_is_refused(tmp_path, capsys):
    _shot(tmp_path, frames=FULL)
    (tmp_path / "render.json").write_text(json.dumps({"passes": {"colour": "red"}}), encoding="utf-8")
    assert main(["render", str(tmp_path), "p1", "--character", "kei"]) == 1
    assert "colour" in capsys.readouterr().err


def test_the_stick_render_draws_the_shots_objects(tmp_path):
    shot = {**SHOTS["sway"], "frames": 4, "loop": False, "keys": [{"f": 0, "yaw": 0.2}, {"f": 4, "yaw": -0.2}],
            "objects": [{"name": "crate", "shape": "box", "size": [0.4, 0.4, 0.4], "rest": [0.0, 0.2, 0.6],
                         "colour": "#ff0000"}]}
    cv = read_png(render_shot(write_shot(tmp_path, shot), tmp_path / "o", "spline", size=120)["frames"][0].read_bytes())
    red = sum(bytes(cv.px[i:i + 3]) == bytes((255, 0, 0)) for i in range(0, len(cv.px), 3))
    assert red > 40
