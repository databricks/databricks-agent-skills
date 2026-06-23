# Genie Query Optimization Guide

Use this reference when analyzing benchmark-generated Genie Agent SQL, Query History Insights, SQL warehouse behavior, and table layout from a performance and cost perspective in Databricks-native workflows.

## Navigation

- `Evidence Order`: use benchmark-generated Query History Insights first when available, then validate with profile, table, and warehouse facts.
- `Benchmark And Insights Workflow`: launch approved benchmark runs and triage Query History insight candidates.
- `Read-Only SQL Templates`: bounded inspection templates for Genie Query History, warehouse activity, table metadata, layout, and optimization history.
- `Issue Taxonomy`: classify performance symptoms with stable labels.
- `Query Performance Insight Routing`: map Databricks insight labels to owners, validation, and anti-patterns.
- `Evidence-To-Lever Routing`: map observed symptoms to the smallest useful recommendation.
- `Validation`: prove that recommendations improve performance without changing the answer.
- `Report Template`: produce a concise, evidence-backed handoff.

## Evidence Order

Use this order unless the user provides a specific statement ID, profile, or existing insight-backed Query History row first:

1. Confirm the benchmark target, target questions, benchmark run window, warehouse, and user approval before launching any native benchmark run.
2. Run the approved native benchmark, or use a completed benchmark run/query history window when benchmark launch is not approved.
3. Open Query History, filter to benchmark-generated Genie queries, and prioritize rows with Query performance insights.
4. Use Query History's Genie Code `/analyze` or `/optimize` action for an insight-backed row when available, but treat the output as a candidate that must be validated.
5. Confirm the generated SQL is semantically correct enough to optimize. If the query is answering the wrong business question, route to `semantic_wrong_sql`.
6. Inspect Query Profile for the slowest operators, scans, joins, shuffles, sorts, aggregates, memory, rows, spill, queue symptoms, and Photon fallback.
7. Inspect `system.query.history` for Genie-originated statements, durations, scan metrics, cache status, spill, queue time, and warehouse ID when system tables are accessible.
8. Inspect the Agent sources and instructions that influence query shape, including broad source scope, hidden/exposed columns, joins, SQL snippets, examples, and Metric Views.
9. Inspect source objects for layout, statistics, clustering, partitioning, predictive optimization, and whether views or materialized views would reduce repeated work.
10. Inspect warehouse settings and events after separating query-shape and table-layout causes from queue, startup, memory, and concurrency causes.

Do not use aggregate latency alone as proof of root cause. Separate compile time, queue time, execution time, scan volume, spill, and result fetch time.

## Databricks Documentation Anchors

- Query Profile: https://docs.databricks.com/aws/en/sql/user/queries/query-profile
- Query History system table: https://docs.databricks.com/aws/en/admin/system-tables/query-history
- SQL warehouse behavior: https://docs.databricks.com/aws/en/compute/sql-warehouse/warehouse-behavior
- SQL warehouse types: https://docs.databricks.com/aws/en/compute/sql-warehouse/warehouse-types
- Query performance insights: https://docs.databricks.com/aws/en/sql/user/queries/performance-insights
- Data skipping: https://docs.databricks.com/aws/en/delta/data-skipping
- Liquid clustering: https://docs.databricks.com/aws/en/delta/clustering
- Optimize data file layout: https://docs.databricks.com/aws/en/delta/optimize
- OPTIMIZE syntax: https://docs.databricks.com/aws/en/sql/language-manual/delta-optimize
- ANALYZE TABLE: https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-analyze-compute-statistics
- Join optimization: https://docs.databricks.com/aws/en/transform/optimize-joins
- Warehouse monitoring queries: https://docs.databricks.com/aws/en/compute/sql-warehouse/monitor/queries
- Warehouses system table: https://docs.databricks.com/aws/en/admin/system-tables/warehouses
- Warehouse events system table: https://docs.databricks.com/aws/en/admin/system-tables/warehouse-events
- Predictive optimization system table: https://docs.databricks.com/aws/en/admin/system-tables/predictive-optimization

