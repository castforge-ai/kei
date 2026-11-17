"""The book that ships with Kei is the folder kei/book: 25 topic files, 924 rules, read by the real loader."""
import re

from kei.book import ALL, BUNDLED_BOOK, load_topics
from kei.config import Config, SeatSpec
from kei.conductor import stage_rules
from kei.stages import STAGES
from kei.topics import stage_block, subject_index

STAGE_IDS = {s.id for s in STAGES}


def files():
    return sorted(BUNDLED_BOOK.glob("*.md"))


def test_the_default_book_is_the_kei_book_folder():
    assert BUNDLED_BOOK.is_dir() and BUNDLED_BOOK.name == "book" and BUNDLED_BOOK.parent.name == "kei"
    assert Config(animator=SeatSpec("a", ["x"])).book == BUNDLED_BOOK
    assert not (BUNDLED_BOOK / "rules.md").exists()


def test_the_shipped_book_is_25_topics_with_924_unique_rule_ids():
    topics = load_topics(BUNDLED_BOOK)
    assert len(topics) == 25 and len(files()) == 25
    ids = [r.id for t in topics for r in t.rules]
    assert len(ids) == 924 and len(set(ids)) == 924


def test_every_rule_has_a_valid_stages_line_right_under_its_heading():
    for f in files():
        lines = f.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.startswith("### "):
                assert re.match(r"^### \S+\. .+$", line), f"{f.name}:{i + 1}"
                assert lines[i + 1].startswith("stages:"), f"{f.name}:{i + 2}"
                stages = [s.strip() for s in lines[i + 1][len("stages:"):].split(",") if s.strip()]
                assert stages and all(s == ALL or s in STAGE_IDS for s in stages), f"{f.name}:{i + 2}"
    for t in load_topics(BUNDLED_BOOK):
        for r in t.rules:
            assert r.stages and all(s == ALL or s in STAGE_IDS for s in r.stages), r.id


def test_no_em_dash_in_any_shipped_topic():
    for f in files():
        assert chr(0x2014) not in f.read_text(encoding="utf-8"), f.name


def test_principle_and_subject_kinds_are_as_in_the_files():
    topics = {t.name: t for t in load_topics(BUNDLED_BOOK)}
    for f in files():
        kinds = [ln[5:].strip() for ln in f.read_text(encoding="utf-8").split("\n### ", 1)[0].splitlines()
                 if ln.startswith("kind:")]
        assert len(kinds) == 1 and kinds[0] in ("principle", "subject"), f.name
        assert topics[f.stem].kind == kinds[0], f.name
    kinds = [t.kind for t in topics.values()]
    assert (kinds.count("principle"), kinds.count("subject")) == (15, 10)


def default_config(tmp_path):
    return Config(animator=SeatSpec("a", ["x"]), lessons=tmp_path / "lessons.local.md")


def test_the_default_max_chars_admits_every_stage_with_its_principles(tmp_path):
    config = default_config(tmp_path)
    topics, lessons = stage_rules(config)          # what a run checks at its start; raises when over the limit
    for s in STAGES:
        assert len(stage_block(s.id, topics, lessons, [])) <= config.max_rule_chars, s.id


def test_the_default_max_chars_admits_every_stage_with_every_subject(tmp_path):
    config = default_config(tmp_path)              # measured: blocking with every subject is the largest stage
    assert config.max_rule_chars == 450000
    topics, lessons = stage_rules(config)
    for s in STAGES:
        block = stage_block(s.id, topics, lessons, None)
        if s.id == "brief":
            block = "\n\n".join(b for b in (block, subject_index(topics)) if b)
        assert len(block) <= config.max_rule_chars, (s.id, len(block))
