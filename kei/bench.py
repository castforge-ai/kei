"""kei bench: the same brief run by several seats, compared blind.

  kei bench <bench folder>

The bench folder holds bench.toml:

  brief = "a 35 kg crate lifted from the floor and set on a table"
  answers = "answers.toml"          # optional: plain questions answered from this file, as kei run --answers
  [[seat]]
  name = "claude"
  config = "kei.claude.toml"        # the kei.toml of that seat, relative to the bench folder
  [[seat]]
  name = "gpt"
  config = "kei.gpt.toml"

For each seat, Kei runs the brief in <bench>/<seat>/ with the seat's config and the fixed answers (a shot already
done is not run again), then checks the hard gates of its final pass, renders it through one camera for every seat
(the first seat's plan camera, else the fixed four views), and copies each video into <bench>/blind/ as A, B, C...
in a random order. The key (which letter is which seat) is written to <bench>/blind/key.json and only its hash is
printed, so nobody judging reads it by accident. RUNS.md gets a row per seat: status, tries, send-backs, hours,
tokens and the scripts the seat wrote.
"""
from __future__ import annotations

import hashlib
import json
import random
import shutil
import string
import tomllib
from pathlib import Path


class BenchError(ValueError):
    pass


def read_bench(folder: Path) -> dict:
    path = Path(folder) / "bench.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise BenchError(f"cannot read {path}: {e}") from e
    seats = data.get("seat")
    if not isinstance(data.get("brief"), str) or not data["brief"].strip():
        raise BenchError(f"{path}: brief is the request every seat animates, in plain words")
    if not isinstance(seats, list) or len(seats) < 2:
        raise BenchError(f"{path}: a bench compares two [[seat]] tables or more")
    names = [s.get("name") for s in seats]
    if len(set(names)) != len(names) or not all(isinstance(n, str) and n for n in names):
        raise BenchError(f"{path}: each seat needs its own name")
    for s in seats:
        if not (Path(folder) / str(s.get("config", ""))).is_file():
            raise BenchError(f"{path}: seat {s['name']}: config {s.get('config')!r} is not a file in the bench folder")
    return data


def _final_pass(shot: Path) -> str | None:
    nums = [int(p.name[5:]) for p in shot.glob("out_p*") if p.name[5:].isdigit() and (p / "shot.json").is_file()]
    return f"p{max(nums)}" if nums else ("blocking" if (shot / "out_blocking" / "shot.json").is_file() else None)


def _row(name: str, shot: Path, hard_misses: list[str]) -> dict:
    from kei.seats import run_totals
    from kei.state import load_state
    st = load_state(shot)
    tot = run_totals(shot)
    scripts = sum(h.get("scripts", 0) for h in st.history)
    return {"seat": name, "status": st.status, "tries": sum(1 for h in st.history if h.get("result") in
                                                            ("fail", "send_back", "seat_error", "pass")),
            "send_backs": sum(1 for h in st.history if h.get("result") == "send_back"),
            "hours": round(tot["seconds"] / 3600, 2), "tokens": tot["tokens"], "scripts": scripts,
            "final_pass": _final_pass(shot), "hard_gate_misses": hard_misses}


def run_bench(folder: Path, run=None, render=None, rng: random.Random | None = None) -> dict:
    """Run every seat, check, render, and write blind/ and RUNS.md. run(shot, brief, config_path, answers_path) and
    render(shot, pass) -> video path are the kei run and kei render steps (replaced in tests)."""
    from kei.gates.pipeline import check
    folder = Path(folder)
    bench = read_bench(folder)
    answers = folder / bench["answers"] if bench.get("answers") else None
    rows, videos = [], {}
    for seat in bench["seat"]:
        shot = folder / seat["name"]
        shot.mkdir(exist_ok=True)
        run(shot, bench["brief"], folder / seat["config"], answers)
        hard = [m for m in check(str(shot))[0] if m.split(" ")[0] in ("P9", "P10")]
        rows.append(_row(seat["name"], shot, hard))
        final = rows[-1]["final_pass"]
        if final is not None:
            videos[seat["name"]] = render(shot, final)
    blind = folder / "blind"
    if blind.exists():
        shutil.rmtree(blind)
    blind.mkdir()
    names = list(videos)
    (rng or random.SystemRandom()).shuffle(names)
    key = {}
    for letter, name in zip(string.ascii_uppercase, names):
        src = Path(videos[name])
        shutil.copy2(src, blind / f"{letter}{src.suffix}")
        key[letter] = name
    key_text = json.dumps(key, sort_keys=True)
    (blind / "key.json").write_text(key_text, encoding="utf-8")
    seal = hashlib.sha256(key_text.encode("utf-8")).hexdigest()
    lines = ["# Bench runs", "", f"Brief: {bench['brief']}", "", f"Blind key sealed: sha256 {seal}", "",
             "| seat | status | tries | send-backs | hours | tokens in/out | scripts | final pass | hard gates |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        tok = r["tokens"]
        tin = tok.get("input", 0) + tok.get("cache_read", 0) + tok.get("cache_write", 0)
        lines.append(f"| {r['seat']} | {r['status']} | {r['tries']} | {r['send_backs']} | {r['hours']} | "
                     f"{tin:,}/{tok.get('output', 0):,} | {r['scripts']} | {r['final_pass'] or '-'} | "
                     f"{'clean' if not r['hard_gate_misses'] else str(len(r['hard_gate_misses'])) + ' open'} |")
    (folder / "RUNS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"rows": rows, "seal": seal, "blind": sorted(p.name for p in blind.iterdir() if p.name != "key.json")}
