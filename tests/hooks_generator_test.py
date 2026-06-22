#!/usr/bin/env python3
"""Tests for the hook-wiring generator (plugin.meta.json "hooks" -> 4 dialects).

Three logical hooks (router/context/auth) render into four runtime dialects:
Claude hooks.json, Codex, Copilot, Cursor. These tests pin byte-reproducible
generation, that the router is wired only on Claude + Codex, and that every
rendered event name is one the target platform actually fires (a wrong-case
event would silently never run; the per-platform allow-lists are #151's).

Stdlib-only; run with: python3 -m unittest discover -s tests -p "*_test.py"
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


class GeneratedHooksTest(unittest.TestCase):
    def setUp(self):
        self.meta = skills.load_meta(_REPO)

    def test_repo_hooks_are_canonical(self):
        # The committed hook-wiring files match what the generator produces.
        self.assertEqual(skills.check_generated_hooks(_REPO, self.meta), [])

    def test_generate_roundtrips_clean(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            written = skills.generate_hooks(root, self.meta)
            self.assertEqual(written, len(skills.generated_hook_files(self.meta)))
            self.assertEqual(skills.check_generated_hooks(root, self.meta), [])

    def test_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            skills.generate_hooks(root, self.meta)
            target = root / "hooks" / "cursor-hooks.json"
            data = json.loads(target.read_text())
            data["version"] = 2
            target.write_text(json.dumps(data, indent=2) + "\n")
            self.assertTrue(skills.check_generated_hooks(root, self.meta))

    def test_event_names_are_valid_per_platform(self):
        cases = [
            (skills.build_nested_hooks(self.meta, "claude"), skills._CLAUDE_EVENTS),
            (skills.build_nested_hooks(self.meta, "codex"), skills._CODEX_EVENTS),
            (skills.build_copilot_hooks(self.meta), skills._COPILOT_EVENTS),
            (skills.build_cursor_hooks(self.meta), skills._CURSOR_EVENTS),
        ]
        for cfg, valid in cases:
            for event in cfg["hooks"]:
                self.assertIn(event, valid, f"event {event!r} is not documented for this platform")

    def test_router_only_on_claude_and_codex(self):
        for key in ("claude", "codex"):
            self.assertIn(
                "UserPromptSubmit", skills.build_nested_hooks(self.meta, key)["hooks"]
            )
        # The other two cannot inject context from a prompt-submit hook, so the
        # router script must not be wired at all.
        for blob in (
            json.dumps(skills.build_copilot_hooks(self.meta)),
            json.dumps(skills.build_cursor_hooks(self.meta)),
        ):
            self.assertNotIn("databricks-router.py", blob)

    def test_wired_scripts_exist(self):
        for script in skills._hook_scripts(self.meta).values():
            self.assertTrue((_REPO / "hooks" / script).exists(), script)

    def test_claude_hooks_has_description_codex_does_not(self):
        self.assertIn("description", skills.build_nested_hooks(self.meta, "claude"))
        self.assertNotIn("description", skills.build_nested_hooks(self.meta, "codex"))

    def test_flat_dialects_declare_version_1(self):
        self.assertEqual(skills.build_copilot_hooks(self.meta)["version"], 1)
        self.assertEqual(skills.build_cursor_hooks(self.meta)["version"], 1)

    def test_no_plugin_declares_hooks(self):
        # Each per-provider bundle ships its wiring as hooks/hooks.json, which the
        # agent auto-discovers from the plugin root, so no plugin.json declares a
        # "hooks" path (declaring the auto-discovered file double-loads it).
        for builder in (
            skills.build_claude_plugin,
            skills.build_codex_plugin,
            skills.build_copilot_plugin,
            skills.build_cursor_plugin,
        ):
            self.assertNotIn("hooks", builder(self.meta))

    def test_no_orphan_hook_scripts(self):
        self.assertEqual(skills.check_no_orphan_hook_scripts(_REPO, self.meta), [])

    def test_orphan_hook_script_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "hooks").mkdir()
            for script in skills._hook_scripts(self.meta).values():
                (root / "hooks" / script).write_text("")
            (root / "hooks" / "databricks-stray.py").write_text("")
            errors = skills.check_no_orphan_hook_scripts(root, self.meta)
            self.assertTrue(any("databricks-stray.py" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
