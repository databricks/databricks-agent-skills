#!/usr/bin/env python3
"""PostToolUse hook: suggest an auth fix when a `databricks` command fails auth.

Watches Bash tool results. When the command involved the `databricks` CLI and
the output looks like an authentication failure (missing credentials, expired
or invalid token, OAuth refresh failure), it injects one line of
`additionalContext` pointing at `/databricks:doctor` and `databricks auth
login`. Everything else passes through silently.

No gating: this never blocks or rewrites a tool call, it only adds context
after the fact.

Contract (Claude Code PostToolUse hook, matcher: Bash):
  stdin : JSON with tool_name, tool_input.command, tool_response
  stdout: JSON -> hookSpecificOutput.additionalContext, or "{}".
  Fail-open: on ANY error print "{}" and exit 0.
"""
import json
import re
import sys

DATABRICKS_CMD_RE = re.compile(r"\bdatabricks\b")

# Phrase-shaped auth-failure signals as emitted by the CLI / Go SDK error
# paths. Deliberately not bare status codes, so ordinary data in stdout
# (e.g. a row containing 401) cannot trip them.
AUTH_ERROR_PATTERNS = [
    r"cannot configure default credentials",
    r"\binvalid_grant\b",
    r"\b401 unauthorized\b",
    r"\binvalid access token\b",
    r"\btoken (?:is |has |was )?expired\b",
    r"\brefresh token (?:is |was )?(?:invalid|expired|revoked)\b",
]
_AUTH_ERRORS = [re.compile(p, re.IGNORECASE) for p in AUTH_ERROR_PATTERNS]

AUTH_HINT = (
    "[DATABRICKS] The `databricks` command above failed with what looks like "
    "an authentication error. Before retrying, fix auth: run "
    "`/databricks:doctor` for a read-only diagnosis, or re-authenticate with "
    "`databricks auth login --host <workspace-url> --profile <name>` "
    "(`/databricks:setup` walks through it). Never auto-select a profile for "
    "the user."
)


def check(tool_name, command, response_text):
    """Return the auth hint when a databricks command hit an auth error, else None."""
    if tool_name != "Bash":
        return None
    if not command or not DATABRICKS_CMD_RE.search(command):
        return None
    if not response_text:
        return None
    if any(p.search(response_text) for p in _AUTH_ERRORS):
        return AUTH_HINT
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("{}")
        sys.exit(0)

    try:
        if not isinstance(data, dict):
            raise TypeError("payload is not an object")
        tool_input = data.get("tool_input")
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        # Serialize the whole response instead of assuming its shape; auth
        # errors can land in stdout, stderr, or a combined error field.
        response_text = json.dumps(data.get("tool_response", ""), default=str)
        result = check(data.get("tool_name", ""), command, response_text)
    except Exception:
        result = None

    if result:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": result,
            }
        }))
    else:
        print("{}")
    sys.exit(0)


if __name__ == "__main__":
    main()
