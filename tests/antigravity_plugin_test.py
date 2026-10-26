"""Native Antigravity bundle, local build, and installation archive tests."""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

from build_provider_plugin import build_provider_plugin
from package_antigravity_plugin import package_antigravity_plugin
from skillsgen.common import BUNDLE_DIR, load_meta
from skillsgen.discovery import iter_skill_dirs


class AntigravityBundleTest(unittest.TestCase):
    def test_generated_manifest_uses_native_fields_and_shared_metadata(self):
        meta = load_meta(_REPO)
        plugin = json.loads((_REPO / BUNDLE_DIR / "antigravity/plugin.json").read_text())
        self.assertEqual(plugin["$schema"], "https://antigravity.google/schemas/v1/plugin.json")
        self.assertEqual(plugin["name"], "databricks")
        for field in ("description", "version", "author", "homepage", "repository", "license"):
            self.assertEqual(plugin[field], meta[field])
        self.assertEqual(plugin["logo"], "./assets/databricks.png")
        self.assertTrue((_REPO / BUNDLE_DIR / "antigravity" / plugin["logo"]).is_file())
        self.assertEqual(set(plugin), {
            "$schema", "name", "displayName", "description", "version", "author",
            "homepage", "repository", "license", "keywords", "logo",
        })

    def test_bundle_contains_all_stable_skills_and_native_components(self):
        base = _REPO / BUNDLE_DIR / "antigravity"
        self.assertEqual({path.name for path in base.iterdir()}, {
            "plugin.json", "skills", "rules", "assets", "LICENSE", "NOTICE",
        })
        self.assertEqual(
            {path.name for path in iter_skill_dirs(_REPO)},
            {path.name for path in (base / "skills").iterdir()},
        )
        self.assertEqual({path.name for path in (base / "rules").iterdir()}, {"databricks-routing.md"})
        self.assertEqual({path.name for path in (base / "assets").iterdir()}, {"databricks.png"})
        rule = (base / "rules/databricks-routing.md").read_text()
        frontmatter = rule.split("---", 2)[1]
        self.assertRegex(frontmatter, r"(?m)^trigger: model_decision$")
        self.assertRegex(frontmatter, r"(?m)^description: .+\S$")
        cursor_rules = _REPO / BUNDLE_DIR / "cursor/rules"
        self.assertEqual({path.name for path in cursor_rules.iterdir()}, {
            "databricks-routing.mdc", "README.md",
        })

    def test_local_build_works_without_release_state_or_generated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            for name in ("skills", "hooks", "commands", "assets", "metaplugin"):
                shutil.copytree(_REPO / name, source / name)
            for name in ("LICENSE", "NOTICE"):
                shutil.copyfile(_REPO / name, source / name)
            (source / "metaplugin/version.meta.json").unlink(missing_ok=True)
            before = {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()}
            for provider, manifest_dir in (("claude", ".claude-plugin"), ("antigravity", ".")):
                with self.subTest(provider=provider):
                    output = root / provider
                    output.mkdir()
                    (output / "obsolete.md").write_text("stale artifact")

                    build_provider_plugin(source, output, provider)

                    plugin = json.loads((output / manifest_dir / "plugin.json").read_text())
                    self.assertEqual(plugin["version"], "0.0.0-unreleased")
                    self.assertTrue((output / "skills/databricks-core/databricks-cli-auth.md").is_file())
                    self.assertFalse((output / "obsolete.md").exists())
                    if provider == "antigravity":
                        self.assertTrue((output / "rules/databricks-routing.md").is_file())
                        self.assertEqual((output / "LICENSE").read_bytes(), (source / "LICENSE").read_bytes())
                    else:
                        self.assertTrue((output / "hooks/hooks.json").is_file())
            after = {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()}
            self.assertEqual(before, after, "Building a plugin must preserve the source-only checkout.")


class AntigravityPackageTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.plugin = self.root / BUNDLE_DIR / "antigravity"
        shutil.copytree(_REPO / BUNDLE_DIR / "antigravity", self.plugin)

    def test_archive_extracts_to_a_complete_native_plugin(self):
        output = self.root / "databricks-antigravity.zip"
        package_antigravity_plugin(self.plugin, output)
        expected = {
            path.relative_to(self.plugin).as_posix(): path.read_bytes()
            for path in self.plugin.rglob("*") if path.is_file()
        }
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(set(archive.namelist()), set(expected))
            for name, data in expected.items():
                self.assertEqual(archive.read(name), data, name)
            archive.extractall(self.root / "extracted")
        manifest = json.loads((self.root / "extracted/plugin.json").read_text())
        self.assertEqual(manifest["version"], load_meta(_REPO)["version"])
        self.assertTrue((self.root / "extracted" / manifest["logo"]).is_file())
        self.assertTrue((self.root / "extracted/skills/databricks-core/databricks-cli-auth.md").is_file())

    def test_archive_is_independent_of_file_times_and_permissions(self):
        first = self.root / "first.zip"
        second = self.root / "second.zip"
        package_antigravity_plugin(self.plugin, first)
        manifest = self.plugin / "plugin.json"
        os.utime(manifest, (1, 1))
        manifest.chmod(0o600)
        package_antigravity_plugin(self.plugin, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_missing_manifest_is_rejected(self):
        (self.plugin / "plugin.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing plugin manifest: plugin.json"):
            package_antigravity_plugin(self.plugin, self.root / "plugin.zip")

    def test_symlinked_resources_are_rejected(self):
        (self.plugin / "linked-resource").symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            package_antigravity_plugin(self.plugin, self.root / "plugin.zip")

    def test_archive_cannot_be_written_inside_its_input(self):
        with self.assertRaisesRegex(ValueError, "outside the plugin directory"):
            package_antigravity_plugin(self.plugin, self.plugin / "plugin.zip")


if __name__ == "__main__":
    unittest.main()
