"""Notes from several critics: one note per fault, and opposite notes become a question or the primary's stands."""
from kei.merge_notes import merge


def test_the_same_fault_from_two_critics_is_one_note_naming_both():
    out, q = merge(["critic a: f12-18 the left foot slides at the contact",
                    "critic b: frames 14 to 16: the left foot skates on the ground", "critic b: f40 the head pops"])
    assert out == ["critic a: f12-18 the left foot slides at the contact (critic b said the same)",
                   "critic b: f40 the head pops"] and q == []


def test_opposite_notes_become_a_question_for_the_author():
    out, q = merge(["critic a: f20-30 the arm swing should be faster", "critic b: f22-28 make the arm slower here"])
    assert out == [] and len(q) == 1 and "disagree" in q[0]["text"] and "faster" in q[0]["text"]


def test_with_a_primary_critic_its_note_stands():
    out, q = merge(["critic a: f20-30 the arm swing should be faster", "critic b: f22-28 make the arm slower here"],
                   primary="b")
    assert out == ["critic b: f22-28 make the arm slower here (critic a asked the opposite; the primary critic's "
                   "note stands)"] and q == []


def test_notes_on_other_frames_parts_or_from_one_critic_stay_apart():
    notes = ["critic a: f10 the head tilts late", "critic b: f50 the head tilts late", "critic a: f10 the hand drifts",
             "critic a: f10 the head is too high", "the stage has no plan sheet"]
    assert merge(notes) == (notes, [])
