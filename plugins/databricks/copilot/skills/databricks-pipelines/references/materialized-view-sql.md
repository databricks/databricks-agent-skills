# Materialized Views in SQL

Databricks supports materialized views in two authoring contexts: **standalone**, defined outside an authored Lakeflow Spark Declarative Pipeline; and **pipeline-defined**, declared in pipeline source and refreshed through pipeline updates. Both materialize a batch query and refresh so the stored result stays equivalent to that query, so they share the same core processing and refresh semantics, the same SQL definition grammar, and the same constraints. They differ only in declaration syntax and refresh orchestration.

## Choose the authoring context

- **Standalone materialized view** — defined outside authored Lakeflow Spark Declarative Pipeline source; created and refreshed through a SQL warehouse or a supported notebook on serverless general compute. Its declaration and lifecycle are standalone, with manual, scheduled, or upstream-change-triggered refresh. Use the **Shared SQL definition** and **Shared refresh semantics** sections, then the **Standalone materialized views** section; do NOT apply the pipeline declaration prefix, lifecycle, or tools.
- **Pipeline-defined materialized view** — declared in pipeline source and refreshed through pipeline updates. Its declaration uses `CREATE OR REFRESH [PRIVATE] MATERIALIZED VIEW`, with no standalone `SCHEDULE`/`TRIGGER ON UPDATE` clause. Use the **Shared SQL definition** and **Shared refresh semantics** sections, then the **Materialized views in Lakeflow Spark Declarative Pipelines** section.

The **Constraints common to both contexts** section at the end applies regardless of context.

## Shared SQL definition

Both contexts define a materialized view with the same grammar, parameters, schema, columns, clustering/partitioning, table properties, generated columns, row filters, column masks, and query. Only the leading declaration clause is context-specific: standalone uses `CREATE MATERIALIZED VIEW`; pipeline-defined uses `CREATE OR REFRESH [PRIVATE] MATERIALIZED VIEW` (`OR REFRESH` and `PRIVATE` are pipeline-only). Everything after the view name is shared.

**CREATE MATERIALIZED VIEW**
Creates a materialized view for batch data processing. For streaming tables, see the `CREATE STREAMING TABLE` guide.

```sql
{ CREATE MATERIALIZED VIEW                        -- standalone
| CREATE OR REFRESH [PRIVATE] MATERIALIZED VIEW } -- pipeline-defined; OR REFRESH and PRIVATE are pipeline-only
  view_name
  [ column_list ]
  [ view_clauses ]
  AS query

column_list
   ( { column_name column_type column_properties } [, ...]
    [ column_constraint ] [, ...]
    [ , table_constraint ] [...] )

   column_properties
      { NOT NULL | COMMENT column_comment | column_constraint | MASK clause } [ ... ]

view_clauses
  { USING DELTA |
    PARTITIONED BY (col [, ...]) |
    CLUSTER BY clause |
    LOCATION path |
    COMMENT view_comment |
    TBLPROPERTIES clause |
    WITH { ROW FILTER clause } } [...]
```

**Parameters:**

- `PRIVATE` (pipeline-defined only): Restricts table to pipeline scope; prevents metastore publication. Use it only for an intermediate you add, or when the request asks for it. A materialized view the request names for this pipeline to create stays published unless explicitly requested private, even when it is called a helper, dedup or lookup step, only feeds other datasets, or isn't in the consumer list.
- `view_name`: Unique identifier for the view (fully qualified name including catalog and schema must be unique unless marked PRIVATE)
- `column_list`: Optional schema definition with column names, types, and properties
  - `column_name`: Name of the column
  - `column_type`: Data type (STRING, BIGINT, DECIMAL, etc.)
  - `column_properties`: Column attributes:
    - `NOT NULL`: Column cannot contain null values
    - `COMMENT column_comment`: Description for the column
    - `column_constraint`: Data quality constraints, consult the expectations reference ([expectations-sql.md](expectations-sql.md)) for details.
      - Syntax: `CONSTRAINT name EXPECT (cond) [ON VIOLATION DROP ROW | FAIL UPDATE]` (see [expectations-sql.md](expectations-sql.md))
    - `MASK clause`: Column masking syntax `MASK catalog.schema.mask_fn USING COLUMNS (other_column)`
  - `table_constraint`: Informational table-level constraints (Unity Catalog only, **not enforced** by Databricks):
    - Look up exact documentation when using
    - Note: Constraints are informational metadata for documentation and query optimization hints; data validation must be performed independently
