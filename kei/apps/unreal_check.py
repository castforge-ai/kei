"""kei unreal check: is this Unreal project ready for Kei, and is it a combination Kei was tested on?

checks(project_dir, url, probe) -> [(status, what, found, fix)], the same rows as kei doctor (ok, warn, fail):
  the project file, the engine version, Claireon and its version, the Python Editor Script Plugin, the port the editor
  wrote, whether an editor answers there (its server, protocol and the tool Kei needs), and the ignore line for
  Content/Kei/. Reading files never needs the editor; the answer row needs it open, and says how to start it.
COMPATIBILITY is the table the README prints: each row is a combination and how far it was tested. A combination that is
  not in the table is a warning, never a failure: it may work, and nobody has checked it.
Kei sends nothing to any address but 127.0.0.1, and the probe only runs the handshake and lists the tools.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

from kei.apps.unreal import Claireon, NEEDED_TOOLS, UnrealError, server_url
from kei.doctor import FAIL, OK, WARN

# One row per combination. "live" is a real editor driven by Kei; "files" is read from the project only.
COMPATIBILITY: tuple[dict, ...] = (
    {"unreal": "5.8", "claireon": "2.2.0", "protocol": "2025-03-26", "platform": "Windows 11",
     "tested": "live: rig probe, keying, read-back, checks, bake (Third Person mannequin)"},
)
SETUP = "kei unreal setup lists the steps"


def compatibility_lines() -> list[str]:
    out = ["Unreal | Claireon | protocol | platform | tested"]
    for r in COMPATIBILITY:
        out.append(f"{r['unreal']} | {r['claireon']} | {r['protocol']} | {r['platform']} | {r['tested']}")
    return out


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _uproject(project_dir: Path) -> Path | None:
    found = sorted(project_dir.glob("*.uproject"))
    return found[0] if found else None


def _engine_version(assoc: str) -> str:
    """5.8 from "5.8"; a source build writes a GUID, which says nothing about the version."""
    return assoc if assoc and assoc[0].isdigit() else ""


def _plugin_enabled(uproject: dict, name: str) -> bool | None:
    for p in uproject.get("Plugins") or []:
        if isinstance(p, dict) and p.get("Name") == name:
            return bool(p.get("Enabled"))
    return None


def _claireon(project_dir: Path) -> tuple[Path, dict] | None:
    for f in sorted((project_dir / "Plugins").glob("**/Claireon.uplugin")):
        data = _read_json(f)
        if data is not None:
            return f, data
    return None


def _ignored(project_dir: Path) -> bool | None:
    """True when a .gitignore of the project names Content/Kei; None when the project has no .gitignore."""
    f = project_dir / ".gitignore"
    try:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        s = line.strip().lstrip("/").rstrip("/")
        if s.lower() in ("content/kei", "content/kei/*", "content/kei/**"):
            return True
    return False


def probe_server(url: str, timeout: float = 5) -> dict:
    """The handshake and the tool list only. Raises UnrealError when nothing answers."""
    c = Claireon(url, timeout=timeout)
    return c.initialize()


def checks(project_dir: str | Path | None, url: str | None,
           probe: Callable[[str], dict] = probe_server) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    tested_unreal = {r["unreal"] for r in COMPATIBILITY}
    tested_claireon = {r["claireon"] for r in COMPATIBILITY}
    tested_protocol = {r["protocol"] for r in COMPATIBILITY}
    proj = Path(project_dir) if project_dir else None
    if proj is None:
        rows.append((WARN, "project", "no [apps.unreal] project in kei.toml",
                     'set project = "C:/path/to/YourProject" so Kei can read its files and its port'))
    elif (up := _uproject(proj)) is None:
        rows.append((FAIL, "project", f"no .uproject file in {proj}", "point [apps.unreal] project at the folder "
                     "that holds the .uproject file"))
        proj = None
    else:
        data = _read_json(up) or {}
        rows.append((OK, "project", str(up), ""))
        assoc = str(data.get("EngineAssociation") or "")
        ver = _engine_version(assoc)
        if not ver:
            rows.append((WARN, "Unreal version", f"a source build ({assoc or 'no EngineAssociation'})",
                         f"Kei was tested on Unreal {', '.join(sorted(tested_unreal))}; check the engine version by hand"))
        elif ver in tested_unreal:
            rows.append((OK, "Unreal version", ver, ""))
        else:
            rows.append((WARN, "Unreal version", f"{ver}, not tested",
                         f"Kei was tested on Unreal {', '.join(sorted(tested_unreal))}; it may work"))
        cl = _claireon(proj)
        if cl is None:
            rows.append((FAIL, "Claireon", f"not in {proj / 'Plugins'}",
                         "install Claireon in the project's Plugins folder (https://github.com/believer-oss/claireon)"))
        else:
            cver = str(cl[1].get("VersionName") or "")
            if cver in tested_claireon:
                rows.append((OK, "Claireon", cver, ""))
            else:
                rows.append((WARN, "Claireon", f"{cver or 'no version'}, not tested",
                             f"Kei was tested with Claireon {', '.join(sorted(tested_claireon))}; it may work"))
            if _plugin_enabled(data, "Claireon") is False:
                rows.append((FAIL, "Claireon enabled", "turned off in the .uproject",
                             "turn Claireon on (Edit, Plugins), then restart the editor"))
        py = _plugin_enabled(data, "PythonScriptPlugin")
        needed_by_claireon = cl is not None and _plugin_enabled(cl[1], "PythonScriptPlugin")
        if py is False:
            rows.append((FAIL, "Python plugin", "turned off in the .uproject",
                         "enable the Python Editor Script Plugin (Edit, Plugins, Scripting), then restart the editor"))
        elif py or needed_by_claireon:
            rows.append((OK, "Python plugin", "on" + ("" if py else " (Claireon turns it on)"), ""))
        else:
            rows.append((WARN, "Python plugin", "not listed in the .uproject",
                         "enable the Python Editor Script Plugin (Edit, Plugins, Scripting), then restart the editor"))
        ign = _ignored(proj)
        if ign is False:
            rows.append((WARN, "ignore line", "Content/Kei/ is not in .gitignore",
                         "add a line Content/Kei/ to .gitignore, so Kei's working assets stay out of your repository"))
        elif ign:
            rows.append((OK, "ignore line", "Content/Kei/ in .gitignore", ""))
    urls = [u for u in ([url] if url else []) + ([server_url(proj)] if proj else []) if u]
    urls = list(dict.fromkeys(urls))
    if not urls:
        rows.append((FAIL, "port", "no port: the editor has not written Saved/Claireon/MCPServer.json",
                     f"open the editor with -StartMCPServer or click the Claireon button ({SETUP})"))
        return rows
    rows.append((OK, "port", ", ".join(urls), ""))
    for u in urls:
        try:
            info = probe(u)
        except UnrealError as e:
            fix = "" if "-StartMCPServer" in str(e) else f"open the editor with -StartMCPServer ({SETUP})"
            rows.append((FAIL, "editor answers", str(e), fix))
            continue
        rows.append((OK, "editor answers", f"{u}: {info.get('server', 'unknown')}", ""))
        proto = str(info.get("protocol_version") or "")
        rows.append((OK, "protocol", proto, "") if proto in tested_protocol else
                    (WARN, "protocol", f"{proto or 'none'}, not tested",
                     f"Kei was tested on protocol {', '.join(sorted(tested_protocol))}"))
        missing = [t for t in NEEDED_TOOLS if t not in (info.get("tools") or [])]
        rows.append((FAIL, "tools", f"missing {', '.join(missing)}", "update Claireon") if missing else
                    (OK, "tools", ", ".join(NEEDED_TOOLS), ""))
    if sys.platform != "win32":
        rows.append((WARN, "editor memory", "read with lsof and ps (resident memory only)",
                     "the private-memory figure is Windows only"))
    return rows
