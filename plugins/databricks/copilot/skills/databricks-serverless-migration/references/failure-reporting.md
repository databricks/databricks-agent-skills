# Failure Reporting — Filing a Migration Skill Issue

Reference for the Failure Reporting Protocol in `SKILL.md`. Read this when migration could not complete and you need to file a GitHub issue with anonymized context.

## Why this exists

The skill detects ~40 patterns across 7 categories today. Every new pattern in the wild that the skill doesn't recognize, every fix that didn't work, every Cat 3 blocker surfaced late — these are the inputs that close detection gaps. Reports are opt-in and never auto-submitted; the user owns the data.

## Redaction checklist (apply before writing the JSON)

Walk every string-typed field in the report and confirm none of these appear. If anything matches, drop the field rather than partially redacting.

- **Identifiers**: emails, employee names, Slack user/channel IDs (`U…`, `C…`), customer / company names, account IDs, workspace IDs.
- **Paths and URLs**: `dbfs:/`, `/dbfs/`, `s3://`, `abfss://`, `gs://`, `wasbs://`, notebook paths, workspace URLs (`*.cloud.databricks.com`, `adb-*.azuredatabricks.net`), git remote URLs.
- **Internal references**: `go/` links, internal codenames not in public docs, Confluence page IDs, Google Doc IDs (`1[A-Za-z0-9_-]{20,}`), Slack channel names, PROD-* / SEV-* / SC-* tickets.
- **Catalog / schema / table / column names** from the analyzed notebook. Pattern IDs from this skill's catalog are fine; literals from the workload are not.
- **Credentials**: tokens, API keys, connection strings, JDBC URLs, service principal IDs, secret scope names.
- **Stack frame contents**: hash the top 3 frames with SHA-256, never include the frames themselves.
- **Error messages**: store only the `final_error_category` enum, never the raw error text.

If a field is ambiguous, drop it. `notebook_characteristics` is the safe surface for workload metadata — do not invent new fields here without first updating this checklist and the schema in `SKILL.md`.

## Building the pre-filled GitHub issue URL

GitHub's `issues/new` endpoint accepts URL-encoded `title=` and `body=` query parameters. Combined with the `template=migration-feedback.md` parameter, you can produce a one-click link that drops the user straight into a pre-filled issue.

### Title format

```
[migration-skill] <final_error_category> in <failure_phase> phase
```

Examples:
- `[migration-skill] custom_data_source in migrate phase`
- `[migration-skill] unknown_api in analyze phase`
- `[migration-skill] jvm_access in test phase`

### Body skeleton

Use this Markdown template. Replace the placeholders, then URL-encode the whole thing.

```markdown
## Category

- [x] Failure report (see JSON below)

## Pre-submission checklist

- [x] I reviewed the JSON below and confirmed no PII slipped through

## Environment

- Skill version: <skill_version from report>
- Agent: Claude Code / Cursor / other
- Databricks Runtime of source workload: <databricks_runtime_source from report>

## Description

Migration failed in the `<failure_phase>` phase. Final error category:
`<final_error_category>`. Retry count: <retry_count>.

## Failure report JSON

<details>
<summary>failure-&lt;timestamp&gt;.json</summary>

```json
<paste the full report JSON here>
```

</details>
```

### URL-encoding

Encode the title and body with standard `application/x-www-form-urlencoded` rules (space → `%20`, newline → `%0A`, `#` → `%23`, `<` → `%3C`, `>` → `%3E`, backtick → `%60`, `[` → `%5B`, `]` → `%5D`, etc.). In Python:

```python
import urllib.parse
url = (
    "https://github.com/databricks/databricks-agent-skills/issues/new"
    "?template=migration-feedback.md"
    f"&title={urllib.parse.quote(title)}"
    f"&body={urllib.parse.quote(body)}"
)
```

GitHub accepts URLs up to ~8 KB. The failure report JSON is well under 2 KB after redaction, so the encoded URL fits.

