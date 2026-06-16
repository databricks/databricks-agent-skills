#!/usr/bin/env python3
"""UserPromptSubmit hook: route Databricks-related prompts into the skills.

Reads the user prompt from stdin, runs a fast keyword regex (sub-50ms, no LLM,
no network), and if the prompt is Databricks-related, injects an
`additionalContext` instruction telling Claude to load the `databricks-core`
skill (the parent/router) plus the matching product skill before answering.

There is no second agent to delegate to: Claude itself drives the `databricks`
CLI through the skills, so "routing" just means "make sure the Databricks skills
are loaded." No permission gating, no cost warnings.

The keyword lists and the injected instruction are generated from
plugin.meta.json into `_routing_data.json` next to this file and loaded at
import time; a minimal inline fallback keeps the hook working if that file is
missing or unreadable. Regenerate with `python3 scripts/skills.py generate`.

The full routing instruction is injected once per session (keyed by the
payload's session_id via a marker file in the temp dir); later Databricks
prompts in the same session get a one-line reminder instead, keeping repeat
token cost low.

Contract (Claude Code UserPromptSubmit hook):
  stdin : JSON, e.g. {"prompt": "...", "session_id": "..."} or {"message": "..."}
  stdout: JSON -> hookSpecificOutput.additionalContext (injected before the turn),
          or "{}" to stay out of the way.
  Fail-open: on ANY error print "{}" and exit 0, so a broken hook never blocks a
  prompt.
"""
import json
import re
import sys
import tempfile
from pathlib import Path

# Routing config (keyword lists + the injected instruction) is generated from
# plugin.meta.json into _routing_data.json next to this file (see
# rules/README.md and CONTRIBUTING.md) and loaded at import time. If that file
# is missing or unreadable the hook stays fail-open via a minimal inline
# fallback that still routes obvious Databricks prompts.
_FALLBACK_STRONG = [r"\bdatabricks\b"]
_FALLBACK_AMBIGUOUS = []
_FALLBACK_SUPPRESS = []
_FALLBACK_INSTRUCTION = (
    "[DATABRICKS] This request is Databricks-related. Handle it through the "
    "Databricks skills rather than ad hoc commands: load `databricks-core` (the "
    "parent skill) plus the matching product skill before answering."
)
_FALLBACK_REMINDER = (
    "[DATABRICKS] Databricks-related prompt: keep routing through the Databricks "
    "skills (databricks-core plus the matching product skill)."
)


def _load_routing_data(path=None):
    """Load the generated _routing_data.json next to this file; None on any problem.

    Returns None (so the inline fallback engages) for a missing, unreadable,
    malformed, wrong-typed, or regex-invalid file. The patterns are compiled
    here, so a corrupt data file degrades the router to "route obvious
    databricks mentions" rather than raising at import (which would otherwise
    take the whole hook down, fallback included).
    """
    try:
        if path is None:
            path = Path(__file__).resolve().parent / "_routing_data.json"
        data = json.loads(Path(path).read_text())
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if not all(
        k in data for k in ("strong", "ambiguous", "suppress", "instruction", "reminder")
    ):
        return None
    if not all(isinstance(data[k], list) for k in ("strong", "ambiguous", "suppress")):
        return None
    if not all(isinstance(data[k], str) for k in ("instruction", "reminder")):
        return None
    try:
        for key in ("strong", "ambiguous", "suppress"):
            for pattern in data[key]:
                re.compile(pattern)
    except (re.error, TypeError):
        return None
    return data


_DATA = _load_routing_data()

# STRONG: unambiguously Databricks -> always route, even alongside a mention of
# an alternative platform (e.g. "migrate from redshift to databricks").
# AMBIGUOUS: Databricks-likely but also used elsewhere -> route only when no
# SUPPRESS signal (alternative platform / local dev) is present. STRONG matches
# ignore SUPPRESS. All are sourced from the generated data file; the inline
# fallback degrades gracefully (routes only clear "databricks" mentions).
STRONG = list(_DATA["strong"]) if _DATA else list(_FALLBACK_STRONG)
AMBIGUOUS = list(_DATA["ambiguous"]) if _DATA else list(_FALLBACK_AMBIGUOUS)
SUPPRESS = list(_DATA["suppress"]) if _DATA else list(_FALLBACK_SUPPRESS)

