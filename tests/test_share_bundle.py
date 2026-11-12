"""A lesson bundle: the lesson, two cases rebuilt on the reference character, their numbers and the hashes. Nothing of
the user's own shot, character, paths or name."""
import json
import shutil
from pathlib import Path

import pytest

from kei.lessons import add_lesson
from kei.seats import FakeSeat, SeatResult
from kei.state import ShotState, save_state

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "stepped_walk" / "out_blocking" / "shot.json"
FILES = ["bundle.json", "cases/fails/shot.json", "cases/passes/shot.json", "lesson.md", "numbers.json"]


def walk():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def sliding(shot):
    """The same walk with the left foot lifted 3 cm on every key: kei check flags it as hovering."""
    s = json.loads(json.dumps(shot))
    for k in s["keys"]:
        k["footL"] = [k["footL"][0], k["footL"][1] + 0.03, k["footL"][2]]
    return s


def seat_writing(fails, passes, check="hover", extra=None):
    def act(prompt, workdir):
        act.prompt = prompt
        for name, data in (("fails", fails), ("passes", passes)):
            d = Path(workdir) / "cases" / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "shot.json").write_text(json.dumps(data), encoding="utf-8")
        (Path(workdir) / "cases" / "check.txt").write_text(check, encoding="utf-8")
        for rel, text in (extra or {}).items():
            (Path(workdir) / rel).write_text(text, encoding="utf-8")
        return SeatResult(0, "done")
    return FakeSeat("fake", act)


@pytest.fixture
def lesson(tmp_path):
    lessons = tmp_path / "lessons.local.md"
    add_lesson(lessons, "the planted foot slides forward on contact\nkeep the sole still", "passes")
    return lessons


def measured(shot):
    import tempfile
    from kei.body_check import check_pass
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "out_x").mkdir()
        (Path(d) / "out_x" / "shot.json").write_text(json.dumps(shot), encoding="utf-8")
        return [f["check"] for f in json.loads(check_pass(Path(d), "x", "kei", "spline").read_text())["flags"]]


def test_the_cases_measure_as_the_test_expects():
    assert "hover" in measured(sliding(walk()))
    assert "hover" not in measured(walk())


def test_a_bundle_has_the_five_files_and_their_hashes(tmp_path, lesson):
    from kei.share import build_bundle, check_bundle
    out = build_bundle("local.1", lesson, tmp_path / "bundle", seat_writing(sliding(walk()), walk()))
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert files == FILES
    meta = check_bundle(out)
    assert meta["stage"] == "passes" and meta["format"] == 1 and set(meta["files"]) == set(FILES) - {"bundle.json"}
    numbers = json.loads((out / "numbers.json").read_text(encoding="utf-8"))
    assert numbers["measured"] is True and numbers["check"] == "hover" and numbers["character"] == "kei"
    assert numbers["fails"]["count"] >= 1 and numbers["passes"]["count"] == 0
    lesson_md = (out / "lesson.md").read_text(encoding="utf-8")
    assert lesson_md.startswith("### local.1. ") and "stages: passes" in lesson_md and "keep the sole still" in lesson_md
    for case in ("fails", "passes"):
        data = json.loads((out / "cases" / case / "shot.json").read_text(encoding="utf-8"))
        assert data["character"] == "kei" and "props" not in data


def test_the_seat_gets_the_lesson_and_the_case_contract(tmp_path, lesson):
    from kei.share import build_bundle
    seat = seat_writing(sliding(walk()), walk())
    build_bundle("local.1", lesson, tmp_path / "b", seat)
    p = seat.action.prompt
    assert "the planted foot slides forward" in p and "cases/fails/shot.json" in p and "kei" in p


def test_a_failing_case_that_passes_is_refused(tmp_path, lesson):
    from kei.share import BundleError, build_bundle
    with pytest.raises(BundleError, match="fails"):
        build_bundle("local.1", lesson, tmp_path / "b", seat_writing(walk(), walk()))
    assert not (tmp_path / "b").exists()


def test_a_passing_case_that_fails_is_refused(tmp_path, lesson):
    from kei.share import BundleError, build_bundle
    with pytest.raises(BundleError, match="passes"):
        build_bundle("local.1", lesson, tmp_path / "b", seat_writing(sliding(walk()), sliding(walk())))


def test_a_taste_lesson_with_no_check_is_kept_unmeasured(tmp_path, lesson):
    from kei.share import build_bundle
    out = build_bundle("local.1", lesson, tmp_path / "b", seat_writing(walk(), walk(), check="none"))
    assert json.loads((out / "numbers.json").read_text(encoding="utf-8"))["measured"] is False


def test_an_unknown_lesson_is_refused(tmp_path, lesson):
    from kei.share import BundleError, build_bundle
    with pytest.raises(BundleError, match="local.9"):
        build_bundle("local.9", lesson, tmp_path / "b", seat_writing(walk(), walk()))


