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
import shutil
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("skills", _REPO / "scripts" / "skills.py")
assert _spec is not None
assert _spec.loader is not None
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
            self.assertEqual(written, len(skills.generated_plugin_files(self.meta)))
            self.assertEqual(skills.check_generated_plugins(root, self.meta), [])

    def test_each_dir_has_generated_marker(self):
        # Every generated-manifest directory ships a README marker so a reader
        # browsing the folder sees it is generated.
        files = skills.generated_plugin_files(self.meta)
        for directory in skills._GENERATED_MANIFEST_DIRS:
            self.assertIn(f"{directory}/README.md", files)

    def test_content_drift_detected(self):
        # The root generated set is now the marketplace catalogs (the four
        # plugin.json moved into the bundle). Edit a catalog and expect drift.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills.generate_plugins(root, self.meta)
            target = root / ".claude-plugin" / "marketplace.json"
            data = json.loads(target.read_text())
            data["description"] = "drifted"
            target.write_text(json.dumps(data, indent=2) + "\n")
            errors = skills.check_generated_plugins(root, self.meta)
            self.assertTrue(
                any("out of date" in e and ".claude-plugin/marketplace.json" in e for e in errors),
                errors,
            )

    def test_formatting_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills.generate_plugins(root, self.meta)
            target = root / ".agents" / "plugins" / "marketplace.json"
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
            (root / ".cursor-plugin" / "marketplace.json").unlink()
            errors = skills.check_generated_plugins(root, self.meta)
            self.assertTrue(
                any("Missing generated file .cursor-plugin/marketplace.json" in e for e in errors),
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


class SkillFrontmatterTest(unittest.TestCase):
    def _make_skill(self, root: Path, name: str, description: str) -> None:
        skill_dir = root / "skills" / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n"
        )

    def test_repo_skills_are_clean(self):
        # Pins the databricks-app-design fix and guards every shipped skill: no
        # SKILL.md may carry a description a strict YAML parser would reject.
        self.assertEqual(skills.check_skill_frontmatter(_REPO), [])

    def test_unquoted_colon_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(
                root, "databricks-bad", "Use when answering questions: pick a chart."
            )
            errors = skills.check_skill_frontmatter(root)
            self.assertTrue(
                any("databricks-bad" in e and "unquoted ':'" in e for e in errors),
                errors,
            )

    def test_quoted_colon_ok(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(
                root, "databricks-good", '"Use when answering questions: pick a chart."'
            )
            self.assertEqual(skills.check_skill_frontmatter(root), [])

    def test_unquoted_no_colon_ok(self):
        # The common, valid shape: a plain bare scalar with no colon. Guards
        # against the regex over-matching and flagging legitimate descriptions.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._make_skill(
                root, "databricks-plain", "Use when building dashboards and charts."
            )
            self.assertEqual(skills.check_skill_frontmatter(root), [])


