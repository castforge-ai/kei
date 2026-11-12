"""Plan 6c, Task 3: kei maya feedback <shot>. Maya is stood in for by a fake run_job (it answers the feedback read and
writes empty playblast folders) and a fake host, so no Maya is needed."""
import hashlib
import json
from pathlib import Path

import pytest

from kei.apps import maya_feedback
from kei.cli import main
from kei.state import ShotState, load_state, save_state

KNEE = [{"control": "kei:l_leg_pv_ctl", "attr": "translateX", "frame": 6, "value": 15.0, "offset": 5.0,
         "key": True}]
SENTENCE = "The knee  must read heavier at the contact, not lighter."


class FakeMaya:
    """Stands in for run_job: answers read_feedback_layers with the layers given, and writes empty playblast folders."""

    def __init__(self, layers=None, outside=(), other_rig=()):
        self.layers = {"feedback": KNEE} if layers is None else layers
        self.outside, self.other_rig = list(outside), list(other_rig)
        self.jobs = []

    def __call__(self, mayapy, job, **kw):
        self.jobs.append(job)
        results = []
        for c in job["calls"]:
            if c["tool"] == "read_feedback_layers":
                results.append({"layers": self.layers, "modes": {n: "additive" for n in self.layers},
                                "outside": self.outside, "other_rig": self.other_rig, "units": "cm",
                                "other_pass": getattr(self, "other_pass", []),
                                "unit_per_m": 100.0, "start": c["inputs"]["start"], "end": c["inputs"]["end"]})
            elif c["tool"] == "playblast":
                views = {}
                for v in c["inputs"].get("views") or ["front", "side", "top", "three quarter"]:
                    d = Path(c["inputs"]["folder"]) / v.replace(" ", "_")
                    d.mkdir(parents=True, exist_ok=True)
                    views[v] = {"folder": str(d), "frames": 13}
                results.append({"views": views, "renderer": "maya playblast"})
            else:
                results.append({"layers": list(self.layers), "mute": c["inputs"].get("mute")})
        return {"ok": True, "maya_version": "2027", "results": results}

    def tools(self):
        return [[c["tool"] for c in j["calls"]] for j in self.jobs]


@pytest.fixture
def shot(tmp_path, monkeypatch):
    root = tmp_path / "walk"
    (root / "out_p1").mkdir(parents=True)
    (root / "out_p1" / "shot.json").write_text(json.dumps({"rig": "maya", "frames": 12, "fps": 24, "keys": [
        {"f": 0, "kei:l_leg_pv_ctl.translateX": 10.0}, {"f": 12, "kei:l_leg_pv_ctl.translateX": 10.0}]}))
    (root / "out_p1" / "scene.ma").write_text("//Maya ASCII the pass, with the animator's feedback layer\n")
    (root / "maya").mkdir()
    (root / "maya" / "scene.ma").write_text("//Maya ASCII base\n")
    (root / "rig").mkdir()
    (root / "rig" / "maya_controls.json").write_text(json.dumps(
        {"character": "kei", "namespace": "kei", "unit_per_m": 100.0, "units": "cm", "controls": []}))
    save_state(root, ShotState(stage="deliver", status="needs_approval", request="a walk"))
    fake = FakeMaya()
    monkeypatch.setattr(maya_feedback, "run_job", fake)
    monkeypatch.setattr(maya_feedback, "find_mayapy", lambda *a: (Path("mayapy"), "2027"))
    monkeypatch.setattr(maya_feedback, "view_videos", lambda views, fps, folder: {
        "videos": {}, "side_by_side": None, "loops": None})
    monkeypatch.delenv(maya_feedback.RUN_ENV, raising=False)
    (tmp_path / "kei.toml").write_text('[animator]\ncmd = ["x"]\n\n[[critics]]\nname = "c"\ncmd = ["y"]\n')
    return root, fake, str(tmp_path / "kei.toml")


def _feedback(shot, *more):
    root, _, config = shot
    return main(["maya", "feedback", str(root), "--config", config, *more])


def _waiting_again(root):
    """The next pass was delivered: the shot waits for the author's sign-off again."""
    save_state(root, ShotState(stage="deliver", status="needs_approval", request="a walk",
                               history=load_state(root).history))


def test_no_feedback_layer_gives_a_clear_message_and_records_nothing(shot, capsys):
    root, fake, _ = shot
    fake.layers = {}
    before = load_state(root)
    assert _feedback(shot, "--text", SENTENCE) == 1
    assert "no animation layer named feedback" in capsys.readouterr().out
    assert load_state(root) == before and not (root / "feedback").exists()
    assert fake.tools() == [["read_feedback_layers"]]       # nothing rendered either


