"""kei share check, export, import and list, and the opt-in Signed-off-by line."""
import json
import zipfile

import pytest

from kei.cli import main
from kei.config import load_config
from kei.share import BundleError, share_plan
from kei.share_tools import accepted, accepted_md, export_zip, import_zip
from test_share_bundle import bundle, lesson  # noqa: F401 - fixtures


def test_check_passes_a_good_bundle_and_fails_a_changed_one(tmp_path, bundle, capsys):  # noqa: F811
    assert main(["share", "check", str(bundle.parent)]) == 0
    assert "1 of 1 bundle(s) pass" in capsys.readouterr().out
    (bundle / "lesson.md").write_text("changed", encoding="utf-8")
    assert main(["share", "check", str(bundle)]) == 1
    assert "fail" in capsys.readouterr().out


def test_check_with_no_bundle(tmp_path, capsys):
    assert main(["share", "check", str(tmp_path)]) == 1
    assert main(["share", "check", str(tmp_path), "--allow-none"]) == 0


def test_a_maintainers_verdict_beside_a_bundle_still_checks(tmp_path, bundle, capsys):  # noqa: F811
    (bundle / "verdict.json").write_text(json.dumps({"verdict": "accept"}))
    assert main(["share", "check", str(bundle)]) == 0


def test_export_then_import_gives_the_same_checked_bundle(tmp_path, bundle):  # noqa: F811
    z = export_zip(bundle, tmp_path / "out" / "lesson.zip")
    with zipfile.ZipFile(z) as f:
        assert sorted(f.namelist()) == sorted(f"{bundle.name}/{r}" for r in
                                              ("lesson.md", "cases/fails/shot.json", "cases/passes/shot.json",
                                               "numbers.json", "bundle.json"))
    dest = import_zip(z, tmp_path / "repo" / "lessons" / "incoming")
    assert (dest / "lesson.md").read_bytes() == (bundle / "lesson.md").read_bytes()
    with pytest.raises(BundleError, match="already there"):
        import_zip(z, tmp_path / "repo" / "lessons" / "incoming")


def _zip(tmp_path, names):
    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as f:
        for n in names:
            f.writestr(n, "x")
    return z


@pytest.mark.parametrize("names,said", [
    (["l/../evil.txt"], "path Kei does not unpack"),
    (["/abs/lesson.md"], "path Kei does not unpack"),
    (["l/run.py"], "never holds"),
    (["a/lesson.md", "b/lesson.md"], "exactly one"),
    (["lesson.md"], "path Kei does not unpack"),
])
def test_a_bad_zip_is_refused_and_writes_nothing(tmp_path, names, said):
    into = tmp_path / "incoming"
    with pytest.raises(BundleError, match=said):
        import_zip(_zip(tmp_path, names), into)
    assert not into.exists()


def test_a_zip_whose_bundle_fails_its_check_leaves_nothing(tmp_path, bundle):  # noqa: F811
    z = tmp_path / "x.zip"
    with zipfile.ZipFile(z, "w") as f:
        for p in bundle.rglob("*"):
            if p.is_file():
                data = b"changed" if p.name == "lesson.md" else p.read_bytes()
                f.writestr(f"{bundle.name}/{p.relative_to(bundle).as_posix()}", data)
    with pytest.raises(BundleError, match="hash"):
        import_zip(z, tmp_path / "incoming")
    assert not (tmp_path / "incoming" / bundle.name).exists()


def test_the_accepted_list_reads_verdicts(tmp_path, capsys):
    for name, verdict, at in (("b", "accept", "2026-11-02T10:00"), ("a", "accept", "2026-11-01T10:00"),
                              ("c", "reject", "2026-11-03T10:00")):
        d = tmp_path / "lessons" / "incoming" / name
        d.mkdir(parents=True)
        (d / "lesson.md").write_text(f"Lesson {name} | about feet\n", encoding="utf-8")
        (d / "verdict.json").write_text(json.dumps({"verdict": verdict, "at": at, "rule": f"K{name}",
                                                    "book": "contacts.md"}))
    rows = accepted(tmp_path / "lessons")
    assert [r["folder"] for r in rows] == ["a", "b"]
    md = accepted_md(rows)
    assert "| 2026-11-01 | Ka | contacts.md | Lesson a / about feet (a) |" in md
    assert main(["share", "list", str(tmp_path), "--write"]) == 0
    assert (tmp_path / "lessons" / "ACCEPTED.md").read_text(encoding="utf-8") == md
    assert "None yet." in accepted_md([])


def test_sign_off_adds_the_line_for_the_github_account_only_when_asked(tmp_path, bundle):  # noqa: F811
    plain = share_plan(bundle, "castforge-ai/kei", ("octo", 4242))
    signed = share_plan(bundle, "castforge-ai/kei", ("octo", 4242), sign_off=True)
    commit = next(c for c in signed if "commit" in c)
    assert "Signed-off-by: octo <4242+octo@users.noreply.github.com>" in commit
    assert not any("Signed-off-by" in " ".join(c) for c in plain)


def test_share_sign_off_is_a_setting_off_by_default(tmp_path):
    c = tmp_path / "kei.toml"
    c.write_text('[animator]\ncmd = ["x"]\n')
    assert load_config(c).share_sign_off == "off"
    c.write_text('[animator]\ncmd = ["x"]\n[share]\nsign_off = "on"\n')
    assert load_config(c).share_sign_off == "on"
    c.write_text('[animator]\ncmd = ["x"]\n[share]\nsign_off = "yes"\n')
    with pytest.raises(Exception, match="sign_off"):
        load_config(c)
