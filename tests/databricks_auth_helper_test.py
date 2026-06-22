#!/usr/bin/env python3
"""Unit tests for the databricks-auth-helper PostToolUse hook.

The helper should fire only for `databricks` shell commands whose output looks
like an auth failure, and stay silent for everything else. Stdlib-only; run
the suite with: python3 -m unittest discover -s tests -p "*_test.py"
"""
import importlib.util
import json
import unittest
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
_spec = importlib.util.spec_from_file_location(
    "databricks_auth_helper", _HOOKS_DIR / "databricks-auth-helper.py"
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

    def test_non_shell_tool_no_hint(self):
        for tool in ["Read", "Edit", "WebFetch", ""]:
            self.assertIsNone(
                helper.check(tool, "databricks jobs list", "401 Unauthorized"),
                f"should not hint for tool {tool!r}",
            )

    def test_shell_tool_name_variants_hint(self):
        # Claude Code: Bash. Cursor: Shell. Codex: Bash (shell variants seen in
        # the wild). VS Code Copilot: run_in_terminal. All run shell commands,
        # so all are in scope; _invokes_databricks_cli stays the real filter.
        for tool in ["Bash", "bash", "Shell", "shell", "local_shell", "unified_exec", "run_in_terminal"]:
            self.assertIsNotNone(
                helper.check(tool, "databricks jobs list", "Error: 401 Unauthorized"),
                f"should hint for tool {tool!r}",
            )

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


class PlatformTest(unittest.TestCase):
    """The --platform flag picks hint command names and the output envelope."""

    AUTH_ERROR = "Error: 401 Unauthorized"

    def test_default_platform_is_claude(self):
        self.assertEqual(helper._platform_from_argv([]), "claude")
        hint = helper.check("Bash", "databricks jobs list", self.AUTH_ERROR)
        self.assertIn("/databricks:doctor", hint)
        self.assertIn("/databricks:setup", hint)

    def test_cursor_platform_parsed(self):
        self.assertEqual(helper._platform_from_argv(["--platform", "cursor"]), "cursor")
        self.assertEqual(helper._platform_from_argv(["--platform=cursor"]), "cursor")
        self.assertEqual(helper._platform_from_argv(["--platform", "vim"]), "claude")

    def test_cursor_hint_uses_cursor_command_names(self):
        hint = helper.check("Shell", "databricks jobs list", self.AUTH_ERROR, platform="cursor")
        self.assertIn("/databricks-doctor", hint)
        self.assertIn("/databricks-setup", hint)
        self.assertNotIn("/databricks:doctor", hint)

    def test_claude_output_envelope(self):
        out = json.loads(helper.render_output("hint", "claude"))
        self.assertEqual(
            out["hookSpecificOutput"],
            {"hookEventName": "PostToolUse", "additionalContext": "hint"},
        )

    def test_cursor_output_envelope(self):
        out = json.loads(helper.render_output("hint", "cursor"))
        self.assertEqual(out, {"additional_context": "hint"})


class ExtractPayloadTest(unittest.TestCase):
    """Payload extraction handles Claude/Codex and Cursor shapes."""

    def test_claude_shape(self):
        tool, command, text = helper.extract_payload({
            "tool_name": "Bash",
            "tool_input": {"command": "databricks jobs list"},
            "tool_response": {"stdout": "Error: 401 Unauthorized", "stderr": ""},
        })
        self.assertEqual(tool, "Bash")
        self.assertEqual(command, "databricks jobs list")
        self.assertIn("401 Unauthorized", text)

    def test_cursor_shape_with_json_encoded_strings(self):
        # Cursor delivers tool_input/tool_output as JSON-encoded strings.
        tool, command, text = helper.extract_payload({
            "tool_name": "Shell",
            "tool_input": json.dumps({"command": "databricks jobs list"}),
            "tool_output": json.dumps({"exitCode": 1, "stdout": "Error: 401 Unauthorized"}),
        })
        self.assertEqual(tool, "Shell")
        self.assertEqual(command, "databricks jobs list")
        self.assertIn("401 Unauthorized", text)

    def test_missing_fields_degrade_to_empty(self):
        tool, command, text = helper.extract_payload({})
        self.assertEqual(tool, "")
        self.assertEqual(command, "")
        self.assertEqual(text, "")

    def test_non_dict_tool_input_gives_empty_command(self):
        _, command, _ = helper.extract_payload({"tool_name": "Shell", "tool_input": "not json"})
        self.assertEqual(command, "")


if __name__ == "__main__":
    unittest.main()
