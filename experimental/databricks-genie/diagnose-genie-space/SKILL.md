---
name: diagnose-genie-space
description: "Diagnose Databricks Genie Space quality issues without making changes in Databricks Genie Code Agent mode. Use inside Databricks when users ask for plan-only root-cause analysis, health checks, or explanations for wrong SQL, wrong answers, inconsistent answers, weak Agent-mode reports, source-selection errors, metric, dimension, filter, join, time logic, benchmark size, benchmark coverage, benchmark pruning, monitoring feedback, thumbs up/down trends, review requests, user comments, usage trends, conversation-quality signals, or instruction problems before tuning."
---

# Diagnose Genie Space For Genie Code

Diagnose Genie Space quality without making changes. Use Genie Code Agent mode to inspect the Space, Monitor-tab feedback, workspace assets, Unity Catalog metadata, and bounded read-only SQL output when needed.

## Boundaries

- This skill is plan-only. Do not edit the Genie Space, change benchmarks, run benchmark evaluation, or mutate source data.
- Do not send feedback, create comments, delete conversations, edit generated SQL, save instructions, add benchmarks, or change conversation review status during diagnosis.
- Use only bounded read-only SQL: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema`.
- Ask for missing business intent or expected behavior when workspace evidence is insufficient.
- Prefer concrete evidence over generic best-practice advice.

## Workflow

1. Establish the tuning case:
   - Space name or identifier
   - failing question, if any
   - observed bad behavior
   - expected answer, SQL, evaluation note, or business rule
   - generated SQL, final response, Agent research evidence, or error text, if available
   - whether the issue came from Chat benchmark execution, Agent benchmark execution, or ad hoc use
   - whether the failure is intermittent or repeatable
2. Inspect the Space context:
   - attached tables, views, Metric Views, measures, dimensions, filters, and descriptions
   - relevant column comments, synonyms, prompt matching settings, and hidden fields
   - join specs, SQL snippets, example SQL, text instructions, sample questions, and benchmarks
   - benchmark inventory size, validity, duplicate clusters, coverage categories, and difficulty mix when benchmarks are part of the case
3. Inspect existing Monitor-tab feedback as first-class evidence:
   - weekly digest message volume, active users, thumbs up/down counts or trends, and usage patterns
   - filtered conversations with negative ratings, `Fix it`, `Request review`, needs-review status, repeated questions, or common user phrasing
   - reviewable conversation details: user prompt, Genie response, generated SQL or error, feedback comment, reviewer comments, citations, and whether the issue repeats across conversations
   - privacy limitations: when conversations are private, use only visible prompt, status, rating, timestamp, and trend metadata; state what could not be inspected
   - fallback evidence, when UI access supports it: Genie `Analyze space usage`, Genie conversation APIs, or read-only `system.access.audit` queries for `updateConversationMessageFeedback` and `createConversationMessageComment`
4. Use bounded read-only SQL only when the Space context or feedback evidence does not explain the issue. For Metric View failures, inspect the Metric View definition before dropping down to raw sources.
5. Classify the primary failure and secondary contributors using `references/failure-routing.md`. Treat feedback as evidence that helps cluster failures, not as a separate tuning surface.
6. Recommend the smallest structured tuning change. Prefer metadata, Metric View semantics, prompt matching, joins, snippets, and representative examples before text instructions.
7. Produce a concise diagnostic write-up in chat or notebook output.

## Diagnostic Write-Up

Use this shape:

```markdown
# Genie Space Diagnosis: <space>

## Case
- Question:
- Observed:
- Expected:

## Finding
- Primary failure:
- Contributors:
- Confidence:

## Evidence
- Space context:
- Feedback signals:
- Read-only inspection:
- Limitations:

## Recommended Tuning
| Priority | Surface | Change | Rationale | Validation |
|---|---|---|---|---|

## Health Check
- Ready for tuning:
- Feedback coverage:
- Feedback concerns:
- Benchmark concerns:
- Pruning opportunity:
- Benchmark execution target:
- Highest-risk static issues:
```

End with the next action: either user confirmation needed, a handoff to `optimize-genie-space`, or a user-approved manual edit outside this diagnostic pass.

## Related Skills

- **`optimize-genie-space`** — apply approved benchmark-driven tuning after this plan-only diagnosis.
- **`optimize-genie-query`** — when the issue is query performance/cost rather than answer quality.
- **`databricks-metric-views`** — for Metric View failures, consult `genie-integration.md` (design rules) and `query-patterns.md` (`MEASURE()` query rules, e.g. `MISSING_AGGREGATION`) before dropping to raw sources.
- **`databricks-genie`** — the programmatic / MCP companion (create, query, export, import, migrate) for work outside Genie Code Agent mode.
