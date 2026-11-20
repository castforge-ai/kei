"""Lesson sharing without the review page: check bundles (the CI job on lesson pull requests runs this), move a lesson
as one zip file for a studio without GitHub, and list the lessons maintainers accepted.

check_folders(folders) -> [(folder, None | reason)]
  check_bundle on each, the same checks the review page runs: only the five files, every hash, both cases playable,
  2 MB at most. A maintainer's verdict beside a bundle is allowed.
export_zip(bundle, out) -> Path
  The bundle checked, then written as <name>.zip holding <name>/ and its five files, nothing else.
import_zip(zip_path, incoming) -> Path
  Unpacks a zip from export_zip into incoming/<name>/ and checks it. Refused before anything is written: a name
  outside the five files, a path that leaves the folder, more than one folder, over 2 MB, or a folder already there.
accepted(root) -> [{"folder", "title", "rule", "book", "at"}]
  Every bundle under lessons/ whose verdict.json says accept, oldest first. accepted_md writes them as a page,
  lessons/ACCEPTED.md, which the public project keeps as its list of accepted lessons.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path, PurePosixPath

from kei.share import BUNDLE_FILES, MAX_BYTES, VERDICT, BundleError, check_bundle


def check_folders(folders: list[Path]) -> list[tuple[Path, str | None]]:
    out = []
    for f in folders:
        try:
            check_bundle(Path(f), reviewed=True)
            out.append((Path(f), None))
        except BundleError as e:
            out.append((Path(f), str(e)))
    return out


def bundle_folders(root: Path) -> list[Path]:
    """The bundle folders under root: root itself when it is one, else every folder with a bundle.json below it."""
    root = Path(root)
    if (root / "bundle.json").is_file():
        return [root]
    return sorted(p.parent for p in root.rglob("bundle.json"))


def export_zip(bundle: Path, out: Path | None = None) -> Path:
    bundle = Path(bundle)
    check_bundle(bundle, reviewed=False)
    dest = Path(out) if out else bundle.parent / f"{bundle.name}.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for rel in BUNDLE_FILES:
            z.write(bundle / rel, f"{bundle.name}/{rel}")
    return dest


def import_zip(zip_path: Path, incoming: Path) -> Path:
    zip_path, incoming = Path(zip_path), Path(incoming)
    try:
        z = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as e:
        raise BundleError(f"{zip_path.name} is not a zip file") from e
    with z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        tops = set()
        for i in infos:
            p = PurePosixPath(i.filename)
            if p.is_absolute() or ".." in p.parts or "\\" in i.filename or len(p.parts) < 2:
                raise BundleError(f"{zip_path.name} holds a path Kei does not unpack: {i.filename[:80]!r}")
            tops.add(p.parts[0])
            if "/".join(p.parts[1:]) not in BUNDLE_FILES:
                raise BundleError(f"{zip_path.name} holds a file a bundle never holds: {i.filename[:80]!r}")
        if len(tops) != 1:
            raise BundleError(f"{zip_path.name} must hold exactly one lesson folder, not {len(tops)}")
        if sum(i.file_size for i in infos) > MAX_BYTES:
            raise BundleError(f"{zip_path.name} unpacks to over 2 MB")
        name = tops.pop()
        dest = incoming / name
        if dest.exists():
            raise BundleError(f"{dest} is already there: remove it first, or this lesson was brought in before")
        try:
            for i in infos:
                target = dest / "/".join(PurePosixPath(i.filename).parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(i))
            check_bundle(dest, reviewed=False)
        except Exception:
            import shutil
            shutil.rmtree(dest, ignore_errors=True)
            raise
    return dest


def _title(bundle: Path) -> str:
    try:
        first = (bundle / "lesson.md").read_text(encoding="utf-8").strip().splitlines()[0]
    except (OSError, IndexError):
        return bundle.name
    return first.lstrip("#").strip()[:160] or bundle.name


def accepted(root: Path) -> list[dict]:
    out = []
    for v in sorted(Path(root).rglob(VERDICT)):
        try:
            data = json.loads(v.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("verdict") != "accept":
            continue
        out.append({"folder": v.parent.name, "title": _title(v.parent), "rule": data.get("rule") or "",
                    "book": data.get("book") or "", "at": str(data.get("at") or "")[:10]})
    return sorted(out, key=lambda r: (r["at"], r["folder"]))


def accepted_md(rows: list[dict]) -> str:
    lines = ["# Accepted lessons", "",
             "Lessons people shared that the maintainers accepted into the rule book. Written by kei share list "
             "--write; do not edit by hand.", ""]
    if not rows:
        lines.append("None yet.")
    else:
        lines += ["| Accepted | Rule | Book file | Lesson |", "|---|---|---|---|"]
        for r in rows:
            title = r["title"].replace("|", "/")
            lines.append(f"| {r['at']} | {r['rule']} | {r['book']} | {title} ({r['folder']}) |")
    return "\n".join(lines) + "\n"