- `view_clauses`: Optional clauses for view configuration:
  - `USING DELTA`: Optional format specification (only DELTA supported, can be omitted)
  - `PARTITIONED BY (col [, ...])`: Columns for traditional partitioning, mutually exclusive with CLUSTER BY
  - `CLUSTER BY (col [, ...])`: Explicit columns for liquid clustering (optimized query performance)
  - `CLUSTER BY AUTO`: Databricks automatically selects the liquid-clustering columns; `AUTO` has no parentheses
  - `LOCATION path`: Storage path (Hive metastore only)
  - `COMMENT view_comment`: Description for the view
  - `TBLPROPERTIES clause`: Custom table properties `(key = value [, ...])`
  - `WITH ROW FILTER clause`: Row-level security filtering
    - Syntax: `ROW FILTER func_name ON (column_name [, ...])`
      - `func_name` must be a SQL UDF returning BOOLEAN (can be defined in Unity Catalog)
      - Rows are filtered out when function returns FALSE or NULL
      - Accepts table columns or constant literals (STRING, numeric, BOOLEAN, INTERVAL, NULL)
      - Filter applies when rows are fetched from the data source
      - Runs with pipeline owner's rights during refresh and invoker's rights during queries
    - Note: Using row filters on source tables forces full refresh of downstream materialized views
    - Note: It is NOT possible to call `CREATE FUNCTION` within a Spark Declarative Pipeline.
- `query`: A Spark SQL query that defines the dataset for the table

**Common Patterns:**

**Pattern 1: Simple batch transformation**

```sql
CREATE MATERIALIZED VIEW bronze_batch
AS SELECT * FROM delta.`/path/to/data`;

CREATE MATERIALIZED VIEW silver_batch
AS SELECT * FROM bronze_batch WHERE id IS NOT NULL;
```

**Pattern 2: Schema with generated columns**

```sql
CREATE MATERIALIZED VIEW orders_with_day (
  order_datetime STRING,
  order_day_of_week STRING GENERATED ALWAYS AS (dayofweek(order_datetime)),
  customer_id BIGINT,
  amount DECIMAL(10,2)
)
CLUSTER BY (order_day_of_week, customer_id)
AS SELECT order_datetime, customer_id, amount FROM raw.orders;
```

**Pattern 3: Row filters for data security**

```sql
-- Assumes filter_by_dept is a SQL UDF defined in Unity Catalog that returns BOOLEAN

CREATE MATERIALIZED VIEW employees (
  emp_id INT,
  emp_name STRING,
  dept STRING,
  salary DECIMAL(10,2)
)
WITH ROW FILTER my_catalog.my_schema.filter_by_dept ON (dept)
AS SELECT * FROM source.employees;
```

**Pattern 4: Column masking for sensitive data**

```sql
CREATE MATERIALIZED VIEW users_with_masked_ssn (
  user_id BIGINT,
  ssn STRING MASK catalog.schema.ssn_mask_fn USING COLUMNS (region),
  region STRING
)
AS SELECT user_id, ssn, region FROM raw.users;
```

**Pattern 5: Aggregations with liquid clustering**

```sql
CREATE MATERIALIZED VIEW daily_sales_summary
CLUSTER BY (sale_date, region)
AS
SELECT
  DATE(order_timestamp) AS sale_date,
  region,
  COUNT(*) AS order_count,
  SUM(amount) AS total_revenue
FROM raw.orders
GROUP BY DATE(order_timestamp), region;
```

