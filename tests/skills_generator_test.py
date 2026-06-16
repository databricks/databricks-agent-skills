#!/usr/bin/env python3
"""Unit tests for the plugin.meta.json -> plugin manifests generator.

P1 made plugin.meta.json the single source of truth and generates every
target's plugin.json + marketplace.json from it, with a CI drift guard. These
tests pin that machinery (byte-reproducible generation, drift detection, skill
coverage) so a future refactor of a build_* renderer can't silently change a
target's output. Stdlib-only; run with:
  python3 -m unittest discover -s tests -p "*_test.py"
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("skills", _REPO / "scripts" / "skills.py")
skills = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(skills)


class GeneratedPluginsTest(unittest.TestCase):
    def setUp(self):
        self.meta = skills.load_meta(_REPO)

    def test_repo_is_canonical(self):
        # The committed plugin manifests must equal what the generator produces
        # from plugin.meta.json, and every skill must be covered. This pins the
        # committed state even if the validate wiring changes.
        self.assertEqual(skills.check_generated_plugins(_REPO, self.meta), [])
        self.assertEqual(skills.check_meta_skill_coverage(_REPO, self.meta), [])

    def test_generate_roundtrips_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            written = skills.generate_plugins(root, self.meta)
            self.assertEqual(written, 7)
            self.assertEqual(skills.check_generated_plugins(root, self.meta), [])

    def test_content_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills.generate_plugins(root, self.meta)
            target = root / ".claude-plugin" / "plugin.json"
            data = json.loads(target.read_text())
            data["version"] = "9.9.9"
            target.write_text(json.dumps(data, indent=2) + "\n")
            errors = skills.check_generated_plugins(root, self.meta)
            self.assertTrue(
                any("out of date" in e and ".claude-plugin/plugin.json" in e for e in errors),
                errors,
            )

    def test_formatting_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills.generate_plugins(root, self.meta)
            target = root / ".codex-plugin" / "plugin.json"
            # Same content, non-canonical formatting (4-space + sorted keys).
            data = json.loads(target.read_text())
            target.write_text(json.dumps(data, indent=4, sort_keys=True) + "\n")
            errors = skills.check_generated_plugins(root, self.meta)
            self.assertTrue(
                any("canonical generated form" in e for e in errors), errors
            )

    def test_missing_file_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills.generate_plugins(root, self.meta)
            (root / ".cursor-plugin" / "plugin.json").unlink()
            errors = skills.check_generated_plugins(root, self.meta)
            self.assertTrue(
                any("Missing generated file .cursor-plugin/plugin.json" in e for e in errors),
                errors,
            )

    def test_keyword_composition(self):
        kw = skills.build_keywords(self.meta)
        skill_kws = [s["keyword"] for s in self.meta["skills"].values()]
        expected = [
            *self.meta["keywords_lead"],
            *skill_kws,
            *self.meta["keywords_tail"],
        ]
        self.assertEqual(kw, expected)
        # No duplicate keywords (lead/tail must not collide with a skill keyword).
        self.assertEqual(len(kw), len(set(kw)))

    def test_all_targets_share_one_version(self):
        versions = {
            build(self.meta)["version"]
            for build in (
                skills.build_claude_plugin,
                skills.build_codex_plugin,
                skills.build_copilot_plugin,
                skills.build_cursor_plugin,
            )
        }
        self.assertEqual(versions, {self.meta["version"]})

    def test_name_is_databricks_everywhere(self):
        # The plugin name keys Cursor/Claude installs; the generator must never
        # emit anything but "databricks".
        for build in (
            skills.build_claude_plugin,
            skills.build_codex_plugin,
            skills.build_copilot_plugin,
            skills.build_cursor_plugin,
        ):
            self.assertEqual(build(self.meta)["name"], "databricks")

    def test_claude_plugin_has_no_hooks_key(self):
        # hooks/hooks.json is auto-loaded by Claude Code; declaring it double-loads.
        self.assertNotIn("hooks", skills.build_claude_plugin(self.meta))


class MetaSkillCoverageTest(unittest.TestCase):
    def _make_skill(self, root: Path, name: str) -> None:
        skill_dir = root / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\n---\n")

    def test_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(root, "databricks-core")
            meta = {"skills": {"databricks-core": {"keyword": "cli"}}}
            self.assertEqual(skills.check_meta_skill_coverage(root, meta), [])

    def test_disk_skill_missing_from_meta(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(root, "databricks-core")
            self._make_skill(root, "databricks-newthing")
            meta = {"skills": {"databricks-core": {"keyword": "cli"}}}
            errors = skills.check_meta_skill_coverage(root, meta)
            self.assertTrue(any("databricks-newthing" in e for e in errors), errors)

    def test_meta_entry_without_disk_skill(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(root, "databricks-core")
            meta = {
                "skills": {
                    "databricks-core": {"keyword": "cli"},
                    "databricks-ghost": {"keyword": "ghost"},
                }
            }
            errors = skills.check_meta_skill_coverage(root, meta)
            self.assertTrue(any("databricks-ghost" in e for e in errors), errors)

    def test_missing_keyword(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(root, "databricks-core")
            meta = {"skills": {"databricks-core": {}}}
            errors = skills.check_meta_skill_coverage(root, meta)
            self.assertTrue(any("keyword" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
