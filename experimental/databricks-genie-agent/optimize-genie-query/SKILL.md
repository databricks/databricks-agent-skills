---
name: optimize-genie-query
description: "Run approved benchmark-driven Databricks Genie Agent query performance triage using Query History, Query Profile, table layout, and SQL warehouse evidence. Works inside Databricks Genie Code (native UI) or from an external agent via the Databricks CLI/REST. Use to investigate slow, expensive, queued, spilling, full-scan, poorly pruned, high-latency, high-cost, or warehouse-constrained Genie Agent benchmark queries while preserving answer correctness."
---

# Optimize Genie Query

Analyze Genie Agent benchmark-generated SQL from a performance and cost lens. Start from benchmark questions, launch native benchmark execution only after explicit user approval, then triage query performance evidence. Validate every signal against Query Profile / query metrics, generated SQL, table layout, SQL warehouse evidence, Unity Catalog metadata, system tables, and bounded read-only SQL output as needed.

> **Naming:** "Genie Agent" is the current name for what was formerly called a **Genie Space**. The two terms are interchangeable — "Genie Space" still appears in the Databricks UI, CLI (`create-space`, `serialized_space`, …), and API, and remains valid for backward compatibility.

## Execution Context

This skill runs in either of two contexts. **The diagnostic workflow below is identical; only the *mechanism* differs.**

