"""Sharing a lesson: a small bundle rebuilt on Kei's own character, checked, then sent with the user's own gh.

A bundle is one folder that holds only lesson.md, cases/fails/shot.json, cases/passes/shot.json, numbers.json and
bundle.json. It never holds the user's character, rig, shot, frames, drawings, file paths or name. Kei holds no
GitHub credential: the user's own gh and git do the sending, and the last step is GitHub's own submit button."""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

from kei.body_check import CheckError, check_pass
from kei.config import SHARE_REPO
from kei.book import BookError, load_rules
from kei.prompts import HERE as PROMPTS
from kei.sample import ShotError, check_shot
from kei.seats import Seat
from kei.state import load_state

REFERENCE_CHARACTER = "kei"
FORMAT = 1
CASES = ("fails", "passes")
CASE_FILES = tuple(f"cases/{c}/shot.json" for c in CASES)
BUNDLE_FILES = ("lesson.md", *CASE_FILES, "numbers.json", "bundle.json")
VERDICT = "verdict.json"            # a maintainer's verdict, written beside a bundle under review
VERDICT_DRAWINGS = "verdict_drawings"
MAX_BYTES = 2 * 1024 * 1024
CHECKS = ("contacts", "hover", "foot_slide", "balance", "trunk_lean", "joint_ranges", "knee_snap", "arcs")
SHOT_KEYS = ("rig", "fps", "frames", "loop", "keys")   # what a case keeps: never props (the user's proportions)


class BundleError(ValueError):
    """A bundle cannot be made or is refused. The message says why in plain words."""


def kei_version() -> str:
    try:
        from importlib.metadata import version
        return version("kei")
    except Exception:  # noqa: BLE001 - a source checkout with no installed metadata
        return "0.1.0"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


RULE = "every shot"     # the scope of a note that is a rule; a note for this shot never shares
NOT_CONFIRMED = "fix not confirmed"


def _yes_to(entry: dict, checks: list[str], lesson: str | None = None) -> bool:
    """Whether the entry holds a yes to one of the checks, or to the same check as the critics reworded it. A yes
    that names a note (kei fixed: "lesson") answers that note only, never a check that reads alike."""
    from kei.checklist import _same, parse_check
    wanted = [parse_check(c) for c in checks]
    for card in entry.get("cards") or []:
        if not isinstance(card, dict) or card.get("answer") != "yes" or not isinstance(card.get("check"), str):
            continue
        if "lesson" in card:
            if lesson is not None and card["lesson"] == lesson:
                return True
            continue
        if card["check"] in checks:
            return True
        got = parse_check(card["check"])
        if any(_same(got, w) for w in wanted):
            return True
    return False


def _no_checks(note: dict) -> list[str]:
    return [c["check"] for c in note.get("cards") or [] if isinstance(c, dict) and c.get("answer") == "no"
            and isinstance(c.get("check"), str)]


def confirms(note: dict, later: dict) -> bool:
    """Whether a later history entry confirms the fix of a note: a yes, in a later round, to the check the note
    answered no to (the review page), or to the note itself (kei fixed). Approval is counted by rule_status."""
    same_round = later.get("round") is not None and later.get("round") == note.get("round")
    return not same_round and _yes_to(later, _no_checks(note), note.get("lesson"))


def rule_status(shot: Path) -> list[dict]:
    """Every rule (a note for every shot) of the shot and whether a later round confirmed its fix: the author said yes
    to the check the note answered no to, in a later round, or to the note itself with kei fixed, or approved the
    shot after the note. The note's round is the failing case, the confirming round the passing case."""
    history = load_state(Path(shot)).history
    out = []
    for i, h in enumerate(history):
        if h.get("result") != "note" or not h.get("lesson") or h.get("scope") != RULE:
            continue
        rule = {"lesson": h["lesson"], "fails_round": h.get("round"), "passes_round": None, "how": None,
                "confirmed": False}
        for later in history[i + 1:]:
            if later.get("result") == "approved":
                rule.update(confirmed=True, how="approval", passes_round=later.get("round"))
                break
            if confirms(h, later):
                rule.update(confirmed=True, how="yes", passes_round=later.get("round"))
                break
        out.append(rule)
    return out


def shareable(shot: Path) -> list[str]:
    """The rules of the shot whose fix a later round confirmed, in order, each once."""
    return list(dict.fromkeys(r["lesson"] for r in rule_status(shot) if r["confirmed"]))


