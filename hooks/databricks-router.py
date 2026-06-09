#!/usr/bin/env python3
"""UserPromptSubmit hook: route Databricks-related prompts into the skills.

Reads the user prompt from stdin, runs a fast keyword regex (sub-50ms, no LLM,
no network), and if the prompt is Databricks-related, injects an
`additionalContext` instruction telling Claude to load the `databricks-core`
skill (the parent/router) plus the matching product skill before answering.

There is no second agent to delegate to: Claude itself drives the `databricks`
CLI through the skills, so "routing" just means "make sure the Databricks skills
are loaded." No permission gating, no cost warnings.

Contract (Claude Code UserPromptSubmit hook):
  stdin : JSON, e.g. {"prompt": "..."} or {"message": "..."}
  stdout: JSON -> hookSpecificOutput.additionalContext (injected before the turn),
          or "{}" to stay out of the way.
  Fail-open: on ANY error print "{}" and exit 0, so a broken hook never blocks a
  prompt.
"""
import json
import re
import sys

# Unambiguously Databricks -> always route, even alongside a competitor mention
# (e.g. "migrate from redshift to databricks").
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
    r"\bdelta\s+live\s+tables?\b",
    r"\bspark\s+declarative\s+pipelines?\b",
    r"\bmosaic\s+ai\b",
]

# Databricks-likely but also used elsewhere -> route only when no competitor /
# local-dev signal is present.
AMBIGUOUS = [
    r"\bgenie\b",
    r"\bdelta\s+(lake|tables?)\b",
    r"\bmodel\s+serving\b",
    r"\bvector\s+search\b",
    r"\bmlflow\b",
    r"\bpyspark\b",
    r"\bspark\s*\.\s*(sql|read|write|table)\b",
    r"\bserverless\s+(compute|warehouse|migration)\b",
    r"\bmedallion\s+(architecture|tables?)\b",
]

# Competitor platforms + plainly-local dev work -> suppress an AMBIGUOUS match.
# (STRONG matches ignore this list.)
SUPPRESS = [
    r"\bbigquery\b",
    r"\bredshift\b",
    r"\bsynapse\b",
    r"\bgit\s+(commit|push|pull|status|log|diff|branch|rebase|merge|clone|stash)\b",
    r"\b(read|edit|open|write|create|delete)\s+(the\s+|this\s+|a\s+|that\s+)?file\b",
    r"\bunit\s+tests?\b",
    r"\bnpm\b",
    r"\bpip\s+install\b",
    r"\bdocker\b",
    r"\bkubernetes\b",
]

_STRONG = [re.compile(p, re.IGNORECASE) for p in STRONG]
_AMBIGUOUS = [re.compile(p, re.IGNORECASE) for p in AMBIGUOUS]
_SUPPRESS = [re.compile(p, re.IGNORECASE) for p in SUPPRESS]

ROUTING_INSTRUCTION = (
    "[DATABRICKS] This request is Databricks-related. Handle it through the "
    "Databricks skills rather than ad hoc commands. Use the Skill tool to load "
    "`databricks-core` first (the parent skill: CLI, auth, profile selection, "
    "data exploration), then load the product skill that matches the request:\n"
    "- Jobs / Lakeflow / workflows -> databricks-jobs\n"
    "- Pipelines / DLT / Spark Declarative Pipelines -> databricks-pipelines\n"
    "- Apps / AppKit -> databricks-apps\n"
    "- Asset Bundles / DABs / databricks.yml -> databricks-dabs\n"
    "- Model Serving / endpoints -> databricks-model-serving\n"
    "- Lakebase / Postgres -> databricks-lakebase\n"
    "- Vector Search / RAG -> databricks-vector-search\n"
    "- Classic-to-serverless migration -> databricks-serverless-migration\n"
    "Then follow the skill's guidance (it drives the `databricks` CLI). If no "
    "product skill fits, databricks-core alone is enough."
)


def check_prompt(prompt):
    """Return the routing instruction if the prompt is Databricks-related, else None."""
    if not prompt or len(prompt.strip()) < 4:
        return None
    if any(p.search(prompt) for p in _STRONG):
        return ROUTING_INSTRUCTION
    if any(p.search(prompt) for p in _SUPPRESS):
        return None
    if any(p.search(prompt) for p in _AMBIGUOUS):
        return ROUTING_INSTRUCTION
    return None


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
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("{}")
        sys.exit(0)

    try:
        result = check_prompt(extract_prompt(data))
    except Exception:
        result = None

    if result:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": result,
            }
        }))
    else:
        print("{}")
    sys.exit(0)


if __name__ == "__main__":
    main()
