"""Critics get the stage's rules as a checklist with the files of their full text, not the whole rule text."""
from kei.book import load_topics
from kei.config import example_config, load_config
from kei.topics import critic_block, stage_block


def test_the_checklist_is_much_shorter_and_names_where_the_full_text_is():
    cfg = load_config(example_config())
    topics = load_topics(cfg.book)
    full = stage_block("blocking", topics, [], None)
    chk = critic_block("blocking", topics, [], None, cfg.book)
    assert len(chk) * 4 < len(full), (len(chk), len(full))
    first = next(t for t in topics if t.rules)
    assert f"{first.name}.md" in chk and "read the ones you judge by" in chk


def test_the_authors_own_lessons_stay_in_full():
    from kei.book import Rule
    lesson = Rule(id="local.1", title="the arms swing too wide", stages=("all",), text="Keep the arms close.")
    chk = critic_block("passes", [], [lesson], None, None)
    assert "Keep the arms close." in chk and "The author's own lessons" in chk
