# Diagnose Genie Agent

Plan-only reference for diagnosing Genie Agent quality issues — inspect the Agent config, feedback signals, Unity Catalog metadata, and bounded read-only SQL to find the root cause of a failure before any tuning. No edits happen here; use [optimize-genie-agent.md](optimize-genie-agent.md) to apply an approved fix.

## Boundaries

- This workflow is plan-only. Do not edit the Genie Agent, change benchmarks, run benchmark evaluation, or mutate source data.
- Do not send feedback, create comments, delete conversations, edit generated SQL, save instructions, add benchmarks, or change conversation review status during diagnosis.
- Use only bounded read-only SQL: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema`.
- Ask for missing business intent or expected behavior when workspace evidence is insufficient.
- Prefer concrete evidence over generic best-practice advice.

## Workflow

### Step 1 — Establish the tuning case ⛔ Gate

**Ask the user for the following before inspecting anything. Do not run any CLI command or query until items 1–3 are provided.**

1. **Agent identifier** — space ID or name of the Agent to diagnose
2. **Failing question** — the exact question (or questions) that produced the bad result
3. **Observed behavior** — what Genie actually returned (wrong SQL, wrong answer, error, empty result, clarification question)
4. **Expected behavior** — what the correct answer or SQL should be (may be inferred from context, but state the assumption)

Also collect if available: generated SQL, final response, error text, whether the failure came from Chat/Agent benchmark or ad hoc use, and whether it is intermittent or repeatable.

### Step 2 — Inspect the Agent context

- Attached tables, views, Metric Views, measures, dimensions, filters, and descriptions
- Relevant column comments, synonyms, prompt matching settings, and hidden fields
- Join specs, SQL snippets, example SQL, text instructions, sample questions, and benchmarks
- Benchmark inventory size, validity, duplicate clusters, coverage categories, and difficulty mix when benchmarks are part of the case

### Step 3 — Inspect Monitor-tab feedback

- Weekly digest message volume, active users, thumbs up/down counts or trends, and usage patterns
- Filtered conversations with negative ratings, `Fix it`, `Request review`, needs-review status, repeated questions, or common user phrasing
- Reviewable conversation details: user prompt, Genie response, generated SQL or error, feedback comment, reviewer comments, citations, and whether the issue repeats
- Privacy limitations: when conversations are private, use only visible prompt, status, rating, timestamp, and trend metadata; state what could not be inspected
- Fallback: read `system.access.audit` for `updateConversationMessageFeedback` and `createConversationMessageComment` events via `databricks experimental aitools tools query`

### Step 4 — Use bounded read-only SQL

Only when Agent context or feedback evidence does not explain the issue. For Metric View failures, inspect the Metric View definition before dropping down to raw sources.

### Step 5 — Classify the failure

Identify the primary failure and secondary contributors — see [Failure Classes](#failure-classes) and [Routing Order](#routing-order). Treat feedback as evidence for clustering failures, not as a tuning surface (see [Feedback Routing](#feedback-routing)).

### Step 6 — Recommend the smallest fix

Prefer metadata, Metric View semantics, prompt matching, joins, snippets, and representative examples before text instructions.

### Step 7 — Produce a diagnostic write-up

See [Diagnostic Write-Up](#diagnostic-write-up) for the required shape.

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

End with the next action: either user confirmation needed, a handoff to [optimize-genie-agent.md](optimize-genie-agent.md), or a user-approved manual edit outside this diagnostic pass.

## Evidence To Gather

- Relevant table, view, and Metric View identifiers and descriptions.
- Metric View measures, dimensions, filters, joins, time dimensions, comments, display names, synonyms, and formatting.
- Table and column descriptions, synonyms, prompt matching settings, and hidden fields.
- Join specs and comments for raw tables exposed together.
- SQL snippets, example SQL, SQL functions, and text instructions.
- Similar benchmark questions, SQL answers, evaluation notes, and execution mode, if present.
- Benchmark inventory size, duplicate clusters, coverage categories, difficulty levels, and whether the set is too small, too narrow, too easy, or too large for practical iteration.
- Monitor-tab feedback signals: thumbs up/down trends, negative ratings, `Fix it`, `Request review`, needs-review conversations, feedback comments, reviewer comments, repeated user phrasing, generated SQL or error text from reviewable conversations, and private-conversation limitations.
- Agent-mode final reports, research steps, supporting query outputs, citations, tables, charts, and assessment notes when applicable.
- Read-only checks for data types, categorical values, null rates, cardinality, join grain, and Metric View query behavior when needed.

## Feedback Routing

Use feedback as evidence for clustering failures, not as a tuning surface. Do not recommend changing feedback, comments, review status, or conversation history as the fix.

Translate feedback patterns into the existing repair levers:

- Repeated negative feedback on the same source, Metric View, measure, dimension, filter, join, or time pattern: classify the underlying wrong source, semantic model, filter, join, business logic, or time logic failure before choosing the fix.
- Review requests with missing SQL, wrong SQL, failed SQL, or unsupported final answers: inspect the generated SQL/error and route to the smallest structured surface that would prevent the same failure.
- User comments that explain a business term, synonym, category label, KPI definition, fiscal period, or expected result shape: treat the comment as business-intent evidence and encode the durable rule in metadata, Metric View semantics, prompt matching, snippets, representative examples, or short global instructions.
- High negative-feedback volume with weak or missing benchmark coverage: recommend benchmark repair or benchmark additions before benchmark-driven tuning, and use feedback clusters to choose representative benchmark candidates.
- Feedback that contradicts passing benchmark results: check whether benchmarks are stale, too narrow, too easy, missing Agent evaluation notes, or failing to cover real user phrasing before trusting the benchmark signal.
- Private conversations or unavailable Monitor details: use visible prompt, status, rating, timestamp, and trend metadata only; lower confidence and state the limitation.

## Failure Classes

> Diagnose: identify **what is failing and why** (symptom → cause). For **which lever to apply** (cause → fix), see [optimize-genie-agent.md](optimize-genie-agent.md).

### Wrong Data Source Or Field

Symptoms: wrong table, Metric View, column, measure, or dimension; raw table chosen when a governed Metric View should answer; important source omitted; repeated feedback says Genie used the wrong data source or field.

### Wrong Metric View Measure, Dimension, Scope, Or Grain

Symptoms: wrong `MEASURE()` call, invalid grouping, missed persistent filter, wrong time dimension, incorrect semiadditive or rolling logic; feedback clusters around a governed KPI, grouping, scope, or grain mismatch.

### Wrong Filter Value

Symptoms: invalid category, wrong code or label, casing mismatch, misunderstood business term; user feedback names the expected label, code, synonym, or filter scope.

### Wrong Join

Symptoms: missing table, wrong key, duplicate rows, changed grain, unsupported bridge or self-join; feedback or review comments mention duplicated rows, missing related records, or impossible cross-source combinations.

### Business Logic Or Time Logic Error

Symptoms: wrong numerator, denominator, aggregation, fiscal period, date boundary, rolling window, ranking, or answer shape; feedback supplies the expected KPI definition, time convention, ranking rule, or result shape.

### Weak Agent-Mode Report

Symptoms: incomplete research plan, too few supporting queries, weak evidence, unsupported causal claims, missing citations, missing supporting table/chart, poor synthesis, missing caveats, or review requests for unsupported Agent-mode conclusions.

### Benchmark Ground Truth Problem

Symptoms: invalid SQL answer, missing SQL for a deterministic Chat benchmark, unclear or missing evaluation note for an Agent-style benchmark, a multi-query analysis question forced into a single SQL answer, or benchmark pass rates that conflict with recent negative user feedback on the same pattern.

### Benchmark Set Too Large Or Redundant

Symptoms: too many questions for practical benchmark iteration, many near-duplicates that only swap dates or category literals, one source or metric overweighted, too many trivial lookup questions, repeated variants that obscure root-cause patterns, or feedback clusters showing important real user patterns missing from the benchmark.

### Instruction Conflict Or Overload

Symptoms: examples, snippets, benchmarks, feedback-derived assumptions, or text instructions conflict; text instructions contain a long source-specific rulebook.

## Health Signals

Treat these as blockers or warnings during diagnosis:

- Too many overlapping data sources.
- Generic table, Metric View, or column descriptions.
- Important categorical filters without prompt matching.
- Raw tables exposed together with missing joins.
- Example SQL that copies benchmark questions.
- High negative-feedback or review-request volume for patterns with weak benchmark coverage.
- Feedback comments that repeatedly define business terms missing from metadata, Metric Views, prompt matching, snippets, examples, or short global instructions.
- Passing benchmark results that contradict recent negative feedback on equivalent real user questions.
- Benchmark set too small, too narrow, too easy, too redundant, too large for practical iteration, missing checked SQL answers for deterministic Chat execution, or missing evaluation notes for Agent-style questions.
- Text instructions containing source-specific SQL logic.

## CLI Reference

The Monitor tab's aggregate dashboards (thumbs/trends/digest) are UI-only — substitute per-item and audit-log sources below and **state the limitation** (no trend/digest view) in the write-up.

| Diagnostic input | CLI |
|------------------|-----|
| Agent config (Step 2) | `databricks genie get-space SPACE_ID -o json` |
| Conversation evidence (Step 3) | `databricks genie list-conversations SPACE_ID`, `list-conversation-messages`, `list-conversation-comments`, `list-message-comments` |
| Feedback signals (Step 3) | **No aggregate substitute.** For raw events, read `system.access.audit` for `updateConversationMessageFeedback` and `createConversationMessageComment` via `databricks experimental aitools tools query` |
| Reproduce a failing question | `databricks genie start-conversation` / `create-message` + `get-message` (read the generated SQL/error) |
| Read-only data inspection (Step 4) | `databricks experimental aitools tools discover-schema` / `query` |

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

This workflow stays **plan-only** regardless of mechanism: do not send feedback, edit SQL, or change review status with these commands.

## Applying a Fix

**Recommendation-first:** do not run mutating actions (`update-space`, `ALTER`, `OPTIMIZE`, liquid clustering, warehouse changes) until the user approves. Diagnose with read-only queries only.

**Wrong filter values** (Genie filters on a value that returns nothing — e.g. asking for `cancelled` when the column stores a different code or casing): fix with prompt matching / synonyms mapping the user's term to the actual categorical value, not a hardcoded text instruction.

Once the root cause is identified and the user approves:

```bash
# Edit genie_agent.json locally, then push the fix
databricks genie update-space SPACE_ID --json "{\"serialized_space\": $(cat genie_agent.json | jq -c '.' | jq -Rs '.')}"
```

For benchmark-driven iterative tuning after a fix, hand off to [optimize-genie-agent.md](optimize-genie-agent.md).

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Slow answers / query timeouts | Size up the warehouse attached to the agent; simplify or pre-aggregate tall source tables |
| Wrong or empty answers | Diagnose root cause above; add `example_question_sqls` and `text_instructions` |

## See Also

- **[optimize-genie-agent.md](optimize-genie-agent.md)** — apply approved benchmark-driven tuning after this plan-only diagnosis.
- **`databricks-metric-views`** — for Metric View failures, consult this skill (design rules and `MEASURE()` query rules, e.g. `MISSING_AGGREGATION`) before dropping to raw sources.