def test_the_recorded_note_holds_the_sentence_verbatim_and_the_pose_file(shot, capsys):
    root, fake, _ = shot
    assert _feedback(shot, "--text", SENTENCE) == 0
    out = capsys.readouterr().out
    assert "knee_l bend turns 7 deg outward at f6" in out
    pose = json.loads((root / "feedback" / "1" / "pose.json").read_text())
    assert pose["pass"] == "p1" and pose["rig"] == "kei"
    assert pose["poses"][0] == {"layer": "feedback", **KNEE[0]}
    assert pose["targets"] == [{"control": "kei:l_leg_pv_ctl", "attr": "translateX", "frame": 6, "value": 15.0}]
    note = json.loads((root / "feedback" / "1" / "note.json").read_text())
    assert note["sentence"] == SENTENCE and note["scope"] == "this shot"
    state = load_state(root)
    last = state.history[-1]
    assert last["result"] == "note" and last["misses"] == [SENTENCE] and last["pose"] == "feedback/1/pose.json"
    assert (state.stage, state.status) == ("passes", "running")


def test_the_scope_follows_the_note_model_this_shot_by_default_every_shot_on_request(shot, tmp_path):
    root, _, _ = shot
    lessons = tmp_path / "lessons.local.md"
    assert _feedback(shot, "--text", SENTENCE) == 0
    last = load_state(root).history[-1]
    assert last["lesson"] == "local.1" and last["scope"] == "this shot"
    _waiting_again(root)
    assert _feedback(shot, "--text", SENTENCE, "--every-shot") == 0
    last = load_state(root).history[-1]
    assert last["lesson"] == "local.2" and last["scope"] == "every shot"
    text = lessons.read_text(encoding="utf-8")
    assert "scope: this shot" in text and "scope: every shot" in text and "The knee  must read heavier" in text
    assert "l_leg_pv_ctl" not in text                      # the pose stays in the shot, never in a lesson


def test_the_user_s_scene_is_never_opened_only_a_copy_and_its_bytes_stay(shot):
    root, fake, _ = shot
    user = root / "out_p1" / "scene.ma"
    digest = hashlib.sha256(user.read_bytes()).hexdigest()
    assert _feedback(shot, "--text", SENTENCE) == 0
    assert hashlib.sha256(user.read_bytes()).hexdigest() == digest
    scenes = {Path(j["scene"]).resolve() for j in fake.jobs}
    assert user.resolve() not in scenes and all(not j.get("save") for j in fake.jobs)


def test_before_and_after_are_drawn_on_the_copy_with_the_layer_muted_then_on(shot):
    root, fake, _ = shot
    assert _feedback(shot, "--text", SENTENCE) == 0
    render = fake.jobs[1]["calls"]
    assert [c["tool"] for c in render] == ["set_feedback_mute", "playblast", "set_feedback_mute", "playblast"]
    assert render[0]["inputs"] == {"mute": True, "pass_name": "p1"}
    assert render[2]["inputs"] == {"mute": False, "pass_name": "p1"}
    assert render[1]["inputs"]["folder"].endswith("feedback/1/before")
    assert render[3]["inputs"]["folder"].endswith("feedback/1/after")
    assert render[1]["inputs"].get("views") is None                    # every view: four of them
    assert fake.jobs[1]["scene"] == fake.jobs[0]["scene"]
    pose = json.loads((root / "feedback" / "1" / "pose.json").read_text())
    assert pose["before"] == "feedback/1/before" and pose["after"] == "feedback/1/after"


def test_a_feedback_layer_on_another_rig_is_refused_by_name(shot, capsys):
    root, fake, _ = shot
    fake.layers = {"feedback": []}
    fake.other_rig = [{"layer": "feedback", "control": "kei2:l_leg_pv_ctl", "attr": "translateX"}]
    before = load_state(root)
    assert _feedback(shot, "--text", SENTENCE) == 1
    out = capsys.readouterr().out
    assert "kei2:l_leg_pv_ctl" in out and "layer feedback" in out and "rig kei" in out
    assert load_state(root) == before and not list(root.glob("feedback/*/note.json"))
    assert fake.tools() == [["read_feedback_layers"]]


