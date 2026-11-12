"""Automatic sharing for a studio set-up (design Amendment 2): share.mode = "auto" and share.repo."""
import json
from pathlib import Path

import pytest

from kei.config import ConfigError, load_config

BASE = '[animator]\ncmd = ["x"]\n'


def config(tmp_path, body):
    p = tmp_path / "kei.toml"
    p.write_text(BASE + body, encoding="utf-8")
    return load_config(p)


def test_auto_is_a_share_mode_and_the_repo_defaults_to_the_public_kei_project(tmp_path):
    assert config(tmp_path, '[share]\nmode = "auto"\n').share == "auto"
    c = config(tmp_path, "")
    assert c.share_repo == "castforge-ai/kei"


def test_share_repo_takes_any_owner_and_name(tmp_path):
    c = config(tmp_path, '[share]\nmode = "auto"\nrepo = "my-studio/kei-lessons"\n')
    assert c.share_repo == "my-studio/kei-lessons"


@pytest.mark.parametrize("repo", ["kei", "a/b/c", "https://github.com/a/b", "a b/c", "/kei", "owner/", 3, "-x/y",
                                  "a/.."])
def test_a_repo_not_written_owner_slash_name_is_refused(tmp_path, repo):
    with pytest.raises(ConfigError, match="share.repo"):
        config(tmp_path, f"[share]\nrepo = {json.dumps(repo)}\n")


def test_the_settings_table_lists_share_repo_with_its_meaning_and_auto_with_its_help():
    from kei.settings import setting
    row = setting("share.repo")
    assert row.default == "castforge-ai/kei" and row.kind == "text" and "lessons" in row.meaning
    assert "owner/name" in row.help
    mode = setting("share.mode")
    assert "auto" in mode.choices and "auto:" in mode.help and "share.repo" in mode.help


# -- auto is switched on only with kei settings or in kei.toml, never from the page ----------------------------------

@pytest.fixture
def tab(tmp_path):
    import shutil
    from kei.review.server import ReviewServer
    from kei.review.settings_routes import SettingsRoutes
    from reviewkit import PageClient
    toml = tmp_path / "kei.toml"
    shutil.copy(Path(__file__).resolve().parent.parent / "kei.example.toml", toml)
    server = ReviewServer(SettingsRoutes(toml, which=lambda n: f"/usr/bin/{n}").routes, lambda: {})
    yield toml, PageClient(server.start())
    server.stop()


def sha(p):
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_the_page_never_switches_auto_on(tab):
    toml, c = tab
    before = toml.read_bytes()
    status, data = c.post("/api/settings", {"changes": {"share.mode": "auto"}, "sha256": sha(toml)})
    assert status == 409 and "kei settings set share.mode auto" in data["error"] and data["key"] == "share.mode"
    assert toml.read_bytes() == before


def test_the_page_never_repoints_auto_but_can_switch_it_off(tab):
    toml, c = tab
    toml.write_text(toml.read_text(encoding="utf-8").replace('mode = "ask"', 'mode = "auto"'), encoding="utf-8")
    before = toml.read_bytes()
    status, data = c.post("/api/settings", {"changes": {"share.repo": "evil/elsewhere"}, "sha256": sha(toml)})
    assert status == 409 and "kei settings" in data["error"] and toml.read_bytes() == before
    status, data = c.post("/api/settings", {"changes": {"share.mode": "ask"}, "sha256": sha(toml)})
    assert status == 200 and data["saved"] is True and load_config(toml).share == "ask"
    status, data = c.post("/api/settings", {"changes": {"share.repo": "my-studio/lessons"}, "sha256": sha(toml)})
    assert status == 200 and load_config(toml).share_repo == "my-studio/lessons"     # not auto: no lesson goes there


# -- kei settings set share.mode auto says once where lessons go and whether that repository is public -------------

@pytest.fixture
def here(tmp_path, monkeypatch):
    import shutil
    shutil.copy(Path(__file__).resolve().parent.parent / "kei.example.toml", tmp_path / "kei.toml")
    monkeypatch.chdir(tmp_path)
    import kei.settings
    monkeypatch.setattr(kei.settings.shutil, "which", lambda name: f"/usr/bin/{name}")
    return tmp_path


class Visibility:
    """Stands in for gh repo view --json visibility."""

    def __init__(self, answer):
        self.answer = answer
        self.cmds = []

    def __call__(self, cmd):
        self.cmds.append(list(cmd))
        if isinstance(self.answer, Exception):
            raise self.answer
        return json.dumps({"visibility": self.answer})


