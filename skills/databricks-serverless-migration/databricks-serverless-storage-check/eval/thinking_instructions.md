# Thinking Evaluation Criteria — databricks-serverless-storage-check

These layer on top of the four generic L4 dimension judges (Efficiency, Clarity, Recovery, Completeness). They are skill-specific signals that the storage-check skill is being applied correctly, not generic "did the agent answer politely."

## Efficiency

The skill ships an executable preflight scanner. Spending agent tokens to re-derive what the scanner detects is wasted work.

- Prefer running `scripts/preflight.py` against the supplied input (notebook, dir, job-yaml, job-id, or run-id) over reading every file by hand. The whole point of the skill is the scanner.
- For a paste of an error trace (no code), it is correct to skip the scanner and route directly to the pattern catalog plus remediation guide — do not request the user's full notebook just to confirm a symptom that is already diagnostic.
- One read of `SKILL.md` is enough; do not re-read it between every step. Once the pattern is identified, jump to `references/remediation-guide.md` for the fix.
- Do not invoke `databricks` CLI commands unless `--job-id` / `--run-id` modes are explicitly being used; for paste-in cases, the scanner runs locally with no CLI dependency.

## Clarity

Output language has to map cleanly onto the user's mental model of "what happens when I deploy this."

- Name the pattern by ID when the scanner finds one (`FANOUT001`, `FANOUT006`, `ENV001`, etc.) so the user can cross-reference the pattern catalog.
- When recommending a fix, surface the severity tier (Blocker / Warning / Info) explicitly — users need to know whether they can deploy as-is or must change code first.
- Distinguish intra-task scratch (`/local_disk0/tmp` is fine, owned by parent skill) from cross-task handoff (must move off local disk, this skill's domain). Conflating these two is the most common diagnostic error.
- When the parent skill (`databricks-serverless-migration`) is the right destination, say so explicitly and hand off rather than papering over an unmigrated workload.

## Recovery

This skill has well-defined "do not try to fix" boundaries — respect them.

- If the user reports `ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT`, do NOT try to fix it — route to support escalation (this is the `ENV001` info-only finding). Attempts to "fix" this with code changes are off-scope and will fail.
- If `--job-id` mode fails (no CLI, no permission, bad profile), fall back to asking the user to paste the notebook source rather than aborting the entire flow.
- If a fix attempt does not pass the scanner on re-run, re-classify the pattern; do not loop on the same fix. The pattern catalog has six distinct findings — re-running the same Volumes rewrite against a `FANOUT006` hardcoded-path issue is wasted effort.
- When unsure, surface the scanner JSON output verbatim — do not invent severities or pattern IDs.

## Completeness

A correct invocation of this skill produces a small, fixed shape of output regardless of the input mode.

- A complete answer for an error-symptom prompt includes: (1) the pattern name, (2) why it fails on serverless specifically, (3) the recommended fix in priority order (Volumes > Workspace > taskValues), (4) a code snippet for the chosen fix.
- A complete answer for a pre-deploy review includes: scanner output summary (counts per severity), the specific files/lines flagged, and an explicit go/no-go recommendation for the deploy.
- Always invoke the parent `databricks-serverless-migration` skill first when the user has not yet migrated the notebook from classic — do not jump straight to storage-check on an unmigrated workload, because the cross-task handoff antipattern is a deploy-time concern that only matters once single-notebook migration is done.
- For boundary cases (single-notebook, intra-task scratch only), explicitly say "this is not a cross-task antipattern" so the user understands why no fix is needed here. Silence is interpreted as agreement.

## Hierarchy Awareness

This skill is a niche sub-skill of `databricks-serverless-migration` (the parent in the integrated hierarchy). The agent should treat the relationship explicitly:

- Reference the parent skill by name when the user's workload is unmigrated — the parent owns the four-step Ingest → Analyze → Test → Validate lifecycle; this skill plugs in at "Test" for multi-task hardening.
- Do not re-derive single-notebook migration guidance — quote or link to the parent skill instead of duplicating its content.
- When the parent skill's per-task scratch guidance (`/local_disk0/tmp` is fine inside a task) is correct for the case, defer to it; do not override.

## Scanner Output Hygiene

When the preflight scanner is run, the agent must treat its output as authoritative:

- Surface the scanner exit code (0 / 1 / 2) and translate it to a deploy decision (clean / warnings / blockers).
- Quote the scanner's pattern ID and severity verbatim instead of paraphrasing.
- If the scanner exits with `--json`, parse the JSON and present the findings as a small table rather than dumping the raw payload.
- Never silently suppress info-level findings — `ENV001` in particular needs to be surfaced even when other findings are zero, because it routes the user to a different remediation path.
