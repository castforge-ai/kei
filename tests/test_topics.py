import pytest

from kei.book import BookError, load_topics

ARCS = """# Arcs

kind: principle

### ARC1. Curves by default
stages: blocking

Text.
"""
WALKS = """# Locomotion

kind: subject

### LOC1. Walks
stages: blocking, passes

Text.
"""


def book(tmp_path, **files):
    d = tmp_path / "book"
    d.mkdir()
    for name, text in files.items():
        (d / f"{name}.md").write_text(text, encoding="utf-8")
    return d


def test_a_folder_gives_one_topic_per_file(tmp_path):
    topics = load_topics(book(tmp_path, arcs=ARCS, locomotion=WALKS))
    assert [(t.name, t.kind, t.title) for t in topics] == [("arcs", "principle", "Arcs"),
                                                           ("locomotion", "subject", "Locomotion")]
    assert [r.id for r in topics[1].rules] == ["LOC1"]


def test_a_single_file_is_one_principle_topic(tmp_path):
    p = tmp_path / "rules.md"
    p.write_text(ARCS.replace("kind: principle\n", ""), encoding="utf-8")
    topics = load_topics(p)
    assert [(t.name, t.kind) for t in topics] == [("rules", "principle")]


def test_missing_kind_is_refused(tmp_path):
    with pytest.raises(BookError) as e:
        load_topics(book(tmp_path, arcs=ARCS.replace("kind: principle\n", "")))
    assert "arcs.md" in str(e.value) and "kind:" in str(e.value)


def test_unknown_kind_is_refused(tmp_path):
    with pytest.raises(BookError) as e:
        load_topics(book(tmp_path, arcs=ARCS.replace("principle", "princple")))
    assert "princple" in str(e.value)


def test_duplicate_id_across_topics_is_refused(tmp_path):
    with pytest.raises(BookError) as e:
        load_topics(book(tmp_path, arcs=ARCS, locomotion=WALKS.replace("LOC1", "ARC1")))
    assert "ARC1" in str(e.value)


def test_an_empty_folder_is_refused(tmp_path):
    with pytest.raises(BookError):
        load_topics(book(tmp_path))