- **(a) Inside Databricks Genie Code (native UI)** — use **Query History Insights** (Private Preview) as the primary triage signal and the `/analyze`·`/optimize` entry points, validated against Query Profile.
- **(b) Outside Databricks via CLI/REST** (e.g. Claude Code) — pull query rows and Query-Profile-grade metrics from the **Query History REST API** (`databricks query-history list --include-metrics`). Two surfaces are UI-only: pre-computed **insight labels** (derive them yourself via the Issue Taxonomy) and the **`/analyze`·`/optimize` rewrite** (generate + `EXPLAIN`-validate yourself). See [Mechanism Map](#mechanism-map-cli--mcp).

**Prerequisites (context b):** authenticated `databricks` CLI, `SELECT` on `system.query.history` / `system.compute.*` for the system-table templates, and access to the warehouse that ran the queries.

## Hard Rules

- This skill is diagnostic and recommendation-first. It may launch native benchmark runs only after explicit user approval. Do not edit the Genie Agent, benchmark definitions, SQL warehouse settings, Unity Catalog objects, source schemas, or source data.
- Use only bounded read-only SQL: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, `information_schema`, and system-table reads.
- Do not run `ALTER`, `OPTIMIZE`, `ANALYZE`, `VACUUM`, `CREATE`, `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, table rewrites, warehouse edits, benchmark definition edits, or Genie Agent edits.
- Preserve answer correctness. If the generated SQL is semantically wrong, stop performance tuning and hand off to `diagnose-genie-agent` or `optimize-genie-agent`.
- Treat Query performance insights as a Private Preview feature: absent, hidden, or unavailable Insights are limitations, not evidence that performance is healthy.
- Treat cache hits, missing Query Profile access, private or encrypted system-table fields, unavailable system tables, and incomplete query history as limitations.
- Prefer concrete insight, query, profile, warehouse, and table-layout evidence over generic optimization advice.
- Use Query History's Genie Code `/analyze` or `/optimize` entry point for an insight-backed query when available, but validate the result before accepting any recommendation.
- Recommend mutating actions such as `ANALYZE`, predictive optimization, liquid clustering, `OPTIMIZE`, materialized views, source rewrites, Agent edits, benchmark edits, or warehouse scaling only as user-approved follow-up work outside this skill.

## Workflow

1. Establish the performance case:
   - Agent name or identifier
   - benchmark target, execution mode when relevant, and benchmark question IDs or question text
   - explicit user approval before launching a native benchmark run; otherwise use an existing completed run or visible Query History
   - SQL warehouse ID or name
   - benchmark run window or relevant Query History time window
   - latency, queue-time, cost, spill, scan, or concurrency goal
   - expected unchanged answer shape or business result
2. Launch or locate benchmark evidence:
   - if approved, run the narrowest useful native benchmark for the target questions and wait until benchmark executions appear in Query History
   - if benchmark execution is not approved, use the latest completed benchmark run or existing Query History rows
   - record benchmark run identity, time window, target questions, user, warehouse, and any incomplete or delayed query-history visibility
3. Open Query History and filter to benchmark-generated Genie queries:
   - filter by benchmark window, Agent, warehouse, user, statement ID, query source, or available tags
   - prioritize rows with the Insights column populated or a lightbulb/performance insight indicator
   - capture statement ID, question, status, warehouse ID, duration breakdown, insight labels, statement preview, result cache status, scan metrics, spill, queue time, and query source
4. Use Insights as the primary triage signal when available:
   - click the Query History Genie Code `/analyze` or `/optimize` action for an insight-backed query when the UI exposes it
   - preserve the prefilled prompt context, but treat Genie Code's rewrite or recommendation as a candidate, not proof
   - group repeated benchmark queries by insight label, source object, SQL shape, warehouse, and benchmark question pattern
5. Fall back when Insights are absent or inaccessible:
   - if the Insights column is missing, preview-gated, empty, delayed, or unavailable, use `references/query-optimization-guide.md` and inspect Query History, Query Profile, table layout, Agent context, and warehouse evidence manually
   - state the preview/access limitation explicitly in the report
6. Confirm correctness scope before tuning:
   - compare the generated SQL intent to the benchmark question, Agent context, expected SQL/answer, and benchmark evaluation evidence when available
   - if the SQL answers the wrong business question, classify it as `semantic_wrong_sql` and hand off to a quality skill
   - if the SQL is correct but slow, continue with performance diagnosis
7. Validate the insight or candidate rewrite:
   - inspect Query Profile evidence for top operators, scans, joins, shuffles, sorts, windows, aggregates, filters, wide projections, Photon fallback, full table scans, exploding joins, poor pruning, memory, spill, and task time
   - inspect generated SQL and any `/analyze` or `/optimize` rewrite for semantic equivalence before proposing it
   - use `EXPLAIN` only for bounded candidate shape checks; do not treat it as a replacement for runtime profile evidence
8. Inspect the Agent surfaces that can influence expensive SQL:
   - attached tables, views, Metric Views, materialized views, measures, dimensions, filters, and descriptions
   - hidden or exposed columns, especially wide free-text, JSON, arrays, maps, structs, blobs, embeddings, and noisy technical fields
   - joins, snippets, example SQL, SQL functions, prompt matching settings, and text instructions
   - source scope issues, overlapping tables, raw-table exposure where a prejoined view or Metric View would be more efficient, and broad examples that encourage `SELECT *`
9. Inspect table and layout evidence with bounded reads:
   - table type, row count estimates, size, partitioning, clustering keys, file layout, freshness, and whether sources are managed, external, foreign, Delta, Iceberg, views, materialized views, or Metric Views
   - predictive optimization inheritance/status, recent predictive optimization operations when accessible, and whether statistics support data skipping and the optimizer
   - commonly filtered, joined, grouped, ranked, or ordered columns from the generated SQL and Query History
10. Inspect SQL warehouse evidence:
   - warehouse type, size, max clusters, serverless/pro/classic capabilities, Photon/Predictive IO/IWM availability, startup delays, queue pressure, spill symptoms, and warehouse events
   - whether the symptom points to queue/concurrency, startup, memory pressure, scan volume, query shape, or table layout
11. Classify findings using `references/query-optimization-guide.md`. Separate:
   - Query performance insight labels and validated issue labels
   - query-shape issues
   - table-layout/statistics issues
   - warehouse capacity or concurrency issues
   - Genie Agent source/scope issues
   - semantic correctness issues
   - evidence/access limitations
12. Recommend the smallest useful performance lever. Prefer reducing query work before increasing compute unless the evidence primarily shows queue pressure, startup delay, or unavoidable memory pressure.
13. Produce a concise query optimization report in chat or notebook output.

## Output

Use this shape:

```markdown
# Genie Query Optimization: <space>

## Case
- Benchmark:
- Benchmark run/window:
- Questions:
- Warehouse:
- Goal:
- Correctness status:

## Insight Triage
- Insights availability:
- Insight-backed candidates:
- Statement IDs:
- Insight labels:
- Repeated patterns:
- Access limitations:

## Workload Evidence
- Query history:
- Duration breakdown:
- Scan/result ratio:
- Cache status:

## Query Plan Findings
| Severity | Insight/Issue | Statement ID | Evidence | Recommendation | Owner | Validation | Risk |
|---|---|---|---|---|---|---|---|

## Warehouse Findings
| Severity | Insight/Issue | Statement ID | Evidence | Recommendation | Owner | Validation | Risk |
|---|---|---|---|---|---|---|---|

## Table And Layout Findings
| Severity | Insight/Issue | Statement ID | Evidence | Recommendation | Owner | Validation | Risk |
|---|---|---|---|---|---|---|---|

## Recommendations
| Priority | Lever | Change Or Candidate Rewrite | Why | Validation |
|---|---|---|---|---|

## Validation Plan
- Benchmark re-run:
- Unchanged answer check:
- Read-only check:
- Query Profile check:
- Warehouse check:

## Limitations
- Missing evidence:
- Confidence:
- Handoff:
```

End with the next action: user confirmation needed for any mutating follow-up, a handoff to `diagnose-genie-agent` or `optimize-genie-agent` for semantic quality issues, or a recommendation-only summary when no change is justified.

## Mechanism Map (CLI / MCP)

Per-step mapping for context (b). Most evidence is reachable through the **Query History REST API** (`GET /api/2.0/sql/history/queries`, wrapped by `databricks query-history list`), which with `--include-metrics` returns Query-Profile-grade metrics. The two UI-only surfaces (insight labels, `/analyze`·`/optimize` rewrite) are noted in the [Execution Context](#execution-context) above and must be flagged as limitations in the report.

| Evidence | Native (Genie Code) | CLI substitute (default outside) |
|----------|---------------------|----------------------------------|
| Genie-space query rows + metrics | Query History UI, filtered to the Agent | `databricks api get /api/2.0/sql/history/queries --json '{"max_results":50,"include_metrics":true}'`, then filter client-side on `.query_source.genie_space_id` (see command below). The `metrics{}` block carries `spill_to_disk_bytes`, `pruned_files_count`, `read_files_count`, `read_bytes`, `read_cache_bytes`, `result_from_cache`, `photon_total_time_ms`, `compilation_time_ms`, `queue_end_time_ms`, `rows_read_count` |
| Richer history / trends | Query History UI | `system.query.history` read-only templates in `references/query-optimization-guide.md` (via `databricks experimental aitools tools query`) |
| Warehouse / layout evidence | UI | `system.compute.warehouse_events`, `system.compute.warehouses`, `DESCRIBE DETAIL`, `DESCRIBE TABLE EXTENDED` templates in the reference |
| Launch benchmark run | native eval UI | `databricks genie genie-create-eval-run` *(Beta)* — see `optimize-genie-agent` for the eval-run command set |

Verified filter-by-Agent command (client-side, since `filter_by` does not accept `query_source` over the GET-body path):

```bash
databricks api get /api/2.0/sql/history/queries \
  --json '{"max_results":50,"include_metrics":true}' \
| jq '[.res[] | select(.query_source.genie_space_id == "<genie-space-id>")]
       | sort_by(-.duration)
       | .[] | {query_id, status, duration,
                spill: .metrics.spill_to_disk_bytes,
                pruned_files: .metrics.pruned_files_count,
                read_bytes: .metrics.read_bytes,
                cache: .metrics.result_from_cache,
                text: .query_text[0:200]}'
```

This skill stays **diagnostic / recommendation-first** regardless of mechanism: no `ALTER`/`OPTIMIZE`/`ANALYZE`, no Agent/benchmark/warehouse edits — those remain user-approved follow-ups.

## Related Skills

- **`diagnose-genie-agent`** / **`optimize-genie-agent`** — hand off here when the generated SQL is semantically wrong rather than just slow.
- **`databricks-metric-views`** — `query-patterns.md` for correct `MEASURE()` query shapes, and `genie-agent-integration.md` for Metric View design choices (e.g. base views) that affect query cost.
- **`databricks-genie`** — the parent orchestration hub for the full Agent lifecycle (create, query, export, import, migrate) and the verified `serialized_space` field schema; route there for the end-to-end CLI/MCP command surface.
