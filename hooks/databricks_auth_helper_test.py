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


class CommandDetectionTest(unittest.TestCase):
    """`databricks` must be a segment executable, not a substring anywhere."""

    AUTH_ERROR = "Error: 401 Unauthorized"

    def test_databricks_mentioned_but_not_invoked_no_hint(self):
        # Observed false positives: gh commands against the databricks GitHub
        # org whose output quoted auth-failure phrases (a PR body describing
        # this hook, and this hook's own source fetched via the contents API).
        for command in [
            "gh pr view 128 --repo databricks/databricks-agent-skills --json body",
            'gh api "repos/databricks/databricks-agent-skills/contents/hooks/databricks-auth-helper.py"',
            "git clone https://github.com/databricks/cli",
            "curl https://docs.databricks.com/api/auth.html",
            "echo databricks",
            "cat notes/databricks.md",
            "/tmp/databricks-test clusters list",
        ]:
            self.assertIsNone(
                helper.check("Bash", command, self.AUTH_ERROR),
                f"should not hint: {command!r}",
            )

    def test_databricks_invoked_hint(self):
        for command in [
            "databricks clusters list",
            "cd repos/cli && databricks auth describe",
            "databricks jobs list | head -5",
            "/usr/local/bin/databricks --version",
            "./databricks auth env",
            "DATABRICKS_CONFIG_PROFILE=dev databricks current-user me",
            "sudo -E databricks auth login",
            "token=$(databricks auth token --host https://example.com)",
        ]:
            self.assertIsNotNone(
                helper.check("Bash", command, self.AUTH_ERROR),
                f"should hint: {command!r}",
            )


if __name__ == "__main__":
    unittest.main()