### Worked example

Title: `[migration-skill] custom_data_source in migrate phase`

Body (abridged):

```markdown
## Category
- [x] Failure report (see JSON below)
## Environment
- Skill version: 0.1.0
- Agent: Claude Code
- Databricks Runtime: 14.3.x-scala2.12
## Description
Migration failed in the `migrate` phase. Final error category: `custom_data_source`. Retry count: 5.
## Failure report JSON
<details><summary>failure-2026-05-12T08-00-00Z.json</summary>

```json
{
  "report_version": "1.1",
  "report_id": "5b7c8e8e-...",
  "skill_version": "0.1.0",
  "failure_phase": "migrate",
  "detected_patterns": [{"category": "E", "pattern_id": "custom_jar_datasource", "count": 1}],
  "attempted_fixes": [],
  "final_error_category": "custom_data_source",
  "final_error_signature": "a91b5e...",
  "retry_count": 5,
  "notebook_characteristics": {"lines_of_code": 73, "language": "python", "uses_streaming": false, "uses_ml_libraries": false, "databricks_runtime_source": "14.3.x-scala2.12"}
}
\`\`\`

</details>
```

Encoded URL (truncated for readability):

```
https://github.com/databricks/databricks-agent-skills/issues/new?template=migration-feedback.md
  &title=%5Bmigration-skill%5D%20custom_data_source%20in%20migrate%20phase
  &body=%23%23%20Category%0A-%20%5Bx%5D%20Failure%20report...
```

## CLI alternative (`gh`)

If the user has the GitHub CLI on their PATH (`which gh`), offer:

```bash
gh issue create \
  --repo databricks/databricks-agent-skills \
  --title "[migration-skill] <final_error_category> in <failure_phase> phase" \
  --body-file ~/.databricks-migration-skill/reports/failure-<timestamp>.json \
  --label migration-skill
```

This works but skips the issue template's checklist sections. Prefer the browser URL when the user is unfamiliar with the contribution flow.

## What we do with reports

Reports are triaged by the skill maintainers listed in the repo's [CODEOWNERS](https://github.com/databricks/databricks-agent-skills/blob/main/.github/CODEOWNERS) file, and used to:

1. Prioritize new patterns to add to `references/compatibility-checks.md`
2. Identify fixes that don't work in practice and need correction
3. Spot Cat 3 blockers that need clearer up-front detection so users hit them in analyze rather than migrate

Reports never leave the public GitHub issues thread. We do not aggregate them externally.

## Troubleshooting

- **The pre-filled URL is too long for the browser** — GitHub caps at ~8 KB. If the report is unusually large (many `attempted_fixes`), fall back to the `gh` CLI command, or open the issue manually and paste the JSON in.
- **The browser opens an empty issue** — the `template=` parameter requires the template file to exist in the repo's `.github/ISSUE_TEMPLATE/`. If it's missing, file with the title and body only; the maintainers will update the template.
- **The user wants to share more context** — that's fine, but ask them to add it as a follow-up comment, not in the initial report body. Initial body should be the anonymized JSON only.

### Decision tree: when to offer to file an issue

**Offer to file a GitHub issue any time the workload cannot be fully migrated to serverless as-is.** Reports from "known" patterns (R, Scala, custom JAR data sources, JVM access, third-party connectors) are just as valuable as reports from unknown patterns — they tell maintainers which gaps users hit most often, which drives prioritization.

Concretely, ALWAYS offer if **any** of these is true:

1. **Workload contains any Category 3 (classic-only) blocker** — R, Scala notebook cells, custom JAR data sources, JVM/Py4J access, third-party connectors without serverless equivalents, native binary dependencies, etc. The fact that the pattern is "documented as Cat 3" is not a reason to skip the offer.
2. **Retries exhausted** — `retry_count >= max_retries` (typically 5) and final status is FAILED
3. **Unknown pattern** — a classic-compute construct was detected that isn't in the skill's catalog
4. **Fix didn't resolve** — a known fix was applied but the workload still fails on serverless
5. **Explicit request** — the user invokes `/migration-report`