class BundleTest(unittest.TestCase):
    """The per-provider bundles under plugins/databricks/<provider>/."""

    # Source dirs the per-provider build copies/renders from.
    _SRC_DIRS = ("skills", "hooks", "commands", "rules", "assets")

    def setUp(self):
        self.meta = skills.load_meta(_REPO)

    def test_repo_bundle_is_canonical(self):
        # The committed bundle equals a fresh build (copies + generated
        # plugin.json + rendered commands), with no missing or extra files.
        self.assertEqual(skills.check_generated_bundle(_REPO, self.meta), [])

    def _seed(self, root: Path) -> Path:
        # Copy the real source tree (skills/, the generated wiring+routing in
        # hooks/ and rules/, the command templates, assets/) so a per-provider
        # build can run, then build the bundle.
        for d in self._SRC_DIRS:
            shutil.copytree(_REPO / d, root / d)
        skills.generate_bundle(root, self.meta)
        return root

    def test_generate_bundle_roundtrips_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            self.assertEqual(skills.check_generated_bundle(root, self.meta), [])

    def test_copied_file_drift_detected(self):
        # Hand-editing a copied file inside a provider folder must fail the check.
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            (root / "plugins/databricks/claude/skills/databricks-core/SKILL.md").write_text("tampered")
            errors = skills.check_generated_bundle(root, self.meta)
            self.assertTrue(any("out of date" in e for e in errors), errors)

    def test_extra_file_detected(self):
        # A hand-added file in a provider folder (no source) must be flagged.
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            (root / "plugins/databricks/codex/skills/STRAY.md").write_text("hand-added")
            errors = skills.check_generated_bundle(root, self.meta)
            self.assertTrue(
                any("STRAY.md" in e and "not produced by the generator" in e for e in errors),
                errors,
            )

    def test_generated_plugin_json_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            target = root / "plugins/databricks/claude/.claude-plugin/plugin.json"
            data = json.loads(target.read_text())
            data["version"] = "9.9.9"
            target.write_text(json.dumps(data, indent=2) + "\n")
            errors = skills.check_generated_bundle(root, self.meta)
            self.assertTrue(
                any("claude/.claude-plugin/plugin.json" in e and "out of date" in e for e in errors),
                errors,
            )

    def test_copilot_has_no_router(self):
        # Each provider folder ships only what it uses: Copilot's wiring does not
        # reference the router, so no router script or routing data is copied.
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            cph = root / "plugins/databricks/copilot/hooks"
            self.assertFalse((cph / "databricks-router.py").exists())
            self.assertFalse((cph / "_routing_data.json").exists())
            self.assertTrue((cph / "databricks-context.py").exists())

    def test_copilot_bundle_uses_root_hooks_file(self):
        # VS Code treats .github/plugin/plugin.json as a Copilot-format plugin;
        # its hook auto-discovery looks for hooks.json at the plugin root, not
        # hooks/hooks.json (the Claude-format location).
        with tempfile.TemporaryDirectory() as d:
            root = self._seed(Path(d))
            cph = root / "plugins/databricks/copilot"
            self.assertTrue((cph / "hooks.json").exists())
            self.assertFalse((cph / "hooks" / "hooks.json").exists())

    def test_bundle_skips_vcs_noise(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for dd in self._SRC_DIRS:
                shutil.copytree(_REPO / dd, root / dd)
            noise = root / "skills" / "databricks-core" / "__pycache__"
            noise.mkdir(parents=True, exist_ok=True)
            (noise / "x.pyc").write_text("x")
            (root / "skills" / "databricks-core" / ".DS_Store").write_text("x")
            skills.generate_bundle(root, self.meta)
            seeded = root / "plugins/databricks/claude/skills/databricks-core"
            self.assertFalse((seeded / ".DS_Store").exists())
            self.assertFalse((seeded / "__pycache__").exists())


class ScopedSourcesTest(unittest.TestCase):
    """Every marketplace catalog points a scoped source at its provider subfolder."""

    def setUp(self):
        self.meta = skills.load_meta(_REPO)
        self.subdir = self.meta["marketplace"]["source"]["subdir"]

    def test_repo_catalogs_are_scoped(self):
        self.assertEqual(skills.check_scoped_sources(self.meta), [])

    def test_each_catalog_points_at_its_provider_subfolder(self):
        # Currently ref "main" (the bundle is committed there); the tag-pinning
        # follow-up flips marketplace.source.ref_template to "v{version}".
        self.assertEqual(skills.marketplace_ref(self.meta), "main")
        claude = skills.build_claude_marketplace(self.meta)["plugins"][0]["source"]
        self.assertEqual(claude["path"], f"{self.subdir}/claude")
        self.assertEqual(claude["ref"], "main")
        codex = skills.build_codex_marketplace(self.meta)["plugins"][0]["source"]
        self.assertEqual(codex["path"], f"{self.subdir}/codex")

    def test_cursor_source_is_bare_provider_subfolder_no_ref(self):
        # Cursor cannot pin a ref; its source is the bare relative subfolder.
        cursor = skills.build_cursor_marketplace(self.meta)["plugins"][0]["source"]
        self.assertEqual(cursor, f"{self.subdir}/cursor")

    def test_wrong_subfolder_rejected(self):
        # check_scoped_sources requires each catalog's path to be its own provider
        # subfolder; a source pointing elsewhere (here the whole repo) must fail.
        bad = json.loads(json.dumps(self.meta))
        bad["marketplace"]["source"]["subdir"] = "."
        self.assertTrue(skills.check_scoped_sources(bad))


if __name__ == "__main__":
    unittest.main()
