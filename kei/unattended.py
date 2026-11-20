"""Unattended runs: answer a shot's questions from a file, so a run needs nobody at the keyboard.

  kei run <shot> --answers answers.toml

The file (TOML):

  default = "Take your recommended option and go on; do not stop to ask."   # optional
  [[answer]]
  match = "(?i)camera|lens"           # a regular expression, searched in the question's text
  text = "Lock the camera on the side view, 50 mm."

When the shot stops with questions, each question gets the text of the first [[answer]] whose match finds it, else
the default. Kei records the answers as the author's answers, marked as read from the file, and runs on. A question
no rule and no default covers stops the run as before, and so does a choice Kei asks about (where to animate in Maya
or Unreal, an imported character's fit): those wait for a person. A run answers at most MAX_ANSWERS rounds.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

MAX_ANSWERS = 20


class AnswersError(ValueError):
    pass


def load_answers(path: Path) -> dict:
    p = Path(path)
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise AnswersError(f"no answers file {p}") from None
    except tomllib.TOMLDecodeError as e:
        raise AnswersError(f"{p}: {e}") from None
    default = data.get("default")
    if default is not None and (not isinstance(default, str) or not default.strip()):
        raise AnswersError(f"{p}: default is the text of an answer")
    rules = []
    for i, r in enumerate(data.get("answer", []) or []):
        if not (isinstance(r, dict) and isinstance(r.get("match"), str) and isinstance(r.get("text"), str)
                and r["text"].strip()):
            raise AnswersError(f"{p}: answer {i + 1} needs match and text")
        try:
            rules.append((re.compile(r["match"]), r["text"].strip()))
        except re.error as e:
            raise AnswersError(f"{p}: answer {i + 1}: match is not a regular expression ({e})") from None
    if default is None and not rules:
        raise AnswersError(f"{p}: give a default or at least one [[answer]]")
    return {"path": str(p), "default": default.strip() if default else None, "rules": rules}


def pick(answers: dict, question: str) -> str | None:
    for rx, text in answers["rules"]:
        if rx.search(question):
            return text
    return answers["default"]


def answer_from_file(shot: Path, state, answers: dict, now) -> bool:
    """Answer the questions the shot stopped on from the file. False (nothing changed) when a question is a choice
    only a person makes, or when no rule and no default covers one."""
    from kei.state import save_state
    qs = list(state.questions)
    q_file = Path(shot) / "QUESTIONS.md"
    if not qs and q_file.is_file():
        qs = [{"text": q_file.read_text(encoding="utf-8").strip()}]
    if not qs or any(q.get("kind") for q in qs):
        return False
    texts = [pick(answers, q.get("text", "")) for q in qs]
    if any(t is None for t in texts):
        return False
    lines = texts[0] if len(texts) == 1 else "\n".join(f"{i}. {t}" for i, t in enumerate(texts, 1))
    asked = "\n".join(q.get("text", "") for q in qs)
    state.answers.append({"stage": state.stage, "question": asked, "answer": lines, "at": now(),
                          "from": f"answers file {answers['path']}"})
    state.history.append({"stage": state.stage, "attempt": state.attempts, "result": "answer", "misses": [],
                          "from": "answers file", "at": now()})
    state.questions = []
    state.status = "running"
    if q_file.exists():
        q_file.unlink()
    save_state(Path(shot), state)
    return True
