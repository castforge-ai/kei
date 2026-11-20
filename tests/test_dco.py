"""tools/check_dco.py: every commit of a pull request carries a Signed-off-by line; merge commits are skipped."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("check_dco", ROOT / "tools" / "check_dco.py")
dco = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dco)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@example.com",
                           "-c", "core.autocrlf=false", "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a").write_text("1")
    git(tmp_path, "add", "a")
    git(tmp_path, "commit", "-q", "--no-verify", "-m", "base")
    return tmp_path


def commit(repo, name, message):
    (repo / name).write_text(name)
    git(repo, "add", name)
    git(repo, "commit", "-q", "--no-verify", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def test_signed_commits_pass_and_an_unsigned_one_is_named(repo, capsys):
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "b", "add b\n\nSigned-off-by: Ada Lovelace <ada@example.com>")
    assert dco.main([base, "HEAD", "--repo", str(repo)]) == 0
    commit(repo, "c", "add c without a sign-off")
    capsys.readouterr()
    assert dco.main([base, "HEAD", "--repo", str(repo)]) == 1
    out = capsys.readouterr().out
    assert "add c without a sign-off" in out and "add b" not in out and "git commit -s" in out


def test_a_sign_off_needs_a_name_and_an_address(repo):
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "d", "add d\n\nSigned-off-by: someone")
    assert len(dco.missing(base, "HEAD", str(repo))) == 1


def test_merge_commits_are_skipped(repo):
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "side")
    commit(repo, "e", "add e\n\nSigned-off-by: Ada Lovelace <ada@example.com>")
    git(repo, "checkout", "-q", "main")
    commit(repo, "f", "add f\n\nSigned-off-by: Ada Lovelace <ada@example.com>")
    git(repo, "merge", "-q", "--no-ff", "--no-edit", "side")         # git's own merge message, unsigned
    assert dco.missing(base, "HEAD", str(repo)) == []


def test_git_that_cannot_list_says_so(repo, capsys):
    assert dco.main(["nope", "HEAD", "--repo", str(repo)]) == 2
    assert "git could not list" in capsys.readouterr().out


def test_the_workflow_runs_the_script_on_every_pull_request():
    text = (ROOT / ".github" / "workflows" / "dco.yml").read_text(encoding="utf-8")
    assert "pull_request:" in text and "paths" not in text and "tools/check_dco.py" in text
    assert "fetch-depth: 0" in text