def test_keys_outside_the_pass_are_reported(shot, capsys):
    root, fake, _ = shot
    fake.outside = [{"layer": "feedback", "control": "kei:c_body_ctl", "attr": "translateY", "frame": 30}]
    assert _feedback(shot, "--text", SENTENCE) == 0
    out = capsys.readouterr().out
    assert "kei:c_body_ctl.translateY at f30" in out and "outside the pass" in out and "not wrapped" in out
    pose = json.loads((root / "feedback" / "1" / "pose.json").read_text())
    assert pose["outside"] == fake.outside


def test_a_second_run_after_an_edit_makes_note_2_and_never_rewrites_note_1(shot):
    root, fake, _ = shot
    assert _feedback(shot, "--text", SENTENCE) == 0
    first = {p.name: p.read_bytes() for p in (root / "feedback" / "1").glob("*.json")}
    _waiting_again(root)
    fake.layers = {"feedback": [{**KNEE[0], "value": 18.0, "offset": 8.0}]}
    assert _feedback(shot, "--text", "Even more bend.") == 0
    assert {p.name: p.read_bytes() for p in (root / "feedback" / "1").glob("*.json")} == first
    assert json.loads((root / "feedback" / "2" / "note.json").read_text())["sentence"] == "Even more bend."
    assert load_state(root).history[-1]["pose"] == "feedback/2/pose.json"


def test_a_shot_not_waiting_for_a_sign_off_is_refused_before_maya_runs(shot, capsys):
    root, fake, _ = shot
    save_state(root, ShotState(stage="passes", status="needs_human", request="a walk"))
    assert _feedback(shot, "--text", SENTENCE) == 1
    assert "not waiting for a sign-off" in capsys.readouterr().out and fake.jobs == []


def test_an_empty_reason_is_refused_and_kei_never_writes_one(shot, capsys, monkeypatch):
    root, fake, _ = shot
    assert _feedback(shot, "--text", "   ") == 1
    assert "one sentence" in capsys.readouterr().out and fake.jobs == []
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    before = load_state(root)
    assert _feedback(shot) == 1
    assert "--text" in capsys.readouterr().out and load_state(root) == before
    assert not list(root.glob("feedback/*/note.json"))


def test_at_a_terminal_kei_asks_for_the_sentence_and_the_scope(shot, monkeypatch, tmp_path):
    root, _, _ = shot
    answers = iter([SENTENCE, "every"])
    asked = []
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": asked.append(prompt) or next(answers))
    assert _feedback(shot) == 0
    assert "one sentence" in asked[0] and "every shot" in asked[1]
    assert load_state(root).history[-1]["misses"] == [SENTENCE]
    assert load_state(root).history[-1]["scope"] == "every shot"


def test_an_empty_answer_at_the_terminal_records_nothing(shot, monkeypatch, capsys):
    root, _, _ = shot
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    before = load_state(root)
    assert _feedback(shot) == 1
    assert load_state(root) == before and not list(root.glob("feedback/*/note.json"))


def test_the_open_session_is_copied_through_its_host_and_read_in_the_background(shot, monkeypatch):
    root, fake, _ = shot
    (root / "maya" / "target.json").write_text(json.dumps({"kind": "open", "pid": 7, "start_time": 1.0}))
    sent = []

    class S:
        pid, port, token = 7, 1, "t"
    monkeypatch.setattr(maya_feedback, "locate", lambda target: S)
    monkeypatch.setattr(maya_feedback, "call_host", lambda port, token, tool, inputs=None, **kw: sent.append(
        (tool, inputs)) or {})
    assert _feedback(shot, "--text", SENTENCE) == 0
    assert [t for t, _ in sent] == ["save_temp_copy"]               # nothing else runs in the user's Maya
    copy = sent[0][1]["path"]
    assert fake.jobs[0]["scene"] == copy and copy.endswith("maya/feedback_copy.ma")


def test_inside_kei_run_the_question_goes_to_the_author_and_kei_answer_records_it(shot, monkeypatch, tmp_path):
    root, _, config = shot
    save_state(root, ShotState(stage="passes", status="running", request="a walk"))
    monkeypatch.setenv(maya_feedback.RUN_ENV, "1")
    assert _feedback(shot) == 0
    q = (root / "QUESTIONS.md").read_text(encoding="utf-8")
    assert "[feedback:1]" in q and "knee_l bend" in q and "one sentence" in q and "--every-shot" in q
    assert not (root / "feedback" / "1" / "note.json").exists()
    monkeypatch.delenv(maya_feedback.RUN_ENV)
    state = load_state(root)
    state.status, state.questions = "needs_answer", [{"from": "animator", "stage": "passes", "text": q}]
    save_state(root, state)
    assert main(["answer", str(root), "--text", SENTENCE, "--every-shot", "--config", config]) == 0
    last = load_state(root).history[-1]
    assert last["result"] == "note" and last["misses"] == [SENTENCE] and last["scope"] == "every shot"
    assert last["pose"] == "feedback/1/pose.json" and load_state(root).history[-2]["result"] == "answer"
    assert json.loads((root / "feedback" / "1" / "note.json").read_text())["sentence"] == SENTENCE
    text = (tmp_path / "lessons.local.md").read_text(encoding="utf-8")
    assert SENTENCE in text and "scope: every shot" in text


