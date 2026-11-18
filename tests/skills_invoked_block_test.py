#!/usr/bin/env python3
"""Unit tests for the generated skills-invoked telemetry block in SKILL.md.

Every skill tells the agent to prefix its `databricks` CLI calls with
DATABRICKS_SKILLS_INVOKED=<skills>. These tests pin where the block goes, that
regeneration is idempotent, and that validate catches a missing or stale block.
Stdlib-only; run with:
  python3 -m unittest discover -s tests -p "*_test.py"
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("skills", _REPO / "scripts" / "skills.py")
assert _spec is not None
assert _spec.loader is not None
skills = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skills)

FRONTMATTER = "---\nname: databricks-jobs\ndescription: Jobs.\n---\n"


def _make_skill(root: Path, name: str, body: str) -> Path:
    path = root / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(FRONTMATTER.replace("databricks-jobs", name) + body)
    return path


class RenderBlockTest(unittest.TestCase):
    def test_names_the_skill_and_env_var(self):
        block = skills.render_block("databricks-jobs")
        self.assertTrue(block.startswith(skills.BLOCK_START))
        self.assertTrue(block.endswith(skills.BLOCK_END))
        self.assertIn("including `databricks-jobs`", block)
        self.assertIn(
            "DATABRICKS_SKILLS_INVOKED=databricks-core,databricks-jobs databricks current-user me",
            block,
        )
        # The CLI has no flag for this; only the env var exists.
        self.assertNotIn("--skills-invoked", block)
        # The CLI drops names with a colon, so agents must send the bare name.
        self.assertIn("bare skill names (never `plugin:name`)", block)
        self.assertNotIn("X-Databricks-Skills-Invoked", block)

    def test_core_example_is_not_duplicated(self):
        block = skills.render_block("databricks-core")
        self.assertIn("DATABRICKS_SKILLS_INVOKED=databricks-core databricks", block)
        self.assertNotIn("databricks-core,databricks-core", block)


class ApplyBlockTest(unittest.TestCase):
    def test_inserted_after_h1(self):
        text = FRONTMATTER + "\n# Jobs\n\nBody.\n"
        out = skills.apply_block(text, "databricks-jobs")
        self.assertTrue(out.startswith(FRONTMATTER + "\n# Jobs\n\n" + skills.BLOCK_START))
        self.assertTrue(out.endswith(skills.BLOCK_END + "\n\nBody.\n"))

    def test_inserted_after_frontmatter_without_h1(self):
        text = FRONTMATTER + "\n> Note.\n"
        out = skills.apply_block(text, "databricks-jobs")
        self.assertTrue(out.startswith(FRONTMATTER + "\n" + skills.BLOCK_START))
        self.assertTrue(out.endswith(skills.BLOCK_END + "\n\n> Note.\n"))

    def test_idempotent(self):
        once = skills.apply_block(FRONTMATTER + "\n# Jobs\n\nBody.\n", "databricks-jobs")
        self.assertEqual(skills.apply_block(once, "databricks-jobs"), once)

    def test_stale_block_is_replaced(self):
        fresh = skills.apply_block(FRONTMATTER + "\n# Jobs\n\nBody.\n", "databricks-jobs")
        stale = fresh.replace("including `databricks-jobs`", "including `old-text`")
        self.assertEqual(skills.apply_block(stale, "databricks-jobs"), fresh)

    def test_unterminated_block_raises(self):
        text = FRONTMATTER + "\n# Jobs\n\n" + skills.BLOCK_START + "\nhalf\n"
        with self.assertRaises(ValueError):
            skills.apply_block(text, "databricks-jobs")


class EnsureAndCheckTest(unittest.TestCase):
    def test_repo_is_canonical(self):
        self.assertEqual(skills.check_skills_invoked_block(_REPO), [])

    def test_missing_then_ensure_then_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_skill(root, "databricks-jobs", "\n# Jobs\n\nBody.\n")
            errors = skills.check_skills_invoked_block(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("Missing", errors[0])

            self.assertEqual(skills.ensure_skills_invoked_block(root), 1)
            self.assertEqual(skills.check_skills_invoked_block(root), [])
            self.assertEqual(skills.ensure_skills_invoked_block(root), 0)

    def test_stale_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = _make_skill(root, "databricks-jobs", "\n# Jobs\n\nBody.\n")
            skills.ensure_skills_invoked_block(root)
            path.write_text(path.read_text().replace("databricks-jobs`", "someone-else`"))
            errors = skills.check_skills_invoked_block(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("Stale", errors[0])


if __name__ == "__main__":
    unittest.main()
