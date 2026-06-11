#!/usr/bin/env python3
"""UserPromptSubmit hook: route Databricks-related prompts into the skills.

Reads the user prompt from stdin, runs a fast keyword regex (sub-50ms, no LLM,
no network), and if the prompt is Databricks-related, injects an
`additionalContext` instruction telling Claude to load the `databricks-core`
skill (the parent/router) plus the matching product skill before answering.

There is no second agent to delegate to: Claude itself drives the `databricks`
CLI through the skills, so "routing" just means "make sure the Databricks skills
are loaded." No permission gating, no cost warnings.

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

# Unambiguously Databricks -> always route, even alongside a mention of an
# alternative platform (e.g. "migrate from redshift to databricks").
STRONG = [
    r"\bdatabricks\b",
    r"\bunity\s+catalog\b",
    r"\blakeflow\b",
    r"\blakebase\b",
    r"\bdbfs\b",
    r"\bdbutils\b",
    r"\bdbsql\b",
    r"\bdatabricks\.yml\b",
    r"\basset\s+bundle\b",
    r"\bdabs\b",
    r"\b(?:lakeflow|spark)\s+declarative\s+pipelines?\b",
    r"\bdelta\s+live\s+tables?\b",  # legacy name for Declarative Pipelines
    r"\bmosaic\s+ai\b",
    r"\bdelta\s+sharing\b",
    r"\bcloudfiles\b",
]

# Databricks-likely but also used elsewhere -> route only when no
# alternative-platform / local-dev signal is present.
AMBIGUOUS = [
    r"\bgenie\b",
    r"\bdelta\s+(lake|tables?)\b",
    r"\bdeclarative\s+pipelines?\b",  # bare form collides with Jenkins pipelines
    r"\bmodel\s+serving\b",
    r"\bvector\s+search\b",
    r"\bmlflow\b",
    r"\bpyspark\b",
    r"\bspark\s*\.\s*(sql|read|write|table)\b",
    r"\bserverless\s+(compute|warehouse|migration)\b",
    r"\bmedallion\s+(architecture|tables?)\b",
    r"\bsql\s+warehouse\b",
    r"\bauto\s+loader\b",
]

# Alternative data platforms + plainly-local dev work -> suppress an AMBIGUOUS
# match. (STRONG matches ignore this list.)
SUPPRESS = [
    r"\bbigquery\b",
    r"\bredshift\b",
    r"\bsynapse\b",
    r"\bsnowflake\b",
    r"\bgit\s+(commit|push|pull|status|log|diff|branch|rebase|merge|clone|stash)\b",
    r"\b(read|edit|open|write|create|delete)\s+(the\s+|this\s+|a\s+|that\s+)?file\b",
    r"\bunit\s+tests?\b",
    r"\bnpm\b",
    r"\bpip\s+install\b",
    r"\bdocker\b",
    r"\bkubernetes\b",
    r"\bjenkins(?:file)?\b",
]

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

ROUTING_INSTRUCTION = (
    "[DATABRICKS] This request is Databricks-related. Handle it through the "
    "Databricks skills rather than ad hoc commands. Use the Skill tool to load "
    "`databricks-core` first (the parent skill: CLI, auth, profile selection, "
    "data exploration), then load the product skill that matches the request:\n"
    "- Jobs / Lakeflow / workflows -> databricks-jobs\n"
    "- Pipelines / Lakeflow Spark Declarative Pipelines (formerly DLT) -> "
    "databricks-pipelines\n"
    "- Apps / AppKit -> databricks-apps\n"
    "- Asset Bundles / DABs / databricks.yml -> databricks-dabs\n"
    "- Model Serving / endpoints -> databricks-model-serving\n"
    "- Lakebase / Postgres -> databricks-lakebase\n"
    "- Vector Search / RAG -> databricks-vector-search\n"
    "- Classic-to-serverless migration -> databricks-serverless-migration\n"
    "- Genie / natural-language data Q&A -> databricks-core (Genie CLI support "
    "is experimental)\n"
    "Then follow the skill's guidance (it drives the `databricks` CLI). If no "
    "product skill fits, databricks-core alone is enough."
)

# After the first routed prompt the skills are loaded (or being loaded), so the
# rest of the session gets this one-liner instead of the full block above.
ROUTING_REMINDER = (
    "[DATABRICKS] Databricks-related prompt: keep routing through the "
    "Databricks skills (databricks-core plus the matching product skill); load "
    "any that are not already loaded."
)

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
