#!/usr/bin/env python3
"""PostToolUse hook: suggest an auth fix when a `databricks` command fails auth.

Watches shell tool results. When the command actually invoked the `databricks`
CLI (as a segment executable, not merely "databricks" appearing in a repo
path, URL, or argument) and the output looks like an authentication failure
(missing credentials, expired or invalid token, OAuth refresh failure), it
injects one line of additional context pointing at the doctor command and
`databricks auth login`. Everything else passes through silently.

No gating: this never blocks or rewrites a tool call, it only adds context
after the fact.

Contract (Claude Code PostToolUse hook, matcher: Bash; Cursor postToolUse,
matcher: Shell, with `--platform cursor`):
  stdin : JSON with tool_name + the command and result. Claude/Codex carry
          tool_input.command and tool_response; Cursor carries tool_input /
          tool_output, either of which may itself be a JSON-encoded string.
  stdout: platform-shaped JSON carrying the hint, or "{}".
          Claude/Codex -> hookSpecificOutput.additionalContext
          Cursor       -> additional_context
  Fail-open: on ANY error print "{}" and exit 0.
"""
import json
import re
import sys

# `databricks` must be the executable of one of the command's shell segments,
# not a substring anywhere in the command line: `gh pr view --repo
# databricks/cli`, URLs, and file paths mention databricks without invoking
# the CLI, and their output can legitimately quote auth-failure phrases (a PR
# body, this hook's own source). Segments are split on shell connectors and
# command-substitution openers; each segment's executable is its first token
# after env assignments, common wrappers, and wrapper flags. Path-prefixed
# invocations (`/usr/local/bin/databricks`) count; `databricks-test` does not.
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||\$\(|[;|&\n`(]")
_ENV_ASSIGNMENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = frozenset({"sudo", "env", "command", "exec", "time", "nohup", "xargs"})

# Shell-running tool names across the harnesses that consume this hook:
# Claude Code uses Bash, Cursor uses Shell, Codex documents Bash (with
# shell/unified_exec variants in the wild), VS Code Copilot uses
# run_in_terminal. The real filter is _invokes_databricks_cli below; this
# gate only keeps non-shell tools (file reads, edits) from being scanned.
_SHELL_TOOL_RE = re.compile(r"(?i)^(bash|shell|local_shell|unified_exec|run_in_terminal)$")

# Per-platform names for the setup/doctor commands referenced in the hint
# (Claude Code namespaces plugin commands as /databricks:<name>; Cursor has a
# flat / menu, so the Cursor plugin ships them as /databricks-<name>).
PLATFORMS = {
    "claude": {"setup_cmd": "/databricks:setup", "doctor_cmd": "/databricks:doctor"},
    "cursor": {"setup_cmd": "/databricks-setup", "doctor_cmd": "/databricks-doctor"},
}


def _platform_from_argv(argv):
    """Platform from `--platform <name>` / `--platform=<name>`, default claude.

    Unknown values fall back to claude rather than erroring: a wiring typo must
    degrade to a working hook, never a broken one.
    """
    for i, arg in enumerate(argv):
        if arg == "--platform" and i + 1 < len(argv):
            value = argv[i + 1]
        elif arg.startswith("--platform="):
            value = arg.split("=", 1)[1]
        else:
            continue
        return value if value in PLATFORMS else "claude"
    return "claude"


def _segment_executable(tokens):
    """First token that is not an env assignment, wrapper, or wrapper flag."""
    after_wrapper = False
    for token in tokens:
        if _ENV_ASSIGNMENT_RE.match(token):
            continue
        if token in _WRAPPERS:
            after_wrapper = True
            continue
        if after_wrapper and token.startswith("-"):
            continue
        return token
    return ""


def _invokes_databricks_cli(command):
    """True when any segment of the command runs the `databricks` executable."""
    for segment in _SEGMENT_SPLIT_RE.split(command):
        executable = _segment_executable(segment.split())
        if executable.rsplit("/", 1)[-1] == "databricks":
            return True
    return False

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

AUTH_HINT_TEMPLATE = (
    "[DATABRICKS] The `databricks` command above failed with what looks like "
    "an authentication error. Before retrying, fix auth: run "
    "`{doctor_cmd}` for a read-only diagnosis, or re-authenticate with "
    "`databricks auth login --host <workspace-url> --profile <name>` "
    "(`{setup_cmd}` walks through it). Never auto-select a profile for "
    "the user."
)


def _parse_maybe_json(value):
    """Return a dict from `value`, decoding it first if it's a JSON string."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return None
    return value if isinstance(value, dict) else None


def extract_payload(data):
    """(tool_name, command, response_text) from a Claude/Codex or Cursor payload."""
    tool_name = str(data.get("tool_name", ""))
    tool_input = _parse_maybe_json(data.get("tool_input"))
    command = tool_input.get("command", "") if tool_input else ""
    if not isinstance(command, str):
        command = ""
    # Claude/Codex put the result in tool_response; Cursor in tool_output
    # (often as an already-JSON-encoded string). Serialize non-strings instead
    # of assuming their shape; auth errors can land in stdout, stderr, or a
    # combined error field.
    raw = data.get("tool_response", data.get("tool_output", ""))
    response_text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
    return tool_name, command, response_text


def check(tool_name, command, response_text, platform="claude"):
    """Return the auth hint when a databricks command hit an auth error, else None."""
    if not _SHELL_TOOL_RE.match(tool_name or ""):
        return None
    if not command or not _invokes_databricks_cli(command):
        return None
    if not response_text:
        return None
    if any(p.search(response_text) for p in _AUTH_ERRORS):
        return AUTH_HINT_TEMPLATE.format(**PLATFORMS.get(platform, PLATFORMS["claude"]))
    return None


def render_output(hint, platform="claude"):
    """Wrap the hint in the platform's hook output envelope."""
    if platform == "cursor":
        return json.dumps({"additional_context": hint})
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": hint,
        }
    })


def main():
    # One outer try so the fail-open guarantee covers the entire main block,
    # including JSON serialization; the final print gets its own guard (a
    # closed stdout must not surface as a hook failure either).
    output = "{}"
    try:
        platform = _platform_from_argv(sys.argv[1:])
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise TypeError("payload is not an object")
        tool_name, command, response_text = extract_payload(data)
        result = check(tool_name, command, response_text, platform)
        if result:
            output = render_output(result, platform)
    except Exception:
        output = "{}"
    try:
        print(output)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