def new_lessons(shot: Path) -> list[str]:
    """The lesson IDs this shot's notes (and kept rejects) made, in order, each once."""
    ids = [h["lesson"] for h in load_state(Path(shot)).history if h.get("lesson")]
    return list(dict.fromkeys(ids))


def _lesson_md(lesson_id: str, lessons: Path) -> tuple[str, str]:
    try:
        rules = load_rules([Path(lessons)])
    except BookError as e:
        raise BundleError(str(e)) from e
    rule = next((r for r in rules if r.id == lesson_id), None)
    if rule is None:
        raise BundleError(f"there is no lesson {lesson_id} in {lessons}")
    stage = ",".join(rule.stages)
    return f"### {rule.id}. {rule.title}\nstages: {stage}\n\n{rule.text}\n", stage


def _private_words(extra) -> list[str]:
    words = [str(Path.home()), Path.home().name, *extra]
    try:
        words.append(getpass.getuser())
    except Exception:  # noqa: BLE001 - no user name to guard
        pass
    return sorted({w for w in words if w and len(w) >= 3}, key=len, reverse=True)


def _holds(text: str, word: str) -> bool:
    """A path is found anywhere (also JSON-escaped); a plain name only as a whole word, so a shot folder called
    walk does not refuse a lesson about walking."""
    if any(sep in word for sep in ("/", "\\", ":")):
        return word in text or word.replace("\\", "\\\\") in text
    return re.search(rf"(?<![a-z0-9_]){re.escape(word)}(?![a-z0-9_])", text) is not None


def _screen(name: str, text: str, private) -> None:
    """Refuse text that holds a private word. Run on the lesson BEFORE any agent sees it (an agent may send its prompt
    to its provider), and again on every file of the finished bundle. No scan can promise a text is anonymous or free
    of confidential matter: the author reviews every bundle before it is sent."""
    low = text.lower()
    for word in _private_words(private):
        if _holds(low, word.lower()):
            raise BundleError(f"{name} holds a private word ({word!r}): rewrite the lesson without it, then share")


def _case(path: Path, name: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        check_shot(data)
    except (OSError, ValueError, ShotError) as e:
        raise BundleError(f"the {name} case (cases/{name}/shot.json) cannot be played on {REFERENCE_CHARACTER}: {e}")
    clean = {k: data[k] for k in SHOT_KEYS if k in data}
    clean["character"] = REFERENCE_CHARACTER          # the open reference rig, whatever the seat wrote
    return clean


def measure_case(shot: dict) -> dict:
    """kei check on the reference character: every flag, and the count of each check."""
    with tempfile.TemporaryDirectory(prefix="kei-case-") as d:
        out = Path(d) / "out_case"
        out.mkdir()
        (out / "shot.json").write_text(json.dumps(shot), encoding="utf-8")
        try:
            report = json.loads(check_pass(Path(d), "case", REFERENCE_CHARACTER, "spline").read_text(encoding="utf-8"))
        except (CheckError, ShotError) as e:
            raise BundleError(f"kei check cannot measure a case: {e}") from e
    flags = [{"check": f["check"], "frames": f["frames"], "what": f.get("what", "")} for f in report["flags"]]
    counts: dict[str, int] = {}
    for f in flags:
        counts[f["check"]] = counts.get(f["check"], 0) + 1
    return {"flags": flags, "counts": counts}


def _numbers(cases: dict[str, dict], check: str | None) -> dict:
    out = {"kei_version": kei_version(), "character": REFERENCE_CHARACTER, "check": check,
           "measured": check is not None}
    for name, shot in cases.items():
        m = measure_case(shot)
        out[name] = {**m, "count": m["counts"].get(check, 0) if check else len(m["flags"])}
    return out


def build_bundle(lesson_id: str, lessons: Path, out: Path, seat: Seat, private: list[str] = ()) -> Path:
    """Have the seat rebuild the lesson as two cases on the reference character, measure both, and write the bundle
    to out. private lists words that must appear in no file (the shot's path, its character's name); the user's home
    folder and name are always on it."""
    out = Path(out)
    if out.exists():
        raise BundleError(f"{out} exists already")
    lesson_md, stage = _lesson_md(lesson_id, lessons)
    _screen("the lesson", lesson_md, private)      # before the seat: nothing private reaches an agent's provider
    contract = (PROMPTS / "share_cases.md").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="kei-share-") as work:
        work = Path(work)
        prompt = f"{contract}\n## The lesson\n\n{lesson_md}"
        result = seat.run(prompt, work)
        if result.exit_code != 0:
            raise BundleError(f"the seat could not write the cases: {result.output.strip()[:300]}")
        cases = {c: _case(work / "cases" / c / "shot.json", c) for c in CASES}
        check_file = work / "cases" / "check.txt"
        named = check_file.read_text(encoding="utf-8").strip().lower() if check_file.is_file() else "none"
        if named not in (*CHECKS, "none"):
            raise BundleError(f"cases/check.txt names {named!r}: use one of {', '.join(CHECKS)}, or none")
        check = None if named == "none" else named
    numbers = _numbers(cases, check)
    if check:
        if numbers["fails"]["count"] == 0:
            raise BundleError(f"the fails case does not fail: kei check finds no {check} flag in it")
        if numbers["passes"]["count"] != 0:
            raise BundleError(f"the passes case does not pass: kei check finds {numbers['passes']['count']} "
                              f"{check} flag(s) in it")
    files = {"lesson.md": lesson_md.encode("utf-8"),
             **{f"cases/{c}/shot.json": json.dumps(cases[c], indent=1).encode("utf-8") for c in CASES},
             "numbers.json": json.dumps(numbers, indent=1).encode("utf-8")}
    meta = {"format": FORMAT, "kei_version": kei_version(), "stage": stage, "lesson": lesson_id,
            "files": {k: _sha(v) for k, v in files.items()}}
    files["bundle.json"] = json.dumps(meta, indent=1).encode("utf-8")
    for rel, data in files.items():
        _screen(rel, data.decode("utf-8"), private)
    for rel, data in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return out


