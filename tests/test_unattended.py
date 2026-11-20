"""kei run --answers: an unattended run answers its plain questions from a file and goes on."""
import pytest

from kei.conductor import run_shot
from kei.seats import FakeSeat
from kei.state import load_state
from kei.unattended import AnswersError, answer_from_file, load_answers, pick
from shotkit import write
from test_conductor import CFG, Recorder, shot
from test_questions import no_review

FILE = '''default = "Take your recommended option and go on."
[[answer]]
match = "(?i)rig"
text = "Kei's own rig."
'''


def _answers(tmp_path, text=FILE):
    p = tmp_path / "answers.toml"
    p.write_text(text, encoding="utf-8")
    return load_answers(p)


def test_the_first_matching_rule_answers_else_the_default(tmp_path):
    a = _answers(tmp_path)
    assert pick(a, "Which rig should I use?") == "Kei's own rig."
    assert pick(a, "How long is the hold?") == "Take your recommended option and go on."


def test_a_file_with_nothing_to_answer_or_a_bad_pattern_is_refused(tmp_path):
    with pytest.raises(AnswersError, match="default"):
        _answers(tmp_path, "# empty\n")
    with pytest.raises(AnswersError, match="regular expression"):
        _answers(tmp_path, '[[answer]]\nmatch = "("\ntext = "x"\n')


def _asked(tmp_path, question):
    root = shot(tmp_path)

    def fault(sid, n, r):
        if sid == "rig" and n == 1:
            write(r, "QUESTIONS.md", question + "\n")
        return False
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder(fault)), review=no_review)
    assert state.status == "needs_answer"
    return root, state


def test_a_plain_question_is_answered_from_the_file_and_marked_so(tmp_path):
    root, state = _asked(tmp_path, "Which rig?")
    assert answer_from_file(root, state, _answers(tmp_path), lambda: "2026-11-19T00:00:00Z")
    s = load_state(root)
    assert s.status == "running" and s.answers[-1]["answer"] == "Kei's own rig."
    assert s.answers[-1]["from"].startswith("answers file")
    assert not (root / "QUESTIONS.md").exists()
    state = run_shot(root, "a box falls", CFG, animator=FakeSeat("fake", Recorder()), review=no_review)
    assert state.stage != "rig"


def test_a_choice_only_a_person_makes_is_left_for_a_person(tmp_path):
    root, state = _asked(tmp_path, "Which rig?")
    state.questions = [{"text": "Where do I animate?", "kind": "unreal_target", "choices": []}]
    assert not answer_from_file(root, state, _answers(tmp_path), lambda: "now")
    assert load_state(root).status == "needs_answer"
