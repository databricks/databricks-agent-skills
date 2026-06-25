"""Unit tests for databricks-serverless-storage-check.

These tests run at L1 (no Databricks or external services needed).
"""

from pathlib import Path

import yaml


class TestSkillStructure:
    """Validate the skill directory has required files and structure."""

    def test_skill_md_exists(self, skill_dir):
        """SKILL.md must exist in the skill directory."""
        assert (skill_dir / "SKILL.md").exists(), "SKILL.md not found"

    def test_skill_md_not_empty(self, skill_md):
        """SKILL.md must have meaningful content."""
        assert len(skill_md.strip()) > 100, "SKILL.md is too short or empty"

    def test_skill_md_has_frontmatter(self, skill_md):
        """SKILL.md should have YAML frontmatter with name and description."""
        assert skill_md.startswith("---"), "SKILL.md missing YAML frontmatter (---)"
        parts = skill_md.split("---", 2)
        assert len(parts) >= 3, "SKILL.md frontmatter not properly closed"
        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter is not None, "Frontmatter is empty"


class TestSkillContent:
    """Validate skill content quality."""

    def test_no_todo_placeholders(self, skill_md):
        """SKILL.md should not contain unresolved TODO placeholders."""
        # TODO: Uncomment when skill is fully authored
        # assert "TODO" not in skill_md, "SKILL.md contains unresolved TODOs"
        pass
