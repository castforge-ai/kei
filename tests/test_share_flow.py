"""The share step after Accept: ask, always or never, and the user's own gh and git through an injected runner."""
import json
from pathlib import Path

import pytest

from kei.lessons import add_lesson
from kei.state import ShotState, save_state
from reviewkit import PageClient, fake_round
from test_share_bundle import seat_writing, sliding, walk


class Runner:
    def __init__(self, fail_on=None):
        self.cmds = []
        self.fail_on = fail_on

    def __call__(self, cmd):
        self.cmds.append(list(cmd))
        return 1 if self.fail_on and cmd[:2] == self.fail_on else 0


def shot_with_a_note(tmp_path):
    lessons = tmp_path / "lessons.local.md"
    add_lesson(lessons, "the left foot hovers at the contact", "passes")
    root = tmp_path / "shots" / "walk"
    save_state(root, ShotState(stage="deliver", status="needs_approval", request="a walk", history=[
        {"stage": "passes", "attempt": 0, "result": "note", "lesson": "local.1", "misses": ["x"],
         "scope": "every shot"}]))
    fake_round(root, "r1")
    return root, lessons


ACCOUNT = {"login": "octo", "id": 4242}
NOREPLY = "4242+octo@users.noreply.github.com"


class GhReader:
    """Stands in for the user's own gh: answers gh api user with the account, or fails."""

    def __init__(self, account):
        self.account = account
        self.cmds = []

    def __call__(self, cmd):
        self.cmds.append(list(cmd))
        if cmd[:3] == ["gh", "repo", "view"] and self.account is not None:   # auto mode asks before it sends
            return json.dumps({"visibility": "PUBLIC"})
        if cmd[:3] != ["gh", "api", "user"] or self.account is None:
            raise OSError("gh: not logged in")
        return json.dumps(self.account)


@pytest.fixture
def make(tmp_path):
    from kei.review.server import ReviewServer
    from kei.review.signoff_routes import SignOffRoutes
    from kei.share import Sharer
    servers = []

    def build(mode, gh=True, fail_on=None, account=ACCOUNT):
        root, lessons = shot_with_a_note(tmp_path)
        runner = Runner(fail_on)
        sharer = Sharer(root, lessons, mode, seat=lambda: seat_writing(sliding(walk()), walk()),
                        runner=lambda bundle, work, identity: runner, gh_found=gh, size=16,
                        reader=GhReader(account))
        routes = SignOffRoutes(root, lessons, "r1", None, sharer=sharer)
        server = ReviewServer(routes.routes, routes.files)
        servers.append(server)
        return PageClient(server.start()), runner, tmp_path / "lessons" / "incoming"

    yield build
    for s in servers:
        s.stop()


def accept(c):
    return c.post("/api/accept", {"round": "r1", "ticked": []})


def test_ask_runs_nothing_until_the_share_post(make):
    c, runner, incoming = make("ask")
    status, data = accept(c)
    assert status == 200 and data["share"]["mode"] == "ask" and data["share"]["lessons"] == ["local.1"]
    assert runner.cmds == [] and not incoming.exists()
    status, panel = c.post("/api/share/prepare", {"lesson": "local.1"})
    assert status == 200, panel
    assert set(panel["files"]) == {"lesson.md", "cases/fails/shot.json", "cases/passes/shot.json", "numbers.json",
                                   "bundle.json"}
    assert "the left foot hovers" in panel["files"]["lesson.md"]
    rounds = panel["rounds"]
    assert rounds["fails"]["character"] == "kei" and rounds["passes"]["frames"] >= 1
    assert c.get(f"/file/{rounds['fails']['round']}/f0000")[0] == 200
    assert not any(p.suffix == ".png" for p in incoming.rglob("*"))     # the drawn cases never enter the bundle
    assert panel["commands"][-1][:4] == ["gh", "pr", "create", "--web"]
    assert runner.cmds == []
    status, sent = c.post("/api/share/send", {"lesson": "local.1"})
    assert status == 200 and runner.cmds == panel["commands"]
    assert "GitHub" in sent["message"]


def test_never_builds_nothing(make):
    c, runner, incoming = make("never")
    status, data = accept(c)
    assert status == 200 and data.get("share", {}).get("mode", "never") == "never"
    assert runner.cmds == [] and not incoming.exists()
    assert c.post("/api/share/prepare", {"lesson": "local.1"})[0] == 409


def test_always_builds_and_runs_the_plan(make):
    c, runner, incoming = make("always")
    status, data = accept(c)
    assert status == 200 and data["share"]["mode"] == "always"
    assert len(list(incoming.glob("*/bundle.json"))) == 1
    assert runner.cmds and runner.cmds[-1][:4] == ["gh", "pr", "create", "--web"]


