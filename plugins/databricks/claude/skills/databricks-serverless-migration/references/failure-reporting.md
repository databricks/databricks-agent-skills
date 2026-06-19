# Failure Reporting — Filing a Migration Skill Issue

Reference for the [Failure Reporting Protocol](../SKILL.md#failure-reporting-protocol) in `SKILL.md`. Read this when migration could not complete and you need to file a GitHub issue with anonymized context.

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