def check_bundle(folder: Path, reviewed: bool = True) -> dict:
    """Refuse a bundle that holds anything else than its five files, a file whose hash differs, a case Kei cannot
    play, more than 2 MB, or an unknown format. Returns bundle.json."""
    folder = Path(folder)
    if not folder.is_dir():
        raise BundleError(f"{folder} is not a folder")
    found = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file() or p.is_symlink())
    if reviewed:   # the maintainer's own verdict and drawings sit beside the bundle once it is reviewed
        found = [f for f in found if f != VERDICT and not f.startswith(VERDICT_DRAWINGS + "/")]
    extra = [f for f in found if f not in BUNDLE_FILES]
    if extra:
        raise BundleError(f"the bundle holds files a bundle never holds: {', '.join(extra)}")
    missing = [f for f in BUNDLE_FILES if f not in found]
    if missing:
        raise BundleError(f"the bundle is missing {', '.join(missing)}")
    size = sum((folder / f).stat().st_size for f in found)
    if size > MAX_BYTES:
        raise BundleError(f"the bundle is {size} bytes, over 2 MB")
    try:
        meta = json.loads((folder / "bundle.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BundleError(f"bundle.json cannot be read: {e}") from e
    if not isinstance(meta, dict) or meta.get("format") != FORMAT:
        raise BundleError(f"bundle.json has an unknown format {meta.get('format') if isinstance(meta, dict) else None!r}")
    hashes = meta.get("files") if isinstance(meta.get("files"), dict) else {}
    for rel in BUNDLE_FILES[:-1]:
        if hashes.get(rel) != _sha((folder / rel).read_bytes()):
            raise BundleError(f"{rel} does not match its hash in bundle.json: it changed after the bundle was made")
    for c in CASES:
        _case(folder / "cases" / c / "shot.json", c)
    return meta


# -- sending: the user's own gh and git ----------------------------------------------------------------------------

UPSTREAM = SHARE_REPO               # where shared lessons go unless share.repo names another repository
CLONE = "kei-share"                 # the clone's folder, inside a temporary folder of Kei's
SHARE_MODES = ("ask", "always", "never", "auto")
SHARE_LOG = "share-log.jsonl"       # beside the lessons file: one line per lesson Kei sent or kept back
AUTO_BODY = ("A lesson shared by Kei at the author's sign-off (share.mode auto): lesson.md, a failing and a passing "
             "case on Kei's own character, and their kei check numbers. Review it with kei review --pr <number>.")
Runner = Callable[[list[str]], "int | tuple[int, str]"]
PUBLIC_NOTE = ("When you press Send, Kei forks the project to your GitHub account and pushes this lesson folder to a "
               "branch of your fork, which is public: anyone can see it. The pull request opens only when you press "
               "GitHub's own button.")
Reader = Callable[[list[str]], str]
_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")


def github_identity(reader: Reader) -> tuple[str, int]:
    """The user's GitHub login and numeric id, read with their own gh (gh api user). The share commit carries only
    this account: the login as name, <id>+<login>@users.noreply.github.com as e-mail. No answer, no share."""
    why = ("Kei could not read your GitHub account from gh, and a shared lesson carries only your GitHub account, "
           "never your git name or e-mail. Run gh auth login, then share again")
    try:
        data = json.loads(reader(["gh", "api", "user"]))
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        raise BundleError(f"{why} ({e})") from e
    login = data.get("login") if isinstance(data, dict) else None
    uid = data.get("id") if isinstance(data, dict) else None
    if not isinstance(login, str) or not _LOGIN.fullmatch(login) or not isinstance(uid, int) or isinstance(uid, bool):
        raise BundleError(f"{why} (gh did not give both a login and an id)")
    return login, uid


def local_reader(cmd: list[str]) -> str:
    """Runs one read-only gh command with the user's own gh and returns what it prints."""
    exe = shutil.which(cmd[0])
    if exe is None:
        raise OSError(f"{cmd[0]} is not installed")
    r = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, encoding="utf-8", timeout=30)
    if r.returncode != 0:
        raise OSError((r.stderr or r.stdout).strip()[:200] or f"exit {r.returncode}")
    return r.stdout


def repo_visibility(repo: str, reader: Reader) -> str | None:
    """public, private or internal, as the user's own gh sees the repository; None when gh cannot tell."""
    try:
        data = json.loads(reader(["gh", "repo", "view", repo, "--json", "visibility"]))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    v = data.get("visibility") if isinstance(data, dict) else None
    v = v.lower() if isinstance(v, str) else None
    return v if v in ("public", "private", "internal") else None


def auto_notice(repo: str, reader: Reader) -> str:
    """What kei settings prints once when share.mode becomes auto, or auto starts sending to another repository."""
    head = (f"share.mode is auto: at every Accept and Reject, with no dialog, Kei opens a pull request on {repo} for "
            "each lesson that is ready to share, and pushes it to a branch of your fork of that repository.")
    vis = repo_visibility(repo, reader)
    if vis == "public":
        tail = f"{repo} is public: anyone can read the lessons and their pull requests."
    elif vis == "private":
        tail = f"{repo} is private: only the people who can open it can read them."
    elif vis == "internal":
        tail = f"{repo} is internal: every member of its organisation's enterprise can read them."
    else:
        tail = (f"gh could not tell whether {repo} is public or private: check it on GitHub before your next "
                "Accept, or switch back with kei settings set share.mode ask.")
    return head + "\n" + tail


def _title(bundle: Path) -> str:
    first = (Path(bundle) / "lesson.md").read_text(encoding="utf-8").splitlines()[0]
    return re.sub(r"^### \S+\. ", "", first).replace(" (provisional)", "").strip()


def bundle_name(lesson_id: str, lessons: Path, when: date | None = None) -> str:
    md, _ = _lesson_md(lesson_id, lessons)
    words = re.findall(r"[a-z0-9]+", md.splitlines()[0].split(". ", 1)[-1].lower().replace("provisional", ""))
    return f"{(when or date.today()).isoformat()}-{'-'.join(words[:6]) or 'lesson'}"


def share_plan(bundle: Path, repo: str, identity: tuple[str, int], stamp: str = "",
               auto: bool = False, sign_off: bool = False) -> list[list[str]]:
    """The exact commands, shown to the user before the click. Relative paths only: the first runs in a temporary
    folder of Kei's, the rest inside the clone it makes. The commit carries the GitHub account only, set for that one
    command with git -c and never written to any git config. The last opens GitHub's own form; the user submits it.
    auto (share.mode = "auto", set by the user in kei settings or kei.toml): the last opens the pull request itself.
    sign_off (share.sign_off = "on", the user's own choice): the commit carries a Signed-off-by line for the GitHub
    account, the user's agreement to the Developer Certificate of Origin in CONTRIBUTING.md."""
    login, uid = identity
    name = Path(bundle).name
    branch = f"lesson/{name}" + (f"-{stamp}" if stamp else "")   # the stamp keeps a re-share off an old branch
    # a whole clone, not a shallow one: the push to the user's fork must carry every commit the fork lacks
    return [["git", "clone", f"https://github.com/{repo}.git", CLONE],
            ["gh", "repo", "fork", "--remote", "--remote-name", "fork"],
            ["git", "switch", "-c", branch],
            ["copy", name, f"lessons/incoming/{name}"],
            ["git", "add", f"lessons/incoming/{name}"],
            ["git", "-c", f"user.name={login}", "-c", f"user.email={noreply(identity)}",
             "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={NO_HOOKS}",
             "commit", "--no-verify", "-m", f"Lesson: {_title(bundle)}",
             *(["-m", f"Signed-off-by: {login} <{noreply(identity)}>"] if sign_off else [])],
            ["git", "push", "-u", "fork", branch],
            (["gh", "pr", "create", "--repo", repo, "--head", f"{login}:{branch}", "--title",
              f"Lesson: {_title(bundle)}", "--body", AUTO_BODY] if auto
             else ["gh", "pr", "create", "--web", "--repo", repo])]


def manual_steps(bundle: Path, repo: str = UPSTREAM) -> list[str]:
    name = Path(bundle).name
    return [f"Fork https://github.com/{repo} on GitHub.",
            f"In your fork, add the folder {name} under lessons/incoming/ (all five files, unchanged).",
            f"Open a pull request from your fork to {repo}, and say in it what the lesson is about."]


def run_plan(plan: list[list[str]], runner: Runner) -> str:
    """Run each command in order; stop at the first that fails and say which. Returns what the last one printed,
    when the runner reads it (gh pr create without --web prints the new pull request's address)."""
    out = ""
    for cmd in plan:
        got = runner(cmd)
        code, out = got if isinstance(got, tuple) else (got, "")
        if code != 0:
            raise BundleError(f"stopped: {' '.join(cmd[:2])} failed (exit {code}); nothing after it ran. "
                              f"The command was: {' '.join(cmd)}")
    return out


def run_share(plan: list[list[str]], runner: Runner) -> str:
    run_plan(plan, runner)
    return "GitHub's pull request form is open in your browser: read it, then press its own button to send."


_PR_URL = re.compile(r"https://github\.com/[^\s/]+/[^\s/]+/pull/\d+")


def pr_address(printed: str) -> str:
    found = _PR_URL.findall(printed or "")
    if not found:
        raise BundleError(f"gh pr create printed no pull request address: {(printed or '').strip()[:200]!r}")
    return found[-1]


NO_HOOKS = ".kei-share-no-hooks"     # a hooks folder that does not exist in the clone: no hook of the user's runs
_GIT_IDENTITY = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")


def noreply(identity: tuple[str, int]) -> str:
    login, uid = identity
    return f"{uid}+{login}@users.noreply.github.com"


def share_env(identity: tuple[str, int]) -> dict[str, str]:
    """A copy of the environment for the share commands: any git name or e-mail the user set there is replaced by
    the GitHub account. The user's own environment is not changed."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_IDENTITY}
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = identity[0]
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = noreply(identity)
    return env


def local_runner(bundle: Path, work: Path, identity: tuple[str, int]) -> Runner:
    """Runs the plan with the user's own gh and git: the clone in work, every later command inside the clone, in an
    environment that carries the GitHub account only."""
    env = share_env(identity)

    def run(cmd: list[str]) -> int:
        cwd = work / CLONE if (work / CLONE).is_dir() else work
        if cmd[0] == "copy":
            shutil.copytree(bundle, cwd / cmd[2])
            return 0
        exe = shutil.which(cmd[0])
        if exe is None:
            return 127
        if cmd[:3] == ["gh", "pr", "create"] and "--web" not in cmd:     # auto: read the address gh prints
            r = subprocess.run([exe, *cmd[1:]], cwd=str(cwd), env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            return r.returncode, r.stdout or ""
        return subprocess.run([exe, *cmd[1:]], cwd=str(cwd), env=env).returncode
    return run


def share_log(lessons: Path) -> Path:
    """The local share log: next to the lessons file, never shared."""
    return Path(lessons).parent / SHARE_LOG


def log_share(lessons: Path, entry: dict) -> dict:
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    p = share_log(lessons)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_share_log(lessons: Path, shot: Path | None = None) -> list[dict]:
    p = share_log(lessons)
    out = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and (shot is None or e.get("shot") == str(Path(shot).resolve())):
                out.append(e)
    return out


class Sharer:
    """The share step after Accept. ask: the page shows the bundle and the commands and runs nothing until the user
    presses the button; always: Kei builds and opens the form at once (the user still submits it on GitHub); auto:
    Kei builds, checks and opens the pull request itself on repo, with no dialog, and logs each lesson; never:
    nothing. seat makes the agent that writes the cases; runner(bundle, work) makes the command runner."""

    def __init__(self, shot: Path, lessons: Path, mode: str, seat: Callable[[], Seat],
                 runner: Callable[[Path, Path, tuple[str, int]], Runner] = local_runner, gh_found: bool | None = None,
                 repo: str = UPSTREAM, private: list[str] = (), size: int = 240, reader: Reader = local_reader,
                 sign_off: bool = False):
        self.shot, self.lessons, self.mode = Path(shot), Path(lessons), mode
        self.seat, self.runner, self.repo, self.private = seat, runner, repo, list(private)
        self.gh = shutil.which("gh") is not None if gh_found is None else gh_found
        self.incoming = self.lessons.parent / "lessons" / "incoming"
        self.renders = self.lessons.parent / "lessons" / "renders"   # the cases drawn for the panel; never shared
        self.bundles: dict[str, Path] = {}
        self.stamps: dict[str, str] = {}     # one branch stamp per lesson, chosen at prepare and used at send
        self.rounds: dict[str, dict] = {}
        self.size = size     # pixels per view of the case rounds the panel plays
        self.reader = reader
        self.sign_off = sign_off

    def _accepted(self) -> None:
        if load_state(self.shot).status not in ("done", "rejected"):
            raise BundleError("share comes after Accept or Reject: this shot is not signed off")
        if self.mode == "never":
            raise BundleError("share.mode is never in kei.toml: Kei shares nothing")

    def _lesson(self, lesson_id) -> str:
        if lesson_id not in shareable(self.shot):
            raise BundleError(f"{lesson_id} is not a rule of this shot whose fix a later round confirmed: only a "
                              "note for every shot, seen fixed, can be shared")
        return lesson_id

    def _rounds(self, lesson_id: str) -> dict:
        r = next((r for r in rule_status(self.shot) if r["lesson"] == lesson_id), {})
        return {"fails_round": r.get("fails_round"), "passes_round": r.get("passes_round")}

    def on_reject(self) -> dict:
        """Amendment 3: shares run at the rejection too, for the rules whose fix the author saw confirmed."""
        return self.on_accept()

    def on_accept(self) -> dict:
        ids = shareable(self.shot)
        out = {"mode": self.mode, "lessons": ids if self.mode not in ("never", "auto") else [], "gh": self.gh}
        if self.mode != "never":
            out["kept"] = []
            for r in rule_status(self.shot):
                if not r["confirmed"] and r["lesson"] not in ids:
                    self._log(r["lesson"], result="kept", reason=NOT_CONFIRMED)
                    out["kept"].append({"lesson": r["lesson"], "reason": NOT_CONFIRMED})
        if self.mode == "auto":
            out["results"] = [self._auto(lesson_id) for lesson_id in ids]
        elif self.mode == "always" and ids:
            out["results"] = []
            for lesson_id in ids:
                try:
                    out["results"].append({"lesson": lesson_id, "message": self.send(lesson_id)})
                except Exception as e:   # noqa: BLE001 - the approval is saved; a share failure is only reported
                    out["results"].append({"lesson": lesson_id, "error": f"not shared: {e}"})
        return out

    def _log(self, lesson_id: str, **fields) -> dict:
        return log_share(self.lessons, {"shot": str(self.shot.resolve()), "lesson": lesson_id, "repo": self.repo,
                                        "mode": self.mode, **fields})

    def _auto(self, lesson_id: str) -> dict:
        """One lesson in auto mode: sent, or refused with the reason. Either way it is logged, and a refusal never
        touches the approval. A repository whose visibility gh cannot tell gets nothing sent automatically."""
        if repo_visibility(self.repo, self.reader) is None:
            reason = (f"gh could not tell whether {self.repo} is public or private, so nothing is sent automatically: "
                      "check it on GitHub, or share by hand with kei review")
            self._log(lesson_id, result="refused", reason=reason, **self._rounds(lesson_id))
            return {"lesson": lesson_id, "error": f"not sent to {self.repo}: {reason}"}
        try:
            url = self._send(lesson_id)
        except Exception as e:   # noqa: BLE001 - the approval is saved; a refused lesson is reported and logged
            reason = str(e) or type(e).__name__
            self._log(lesson_id, result="refused", reason=reason, **self._rounds(lesson_id))
            return {"lesson": lesson_id, "error": f"not sent to {self.repo}: {reason}"}
        self._log(lesson_id, result="sent", pr=url, **self._rounds(lesson_id))
        return {"lesson": lesson_id, "url": url, "message": f"sent to {self.repo}: {url}"}

    def _bundle(self, lesson_id: str) -> Path:
        """The lesson's bundle, built once: the seat's two cases, measured, and the private-word scan."""
        lesson_id = self._lesson(lesson_id)
        bundle = self.bundles.get(lesson_id)
        if bundle is None:
            name = bundle_name(lesson_id, self.lessons)
            bundle, n = self.incoming / name, 2
            while bundle.exists():
                bundle, n = self.incoming / f"{name}-{n}", n + 1
            build_bundle(lesson_id, self.lessons, bundle, self.seat(), private=self.private)
            self.bundles[lesson_id] = bundle
        return bundle

    def _stamp(self, lesson_id: str) -> str:
        return self.stamps.setdefault(lesson_id, datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))

    def prepare(self, lesson_id: str) -> dict:
        self._accepted()
        bundle = self._bundle(lesson_id)
        files = {rel: (bundle / rel).read_text(encoding="utf-8") for rel in BUNDLE_FILES}
        rounds = {}
        if self.size:
            from kei.review.rounds import case_rounds
            rounds = case_rounds(bundle, self.renders / bundle.name, self.size, prefix=f"share-{lesson_id}")
            self.rounds[lesson_id] = {"dir": self.renders / bundle.name, **rounds}
        stamp = self._stamp(lesson_id)
        commands = (share_plan(bundle, self.repo, github_identity(self.reader), stamp, auto=self.mode == "auto",
                               sign_off=self.sign_off) if self.gh else [])
        return {"lesson": lesson_id, "folder": str(bundle), "files": files, "gh": self.gh, "rounds": rounds,
                "commands": commands, "manual": manual_steps(bundle, self.repo), "public_note": PUBLIC_NOTE}

    def files(self) -> dict[str, Path]:
        """The case frames the share panel plays."""
        out = {}
        for info in self.rounds.values():
            for case in ("fails", "passes"):
                rid = info[case]["round"]
                out.update({f"{rid}/{p.stem}": p for p in sorted((info["dir"] / case / "frames").glob("f*.png"))})
        return out

    def panel(self) -> dict | None:
        """What a reloaded page of a signed-off shot offers: the lessons to share, unless share.mode is never; in
        auto mode nothing to press, only what the log says Kei sent or kept back."""
        if self.mode == "never" or load_state(self.shot).status not in ("done", "rejected"):
            return None
        if self.mode == "auto":
            return {"mode": "auto", "lessons": [], "gh": self.gh, "repo": self.repo,
                    "log": read_share_log(self.lessons, self.shot)}
        return {"mode": "ask" if self.mode == "ask" else self.mode, "lessons": shareable(self.shot), "gh": self.gh}

    def send(self, lesson_id: str) -> str:
        """The page's Send (ask) and the always mode: the plan ends on GitHub's own form."""
        if self.mode == "auto":
            raise BundleError("share.mode is auto: Kei sent this shot's lessons itself at the sign-off; the share "
                              f"log beside your lessons file ({SHARE_LOG}) says what went where")
        message = self._send(lesson_id)
        self._log(lesson_id, result="form opened", **self._rounds(lesson_id))
        return message

    def _send(self, lesson_id: str) -> str:
        self._accepted()            # checked again here: the approval may have been withdrawn since prepare
        bundle = self._bundle(lesson_id)
        if not self.gh:
            raise BundleError("gh is not installed: follow the manual steps on the page")
        check_bundle(bundle, reviewed=False)
        auto = self.mode == "auto"
        with tempfile.TemporaryDirectory(prefix="kei-share-") as work:
            identity = github_identity(self.reader)                              # refused before any command
            plan = share_plan(bundle, self.repo, identity, self._stamp(lesson_id), auto=auto, sign_off=self.sign_off)
            printed = run_plan(plan, self.runner(bundle, Path(work), identity))
        if auto:
            return pr_address(printed)
        return "GitHub's pull request form is open in your browser: read it, then press its own button to send."