def test_the_plan_is_the_users_own_gh_and_git_and_ends_on_githubs_form(tmp_path):
    from kei.share import build_bundle, share_plan
    _, lessons = shot_with_a_note(tmp_path)
    b = build_bundle("local.1", lessons, tmp_path / "lessons" / "incoming" / "2026-11-03-the-left-foot",
                     seat_writing(sliding(walk()), walk()))
    plan = share_plan(b, "castforge-ai/kei", ("octo", 4242))
    assert [c[0] for c in plan] == ["git", "gh", "git", "copy", "git", "git", "git", "gh"]
    assert plan[0][:2] == ["git", "clone"]
    assert plan[-1][:4] == ["gh", "pr", "create", "--web"]
    flat = " ".join(" ".join(c) for c in plan)
    for private in (str(tmp_path), str(Path.home()), Path.home().name):
        assert private not in flat
    assert "token" not in flat.lower() and "GH_TOKEN" not in flat


def test_a_failing_git_push_stops_the_plan_and_names_it(make):
    c, runner, _ = make("ask", fail_on=["git", "push"])
    accept(c)
    c.post("/api/share/prepare", {"lesson": "local.1"})
    status, data = c.post("/api/share/send", {"lesson": "local.1"})
    assert status == 409 and "git push" in data["error"]
    assert runner.cmds[-1][:2] == ["git", "push"]
    assert not any(cmd[:2] == ["gh", "pr"] for cmd in runner.cmds)


def test_with_no_gh_the_panel_shows_the_folder_and_the_manual_steps(make):
    c, runner, incoming = make("ask", gh=False)
    accept(c)
    status, panel = c.post("/api/share/prepare", {"lesson": "local.1"})
    assert status == 200 and panel["gh"] is False
    assert panel["folder"].replace("\\", "/").endswith(Path(panel["folder"]).name)
    assert any("pull request" in step for step in panel["manual"])
    assert c.post("/api/share/send", {"lesson": "local.1"})[0] == 409
    assert runner.cmds == []


def test_share_before_accept_is_refused(make):
    c, runner, incoming = make("ask")
    assert c.post("/api/share/prepare", {"lesson": "local.1"})[0] == 409
    assert not incoming.exists()


def test_a_lesson_not_from_this_shot_cannot_be_shared(make):
    c, _, incoming = make("ask")
    accept(c)
    assert c.post("/api/share/prepare", {"lesson": "local.7"})[0] == 409


def test_the_share_commit_carries_the_github_account_only_never_the_users_git_identity(make):
    """Author decision 2026-11-03: the GitHub account is the only identity on a shared lesson."""
    c, runner, _ = make("ask")
    accept(c)
    status, panel = c.post("/api/share/prepare", {"lesson": "local.1"})
    assert status == 200, panel
    commit = next(cmd for cmd in panel["commands"] if "commit" in cmd)
    assert commit[:5] == ["git", "-c", "user.name=octo", "-c", f"user.email={NOREPLY}"]
    assert "commit" in commit and commit[commit.index("commit") + 1:][:2] == ["--no-verify", "-m"]
    assert not any(cmd[:2] == ["git", "config"] for cmd in panel["commands"])
    c.post("/api/share/send", {"lesson": "local.1"})
    assert commit in runner.cmds


def test_with_no_github_account_from_gh_the_share_is_refused_in_plain_words(make):
    c, runner, incoming = make("ask", account=None)
    accept(c)
    status, data = c.post("/api/share/prepare", {"lesson": "local.1"})
    assert status == 409 and "gh auth login" in data["error"] and "GitHub account" in data["error"]
    assert runner.cmds == []
    assert c.post("/api/share/send", {"lesson": "local.1"})[0] == 409 and runner.cmds == []


@pytest.mark.parametrize("answer", [{"login": "octo"}, {"id": 4242}, {"login": "", "id": 4242},
                                    {"login": "octo", "id": "x"}, {"login": "a b", "id": 1}])
def test_an_account_gh_cannot_fully_tell_is_refused(answer):
    from kei.share import BundleError, github_identity
    with pytest.raises(BundleError, match="GitHub account"):
        github_identity(GhReader(answer))


def test_the_identity_is_read_with_gh_api_user():
    from kei.share import github_identity
    reader = GhReader(ACCOUNT)
    assert github_identity(reader) == ("octo", 4242)
    assert reader.cmds == [["gh", "api", "user"]]


ROOT = Path(__file__).resolve().parent.parent


def test_the_copy_says_kei_pushes_to_the_users_public_fork_before_githubs_button(make):
    from kei.share import PUBLIC_NOTE
    for words in ("fork", "push", "public", "GitHub's own button"):
        assert words in PUBLIC_NOTE
    c, runner, _ = make("ask")
    accept(c)
    panel = c.post("/api/share/prepare", {"lesson": "local.1"})[1]
    assert panel["public_note"] == PUBLIC_NOTE and runner.cmds == []      # ask: nothing runs before Send
    js = (ROOT / "kei" / "review" / "page" / "review.js").read_text(encoding="utf-8")
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())   # the README wraps its lines
    assert "Nothing is sent until" not in js and "Nothing is sent until" not in readme
    assert "b.public_note" in js
    assert "which is public" in readme and "pushes the lesson folder to a branch of your fork" in readme