## Benchmark And Insights Workflow

Query performance insights are a Private Preview Databricks feature. If the Insights column, lightbulb indicator, or Genie Code action is absent, say so and use the fallback workflow below.

When Insights are available:

1. Run only the approved benchmark scope and capture the exact run window.
2. In Query History, filter by benchmark window, Agent, warehouse, user, statement ID, query source, or available tags.
3. Sort or scan for rows with performance insights before manually reviewing slow rows without insights.
4. For each candidate, record the benchmark question, statement ID, insight labels, duration breakdown, warehouse, cache status, and statement preview.
5. Click the Query History Genie Code `/analyze` or `/optimize` action when available. Keep its candidate rewrite or recommendation only after semantic and profile validation.
6. Group candidates by repeated insight label, SQL shape, source object, and benchmark question pattern so recommendations address durable workload behavior.

Fallback when Insights are absent or inaccessible:

- Inspect slow and expensive benchmark queries from Query History by duration, scan bytes, spill, queue time, and cache status.
- Open Query Profile for representative rows and classify using the manual issue taxonomy.
- State the limitation as preview/access/missing-insight evidence, not as a healthy-performance signal.

## Read-Only SQL Templates

Use exact identifiers provided by the user or discovered from the Agent. Keep time windows narrow. If a system table is unavailable, state the limitation and use Query History UI or Query Profile UI evidence instead.

### Genie query history by Agent

```sql
SELECT
  statement_id,
  start_time,
  end_time,
  execution_status,
  compute.warehouse_id AS warehouse_id,
  total_duration_ms,
  waiting_for_compute_duration_ms,
  waiting_at_capacity_duration_ms,
  compilation_duration_ms,
  execution_duration_ms,
  total_task_duration_ms,
  result_fetch_duration_ms,
  read_partitions,
  pruned_files,
  read_files,
  read_rows,
  produced_rows,
  read_bytes,
  read_io_cache_percent,
  from_result_cache,
  spilled_local_bytes,
  SUBSTRING(statement_text, 1, 2000) AS statement_preview
FROM system.query.history
WHERE query_source.genie_space_id = '<genie-space-id>'
  AND start_time >= current_timestamp() - INTERVAL 7 DAYS
ORDER BY total_duration_ms DESC
LIMIT 50;
```

### Specific statement lookup

```sql
SELECT
  statement_id,
  workspace_id,
  execution_status,
  compute,
  query_source,
  client_application,
  total_duration_ms,
  waiting_for_compute_duration_ms,
  waiting_at_capacity_duration_ms,
  compilation_duration_ms,
  execution_duration_ms,
  total_task_duration_ms,
  read_files,
  read_rows,
  produced_rows,
  read_bytes,
  from_result_cache,
  spilled_local_bytes,
  error_message,
  statement_text
FROM system.query.history
WHERE statement_id = '<statement-id>';
```

### Slow and expensive Genie patterns

```sql
WITH genie_queries AS (
  SELECT
    statement_id,
    compute.warehouse_id AS warehouse_id,
    start_time,
    total_duration_ms,
    waiting_at_capacity_duration_ms,
    execution_duration_ms,
    compilation_duration_ms,
    read_bytes,
    read_rows,
    produced_rows,
    read_files,
    pruned_files,
    spilled_local_bytes,
    from_result_cache,
    SUBSTRING(statement_text, 1, 500) AS query_preview
  FROM system.query.history
  WHERE query_source.genie_space_id = '<genie-space-id>'
    AND execution_status = 'FINISHED'
    AND start_time >= current_timestamp() - INTERVAL 30 DAYS
)
SELECT *
FROM genie_queries
WHERE from_result_cache = false
ORDER BY total_duration_ms DESC, read_bytes DESC
LIMIT 25;
```

