# Data Profiling And Readiness

Use this reference after candidate data sources are selected and before proposing Genie Agent changes in Genie Code. Prefer Databricks-native metadata first, then run bounded read-only SQL only where it improves the plan.

## Phased Inspection

1. **Structure.** Confirm each table/view/Metric View, comments, columns, data types, constraints, and sample rows with a narrow selected column list.
2. **Quality and usage.** Profile nulls, empty strings, constants, distinct counts, casing issues, boolean-as-string values, sensitive/noisy columns, and usage/lineage when system tables are accessible.
3. **Column profiling.** Profile only columns that affect Genie quality: dates, likely filters, categorical strings, join keys, and candidate measures.
4. **Readiness.** Map the profiled data back to the user's 3-5 business questions and record High/Medium/Low confidence for each question.

## Required Data Signals

For each table or standard view, identify row count, grain, freshness/date range, measures, dimensions, likely filters, data-quality caveats, sensitive/noisy fields, join candidates, and whether joins are supported by constraints, naming, row-count checks, query history, or user confirmation.

For each Metric View, identify governed measures, dimensions, filters, joins, time dimensions, display names, synonyms, formatting, comments, valid `MEASURE()` query patterns, and upstream semantic gaps.

## Read-Only SQL Templates

Workspace metadata and columns:

```sql
SELECT table_catalog, table_schema, table_name, table_type, comment
FROM <catalog>.information_schema.tables
WHERE table_schema = '<schema>'
ORDER BY table_name;
```

```sql
SELECT table_name, ordinal_position, column_name, data_type, comment
FROM <catalog>.information_schema.columns
WHERE table_schema = '<schema>'
ORDER BY table_name, ordinal_position;
```

Metric View metadata:

```sql
DESCRIBE TABLE EXTENDED <catalog.schema.metric_view> AS JSON;
```

Row count, key cardinality, and date range:

```sql
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT <candidate_key>) AS distinct_key_count,
  MIN(<date_col>) AS min_date,
  MAX(<date_col>) AS max_date
FROM <catalog>.<schema>.<table>;
```

Null, empty, and distinct metrics:

```sql
SELECT
  SUM(CASE WHEN <col_a> IS NULL THEN 1 ELSE 0 END) AS col_a_nulls,
  COUNT(DISTINCT <col_a>) AS col_a_distinct,
  SUM(CASE WHEN TRIM(CAST(<col_a> AS STRING)) = '' AND <col_a> IS NOT NULL THEN 1 ELSE 0 END) AS col_a_empty
FROM <catalog>.<schema>.<table>;
```

Categorical values:

```sql
SELECT <category_col>, COUNT(*) AS row_count
FROM <catalog>.<schema>.<table>
WHERE <category_col> IS NOT NULL
GROUP BY <category_col>
ORDER BY row_count DESC
LIMIT 50;
```

Casing and boolean-as-string checks:

```sql
SELECT
  LOWER(CAST(<string_col> AS STRING)) AS normalized_value,
  COLLECT_SET(CAST(<string_col> AS STRING)) AS variants,
  COUNT(*) AS row_count
FROM <catalog>.<schema>.<table>
WHERE <string_col> IS NOT NULL
GROUP BY LOWER(CAST(<string_col> AS STRING))
HAVING COUNT(DISTINCT CAST(<string_col> AS STRING)) > 1
   OR LOWER(CAST(<string_col> AS STRING)) IN ('true', 'false', 'yes', 'no', 'y', 'n')
ORDER BY row_count DESC
LIMIT 50;
```

Join overlap:

```sql
SELECT
  COUNT(*) AS left_rows,
  COUNT(DISTINCT l.<left_key>) AS left_key_count,
  COUNT(DISTINCT r.<right_key>) AS matched_right_key_count
FROM <catalog>.<schema>.<left_table> l
LEFT JOIN <catalog>.<schema>.<right_table> r
  ON l.<left_key> = r.<right_key>;
```

Metric View measure and dimension behavior (for the full `MEASURE()` query rules — `CASE`+`MEASURE()` grouping, no measures in `WHERE`/`GROUP BY` — see the `databricks-metric-views` skill's `query-patterns.md`):

```sql
SELECT
  <dimension_name>,
  MEASURE(<measure_name>) AS <measure_alias>
FROM <catalog>.<schema>.<metric_view>
GROUP BY ALL
LIMIT 20;
```

Recent usage and lineage when available:

```sql
SELECT source_table_full_name, target_table_full_name, source_type, target_type
FROM system.access.table_lineage
WHERE (source_table_full_name IN ('<catalog.schema.table>')
   OR target_table_full_name IN ('<catalog.schema.table>'))
  AND event_time >= date_sub(current_date(), 30)
LIMIT 50;
```

```sql
SELECT SUBSTRING(statement_text, 1, 500) AS query_preview, produced_rows
FROM system.query.history
WHERE start_time >= date_sub(current_date(), 7)
  AND execution_status = 'FINISHED'
  AND LOWER(statement_text) LIKE '%<catalog.schema.table>%'
ORDER BY start_time DESC
LIMIT 50;
```

## How To Use Findings

- Hide ETL metadata, all-null columns, raw blobs, embeddings, secrets, tokens, and sensitive free text.
- Put high-null, constant, inconsistent casing, and boolean-as-string caveats in `DATA QUALITY NOTES` only when Genie needs them.
- Enable format assistance on useful dimensions and filters. Enable entity matching only for stable low/medium-cardinality strings users are likely to mention.
- Use actual profiled values for example SQL parameters and benchmark literals.
- Use query history as evidence for joins, sample questions, examples, and benchmarks. If system tables are unavailable, proceed without mentioning the failure unless it limits confidence.
- Ask the user to confirm metric formulas, joins, fiscal/calendar rules, and default filters that are not supported by evidence.

## Readiness Assessment

Score each business question:

- **High:** all required sources, fields, values, and join/metric definitions are supported.
- **Medium:** answerable with caveats, missing descriptions, uncertain filters, or user-confirmed assumptions.
- **Low:** missing source, measure, dimension, time field, join path, or governed metric definition.

Do not present Low-confidence questions as fully supported. Add data, revise the question, ask for confirmation, or mark the draft with limitations.