def settings(capsys, monkeypatch, reader, *args):
    import kei.share
    from kei.cli import main
    monkeypatch.setattr(kei.share, "local_reader", reader)
    code = main(["settings", *args])
    return code, capsys.readouterr().out


def test_set_auto_says_where_lessons_go_and_that_the_repository_is_public(here, capsys, monkeypatch):
    reader = Visibility("PUBLIC")
    code, out = settings(capsys, monkeypatch, reader, "set", "share.mode", "auto")
    assert code == 0 and load_config(here / "kei.toml").share == "auto"
    assert "castforge-ai/kei" in out and "public" in out and "anyone" in out
    assert reader.cmds == [["gh", "repo", "view", "castforge-ai/kei", "--json", "visibility"]]


def test_set_auto_on_a_private_studio_repository_says_private(here, capsys, monkeypatch):
    settings(capsys, monkeypatch, Visibility("PUBLIC"), "set", "share.repo", "my-studio/lessons")
    reader = Visibility("PRIVATE")
    code, out = settings(capsys, monkeypatch, reader, "set", "share.mode", "auto")
    assert code == 0 and "my-studio/lessons" in out and "private" in out
    assert reader.cmds[0][3] == "my-studio/lessons"


def test_when_gh_cannot_tell_the_notice_says_so(here, capsys, monkeypatch):
    code, out = settings(capsys, monkeypatch, Visibility(OSError("gh is not installed")), "set", "share.mode", "auto")
    assert code == 0 and "castforge-ai/kei" in out and "could not tell" in out
    assert load_config(here / "kei.toml").share == "auto"


def test_the_notice_is_printed_once_not_on_every_later_change(here, capsys, monkeypatch):
    settings(capsys, monkeypatch, Visibility("PUBLIC"), "set", "share.mode", "auto")
    reader = Visibility("PUBLIC")
    code, out = settings(capsys, monkeypatch, reader, "set", "limits.max_attempts", "4")
    assert code == 0 and reader.cmds == [] and "lessons" not in out
    code, out = settings(capsys, monkeypatch, reader, "set", "share.mode", "auto")    # already auto
    assert reader.cmds == []
    code, out = settings(capsys, monkeypatch, reader, "set", "share.repo", "my-studio/lessons")
    assert "my-studio/lessons" in out and len(reader.cmds) == 1      # auto now goes elsewhere: said again


# -- auto at Accept: prepare, scan, check, then gh pr create without --web, logged, and never blocks the approval ----

from test_share_bundle import seat_writing, sliding, walk      # noqa: E402
from test_share_flow import ACCOUNT, GhReader, Runner, accept, shot_with_a_note   # noqa: E402

PR_URL = "https://github.com/castforge-ai/kei/pull/77"


class PrRunner(Runner):
    """Records commands; gh pr create without --web prints the new pull request's address, as gh does."""

    def __call__(self, cmd):
        code = super().__call__(cmd)
        if cmd[:3] == ["gh", "pr", "create"] and "--web" not in cmd and code == 0:
            return 0, f"Creating pull request for octo:x into main\n\n{self.url}\n"
        return code

    url = PR_URL


@pytest.fixture
def auto(tmp_path):
    from kei.review.server import ReviewServer
    from kei.review.signoff_routes import SignOffRoutes
    from kei.share import Sharer
    from reviewkit import PageClient
    servers = []

    def build(repo="castforge-ai/kei", seat=None, private=(), runner=None):
        root, lessons = shot_with_a_note(tmp_path)
        runner = runner or PrRunner()
        sharer = Sharer(root, lessons, "auto", seat=seat or (lambda: seat_writing(sliding(walk()), walk())),
                        runner=lambda bundle, work, identity: runner, gh_found=True, size=16,
                        reader=GhReader(ACCOUNT), repo=repo, private=list(private))
        routes = SignOffRoutes(root, lessons, "r1", None, sharer=sharer)
        server = ReviewServer(routes.routes, routes.files)
        servers.append(server)
        return PageClient(server.start()), runner, root, lessons

    yield build
    for s in servers:
        s.stop()


def log_of(lessons):
    from kei.share import share_log
    p = share_log(lessons)
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()] if p.is_file() else []