## Shared refresh semantics

A refresh re-runs the view's query so its stored result stays equivalent to that query. Any refresh either recomputes the whole result (full recompute) or processes only changed data (incremental refresh).


For a **pipeline-defined** MV that **isn't** refreshing incrementally (unexpected full recompute) and you need to find out why, read [pipeline-debugging](pipeline-debugging.md): read the update's `planning_information` events, which show the incrementalization technique and the causes of a full recompute. Don't guess the cause from this reference.


**Automatic incremental refresh (serverless pipelines):**

Materialized views on serverless pipelines support automatic incremental refresh, which processes only changes in underlying data since the last refresh rather than recomputing everything. This significantly reduces compute costs.

**How it works:**

- On serverless pipelines, a cost model decides whether each refresh runs incrementally or falls back to full recompute
- Incremental refresh processes delta changes and appends to the table
- If incremental refresh is not feasible or more expensive, the system falls back to full recompute automatically

**Requirements for incremental refresh (serverless pipelines):**

- Must run on **serverless pipelines** (not classic compute)
- Source tables must be Delta tables, materialized views, or streaming tables
- Row-tracking must be enabled on source tables for certain operations (see Notes column)

**Supported SQL operations for incremental refresh:**

| SQL Operation               | Support | Notes                                                                                                   |
| --------------------------- | ------- | ------------------------------------------------------------------------------------------------------- |
| SELECT expressions          | Yes     | Deterministic built-in functions and immutable UDFs. Requires row tracking                              |
| GROUP BY                    | Yes     | —                                                                                                       |
| WITH                        | Yes     | Common table expressions                                                                                |
| UNION ALL                   | Yes     | Requires row tracking                                                                                   |
| FROM                        | Yes     | Supported base tables include Delta tables, materialized views, and streaming tables                    |
| WHERE, HAVING               | Yes     | Requires row tracking                                                                                   |
| INNER JOIN                  | Yes     | Requires row tracking                                                                                   |
| LEFT OUTER JOIN             | Yes     | Requires row tracking                                                                                   |
| FULL OUTER JOIN             | Yes     | Requires row tracking                                                                                   |
| RIGHT OUTER JOIN            | Yes     | Requires row tracking                                                                                   |
| OVER (Window functions)     | Yes     | Must specify PARTITION BY columns                                                                       |
| QUALIFY                     | Yes     | —                                                                                                       |
| EXPECTATIONS                | Partial | Generally supported; exceptions for views with expectations and DROP expectations with NOT NULL columns |
| Non-deterministic functions | Limited | Time functions like `current_date()` supported in WHERE clauses only                                    |
| Non-Delta sources           | No      | Volumes, external locations, foreign catalogs unsupported                                               |

**Best practices:**

- Enable deletion vectors, row tracking, and change data feed on source tables for optimal incremental refresh
  - Source table properties: `delta.enableDeletionVectors = true`, `delta.enableRowTracking = true`, `delta.enableChangeDataFeed = true`
- Design queries with supported operations to leverage incremental refresh
- For exactly-once processing semantics (Kafka, Auto Loader), use streaming tables instead

## Standalone materialized views

Applies to materialized views created and refreshed outside a Lakeflow Spark Declarative Pipeline, through a SQL warehouse or a supported notebook on serverless general compute. Manual refresh uses `REFRESH MATERIALIZED VIEW view_name`.

**Warehouse requirement:** Standalone materialized views can only be created and refreshed using a **Pro or Serverless SQL warehouse**. Classic (Standard) warehouses are not supported. Do not suggest a Classic warehouse for MV creation or refresh.

**Choosing a Refresh Strategy:**

When a user wants to schedule refreshes, recommend in this order:

