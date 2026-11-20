# Pipeline Parameters (SQL only)

Use named parameters when a value should vary across pipeline updates (a date threshold, a country code, a source table name); prefer a literal when the value is fixed for the pipeline's lifetime. Pipeline parameters are first-class on Spark Declarative Pipelines (DBR 17.0+) and use the SQL named-parameter syntax `:param_name`.

## Syntax in SQL

Reference the parameter with a leading colon. All parameter values arrive as `STRING`, so cast at the use site:

```sql
-- WHERE / filter
WHERE order_date >= CAST(:start_date AS DATE)

-- LIMIT
LIMIT CAST(:row_limit AS INT)

-- Numeric arithmetic
score * CAST(:multiplier AS DOUBLE)
```

A bare `:param` is a value, not an identifier. To use a parameter as a table or column name, wrap it in `IDENTIFIER()`:

```sql
SELECT * FROM IDENTIFIER(:source_table);
CREATE OR REFRESH MATERIALIZED VIEW IDENTIFIER(:catalog || '.' || :schema || '.' || :table_name) AS
SELECT 1 AS value;
```

## Declaring defaults on the pipeline

Parameter defaults live on the pipeline itself, in a top-level `parameters` field — distinct from the `configuration` map. Set them by updating the pipeline settings:

```yaml
parameters:
  start_date: '2024-01-01'
  country: US
```

Keys: 1–100 chars, letters/digits/underscores/dashes. Values: arbitrary strings. The full map serialized as JSON must be ≤ 10,000 chars. A pipeline that uses `:name` references in SQL must declare matching keys here (or have them supplied by the calling job task); an undeclared parameter fails analysis. To override per run from a Lakeflow Job, set `parameters` on the `pipeline_task`.

## Common traps

- `${name}` is legacy string interpolation tied to the pipeline `configuration` map. `:name` is the supported parameter syntax for new pipelines and is the only form a job's `pipeline_task` can override. Prefer `:name`.
- No cast → silent type errors. Always `CAST(:p AS <type>)` when the use site isn't a string.
- `:param` does not work as an identifier. `SELECT * FROM :tbl` is a parse error. Use `SELECT * FROM IDENTIFIER(:tbl)`.
- Python pipelines do not support `:name`; read parameters via `spark.conf.get("name")` against the pipeline configuration.
- `:param` is not supported on DBR 16.x or earlier; pipelines must be on DBR 17.0+.