**Do NOT offer to file** only when:

- The migration succeeded fully (even after retries), or
- The workload is already serverless-compatible and required no changes.

### How to generate the report

Write a JSON file to `~/.databricks-migration-skill/reports/failure-<ISO-timestamp>.json`. Create the directory if it doesn't exist.

**Schema** (strictly follow — no free-text code or identifiers):

```json
{
  "report_version": "1.1",
  "report_id": "<uuid-v4>",
  "skill_version": "<from SKILL.md frontmatter metadata.version>",
  "timestamp": "<ISO 8601 UTC>",
  "failure_phase": "analyze | migrate | test | validate",
  "detected_patterns": [
    {"category": "A", "pattern_id": "rdd_parallelize", "count": 3}
  ],
  "attempted_fixes": [
    {"pattern_id": "rdd_parallelize", "fix_applied": "<fix_id>", "attempt_number": 1, "outcome": "failed"}
  ],
  "final_error_category": "unknown_api | missing_library | data_access | permission | custom_data_source | jvm_access | unsupported_language | other",
  "final_error_signature": "<SHA256 of top 3 stack frames, NOT the frames themselves>",
  "retry_count": 5,
  "total_duration_seconds": 245,
  "notebook_characteristics": {
    "lines_of_code": 180,
    "language": "python | sql | scala | r",
    "uses_streaming": false,
    "uses_ml_libraries": true,
    "databricks_runtime_source": "<DBR version only, no cluster identifiers>"
  }
}
```

### What the report MUST NOT contain

Hard requirement — the report must be safe to share publicly on GitHub Issues:

- **No code content** — pattern IDs only (e.g., `rdd_parallelize`), never code snippets, function bodies, or even single-line examples
- **No file paths** — no notebook names, directory paths, workspace URLs, or DBFS paths
- **No error message text** — only the error category enum and a hashed signature
- **No identifiers** — no table names, column names, catalog names, schema names, secret scope names, user emails, workspace IDs, or account IDs
- **No internal Databricks references** — no Databricks employee names, internal codenames (e.g., product code names not in public docs), `go/` links, Confluence page IDs, Google Doc IDs, Slack user or channel IDs (`U…`, `C…`), PROD-* / SEV-* / SC-* ticket numbers
- **No customer references** — no company names, product names of customer systems, or anything that would identify the workspace's owning organization
- **No credentials** — no tokens, API keys, connection strings, JDBC URLs, or service principal IDs
- **No data descriptions** — no column value samples, row counts tied to specific tables, or schema fingerprints beyond the `notebook_characteristics` fields

### Anonymization safety pass

Before writing the report, scan every string field against this pattern checklist. If any pattern matches, **drop the offending field** (do not redact partially — empty string is safer than risking leakage):

| Pattern | What to scrub |
|---------|---------------|
| `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}` | Email addresses |
| `dbfs:/`, `/dbfs/`, `s3://`, `abfss://`, `gs://`, `wasbs://` | Cloud storage paths |
| `https?://[a-z0-9-]+\.cloud\.databricks\.com`, `https?://adb-\d+\.\d+\.azuredatabricks\.net` | Workspace URLs |
| `U[A-Z0-9]{8,}`, `C[A-Z0-9]{8,}` | Slack user / channel IDs |
| `\bgo/[a-z0-9-]+\b` | go/ links |
| `\b(PROD|SEV|SC|JIRA)-\d+\b` | Internal ticket IDs |
| `[0-9a-f]{20,}` (heuristic) | Likely doc/file/workspace IDs |
| Catalog/schema/table name literals from the analyzed notebook | Drop and replace with `"<redacted>"` |

The `notebook_characteristics` fields are the only safe surface for workload metadata. Do not add new fields without expanding this checklist.

