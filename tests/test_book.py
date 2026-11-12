import pytest

from kei.book import BUNDLED_BOOK, BookError, Rule, load_rules, parse_book, rules_block, rules_for
from kei.stages import STAGES

BOOK = """# A test book

Text before the first rule is a preamble.

### W1. Plan before the first key
stages: plan, blocking

No key goes in before the plan sheet exists.
It holds every key pose.

### W2. Judge by eye
stages: all

Numbers point where to look.
"""


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_parses_rules_and_skips_the_preamble():
    rules = parse_book(BOOK, "book.md")
    assert [r.id for r in rules] == ["W1", "W2"]
    assert rules[0] == Rule("W1", "Plan before the first key", ("plan", "blocking"),
                            "No key goes in before the plan sheet exists.\nIt holds every key pose.")
    assert rules[1].stages == ("all",)


def test_all_reaches_every_stage():
    rules = parse_book(BOOK, "book.md")
    for s in STAGES:
        assert "W2" in [r.id for r in rules_for(rules, s.id)]
    assert [r.id for r in rules_for(rules, "brief")] == ["W2"]
    assert [r.id for r in rules_for(rules, "plan")] == ["W1", "W2"]


def test_unknown_stage_is_refused():
    with pytest.raises(BookError) as e:
        parse_book(BOOK.replace("plan, blocking", "plan, bloking"), "book.md")
    assert "W1" in str(e.value) and "bloking" in str(e.value) and str(e.value).startswith("book.md")


def test_missing_stages_line_is_refused():
    with pytest.raises(BookError) as e:
        parse_book(BOOK.replace("stages: plan, blocking\n", ""), "book.md")
    assert "W1" in str(e.value) and "stages:" in str(e.value)


def test_bad_heading_is_refused():
    with pytest.raises(BookError) as e:
        parse_book(BOOK.replace("### W1. Plan", "### Plan"), "book.md")
    assert "### Plan" in str(e.value)


def test_duplicate_id_is_refused(tmp_path):
    a = write(tmp_path / "a.md", BOOK)
    b = write(tmp_path / "b.md", "### W2. Again\nstages: plan\n\ntext\n")
    with pytest.raises(BookError) as e:
        load_rules([a, b])
    assert "W2" in str(e.value)


def test_missing_local_file_is_skipped(tmp_path):
    a = write(tmp_path / "a.md", BOOK)
    assert [r.id for r in load_rules([a, tmp_path / "nope.md"])] == ["W1", "W2"]


def test_rules_block_names_each_id():
    block = rules_block(parse_book(BOOK, "book.md"))
    assert block.startswith("Rules for this stage:\n\n")
    assert "### W1. Plan before the first key\nNo key goes in" in block
    assert "### W2. Judge by eye" in block
    assert rules_block([]) == ""


def test_bundled_book_parses():
    from kei.book import load_topics
    rules = [r for t in load_topics(BUNDLED_BOOK) for r in t.rules]
    for sid in ("plan", "blocking", "passes"):
        assert rules_for(rules, sid), sid


def test_book_saved_with_a_bom_keeps_its_first_rule(tmp_path):
    p = tmp_path / "bom.md"
    p.write_bytes(b"\xef\xbb\xbf" + "### X1. First\nstages: plan\n\nA.\n\n### X2. Second\nstages: plan\n\nB.\n".encode())
    assert [r.id for r in load_rules([p])] == ["X1", "X2"]


def test_lessons_file_is_never_committed():
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    out = subprocess.run(["git", "check-ignore", "lessons.local.md"], cwd=root, capture_output=True, text=True)
    assert out.stdout.strip() == "lessons.local.md"
