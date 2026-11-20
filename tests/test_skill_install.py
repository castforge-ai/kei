"""kei skill install: the skill ships with Kei and installs where the agent reads it."""
import pytest

from kei.skill_install import SkillError, install, source


def test_the_skill_installs_for_claude_and_codex_and_a_changed_copy_is_kept(tmp_path):
    assert (source() / "SKILL.md").is_file()
    dst = install("claude", home=tmp_path)
    assert dst == tmp_path / ".claude" / "skills" / "kei" and (dst / "SKILL.md").is_file()
    assert install("claude", home=tmp_path) == dst, "the same version again: nothing to do"
    (dst / "SKILL.md").write_text("mine", encoding="utf-8")
    with pytest.raises(SkillError, match="--force"):
        install("claude", home=tmp_path)
    install("claude", home=tmp_path, force=True)
    assert (dst / "SKILL.md").read_text(encoding="utf-8") != "mine"
    assert (install("codex", project=True, cwd=tmp_path) / "SKILL.md").is_file()
    assert (tmp_path / ".agents" / "skills" / "kei" / "SKILL.md").is_file()