def test_auto_opens_the_pull_request_itself_at_accept_with_no_form(auto):
    c, runner, root, lessons = auto()
    status, data = accept(c)
    assert status == 200 and data["status"] == "done" and data["share"]["mode"] == "auto"
    assert not any("--web" in cmd for cmd in runner.cmds)
    create = runner.cmds[-1]
    assert create[:3] == ["gh", "pr", "create"] and create[create.index("--repo") + 1] == "castforge-ai/kei"
    branch = next(cmd for cmd in runner.cmds if cmd[:3] == ["git", "switch", "-c"])[3]
    assert create[create.index("--head") + 1] == f"octo:{branch}"
    assert "--title" in create and "--body" in create
    commit = next(cmd for cmd in runner.cmds if "commit" in cmd)
    assert commit[:5] == ["git", "-c", "user.name=octo", "-c", "user.email=4242+octo@users.noreply.github.com"]
    [result] = data["share"]["results"]
    assert result["lesson"] == "local.1" and result["url"] == PR_URL
    assert result["message"] == f"sent to castforge-ai/kei: {PR_URL}"


def test_every_automatic_send_is_logged_next_to_the_lessons_file(auto):
    from kei.share import share_log
    c, runner, root, lessons = auto()
    accept(c)
    assert share_log(lessons).parent == lessons.parent
    [entry] = log_of(lessons)
    assert entry["lesson"] == "local.1" and entry["repo"] == "castforge-ai/kei" and entry["pr"] == PR_URL
    assert entry["shot"] == str(root.resolve()) and entry["at"] and entry["result"] == "sent"


def test_auto_sends_to_the_studio_repository_named_by_share_repo(auto):
    c, runner, _, lessons = auto(repo="my-studio/kei-lessons")
    data = accept(c)[1]
    assert runner.cmds[0][:3] == ["git", "clone", "https://github.com/my-studio/kei-lessons.git"]
    assert runner.cmds[-1][runner.cmds[-1].index("--repo") + 1] == "my-studio/kei-lessons"
    assert data["share"]["results"][0]["message"].startswith("sent to my-studio/kei-lessons")
    assert log_of(lessons)[0]["repo"] == "my-studio/kei-lessons"


def test_a_lesson_the_private_word_scan_refuses_is_not_sent_logged_and_the_approval_stands(auto, tmp_path):
    from kei.lessons import add_lesson
    from kei.state import load_state
    c, runner, root, lessons = auto(private=["octopus-rig"])
    lessons.write_text("", encoding="utf-8")
    add_lesson(lessons, "the octopus-rig foot hovers at the contact", "passes")
    status, data = accept(c)
    assert status == 200 and data["status"] == "done" and load_state(root).status == "done"
    [result] = data["share"]["results"]
    assert "octopus-rig" in result["error"] and "not sent" in result["error"] and runner.cmds == []
    [entry] = log_of(lessons)
    assert entry["result"] == "refused" and "private word" in entry["reason"] and "pr" not in entry


def test_a_lesson_the_bundle_check_refuses_is_not_sent_and_is_logged(auto):
    c, runner, root, lessons = auto(seat=lambda: seat_writing(walk(), walk()))     # the fails case does not fail
    status, data = accept(c)
    assert status == 200 and data["status"] == "done" and runner.cmds == []
    assert "does not fail" in data["share"]["results"][0]["error"]
    assert "does not fail" in log_of(lessons)[0]["reason"]


def test_a_failing_pull_request_is_logged_with_the_command_that_failed(auto):
    c, runner, root, lessons = auto(runner=PrRunner(fail_on=["git", "push"]))
    data = accept(c)[1]
    assert "git push" in data["share"]["results"][0]["error"]
    assert log_of(lessons)[0]["result"] == "refused" and "git push" in log_of(lessons)[0]["reason"]


def test_a_reloaded_auto_page_shows_what_was_sent_and_offers_nothing_to_press(auto):
    c, runner, root, lessons = auto()
    accept(c)
    share = c.get("/api/shot")[1]["share"]
    assert share["mode"] == "auto" and share["lessons"] == []
    assert share["log"][0]["pr"] == PR_URL
    n = len(runner.cmds)
    assert c.post("/api/share/send", {"lesson": "local.1"})[0] == 409 and len(runner.cmds) == n   # sent once


def test_the_local_runner_reads_the_address_gh_prints_for_the_new_pull_request(tmp_path, monkeypatch):
    import kei.share as share
    monkeypatch.setattr(share.shutil, "which", lambda name: f"/bin/{name}")
    seen = []

    def run(cmd, cwd=None, env=None, **kw):
        seen.append((cmd, kw))
        return type("R", (), {"returncode": 0, "stdout": f"{PR_URL}\n", "stderr": ""})()
    monkeypatch.setattr(share.subprocess, "run", run)
    runner = share.local_runner(tmp_path / "bundle", tmp_path, ("octo", 4242))
    assert runner(["gh", "pr", "create", "--repo", "a/b", "--head", "octo:x", "--title", "t", "--body", "b"]) \
        == (0, f"{PR_URL}\n")
    assert seen[-1][1].get("capture_output") is True
    assert runner(["git", "status"]) == 0