### Deterministic post-serialization scrub (required)

The redaction above happens at generation time and depends on the model applying every rule. That is not enough on a path that ends in a public GitHub issue. After serializing the report to JSON:

1. **Re-run the MUST-NOT-CONTAIN regex set as a literal text search over the final JSON file**. Match the same patterns from the table above, plus any catalog/schema/table names that were referenced in the analyzed notebook.
2. **If any pattern matches, refuse to display the pre-filled URL or the `gh issue create` command**. Print the local file path, list the patterns that matched, and tell the user to redact the file manually before sharing.
3. Only when the post-serialization scrub is clean may the pre-filled URL be shown.

This deterministic check is non-negotiable; do not skip it even when you are confident the generation-time redaction was applied.

### After generating the report — output template

When the decision tree above says "offer to file", the **default output is local-only**. The pre-filled URL and `gh` command are shown only after the user has acknowledged the local file and the post-serialization scrub (see above) is clean.

Default response — always include:

1. The local report file path (`~/.databricks-migration-skill/reports/failure-<timestamp>.json`, with `<timestamp>` filled in).
2. A one-line note that the report contains pattern IDs and notebook characteristics only, no code or identifiers.
3. A prompt: *"This is a draft. Open the file, confirm the redaction looks right, then tell me to share it. I'll generate the pre-filled GitHub issue URL once you've confirmed."*

Only after the user explicitly confirms (e.g. *"share it"*, *"file the issue"*, *"looks good"*) AND the deterministic post-serialization scrub above returned clean, then produce:

- **Option A** — a complete pre-filled `https://github.com/databricks/databricks-agent-skills/issues/new?template=migration-feedback.md&title=<…>&body=<…>` URL, both parameters URL-encoded.
- **Option B** — the literal `gh issue create --repo databricks/databricks-agent-skills …` command, body-file pointing at the local report.

Do not produce the URL or `gh` command in the same turn as the file write. Two turns: write + offer review, then publish after explicit confirmation.

Use this exact wrap-up template, replacing `<…>` placeholders:

```
Migration could not complete. A failure report has been generated at:

  ~/.databricks-migration-skill/reports/failure-<timestamp>.json

The report contains anonymized diagnostic data (detected pattern IDs, error
category, retry count, notebook characteristics) and no code content or PII.
Submission is optional and opt-in.

To help improve this skill, file the report as a GitHub issue:

  Option A — One-click in browser (pre-filled):
    <PREFILLED_ISSUE_URL>

  Option B — From the terminal (if you have the GitHub CLI installed):
    gh issue create \
      --repo databricks/databricks-agent-skills \
      --title "<TITLE>" \
      --body-file ~/.databricks-migration-skill/reports/failure-<timestamp>.json \
      --label migration-skill

Before submitting, please open the JSON and confirm nothing sensitive
slipped through. We never transmit reports automatically.
```

Build `<PREFILLED_ISSUE_URL>` like this:

1. **Title**: `[migration-skill] <final_error_category> in <failure_phase> phase`
   Example: `[migration-skill] custom_data_source in migrate phase`
2. **Body**: the issue template's markdown skeleton (Category, Environment, Description, Failure report JSON fenced in ` ```json `) with the report JSON inlined.
3. **URL-encode** both title and body (`%20` for spaces, `%23` for `#`, `%0A` for newline, etc.).
4. **Final URL**:
   `https://github.com/databricks/databricks-agent-skills/issues/new?template=migration-feedback.md&title=<URL-encoded title>&body=<URL-encoded body>`

If your runtime cannot actually write the file (sandboxed, no filesystem write), still show the path the file WOULD be at and produce Options A and B. The user can write the JSON to disk themselves.

The full recipe with a worked example is in [Failure Reporting](references/failure-reporting.md).

**Never transmit the report automatically.** The user owns their data and must review before sharing. If the user declines, do not press them — log the local report path and move on.
