---
name: Migration Skill Feedback
about: Report a bug, suggest a pattern, or submit a failure report for the serverless migration skill
title: "[migration-skill] "
labels: migration-skill
assignees: ''
---

<!--
Before submitting, please review the PII guidelines in README.md:
- Remove customer code — use minimal reproducible examples
- Remove credentials, workspace URLs, catalog names, user emails
- Remove customer-identifying information
-->

## Category

<!-- Check one -->

- [ ] Pattern not detected (the skill missed a classic-compute construct)
- [ ] Wrong fix suggested (the fix didn't work or was incorrect)
- [ ] Migration succeeded but output differs (code runs, data is different)
- [ ] Documentation unclear
- [ ] Failure report (attach JSON from `~/.databricks-migration-skill/reports/`)
- [ ] New pattern suggestion

## Pre-submission checklist

- [ ] I have removed all customer code and replaced with a minimal reproducible example
- [ ] I have removed all credentials, tokens, and secret scope names
- [ ] I have removed all workspace URLs, catalog names, and user emails
- [ ] I have removed any customer-identifying information

## Environment

- Skill version: <!-- e.g., v0.2.0 (check SKILL.md metadata.version) -->
- Agent: <!-- e.g., Claude Code, Cursor, custom -->
- Model: <!-- e.g., claude-sonnet-4-6 -->
- Databricks Runtime of source workload: <!-- e.g., 14.3 LTS -->

## Description

<!--
What happened? What did you expect to happen?
Include a minimal reproducible example if relevant.
-->

## Minimal reproducible example

<!-- Replace with a 5-10 line snippet that shows the pattern -->
```python
# Classic compute code (minimal example, no customer data)
```

## Expected migration

<!-- What the skill should have done -->

## Actual migration

<!-- What the skill actually did, if anything -->

## Failure report (optional)

<!--
If you're attaching a failure report JSON:
1. Open it and confirm no PII is present
2. Paste the contents below in a code block, OR upload as a file attachment
-->

<details>
<summary>Failure report JSON</summary>

```json
<!-- paste report contents here after reviewing for PII -->
```

</details>

## Additional context

<!-- Any other context, screenshots, or information -->