def test_no_private_data_in_any_bundle_file(tmp_path, lesson):
    """A shot made with an imported character: neither its name, nor the shot's path, nor the user's name leaks."""
    from kei.share import build_bundle
    shot_dir = tmp_path / "my_secret_shot"
    fails = {**sliding(walk()), "character": "zorblax", "note": f"made in {shot_dir}",
             "props": {"proportions": {"thigh": 0.5}}}
    passes = {**walk(), "character": "zorblax"}
    out = build_bundle("local.1", lesson, tmp_path / "b", seat_writing(fails, passes),
                       private=[str(shot_dir), "zorblax"])
    text = "\n".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())
    for secret in ("zorblax", "my_secret_shot", str(Path.home()), Path.home().name, "proportions"):
        assert secret not in text, secret


def test_a_private_word_in_the_lesson_text_refuses_the_bundle(tmp_path):
    from kei.share import BundleError, build_bundle
    lessons = tmp_path / "l.md"
    add_lesson(lessons, f"zorblax slides at {tmp_path}", "passes")
    with pytest.raises(BundleError, match="private"):
        build_bundle("local.1", lessons, tmp_path / "b", seat_writing(sliding(walk()), walk()),
                     private=["zorblax"])


@pytest.fixture
def bundle(tmp_path, lesson):
    from kei.share import build_bundle
    return build_bundle("local.1", lesson, tmp_path / "bundle", seat_writing(sliding(walk()), walk()))


def test_a_sixth_file_is_refused(bundle):
    from kei.share import BundleError, check_bundle
    (bundle / "cases" / "notes.txt").write_text("hi", encoding="utf-8")
    with pytest.raises(BundleError, match="notes.txt"):
        check_bundle(bundle)


def test_a_changed_file_is_refused(bundle):
    from kei.share import BundleError, check_bundle
    p = bundle / "lesson.md"
    p.write_text(p.read_text(encoding="utf-8") + "\nmore\n", encoding="utf-8")
    with pytest.raises(BundleError, match="lesson.md"):
        check_bundle(bundle)


def test_a_huge_file_is_refused(bundle):
    from kei.share import BundleError, check_bundle
    import hashlib
    p = bundle / "lesson.md"
    p.write_text(p.read_text(encoding="utf-8") + "x" * (2 * 1024 * 1024), encoding="utf-8")
    meta = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    meta["files"]["lesson.md"] = hashlib.sha256(p.read_bytes()).hexdigest()
    (bundle / "bundle.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(BundleError, match="2 MB"):
        check_bundle(bundle)


def test_a_missing_file_and_an_unknown_format_are_refused(bundle):
    from kei.share import BundleError, check_bundle
    meta = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    (bundle / "bundle.json").write_text(json.dumps({**meta, "format": 99}), encoding="utf-8")
    with pytest.raises(BundleError, match="format"):
        check_bundle(bundle)
    (bundle / "bundle.json").write_text(json.dumps(meta), encoding="utf-8")
    (bundle / "numbers.json").unlink()
    with pytest.raises(BundleError, match="numbers.json"):
        check_bundle(bundle)


def test_a_case_kei_cannot_play_is_refused(bundle):
    from kei.share import BundleError, check_bundle
    import hashlib
    p = bundle / "cases" / "passes" / "shot.json"
    p.write_text(json.dumps({"rig": "v1"}), encoding="utf-8")
    meta = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    meta["files"]["cases/passes/shot.json"] = hashlib.sha256(p.read_bytes()).hexdigest()
    (bundle / "bundle.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(BundleError, match="passes"):
        check_bundle(bundle)


def test_new_lessons_are_the_lessons_of_this_shots_notes(tmp_path):
    from kei.share import new_lessons
    root = tmp_path / "s"
    save_state(root, ShotState(history=[
        {"stage": "passes", "result": "note", "lesson": "local.2", "misses": ["a"]},
        {"stage": "passes", "result": "pass", "misses": []},
        {"stage": "deliver", "result": "rejected", "lesson": "local.3", "misses": ["b"]},
        {"stage": "passes", "result": "note", "lesson": "local.2", "misses": ["a"]}]))
    assert new_lessons(root) == ["local.2", "local.3"]


def test_the_shot_folder_name_is_private_too(tmp_path):
    from kei.config import Config, SeatSpec
    from kei.review.app import _sharer
    shot_dir = tmp_path / "keira_walk_personality"
    shot_dir.mkdir()
    cfg = Config(animator=SeatSpec("a", ["x"]), lessons=tmp_path / "lessons.local.md")
    assert "keira_walk_personality" in _sharer(shot_dir, cfg).private


def test_a_lesson_naming_the_shot_folder_is_refused_but_a_longer_word_is_not(tmp_path):
    from kei.share import BundleError, build_bundle
    lessons = tmp_path / "l.md"
    add_lesson(lessons, "in keira_walk_personality the foot hovers", "passes")
    with pytest.raises(BundleError, match="private"):
        build_bundle("local.1", lessons, tmp_path / "b1", seat_writing(sliding(walk()), walk()),
                     private=["keira_walk_personality"])
    lessons2 = tmp_path / "l2.md"
    add_lesson(lessons2, "while walking the foot hovers", "passes")
    build_bundle("local.1", lessons2, tmp_path / "b2", seat_writing(sliding(walk()), walk()), private=["walk"])