def test_the_always_mode_hint_says_the_same():
    from kei.settings import setting
    help_text = setting("share.mode").help
    assert "always" in help_text and "public" in help_text and "fork" in help_text


def test_the_share_commands_run_with_the_login_identity_whatever_the_parent_environment(tmp_path, monkeypatch):
    import kei.share as share
    for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(k, "private person <me@example.com>" if "NAME" in k else "me@example.com")
    seen = []
    monkeypatch.setattr(share.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(share.subprocess, "run",
                        lambda cmd, cwd=None, env=None, **kw: (seen.append(env), type("R", (), {"returncode": 0})())[1])
    run = share.local_runner(tmp_path / "bundle", tmp_path, ("octo", 4242))
    assert run(["git", "status"]) == 0
    env = seen[0]
    assert env["GIT_AUTHOR_NAME"] == env["GIT_COMMITTER_NAME"] == "octo"
    assert env["GIT_AUTHOR_EMAIL"] == env["GIT_COMMITTER_EMAIL"] == NOREPLY
    assert "me@example.com" not in " ".join(str(v) for v in env.values())
    import os
    assert os.environ["GIT_AUTHOR_EMAIL"] == "me@example.com"        # the user's own environment is untouched


def test_the_share_commit_signs_nothing_and_runs_no_hook(make):
    c, runner, _ = make("ask")
    accept(c)
    commit = next(cmd for cmd in c.post("/api/share/prepare", {"lesson": "local.1"})[1]["commands"] if "commit" in cmd)
    i = commit.index("commit")
    opts = commit[:i]
    assert "commit.gpgsign=false" in opts and any(o.startswith("core.hooksPath=") for o in opts)
    assert "--no-verify" in commit[i:]


def test_the_clone_is_whole_so_the_push_to_an_outdated_fork_has_every_commit_it_needs(tmp_path):
    from kei.share import build_bundle, share_plan
    _, lessons = shot_with_a_note(tmp_path)
    b = build_bundle("local.1", lessons, tmp_path / "lessons" / "incoming" / "2026-11-03-x",
                     seat_writing(sliding(walk()), walk()))
    clone = share_plan(b, "castforge-ai/kei", ("octo", 4242))[0]
    assert clone[:2] == ["git", "clone"] and "--depth" not in clone and not any(a.startswith("--shallow") for a in clone)


def test_a_share_that_breaks_in_always_mode_never_looks_like_a_failed_approval(tmp_path):
    from kei.review.server import ReviewServer
    from kei.review.signoff_routes import SignOffRoutes
    from kei.share import Sharer
    from kei.state import load_state
    root, lessons = shot_with_a_note(tmp_path)

    def broken_seat():
        raise RuntimeError("the agent CLI crashed")
    sharer = Sharer(root, lessons, "always", seat=broken_seat, runner=lambda b, w, i: Runner(),
                    gh_found=True, size=16, reader=GhReader(ACCOUNT))
    routes = SignOffRoutes(root, lessons, "r1", None, sharer=sharer)
    server = ReviewServer(routes.routes, routes.files)
    try:
        status, data = accept(PageClient(server.start()))
        assert status == 200 and data["status"] == "done"
        [result] = data["share"]["results"]
        assert result["lesson"] == "local.1" and "the agent CLI crashed" in result["error"]
        assert load_state(root).status == "done"
    finally:
        server.stop()


def test_send_after_the_approval_was_withdrawn_is_refused(make, tmp_path):
    from kei.signoff import note_shot
    c, runner, _ = make("ask")
    accept(c)
    assert c.post("/api/share/prepare", {"lesson": "local.1"})[0] == 200
    note_shot(tmp_path / "shots" / "walk", "not done after all", "passes", tmp_path / "lessons.local.md")
    status, data = c.post("/api/share/send", {"lesson": "local.1"})
    assert status == 409 and "not signed off" in data["error"] and runner.cmds == []


def test_a_reshare_never_reuses_a_branch_name_and_send_runs_the_branch_it_showed(make, tmp_path):
    from kei.share import build_bundle, share_plan
    _, lessons = shot_with_a_note(tmp_path / "other")
    b = build_bundle("local.1", lessons, tmp_path / "x" / "2026-11-03-same-name", seat_writing(sliding(walk()), walk()))
    one = share_plan(b, "castforge-ai/kei", ("octo", 4242), stamp="20261103-101500")
    two = share_plan(b, "castforge-ai/kei", ("octo", 4242), stamp="20261104-090000")
    branch = lambda plan: next(c for c in plan if c[:3] == ["git", "switch", "-c"])[3]
    assert branch(one) != branch(two) and branch(one).startswith("lesson/2026-11-03-same-name-")
    c, runner, _ = make("ask")
    accept(c)
    shown = c.post("/api/share/prepare", {"lesson": "local.1"})[1]["commands"]
    c.post("/api/share/send", {"lesson": "local.1"})
    assert runner.cmds == shown