1. `TRIGGER ON UPDATE` (recommended default) — Automatically refreshes when upstream data changes. Lowest latency, no wasted refreshes on unchanged data. Use `AT MOST EVERY` to throttle (minimum 1 minute). Maximum 10 upstream sources per view. Global limit of 1000 streaming tables and materialized views using this mode.
2. `SCHEDULE EVERY` — Fixed periodic refresh. Supports HOUR/HOURS (1-72), DAY/DAYS (1-31), WEEK/WEEKS (1-8). Does NOT support minutes — the smallest unit is 1 HOUR.
3. `SCHEDULE CRON` — Quartz cron expression for precise scheduling. Always include `AT TIME ZONE` for predictable behavior.

If the user asks for a refresh interval shorter than 1 hour (e.g., "every 30 minutes"):

- Do NOT use `SCHEDULE EVERY` — it does not support minutes.
- Use `SCHEDULE CRON` instead: e.g., `SCHEDULE CRON '0 0/30 * * * ? *'` for every 30 minutes.
- Or use `TRIGGER ON UPDATE AT MOST EVERY INTERVAL 30 minutes` if upstream-change-driven refresh is acceptable.

**Standalone scheduling rules:**

- Do NOT put scheduling configuration in `TBLPROPERTIES`. Use the `SCHEDULE` clause or `ALTER MATERIALIZED VIEW ... ADD SCHEDULE`.
- Do NOT use `SCHEDULE EVERY` with minutes — use CRON for sub-hour intervals.
- Do NOT suggest creating a SQL endpoint or external scheduler for MV refreshes. Use the built-in scheduling clauses.
- Do NOT suggest Oracle-style or other non-Databricks MV syntax.

### Optimizing an existing standalone materialized view

When helping optimize an existing standalone MV using a specific execution, the following approach can be useful. Adapt it to the user's request.

- Inspect the existing definition and metadata, for example with `databricks tables get <catalog>.<schema>.<table>` or `DESCRIBE TABLE EXTENDED`.
- Base recommendations on the original execution's Query Profile and Query Insights. When the user gives a statement ID, read that query's profile and insights.
- Consider preparing a complete `CREATE OR REPLACE MATERIALIZED VIEW` draft for review. Preserve the existing name, columns, comments, properties, schedule, clustering, and other clauses unless a change is part of the requested work.

For an optimization recommendation, a draft is usually sufficient; apply it only when the user asks.

If metadata is incomplete, explain what is missing rather than inventing DDL.

## Materialized views in Lakeflow Spark Declarative Pipelines

Applies to materialized views declared in pipeline source. They are refreshed through pipeline updates — full refresh or incremental computation per the **Shared refresh semantics** section — not through standalone `SCHEDULE`/`TRIGGER ON UPDATE` clauses.

- Materialized views perform batch processing of data
- Streaming tables perform incremental streaming processing — for streaming reads, use the streaming table reference ([streaming-table-sql.md](streaming-table-sql.md)) instead
- The `query` must NOT use `STREAM(...)`; streaming reads belong in a streaming table (see [streaming-table-sql.md](streaming-table-sql.md))

- **`ai_*` calls in the query (`ai_classify`, `ai_extract`, ...):** before writing one, read its syntax in the `databricks-ai-functions` skill and use that. A spec's sample call is often legacy v1 (`ARRAY(...)` labels, no options `MAP`); don't copy it.


## Constraints common to both contexts

These apply to materialized views whether created as a standalone materialized view or defined inside a Lakeflow Spark Declarative Pipeline:

- Identity columns and default columns are not supported
- Row filters force full refresh of downstream materialized views
- Sum aggregates over nullable columns return zero instead of NULL when only nulls remain (when the last non-NULL value is removed)
- Non-column expressions require explicit aliases (column references do not need aliases)
- PRIMARY KEY requires explicit NOT NULL specification to be valid
- OPTIMIZE and VACUUM are unavailable; maintenance runs automatically (Predictive Optimization for standalone materialized views; Lakeflow Spark Declarative Pipelines for pipeline materialized views)
- `CLUSTER BY` is recommended over `PARTITIONED BY` for most use cases; `CLUSTER BY AUTO` lets Databricks choose the clustering keys
- Table renaming and ownership changes are prohibited