### Warehouse event correlation

```sql
SELECT
  event_time,
  workspace_id,
  warehouse_id,
  event_type,
  cluster_count
FROM system.compute.warehouse_events
WHERE warehouse_id = '<warehouse-id>'
  AND event_time >= current_timestamp() - INTERVAL 7 DAYS
ORDER BY event_time DESC
LIMIT 100;
```

### Warehouse configuration snapshots

```sql
SELECT
  warehouse_id,
  warehouse_name,
  warehouse_type,
  warehouse_size,
  min_clusters,
  max_clusters,
  auto_stop_minutes,
  change_time
FROM system.compute.warehouses
WHERE warehouse_id = '<warehouse-id>'
ORDER BY change_time DESC
LIMIT 10;
```

### Table inventory and comments

```sql
SELECT
  table_catalog,
  table_schema,
  table_name,
  table_type,
  comment
FROM <catalog>.information_schema.tables
WHERE table_schema = '<schema>'
  AND table_name IN ('<table_1>', '<table_2>')
ORDER BY table_name;
```

### Column metadata for query predicates and joins

```sql
SELECT
  table_name,
  ordinal_position,
  column_name,
  data_type,
  comment
FROM <catalog>.information_schema.columns
WHERE table_schema = '<schema>'
  AND table_name = '<table-name>'
ORDER BY ordinal_position;
```

### Table layout and clustering

```sql
DESCRIBE DETAIL <catalog>.<schema>.<table>;
```

```sql
DESCRIBE TABLE EXTENDED <catalog>.<schema>.<table>;
```

### Predictive optimization status

```sql
DESCRIBE CATALOG EXTENDED <catalog>;
DESCRIBE SCHEMA EXTENDED <catalog>.<schema>;
DESCRIBE TABLE EXTENDED <catalog>.<schema>.<table>;
```

### Predictive optimization operations

```sql
SELECT
  start_time,
  end_time,
  catalog_name,
  schema_name,
  table_name,
  operation_type,
  operation_status,
  operation_metrics
FROM system.storage.predictive_optimization_operations_history
WHERE catalog_name = '<catalog>'
  AND schema_name = '<schema>'
  AND table_name = '<table-name>'
  AND start_time >= current_timestamp() - INTERVAL 30 DAYS
ORDER BY start_time DESC
LIMIT 50;
```

### Explain a bounded candidate query

```sql
EXPLAIN
<generated_sql_or_rewritten_candidate>;
```

Use `EXPLAIN` to inspect query shape without executing the full workload. Do not treat `EXPLAIN` as a replacement for Query Profile when runtime symptoms such as spill, skew, queueing, or poor pruning matter.

## Query Profile Evidence

When Query Profile is available, capture:

- top operators by time, rows, memory, and spill;
- scans with high read bytes, high read files, low pruning, or wide projected columns;
- joins that multiply rows or join large inputs before selective filters;
- shuffles, sorts, windows, and aggregates that dominate task time;
- Photon fallback or non-Photon operators;
- cache status, because cached queries might not have a profile and do not prove cold-query performance.

If only the Query History row is available, use the `statement_id` and workspace ID to instruct the user how to open Query Profile from Query History.

## Issue Taxonomy

