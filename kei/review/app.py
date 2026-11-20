"""kei review: render the round, start the local server, open the page, serve until Ctrl+C or the page's Close."""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path

from kei.config import Config
from kei.review.rounds import before_round, make_round
from kei.review.server import ReviewServer
from kei.review.signoff_routes import SignOffRoutes
from kei.state import load_state, state_path


class ReviewAppError(ValueError):
    """kei review cannot start. The message says why in one line."""


def _closer(server: ReviewServer):
    def close(req):
        threading.Timer(0.2, server.stop).start()   # after the reply is sent
        return 200, {"closed": True}
    return close


def serve(server: ReviewServer) -> None:
    """Block until the page's Close or Ctrl+C. Tests replace it."""
    server.wait()


def check_shot(shot: Path) -> Path:
    shot = Path(shot)
    if not state_path(shot).is_file():
        raise ReviewAppError(f"{shot} is not a Kei shot: it has no .kei/state.json")
    load_state(shot)    # a state file that cannot be read stops here, in one line
    return shot


def _sharer(shot: Path, config: Config):
    """The share step: the animator seat rebuilds a lesson on Kei's own character; nothing of this shot travels."""
    from kei.characters import imported_characters
    from kei.seats import CliSeat
    from kei.share import Sharer
    private = [str(Path(shot).resolve()), Path(shot).resolve().name]   # the shot's path and its folder name
    private += [n for n in imported_characters()]   # an imported character is the user's own
    return Sharer(shot, config.lessons, config.share, seat=lambda: CliSeat(config.animator), private=private,
                  repo=config.share_repo, sign_off=config.share_sign_off == "on")


def settings_routes(target: Path, shown: Path | None = None) -> dict:
    """The Settings tab's routes, on every review page."""
    from kei.review.settings_routes import SettingsRoutes
    return SettingsRoutes(target, shown).routes


def shot_server(shot: Path, config: Config, size: int = 360, port: int = 0, extra: dict | None = None,
                settings: Path | None = None, shown: Path | None = None):
    """The sign-off page of one shot: its newest round (made now if the pass changed) and the round before it."""
    shot = check_shot(shot)
    after = make_round(shot, size=size, character=config.character).name
    before = before_round(shot, after, size=size, character=config.character)
    routes = SignOffRoutes(shot, config.lessons, after, before, sharer=_sharer(shot, config))
    server = ReviewServer({**routes.routes, **settings_routes(settings or Path.cwd() / "kei.toml", shown),
                           **(extra or {})}, routes.files, port=port, single_use_link=True)
    server.routes["POST /api/close"] = _closer(server)
    return server, routes


def waiting_shots(root: Path) -> list[dict]:
    """Shots under root (the folder itself, its children and grandchildren) that wait for a sign-off."""
    root = Path(root)
    found = []
    for state in sorted({*root.glob(".kei/state.json"), *root.glob("*/.kei/state.json"),
                         *root.glob("*/*/.kei/state.json")}):
        shot = state.parent.parent
        try:
            s = load_state(shot)
        except ValueError:
            continue
        if s.status == "needs_approval":
            rel = shot.relative_to(root).as_posix() if shot != root else "."
            found.append({"shot": shot.name, "path": rel, "command": f"kei review {rel}"})
    return found


def incoming_lessons(root: Path) -> list[dict]:
    """Shared lesson bundles waiting under lessons/incoming/."""
    out = []
    for b in sorted(Path(root).glob("lessons/incoming/*/bundle.json")):
        rel = b.parent.relative_to(root).as_posix()
        out.append({"name": b.parent.name, "path": rel, "command": f"kei review --lesson {rel}"})
    return out


def list_server(root: Path, port: int = 0, extra: dict | None = None, settings: Path | None = None,
                shown: Path | None = None):
    shots, lessons = waiting_shots(root), incoming_lessons(root)
    mode = {"mode": "list", "shots": shots, "lessons": lessons}
    server = ReviewServer({"GET /api/mode": lambda req: (200, mode),
                           **settings_routes(settings or Path(root) / "kei.toml", shown), **(extra or {})},
                          lambda: {}, port=port, single_use_link=True)
    server.routes["POST /api/close"] = _closer(server)
    return server, mode


def _run(cmd: list[str], cwd: Path) -> int:
    exe = shutil.which(cmd[0])
    return 127 if exe is None else subprocess.run([exe, *cmd[1:]], cwd=str(cwd)).returncode


def _read(cmd: list[str], cwd: Path) -> str:
    exe = shutil.which(cmd[0])
    if exe is None:
        raise ReviewAppError(f"{cmd[0]} is not installed: kei review --pr needs the GitHub CLI")
    r = subprocess.run([exe, *cmd[1:]], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise ReviewAppError(f"{' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout


def pr_routes(number: int, root: Path, book: Path, runner=None, reader=None, size: int = 360):
    """gh pr checkout <n> in the maintainer's clone, then the lesson the pull request adds. Kei reads the pull
    request with gh and changes nothing on GitHub: no push, no merge, no comment."""
    from kei.review.lesson_routes import LessonRoutes
    root = Path(root)
    runner = runner or (lambda cmd: _run(cmd, root))
    reader = reader or (lambda cmd: _read(cmd, root))
    code = runner(["gh", "pr", "checkout", str(number)])
    if code != 0:
        raise ReviewAppError(f"gh pr checkout {number} failed (exit {code})")
    info = json.loads(reader(["gh", "pr", "view", str(number), "--json", "author,files"]))
    names = sorted({f["path"].split("/")[2] for f in info.get("files", [])
                    if f.get("path", "").startswith("lessons/incoming/") and f["path"].count("/") >= 3})
    if len(names) != 1:
        raise ReviewAppError(f"pull request {number} must add exactly one folder under lessons/incoming/, "
                             f"not {len(names)}")
    login = (info.get("author") or {}).get("login", "")
    return LessonRoutes(root / "lessons" / "incoming" / names[0], book, root / "lessons" / "renders",
                        runner=runner, author=login, size=size)


def lesson_server(a, config_path: Path) -> ReviewServer:
    """kei review --lesson <dir> or --pr <n>: the bundle is checked before anything else."""
    from kei.config import load_config
    from kei.review.lesson_routes import LessonRoutes
    config = load_config(config_path)
    if a.pr:
        routes = pr_routes(a.pr, Path.cwd(), config.book, size=a.size)
    else:
        bundle = Path(a.lesson)
        routes = LessonRoutes(bundle, config.book, bundle.resolve().parent.parent / "renders", size=a.size)
    target = Path(a.config) if a.config else Path.cwd() / "kei.toml"
    server = ReviewServer({**routes.routes, **settings_routes(target, config_path)}, routes.files, port=a.port,
                          single_use_link=True)
    server.routes["POST /api/close"] = _closer(server)
    print(f"lesson {routes.rule.id}: {routes.rule.title}" + (" (Kei's numbers differ from the bundle's)"
                                                              if routes.lesson()["any_differs"] else ""))
    return server


def open_page(server: ReviewServer, browser: bool) -> str:
    url = server.start()
    print(f"review page: {url}", flush=True)
    print("only this machine can open it; stop with Ctrl+C or the page's Close button", flush=True)
    if browser:
        webbrowser.open(url)
    return url
