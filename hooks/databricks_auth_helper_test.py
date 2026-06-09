#!/usr/bin/env python3
"""Unit tests for the databricks-auth-helper PostToolUse hook.

The helper should fire only for `databricks` Bash commands whose output looks
like an auth failure, and stay silent for everything else. Stdlib-only; run
with: python3 hooks/databricks_auth_helper_test.py
"""
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "databricks_auth_helper", Path(__file__).parent / "databricks-auth-helper.py"
)
helper = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(helper)


class CheckTest(unittest.TestCase):
    def test_databricks_auth_failures_hint(self):
        for text in [
            "Error: default auth: cannot configure default credentials",
            'oauth2: "invalid_grant" "Token was not recognized"',
            "Error: 401 Unauthorized",
            "Error: Invalid access token.",
            "token is expired, please log in again",
            "the refresh token was revoked by the server",
        ]:
            self.assertIsNotNone(
                helper.check("Bash", "databricks jobs list", text),
                f"should hint: {text!r}",
            )

    def test_clean_output_no_hint(self):
        self.assertIsNone(helper.check("Bash", "databricks jobs list", '{"jobs": []}'))

    def test_non_databricks_command_no_hint(self):
        self.assertIsNone(helper.check("Bash", "curl https://example.com", "401 Unauthorized"))

    def test_non_bash_tool_no_hint(self):
        self.assertIsNone(helper.check("Read", "databricks", "401 Unauthorized"))

    def test_bare_status_code_in_data_no_hint(self):
        # A bare 401 inside ordinary output is not an auth-failure signal.
        self.assertIsNone(helper.check("Bash", "databricks jobs list", '{"row_id": 401}'))

    def test_empty_inputs_no_hint(self):
        self.assertIsNone(helper.check("Bash", "", "401 unauthorized"))
        self.assertIsNone(helper.check("Bash", "databricks auth env", ""))


if __name__ == "__main__":
    unittest.main()