def test_every_shot_on_an_answer_to_another_question_is_refused(shot, capsys):
    root, _, config = shot
    save_state(root, ShotState(stage="passes", status="needs_answer", request="a walk",
                               questions=[{"from": "animator", "text": "Is the floor wet?"}]))
    assert main(["answer", str(root), "--text", "yes", "--every-shot", "--config", config]) == 1
    assert "--every-shot" in capsys.readouterr().out


def test_kei_run_tells_its_seats_they_run_inside_a_run(tmp_path, monkeypatch):
    import os
    from kei.seats import FakeSeat, SeatResult
    from test_conductor import CFG, run_shot, shot as new_shot
    monkeypatch.delenv(maya_feedback.RUN_ENV, raising=False)
    seen = []
    run_shot(new_shot(tmp_path), "a walk", CFG, animator=FakeSeat("fake", lambda p, r: seen.append(
        os.environ.get(maya_feedback.RUN_ENV)) or SeatResult(1, "stop")))
    assert seen and set(seen) == {"1"} and maya_feedback.RUN_ENV not in os.environ


def _answer_in_run(shot, monkeypatch, *flags):
    """kei maya feedback inside kei run asks; the author answers; the shot later reaches delivery and is approved."""
    from kei.signoff import approve_shot
    root, _, config = shot
    save_state(root, ShotState(stage="passes", status="running", request="a walk"))
    monkeypatch.setenv(maya_feedback.RUN_ENV, "1")
    assert _feedback(shot) == 0
    monkeypatch.delenv(maya_feedback.RUN_ENV)
    q = (root / "QUESTIONS.md").read_text(encoding="utf-8")
    state = load_state(root)
    state.status, state.questions = "needs_answer", [{"from": "animator", "stage": "passes", "text": q}]
    save_state(root, state)
    assert main(["answer", str(root), "--text", SENTENCE, *flags, "--config", config]) == 0
    state = load_state(root)
    state.stage, state.status = "deliver", "needs_approval"
    save_state(root, state)
    approve_shot(root)
    return root


def test_an_every_shot_feedback_answer_is_shared_like_a_kei_note_rule_and_carries_no_pose(shot, monkeypatch,
                                                                                          tmp_path):
    from kei.share import _lesson_md, shareable
    root = _answer_in_run(shot, monkeypatch, "--every-shot")
    note = next(h for h in load_state(root).history if h.get("result") == "note")
    assert note["scope"] == "every shot" and note["misses"] == [SENTENCE] and note["stage"] == "passes"
    assert shareable(root) == [note["lesson"]]
    md, _ = _lesson_md(note["lesson"], tmp_path / "lessons.local.md")
    assert SENTENCE in md
    assert "l_leg_pv_ctl" not in md and "pose" not in md and "feedback/" not in md


def test_a_this_shot_feedback_answer_is_never_shared(shot, monkeypatch):
    from kei.share import shareable
    root = _answer_in_run(shot, monkeypatch)
    assert shareable(root) == []


def test_the_read_names_the_pass_and_an_older_pass_s_layer_is_reported_not_read(shot, capsys):
    root, fake, _ = shot
    fake.other_pass = [{"layer": "feedback_p0", "pass": "p0"}]
    assert _feedback(shot, "--text", SENTENCE) == 0
    assert fake.jobs[0]["calls"][0]["inputs"]["pass_name"] == "p1"
    assert fake.jobs[1]["calls"][0]["inputs"] == {"mute": True, "pass_name": "p1"}
    assert "feedback_p0 belongs to pass p0, not read" in capsys.readouterr().out


def test_an_empty_kei_made_layer_gives_the_no_correction_message(shot, capsys):
    root, fake, _ = shot
    fake.layers = {"feedback_p1": []}
    assert _feedback(shot, "--text", SENTENCE) == 1
    assert "no correction" in capsys.readouterr().out
