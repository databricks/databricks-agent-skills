---
name: diagnose-genie-agent
description: "Diagnose Databricks Genie Agent quality issues without making changes (plan-only). Works inside Databricks Genie Code (native UI) or from an external agent via the Databricks CLI/MCP. Use for root-cause analysis, health checks, or explanations for wrong SQL, wrong answers, inconsistent answers, weak Agent-mode reports, source-selection errors, metric, dimension, filter, join, time logic, benchmark size, benchmark coverage, benchmark pruning, monitoring feedback, thumbs up/down trends, review requests, user comments, usage trends, conversation-quality signals, or instruction problems before tuning."
---

# Diagnose Genie Agent

Diagnose Genie Agent quality without making changes — inspect the Agent config, feedback signals, Unity Catalog metadata, and bounded read-only SQL to find the root cause of a failure before any tuning.

> **Naming:** "Genie Agent" is the current name for what was formerly called a **Genie Space**. The two terms are interchangeable — "Genie Space" still appears in the Databricks UI, CLI (`create-space`, `serialized_space`, …), and API, and remains valid for backward compatibility.

## Execution Context

This skill runs in either of two contexts. **The plan-only workflow below is identical; only the *mechanism* differs.**

- **(a) Inside Databricks Genie Code (native UI)** — inspect the Agent, the **Monitor tab** (thumbs up/down trends, weekly digests, "Fix it"/"Request review"), workspace assets, and run read-only SQL.
- **(b) Outside Databricks via CLI/MCP** (e.g. Claude Code) — use the Databricks CLI as the default, MCP where available. The Monitor-tab *aggregates* are UI-only; substitute per-conversation reads and `system.access.audit` events, and state that limitation. See [Mechanism Map](#mechanism-map-cli--mcp).

**Prerequisites (context b):** authenticated `databricks` CLI, a running SQL warehouse with `CAN USE`, and `SELECT` on `system.access.audit` for the audit-log substitute.

## Boundaries

- This skill is plan-only. Do not edit the Genie Agent, change benchmarks, run benchmark evaluation, or mutate source data.
- Do not send feedback, create comments, delete conversations, edit generated SQL, save instructions, add benchmarks, or change conversation review status during diagnosis.
- Use only bounded read-only SQL: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema`.
- Ask for missing business intent or expected behavior when workspace evidence is insufficient.
- Prefer concrete evidence over generic best-practice advice.

## Workflow

1. Establish the tuning case:
   - Agent name or identifier
   - failing question, if any
   - observed bad behavior
   - expected answer, SQL, evaluation note, or business rule
   - generated SQL, final response, Agent research evidence, or error text, if available
   - whether the issue came from Chat benchmark execution, Agent benchmark execution, or ad hoc use
   - whether the failure is intermittent or repeatable
2. Inspect the Agent context:
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
4. Use bounded read-only SQL only when the Agent context or feedback evidence does not explain the issue. For Metric View failures, inspect the Metric View definition before dropping down to raw sources.
5. Classify the primary failure and secondary contributors using `references/failure-routing.md`. Treat feedback as evidence that helps cluster failures, not as a separate tuning surface.
6. Recommend the smallest structured tuning change. Prefer metadata, Metric View semantics, prompt matching, joins, snippets, and representative examples before text instructions.
7. Produce a concise diagnostic write-up in chat or notebook output.

## Diagnostic Write-Up

Use this shape:

```markdown
# Genie Agent Diagnosis: <space>

## Case
- Question:
- Observed:
- Expected:

## Finding
- Primary failure:
- Contributors:
- Confidence:

## Evidence
- Agent context:
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

End with the next action: either user confirmation needed, a handoff to `optimize-genie-agent`, or a user-approved manual edit outside this diagnostic pass.

## Mechanism Map (CLI / MCP)

Per-step mapping for context (b). Inside Databricks the Monitor tab is first-class evidence; outside, those aggregate dashboards are **UI-only** — substitute the per-item and audit-log sources below and **state the limitation** (no trend/digest view) in the write-up.

| Diagnostic input | Native (Genie Code) | CLI substitute (default outside) | MCP substitute (if available) |
|------------------|---------------------|----------------------------------|-------------------------------|
| Agent config (Step 2) | native editor | `databricks genie get-space SPACE_ID -o json` | `manage_genie(action="get"/"export")` |
| Conversation evidence (Step 3) | Monitor tab conversation list | `databricks genie list-conversations SPACE_ID`, `list-conversation-messages`, `list-conversation-comments`, `list-message-comments` | — |
| Feedback signals (Step 3) | thumbs/trends/digest in Monitor tab | **No aggregate substitute.** For raw events, read `system.access.audit` for `updateConversationMessageFeedback` and `createConversationMessageComment` via `databricks experimental aitools tools query` | `execute_sql` over `system.access.audit` |
| Reproduce a failing question | ad-hoc in Agent UI | `databricks genie start-conversation` / `create-message` + `get-message` (read the generated SQL/error) | `ask_genie` |
| Read-only data inspection (Step 4) | notebook/SQL editor | `databricks experimental aitools tools discover-schema` / `query` | `get_table_stats_and_schema`, `execute_sql` |

Audit-log substitute for feedback events (replace placeholders, keep the window narrow):

```sql
SELECT event_time, user_identity.email, action_name, request_params
FROM system.access.audit
WHERE service_name = 'genie'
  AND action_name IN ('updateConversationMessageFeedback', 'createConversationMessageComment')
  AND event_date >= current_date() - INTERVAL 30 DAYS
ORDER BY event_time DESC
LIMIT 200;
```

This skill stays **plan-only** regardless of mechanism: do not send feedback, edit SQL, or change review status with these commands.

## Related Skills

- **`optimize-genie-agent`** — apply approved benchmark-driven tuning after this plan-only diagnosis.
- **`optimize-genie-query`** — when the issue is query performance/cost rather than answer quality.
- **`databricks-metric-views`** — for Metric View failures, consult `genie-agent-integration.md` (design rules) and `query-patterns.md` (`MEASURE()` query rules, e.g. `MISSING_AGGREGATION`) before dropping to raw sources.
- **`databricks-genie`** — the parent orchestration hub for the full Agent lifecycle (create, query, export, import, migrate) and the verified `serialized_space` field schema; route there for the end-to-end CLI/MCP command surface.