| Issue | Query performance insight labels | Evidence to verify | Preferred routing |
|---|---|---|---|
| `warehouse_queue` | `EXCESSIVE_QUEUE_TIME` | High `waiting_at_capacity_duration_ms`, queued queries, warehouse events near load spikes | Warehouse max clusters, serverless/IWM, scheduling, or workload isolation |
| `warehouse_startup` | none documented | High `waiting_for_compute_duration_ms`, stopped warehouse, cold starts dominate total duration | Auto-stop review, serverless warehouse, scheduled warmup only if justified |
| `warehouse_memory_spill` | `DATA_SPILL` | High `spilled_local_bytes`, Query Profile spill on joins/sorts/aggregates | Reduce rows/columns first; then consider warehouse size if query work is necessary |
| `scan_no_pruning` | `COVERAGE_FILTER_KEYS_CLUSTERING`, `COVERAGE_FILTER_KEYS_PARTITIONING` | High read files/bytes/rows, low pruning, filters missing clustering or partition columns | Add predicates, align with clustering/partition keys, table layout recommendation |
| `missing_delta_stats` | `COVERAGE_STATS_DELTA` | Data-skipping stats missing, partial, unavailable, unused, or layout evidence shows poor file skipping | Recommend Delta statistics/predictive optimization follow-up |
| `missing_optimizer_stats` | `COVERAGE_STATS_OPTIMIZER` | Cost-based optimizer statistics missing/incomplete, weak join/order choices, high planning pressure | Recommend optimizer statistics/predictive optimization follow-up |
| `layout_key_mismatch` | `COVERAGE_FILTER_KEYS_CLUSTERING`, `COVERAGE_FILTER_KEYS_PARTITIONING` | Filters do not use clustering or partition columns; high scan bytes | Recommend query filter rewrite, liquid clustering key review, or source/view redesign |
| `wide_projection` | `WIDE_PROJECTION` | `SELECT *`, projected wide columns, high read bytes relative to produced rows | Hide noisy columns, use narrower examples/snippets, project needed columns only |
| `exploding_join` | `EXPLODING_JOIN` | Join output greatly exceeds input rows; duplicated entities; profile join dominates | Fix join condition, reduce input rows, clarify grain, prejoin or materialize stable relationship |
| `selective_join_filter_late` | `SELECTIVE_JOIN` | Selective filters applied after large joins | Push filters before joins, add source examples/snippets, or pre-filtered view |
| `redundant_aggregation` | `REDUNDANT_AGGREGATION` | Aggregation does not change result or repeats upstream aggregation | Remove redundant aggregation or add constraints/upstream model guidance |
| `data_skew` | `DATA_SKEW` | Uneven task time or input distribution in Query Profile | Salt keys, pre-aggregate, reduce skewed joins, or recommend upstream model change |
| `concurrent_write_pressure` | `CONCURRENT_WRITE` | Concurrent Delta writes, retries, or write conflicts visible in history/profile | Scheduling, write isolation, or pipeline-owner follow-up |
| `flow_full_recompute` | `FLOW_FULL_RECOMPUTE` | Flow planned as full recompute when incremental behavior is expected | Rewrite for incremental support or route to pipeline/data model owner |
| `io_throttling` | `IO_THROTTLING` | Cloud storage throttling insight, IO wait symptoms | Admin/cloud limit follow-up; validate before query rewrite |
| `many_join_planning_pressure` | none documented | Many joins/aggregations, high compilation time, complex plan | Prejoined view, materialized view, Metric View, or source scope reduction |
| `metric_view_or_source_scope_too_broad` | can contribute to `WIDE_PROJECTION`, `EXPLODING_JOIN`, `SELECTIVE_JOIN` | Genie chooses broad raw source or many overlapping sources for simple questions | Focus Genie data sources, hide columns, prefer Metric View or curated view |
| `photon_fallback` | `COVERAGE_PHOTON` | Query Profile or insight shows non-Photon operation | Rewrite unsupported operation or accept fallback when correctness requires it |
| `federated_pushdown_limit` | none documented | Foreign table query reads too much remote data or filters cannot push down | Rewrite pushdown-friendly predicates, use `AND` composition, materialize local Delta when appropriate |
| `cache_only_speedup` | none documented | Fast run only from result cache; cold query remains slow or profile missing | Validate cold-query path with trivial change or uncached profile |
| `semantic_wrong_sql` | any label can coexist | SQL is fast or slow but answers the wrong business question | Stop performance tuning; hand off to `diagnose-genie-agent` or `optimize-genie-agent` |

