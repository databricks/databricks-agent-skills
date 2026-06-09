#!/usr/bin/env python3
"""Unit tests for the databricks-context SessionStart hook.

Covers the pure pieces (config parsing, sanitization) and the build_context
wiring around them. Stdlib-only; run with: python3 hooks/databricks_context_test.py
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location(
    "databricks_context", Path(__file__).parent / "databricks-context.py"
)
ctx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctx)


class ConfigProfilesTest(unittest.TestCase):
    def _write_cfg(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_parses_profiles_and_skips_internal_sections(self):
        cfg = self._write_cfg(
            "[DEFAULT]\nhost = https://x\n\n[__settings__]\nfoo = 1\n\n[prod]\nhost = https://y\n"
        )
        with mock.patch.dict(os.environ, {"DATABRICKS_CONFIG_FILE": cfg}):
            path, names = ctx.config_profiles()
        self.assertEqual(path, cfg)
        self.assertEqual(names, ["DEFAULT", "prod"])

    def test_missing_file_gives_no_profiles(self):
        with mock.patch.dict(os.environ, {"DATABRICKS_CONFIG_FILE": "/nonexistent/nope.cfg"}):
            _, names = ctx.config_profiles()
        self.assertEqual(names, [])

    def test_oversized_file_is_skipped(self):
        cfg = self._write_cfg("[DEFAULT]\n" + "x = y\n" * 200_000)
        with mock.patch.dict(os.environ, {"DATABRICKS_CONFIG_FILE": cfg}):
            _, names = ctx.config_profiles()
        self.assertEqual(names, [])


class SanitizeTest(unittest.TestCase):
    def test_strips_control_chars_and_newlines(self):
        self.assertEqual(ctx._sanitize("a\nb\x00c"), "a b c")

    def test_truncates_long_values(self):
        out = ctx._sanitize("x" * 200, limit=10)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 10)

    def test_plain_value_unchanged(self):
        self.assertEqual(ctx._sanitize("e2-dogfood"), "e2-dogfood")


class BuildContextTest(unittest.TestCase):
    def test_cli_missing_points_at_setup(self):
        with mock.patch.object(ctx.shutil, "which", return_value=None):
            out = ctx.build_context()
        self.assertIn("/databricks:setup", out)

    def test_no_profiles_message_uses_basename_only(self):
        with mock.patch.dict(os.environ, {"DATABRICKS_CONFIG_FILE": "/secret/dir/custom.cfg"}), \
             mock.patch.object(ctx.shutil, "which", return_value="/usr/bin/databricks"), \
             mock.patch.object(ctx, "cli_version", return_value=(1, 2, 3)):
            out = ctx.build_context()
        self.assertIn("custom.cfg", out)
        self.assertNotIn("/secret/dir", out)


if __name__ == "__main__":
    unittest.main()