# The full instruction injected on the session's first Databricks prompt, plus
# the one-line reminder for later prompts. ROUTING_INSTRUCTION stays a
# module-level attribute (scripts/skills.py check_routing_tables reads it).
ROUTING_INSTRUCTION = _DATA["instruction"] if _DATA else _FALLBACK_INSTRUCTION
ROUTING_REMINDER = _DATA["reminder"] if _DATA else _FALLBACK_REMINDER

_STRONG = [re.compile(p, re.IGNORECASE) for p in STRONG]
_AMBIGUOUS = [re.compile(p, re.IGNORECASE) for p in AMBIGUOUS]
_SUPPRESS = [re.compile(p, re.IGNORECASE) for p in SUPPRESS]

# "databricks" inside a code-hosting URL (github.com/databricks/...) is an
# org/repo name, not product intent, so URLs are blanked before matching unless
# the hostname itself contains "databricks" (workspace and docs hosts), which
# keeps "why is https://myco.cloud.databricks.com/jobs/123 failing?" routing.
_URL_RE = re.compile(
    r"(?:https?://|git@)(?P<host>[\w.-]+)[/:]?\S*"
    r"|\b(?:www\.)?(?P<bare>(?:github|gitlab|bitbucket)\.(?:com|org))[/:]\S*",
    re.IGNORECASE,
)


def _strip_non_databricks_urls(text):
    def _keep_or_blank(match):
        host = match.group("host") or match.group("bare") or ""
        return match.group(0) if "databricks" in host.lower() else " "

    return _URL_RE.sub(_keep_or_blank, text)


_SESSION_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")


def _marker_path(session_id):
    """Temp-dir marker recording that this session already got the full instruction."""
    sid = _SESSION_ID_SAFE_RE.sub("", str(session_id or ""))[:64]
    if not sid:
        return None
    return Path(tempfile.gettempdir()) / f"databricks-router-{sid}"


def check_prompt(prompt):
    """Return the routing instruction if the prompt is Databricks-related, else None."""
    if not prompt or len(prompt.strip()) < 4:
        return None
    prompt = _strip_non_databricks_urls(prompt)
    if any(p.search(prompt) for p in _STRONG):
        return ROUTING_INSTRUCTION
    if any(p.search(prompt) for p in _SUPPRESS):
        return None
    if any(p.search(prompt) for p in _AMBIGUOUS):
        return ROUTING_INSTRUCTION
    return None


def routing_context(prompt, session_id):
    """Full instruction on the session's first Databricks prompt, reminder after."""
    if check_prompt(prompt) is None:
        return None
    marker = _marker_path(session_id)
    if marker is None:
        return ROUTING_INSTRUCTION
    try:
        if marker.exists():
            return ROUTING_REMINDER
        marker.touch()
    except Exception:
        # Marker bookkeeping must never break routing itself.
        pass
    return ROUTING_INSTRUCTION


def extract_prompt(data):
    """Pull the prompt text out of the hook payload (Claude or Codex shapes)."""
    if not isinstance(data, dict):
        return ""
    prompt = data.get("prompt", data.get("message", ""))
    if isinstance(prompt, dict):
        prompt = prompt.get("content", "")
    if isinstance(prompt, list):
        prompt = " ".join(
            block.get("text", "") for block in prompt if isinstance(block, dict)
        )
    return str(prompt)


def main():
    # One outer try so the fail-open guarantee covers the entire main block,
    # including JSON serialization; the final print gets its own guard (a
    # closed stdout must not surface as a hook failure either).
    output = "{}"
    try:
        data = json.load(sys.stdin)
        session_id = data.get("session_id", "") if isinstance(data, dict) else ""
        result = routing_context(extract_prompt(data), session_id)
        if result:
            output = json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": result,
                }
            })
    except Exception:
        output = "{}"
    try:
        print(output)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