## Query Performance Insight Routing

| Insight label | Owner | Preferred recommendation | Validation | Avoid |
|---|---|---|---|---|
| `CONCURRENT_WRITE` | Data model owner or pipeline owner | Review Delta history and schedule conflicting writes away from benchmark/query windows | Compare failed/retried query windows with write history and rerun affected benchmark questions | Rewriting correct read SQL as the first response |
| `COVERAGE_FILTER_KEYS_CLUSTERING` | Genie Agent curator, data model owner, or table owner | Add semantically valid filters on clustering keys, or recommend clustering-key review when filters are durable | Re-run affected benchmark questions and confirm lower read bytes/files with unchanged answers | Adding artificial filters that change the requested result |
| `COVERAGE_FILTER_KEYS_PARTITIONING` | Genie Agent curator, data model owner, or table owner | Add required partition filters when the business question implies them, or recommend partition design review | Confirm partition pruning and unchanged benchmark answers | Forcing partition filters when the user asked for all-time/all-partition results |
| `COVERAGE_PHOTON` | Data model owner | Rewrite unsupported operations only when an equivalent Photon-friendly expression preserves correctness | Compare Query Profile operators and benchmark answers before/after approved rewrite | Sacrificing correctness just to avoid fallback |
| `COVERAGE_STATS_DELTA` | Table owner | Recommend Delta statistics or predictive optimization follow-up | After approved maintenance, confirm lower scan bytes/files or better pruning on same benchmark questions | Running `ANALYZE` or maintenance inside this skill |
| `COVERAGE_STATS_OPTIMIZER` | Table owner | Recommend optimizer statistics or predictive optimization follow-up | After approved maintenance, compare join/order choices, duration, and answer stability | Treating stats collection as a Genie Agent edit |
| `DATA_SKEW` | Data model owner or table owner | Reduce skewed join/aggregate input, pre-aggregate, salt keys, or redesign repeated heavy source pattern | Confirm more even task distribution and unchanged benchmark result | Blindly increasing warehouse size without checking query shape |
| `DATA_SPILL` | Genie Agent curator, data model owner, or warehouse admin | Reduce rows/columns before joins/sorts/windows; consider warehouse size only if work is necessary | Compare spill bytes, top operators, and benchmark answers | Scaling compute as the first recommendation when projection/filter fixes exist |
| `EXCESSIVE_QUEUE_TIME` | Warehouse admin | Increase max clusters, use serverless/IWM, isolate workloads, or reschedule benchmark/load | Compare queue metrics across equivalent benchmark windows | Rewriting correct SQL when execution time is already acceptable |
| `EXPLODING_JOIN` | Genie Agent curator or data model owner | Fix join grain/condition, reduce inputs, clarify source descriptions, or recommend prejoined/materialized source | Confirm join output/input ratio drops and benchmark answer is unchanged | Masking grain problems with `DISTINCT` |
| `FLOW_FULL_RECOMPUTE` | Pipeline owner or data model owner | Rewrite or redesign the flow for incremental support when applicable | Compare flow planning mode and bytes read after approved pipeline change | Applying Delta layout advice to an incremental-planning problem |
| `IO_THROTTLING` | Workspace/cloud admin | Investigate cloud storage request limits and IO pressure | Compare throttling signals across rerun or similar windows | Treating throttling as a Genie prompt problem |
| `REDUNDANT_AGGREGATION` | Genie Agent curator or data model owner | Remove redundant aggregation or add upstream constraints/model guidance | Confirm result set is identical and profile removes unnecessary aggregate | Removing aggregation before proving it is redundant |
| `SELECTIVE_JOIN` | Genie Agent curator or data model owner | Push selective filters before joins, add reusable snippets/examples, or recommend pre-filtered source | Confirm lower input rows to joins and unchanged answer | Adding benchmark-specific examples that leak expected answers |
| `WIDE_PROJECTION` | Genie Agent curator or data model owner | Project only needed columns, hide noisy/wide columns, improve examples/snippets, or prefer curated source | Confirm projected columns and read bytes decrease while answer shape is unchanged | Relying only on a broad text instruction like "avoid SELECT *" |

