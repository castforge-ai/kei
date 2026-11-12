"""The sign-off page's routes. Every state change goes through kei/signoff.py, the same functions kei approve and
kei note call. Nothing here approves on its own: only POST /api/accept, naming the round on screen with every
checklist item ticked, reaches approve_shot()."""
from __future__ import annotations

import base64
import binascii
from pathlib import Path

from kei.checklist import current_checks
from kei.review.drawings import save_drawings
from kei.review.rounds import mark_seen, read_round
from kei.signoff import SignOffError, approve_shot, note_refusal, note_shot, reject_shot, round_ids
from kei.stages import STAGES
from kei.state import load_state

ACTIONS = ("accept", "needs_work", "reject")
DEFAULT_STAGE = "passes"


def _bad(why: str) -> tuple[int, dict]:
    return 400, {"error": why}


def _cards(body) -> list | None:
    cards = (body.get("cards") if isinstance(body, dict) else None) or []
    ok = isinstance(cards, list) and all(
        isinstance(c, dict) and c.get("answer") in ("yes", "no") and isinstance(c.get("check"), str) for c in cards)
    return cards if ok else None


def _text(body, key: str) -> str | None:
    v = body.get(key) if isinstance(body, dict) else None
    return v if isinstance(v, str) else None


class SignOffRoutes:
    """The routes and the file allowlist of one shot's sign-off page. after is the round on screen; before is the
    round shown beside it (a round.json dict), or None."""

    def __init__(self, shot: Path, lessons: Path, after: str, before: dict | None, sharer=None):
        self.shot = Path(shot)
        self.lessons = Path(lessons)
        self.after = after
        self.before = before
        self.sharer = sharer     # the share step: called after approve_shot, never before
        self.routes = {
            "GET /api/mode": lambda req: (200, {"mode": "shot"}),
            "GET /api/shot": self.get_shot,
            "POST /api/accept": self.accept,
            "POST /api/needs-work": self.needs_work,
            "POST /api/reject": self.reject,
            "POST /api/seen": self.seen,
            "POST /api/share/prepare": self.share_prepare,
            "POST /api/share/send": self.share_send,
        }

    # -- files ---------------------------------------------------------------------------------------------------
    def _round_files(self, round_id: str) -> dict[str, Path]:
        frames = self.shot / "review" / round_id / "frames"
        return {f"{round_id}/{p.stem}": p for p in sorted(frames.glob("f*.png"))} if frames.is_dir() else {}

    def files(self) -> dict[str, Path]:
        out = self._round_files(self.after)
        if self.before:
            out.update(self._round_files(self.before["round"]))
        if self.sharer is not None:
            out.update(self.sharer.files())
        return out

    # -- reads ---------------------------------------------------------------------------------------------------
    def get_shot(self, req) -> tuple[int, dict]:
        state = load_state(self.shot)
        waiting = state.status == "needs_approval"
        after = read_round(self.shot, self.after)
        differ = bool(self.before and after and self.before.get("character") != after.get("character"))
        return 200, {
            "shot": self.shot.resolve().name, "status": state.status, "stage": state.stage,
            "after": after, "before": self.before, "characters_differ": differ,
            "checklist": self._checks(state, after), "actions": list(ACTIONS) if waiting else [],
            "checklist_hidden": len(state.sign_off) - sum(len(i["checks"]) for i in self._checks(state, after)),
            "stages": [s.id for s in STAGES], "default_stage": DEFAULT_STAGE,
            "latest_round": (round_ids(self.shot) or [None])[-1],
            "share": self.sharer.panel() if self.sharer is not None else None,
        }

    def _checks(self, state, after: dict | None) -> list[dict]:
        """The critics' checks about the pass on screen, the same request merged; the rest stay in state.json."""
        return current_checks(state.sign_off, (after or {}).get("pass"))

    # -- writes --------------------------------------------------------------------------------------------------
    def _round(self, body) -> str | tuple[int, dict]:
        round_id = _text(body, "round")
        if not round_id:
            return _bad("name the round on screen")
        if round_id not in round_ids(self.shot):
            raise SignOffError(f"there is no review round {round_id} in this shot: reload the page")
        return round_id

    def accept(self, req) -> tuple[int, dict]:
        body = req["body"]
        round_id = self._round(body)
        if isinstance(round_id, tuple):
            return round_id
        ticked = body.get("ticked")
        if not isinstance(ticked, list):
            return _bad("ticked must be the list of checklist items you ticked")
        state = load_state(self.shot)
        items = self._checks(state, read_round(self.shot, round_id))
        left = [i["text"] for i in items if any(c not in ticked for c in i["checks"])]
        if left:
            raise SignOffError("tick every item of the checklist before you accept; not ticked: " + "; ".join(left))
        state = approve_shot(self.shot, round_id)
        out = {"status": state.status}
        if self.sharer is not None:
            out["share"] = self.sharer.on_accept()
        return 200, out

    def _drawings(self, round_id: str, body) -> list[str] | tuple[int, dict]:
        """The page's drawings ({"strokes": [...], "pngs": {"f0003_side": base64}}) saved in the shot."""
        drawings = body.get("drawings") or []
        if not drawings:
            return []
        if not isinstance(drawings, dict) or not isinstance(drawings.get("pngs", {}), dict):
            return _bad("drawings must be an object with strokes and pngs")
        pngs = {}
        for key, data in drawings.get("pngs", {}).items():
            try:
                pngs[key] = base64.b64decode(data, validate=True)
            except (TypeError, ValueError, binascii.Error):
                return _bad(f"the picture {key} is not base64")
        return save_drawings(self.shot, round_id, drawings.get("strokes") or [], pngs)

    def needs_work(self, req) -> tuple[int, dict]:
        body = req["body"]
        round_id = self._round(body)
        if isinstance(round_id, tuple):
            return round_id
        text = _text(body, "text")
        stage = _text(body, "stage") or DEFAULT_STAGE
        if text is None or not text.strip():
            return _bad("say what is wrong: the note needs words")
        cards = _cards(body)
        if cards is None:
            return _bad("cards must be a list of answers: check, and yes or no")
        scope = _text(body, "scope") or "shot"
        if scope not in ("shot", "every"):
            return _bad("scope must be shot or every")
        why = note_refusal(load_state(self.shot), stage)   # refused before a drawing is written
        if why:
            raise SignOffError(why)
        drawings = self._drawings(round_id, body)
        if isinstance(drawings, tuple):
            return drawings
        state, lesson = note_shot(self.shot, text, stage, self.lessons, drawings, cards, scope, round_id)
        return 200, {"status": state.status, "stage": state.stage, "lesson": lesson, "drawings": drawings,
                     "scope": state.history[-1]["scope"]}

    def reject(self, req) -> tuple[int, dict]:
        body = req["body"]
        round_id = self._round(body)
        if isinstance(round_id, tuple):
            return round_id
        reason = _text(body, "reason")
        if reason is None or not reason.strip():
            return _bad("say why: a reject needs a reason")
        cards = _cards(body)
        if cards is None:
            return _bad("cards must be a list of answers: check, and yes or no")
        state = reject_shot(self.shot, reason, bool(body.get("keep_as_lesson")), self.lessons, cards, round_id)
        out = {"status": state.status}
        if self.sharer is not None:
            out["share"] = self.sharer.on_reject()
        return 200, out

    def seen(self, req) -> tuple[int, dict]:
        body = req["body"]
        round_id = self._round(body)
        if isinstance(round_id, tuple):
            return round_id
        loops = body.get("loops")
        if loops is not None and (not isinstance(loops, int) or isinstance(loops, bool) or loops < 0):
            return _bad("loops must be a whole number")
        mark_seen(self.shot, round_id, loops)
        return 200, {"seen": round_id}

    # -- sharing (after Accept only) ------------------------------------------------------------------------------
    def _sharer(self):
        if self.sharer is None:
            raise SignOffError("sharing is not set up for this page")
        return self.sharer

    def share_prepare(self, req) -> tuple[int, dict]:
        lesson = _text(req["body"], "lesson")
        if not lesson:
            return _bad("name the lesson to share")
        return 200, self._sharer().prepare(lesson)

    def share_send(self, req) -> tuple[int, dict]:
        lesson = _text(req["body"], "lesson")
        if not lesson:
            return _bad("name the lesson to share")
        return 200, {"message": self._sharer().send(lesson)}
