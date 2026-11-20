"""The live page saved as one file at delivery: <shot>/<shot>_report.html.

write_report(shot) -> Path
  The live page with its style, its code and the shot's data inside one HTML file, written on top of the delivered
  shot folder. It loads nothing from the network and needs no server: images and videos are read from the shot
  folder beside it by relative paths, so the report works wherever the folder is copied, as long as the folder goes
  with it. kei approve writes it after the folder is tidied, and a command that repacks a delivered shot writes it
  again, so it always shows the folder as it is.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from kei.live.snapshot import files, snapshot

PAGE = Path(__file__).resolve().parent / "page"


def report_name(shot: Path) -> str:
    return f"{Path(shot).name}_report.html"


def _inline(text: str) -> str:
    return text.replace("</", "<" + chr(92) + "/")     # "<\/": nothing inside a script may close it


UNREAL_COPY = ".kei/live/unreal_report.json"     # where the copy beside the Unreal assets was written


def page_html(shot: Path, snap: dict, paths: dict, extra: str = "") -> str:
    """The live page as one HTML text: its style and code inline, the snapshot and the file map inside it. extra is
    HTML put before </main> (kei pack adds the reviewer's notes there)."""
    shot = Path(shot)
    data = {"saved": datetime.now(timezone.utc).isoformat(), "snapshot": snap, "files": paths}
    html = (PAGE / "index.html").read_text(encoding="utf-8")
    css = (PAGE / "live.css").read_text(encoding="utf-8")
    js = (PAGE / "live.js").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="/live.css">', f"<style>\n{css}</style>")
    html = html.replace('<script src="/live.js"></script>',
                        f"<script>window.KEI_STATIC = {_inline(json.dumps(data))};</script>\n"
                        f"<script>\n{_inline(js)}</script>")
    html = html.replace("<title>Kei live</title>", f"<title>Kei: {_esc(shot.name)}</title>")
    if extra:
        html = html.replace("</main>", extra + "\n  </main>", 1)
    return html


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def write_report(shot: Path, dest: Path | None = None) -> Path:
    """The report on top of the shot folder; with dest, a copy elsewhere (beside the Unreal assets) whose images and
    videos point back at the shot folder by full path, so it works on this machine only."""
    shot = Path(shot)
    found = files(shot)
    if dest is None:
        paths = {i: p.relative_to(shot).as_posix() for i, p in found.items()}
    else:
        paths = {i: "file:///" + p.resolve().as_posix().lstrip("/") for i, p in found.items()}
    html = page_html(shot, snapshot(shot), paths)
    out = dest or shot / report_name(shot)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def write_unreal_copy(shot: Path, content_dir: str, kei_folder: str) -> Path:
    """The copy in the project's Content folder, beside Kei's assets for the shot (kei_folder, /Game/Kei/<shot>)."""
    shot = Path(shot)
    dest = Path(content_dir) / kei_folder.removeprefix("/Game/") / report_name(shot)
    write_report(shot, dest)
    rec = shot / UNREAL_COPY
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text(json.dumps({"path": str(dest)}), encoding="utf-8")
    return dest


def refresh(shot: Path) -> list[Path]:
    """Write the report again, and its Unreal copy when one was written before."""
    shot = Path(shot)
    out = [write_report(shot)]
    try:
        dest = Path(json.loads((shot / UNREAL_COPY).read_text(encoding="utf-8"))["path"])
    except (OSError, ValueError, KeyError):
        return out
    if dest.parent.is_dir():
        out.append(write_report(shot, dest))
    return out