## Evidence-To-Lever Routing

| Evidence pattern | Preferred recommendation | Avoid |
|---|---|---|
| Queue time dominates and execution time is acceptable | Increase max clusters, use serverless/IWM where available, separate workloads, or schedule heavy runs away from peak | Rewriting correct SQL without evidence of query inefficiency |
| Startup time dominates occasional usage | Review auto-stop, use serverless for faster startup, consider user workflow expectations | Keeping warehouses always on without cost justification |
| Spill on wide join, sort, window, or aggregate | Reduce input rows/columns, push filters, fix join grain, pre-aggregate, or materialize repeated heavy steps; then consider warehouse size | Scaling warehouse as the first answer when query work is avoidable |
| Full scan with low pruning | Add selective predicates, align query with partition/clustering keys, recommend liquid clustering or layout changes when filters are durable | `OPTIMIZE` without identifying filter columns or layout mismatch |
| Missing data-skipping or optimizer stats | Recommend predictive optimization or `ANALYZE` follow-up with owner approval | Running `ANALYZE` inside this skill |
| Wide projection from Genie examples or broad columns | Hide noisy columns, improve examples/snippets to project required fields, prefer curated source | Adding a text instruction that says "avoid SELECT *" as the only fix |
| Exploding joins or duplicated rows | Clarify join keys and grain, add or revise Genie join specs only via quality workflow, recommend upstream prejoined view for repeated pattern | Blind `DISTINCT` or aggregation workaround |
| Many joins and high compilation time | Recommend curated view, materialized view, Metric View, or narrower source set | More raw tables and broader source exposure |
| Metric formula is expensive but governed | Recommend upstream Metric View/materialized view review with semantic owner | Duplicating governed formula in Genie text instructions |
| Query uses foreign or federated source with poor pushdown | Rewrite predicates for pushdown or recommend local Delta/materialized source | Assuming Delta layout features apply to the remote source |
| Query is semantically wrong | Hand off to quality diagnosis or optimization | Optimizing a wrong result |

## Recommendation Owners

Use clear owners in reports:

- `Genie Agent curator`: source scope, hidden columns, examples, snippets, and quality-skill handoff.
- `Data model owner`: views, materialized views, Metric Views, joins, grain, and source design.
- `Table owner`: statistics, predictive optimization, liquid clustering, `OPTIMIZE`, data layout, and file maintenance.
- `Warehouse admin`: warehouse type, size, max clusters, serverless/IWM, auto-stop, workload isolation, and permissions.
- `Business owner`: expected unchanged answer, latency target, cost tradeoff, and acceptable refresh/materialization behavior.

## Validation

Validate recommendations without mutating assets during this skill:

- Re-run or inspect the same benchmark questions with a cold Query Profile when possible.
- Compare answer shape, key totals, and benchmark assessment before and after any approved follow-up change.
- Check `total_duration_ms`, queue durations, execution duration, read bytes, read files, read rows, produced rows, spill bytes, and top operators.
- For insight-backed candidates, confirm the insight label is consistent with Query Profile and Query History evidence before recommending a lever.
- For warehouse recommendations, compare queue/startup metrics across similar workload windows.
- For table-layout recommendations, confirm filters match clustering, partitioning, or statistics columns and that read bytes/files decrease after approved maintenance.
- For source/model recommendations, run affected Genie questions and related correctness checks through `diagnose-genie-agent` or `optimize-genie-agent` when answer quality could change.

## Report Template

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

Each recommendation must name evidence, severity, owner, validation, and risk. If no evidence supports a change, say so and request the missing query profile, statement ID, or warehouse access rather than guessing.