def test_the_app_gives_the_sharer_the_configured_repository(tmp_path):
    from kei.config import load_config
    from kei.review.app import _sharer
    p = tmp_path / "kei.toml"
    p.write_text(BASE + '[share]\nmode = "auto"\nrepo = "my-studio/kei-lessons"\n', encoding="utf-8")
    root, _ = shot_with_a_note(tmp_path)
    s = _sharer(root, load_config(p))
    assert (s.mode, s.repo) == ("auto", "my-studio/kei-lessons")


# -- the review page says "sent to <repo>" or the refusal ----------------------------------------------------------

def js(expr):
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    page = Path(__file__).resolve().parent.parent / "kei" / "review" / "page" / "review.js"
    script = f"const k = require({json.dumps(str(page))}); process.stdout.write(JSON.stringify({expr}));"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_line_for_a_sent_lesson_names_the_repository_and_the_pull_request():
    line = js('k.shareLine({lesson: "local.1", result: "sent", repo: "my-studio/kei", pr: "https://x/pull/3"})')
    assert line == "Lesson local.1: sent to my-studio/kei: https://x/pull/3"


def test_the_page_line_for_a_refused_lesson_gives_the_reason():
    line = js('k.shareLine({lesson: "local.2", result: "refused", repo: "a/b", reason: "lesson.md holds a private word"})')
    assert line == "Lesson local.2: not sent to a/b: lesson.md holds a private word"


def test_a_reloaded_auto_page_lists_the_log():
    src = (Path(__file__).resolve().parent.parent / "kei" / "review" / "page" / "review.js").read_text(encoding="utf-8")
    assert 'data.share.mode === "auto"' in src and "window.KeiShare.sent(data.share)" in src


def test_kei_approve_in_auto_mode_sends_with_no_dialog_and_the_approval_stands(tmp_path, monkeypatch, capsys):
    import kei.review.app as app
    from kei.cli import main
    from kei.share import Sharer
    from kei.state import load_state
    (tmp_path / "kei.toml").write_text(BASE + '[share]\nmode = "auto"\nrepo = "my-studio/kei-lessons"\n',
                                       encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    root, lessons = shot_with_a_note(tmp_path)
    runner = PrRunner()
    made = []

    def sharer(shot, config):
        made.append(config)
        return Sharer(shot, lessons, config.share, seat=lambda: seat_writing(sliding(walk()), walk()),
                      runner=lambda b, w, i: runner, gh_found=True, size=0, reader=GhReader(ACCOUNT),
                      repo=config.share_repo)
    monkeypatch.setattr(app, "_sharer", sharer)
    assert main(["approve", str(root)]) == 0
    out = capsys.readouterr().out
    assert load_state(root).status == "done" and made[0].share == "auto"
    assert f"lesson local.1: sent to my-studio/kei-lessons: {PR_URL}" in out
    assert "kei review" not in out          # no dialog to open


def test_auto_sends_nothing_to_a_repository_whose_visibility_gh_cannot_tell(tmp_path):
    from kei.share import Sharer
    from test_share_flow import ACCOUNT, GhReader

    class Blind(GhReader):
        def __call__(self, cmd):
            if cmd[:3] == ["gh", "repo", "view"]:
                self.cmds.append(list(cmd))
                raise OSError("gh: cannot see it")
            return super().__call__(cmd)
    s = Sharer.__new__(Sharer)
    s.repo, s.reader, s.mode = "someone/lessons", Blind(ACCOUNT), "auto"
    s._log = lambda lesson_id, **f: f
    s._rounds = lambda lesson_id: {}
    out = s._auto("local.1")
    assert "nothing is sent automatically" in out["error"]


def test_the_lesson_is_screened_before_any_agent_sees_it(tmp_path):
    from kei.share import BundleError, build_bundle
    lessons = tmp_path / "lessons.local.md"
    lessons.write_text("### local.1. Plant the feet\nstages: blocking\n\nAt Zorblax studio the feet slid.\n",
                       encoding="utf-8")

    class Seat:
        ran = False

        def run(self, prompt, work):
            Seat.ran = True
    try:
        build_bundle("local.1", lessons, tmp_path / "out", Seat(), private=["Zorblax"])
    except BundleError as e:
        assert "the lesson holds a private word" in str(e)
    assert Seat.ran is False                       # refused before the seat, so before any provider
