# DBT → SDP Conversion Rules

DBT-specific transpilation rules used by the Generate and Repair phases. The generic
SDP target syntax lives in `references/migrate-to-sdp/sdp-syntax.md`; this file covers the DBT-side
of the mapping.

## Reference resolution

| DBT                              | SDP Python                             | SDP SQL                        |
| -------------------------------- | -------------------------------------- | ------------------------------ |
| `{{ ref('model') }}`             | `spark.read.table("model")`            | `SELECT ... FROM model`        |
| `{{ ref('model') }}` (streaming) | `spark.readStream.table("model")`      | `SELECT ... FROM STREAM model` |
| `{{ source('s', 't') }}`         | `spark.read.table("catalog.schema.t")` | `catalog.schema.t`             |

`ref()` always resolves to the bare dataset name within the pipeline. `source()`
resolves to the fully qualified UC name from the IR's `sources[]` mapping.

## Materialization signals → SDP API

| DBT config                                  | SDP Python                                                        | SDP SQL                                  |
| ------------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------- |
| `materialized='view'` (intra-project)       | `@dp.temporary_view()`                                            | `CREATE TEMPORARY VIEW`                  |
| `materialized='view'` (external consumers)  | `@dp.materialized_view()`                                         | `CREATE OR REFRESH MATERIALIZED VIEW`    |
| `materialized='table'`                      | `@dp.materialized_view()`                                         | `CREATE OR REFRESH MATERIALIZED VIEW`    |
| `materialized='incremental'` (append)       | `@dp.table()` returning streaming DF                              | `CREATE OR REFRESH STREAMING TABLE`      |
| `materialized='incremental'` (merge, SCD 1) | `dp.create_auto_cdc_flow(... stored_as_scd_type=1)`               | `AUTO CDC INTO ... STORED AS SCD TYPE 1` |
| `materialized='incremental'` (merge, SCD 2) | `dp.create_auto_cdc_flow(... stored_as_scd_type=2)`               | `AUTO CDC INTO ... STORED AS SCD TYPE 2` |
| `materialized='ephemeral'`                  | `@dp.temporary_view()` (or inline CTE)                            | `CREATE TEMPORARY VIEW` (or inline CTE)  |
| `snapshot` (timestamp)                      | `dp.create_auto_cdc_flow(... stored_as_scd_type=2)`               | `AUTO CDC INTO ... STORED AS SCD TYPE 2` |
| `snapshot` (check)                          | `dp.create_auto_cdc_from_snapshot_flow(... stored_as_scd_type=2)` | Versioned recurring SQL for immutable complete partitions, or unversioned `AUTO CDC ONCE` for an initial empty target |

`sdp_type` from the IR is your constraint — never override it during generation.
Decision rules live in `decision-rules.md`; if you think the IR is wrong, that's a
Repair-phase concern, not a Generate-phase concern.

For a check-strategy snapshot with `output_format: sql`, `source_meta` must identify an orderable version and confirm that each version is an immutable, complete snapshot. Generate `WITH VERSION` to select the next version and filter `snapshot_query` with `current_snapshot_version()`. If the source is current-state only but complete, determine whether the user needs a one-time initial load or recurring DBT snapshot behavior. A one-time load into an empty target can use SQL `AUTO CDC ONCE` without `WITH VERSION`; recurring behavior requires the Python snapshot API and a `manual_review` entry. If versions can be partial, flag the node for `manual_review` and do not generate snapshot CDC until complete snapshots can be reconstructed. Never emit recurring SQL snapshot CDC without `WITH VERSION`.

## Schema tests → SDP expectations

**Column-level data tests map directly to native SDP expectations** — a
`CONSTRAINT ... EXPECT (<boolean>)` (SQL) or `@dp.expect*` decorator (Python).
`not_null` is one of these. Only **set-level** tests (`unique`, `relationships`)
lack a native equivalent — an expectation is a per-row boolean and can't contain an
aggregate or a cross-table subquery. Do not generalize that limit onto column-level
tests like `not_null`.

| DBT test                  | Native SDP expectation?           | SDP                                                                                                                |
| ------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `not_null`                | Yes                               | `@dp.expect_or_drop("name", "col IS NOT NULL")` / `CONSTRAINT name EXPECT (col IS NOT NULL) ON VIOLATION DROP ROW` |
| `accepted_values: [a, b]` | Yes                               | `@dp.expect("name", "col IN ('a','b')")` / `CONSTRAINT name EXPECT (col IN ('a','b'))`                             |
| any column-level test     | Yes                               | One `CONSTRAINT ... EXPECT (<boolean>)` per test (e.g. `col >= 0`, `col LIKE '%@%'`)                               |
| `unique`                  | No — needs an aggregate           | No row-level expectation; emit a `TODO` for a post-pipeline uniqueness check                                       |
| `relationships`           | No — needs a cross-table subquery | No row-level expectation (EXPECT forbids subqueries); emit a `TODO` for a post-pipeline referential check          |

See `references/expectations-sql.md` /
`references/expectations-python.md` for violation actions (warn / drop / fail) and the full
reference.

> **AUTO CDC**: expectations apply on the **source view** feeding into
> `create_auto_cdc_flow()`, not on the target streaming table itself.

## Table properties

`{{ config(tblproperties={...}) }}` carries over to SDP:

| DBT                                 | SDP Python                          | SDP SQL                         |
| ----------------------------------- | ----------------------------------- | ------------------------------- |
| `{{ config(tblproperties={...}) }}` | `@dp.table(table_properties={...})` | `TBLPROPERTIES (key = 'value')` |

See `references/migrate-to-sdp/sdp-syntax.md` for placement rules in SQL.

## Jinja → native SDP

| DBT Jinja                          | SDP equivalent                                                                                |
| ---------------------------------- | --------------------------------------------------------------------------------------------- |
| `{{ var('x') }}`                   | SQL: `:x` / Python: `spark.conf.get("x")` — see `references/migrate-to-sdp/sdp-syntax.md` → Parameters       |
| `{{ env_var('X') }}`               | Same as `var` — SQL `:x` / Python `spark.conf.get("x")`; surface the env-var name to the user |
| `{{ config(materialized='...') }}` | Strip — the `sdp_type` decision is in the IR                                                  |
| `{% if is_incremental() %}`        | Strip — SDP handles incrementality automatically                                              |
| `{{ this }}`                       | Strip — SDP manages self-references internally                                                |
| Custom `{{ macro() }}`             | Expand inline using the macro's `macros/**/*.sql` definition                                  |

Always remove the `{{ config(...) }}` block — its information has already been
captured in the IR.

## Common DBT package → SDP equivalents

| DBT package call            | SDP equivalent                                 |
| --------------------------- | ---------------------------------------------- |
| `dbt_utils.date_spine`      | PySpark `sequence()` + `explode()`             |
| `dbt_utils.pivot`           | PySpark `.groupBy().pivot()`                   |
| `dbt_utils.surrogate_key`   | `sha2(concat_ws('\|', ...), 256)`              |
| `dbt_utils.union_relations` | `UNION ALL` (SQL) or `.union()` (PySpark)      |
| `dbt_expectations.*` tests  | `@dp.expect*` decorators / `CONSTRAINT EXPECT` |

If a custom or third-party macro has no clean equivalent, emit a `TODO` comment in
the generated file rather than guessing — flag it back to the user.

## Seeds

Seed CSVs are uploaded to a UC Volume before pipeline runs. Use the IR's
`seed_volume_path` to emit:

- **Python**: `spark.read.csv("/Volumes/.../seed.csv", header=True, inferSchema=True)` inside an `@dp.materialized_view()`.
- **SQL**: `read_files('/Volumes/.../seed.csv', format => 'csv', header => 'true')`.

If `seed_volume_path` is unset, flag the node for `manual_review` — the user must
upload the CSV and provide the Volume path.

## Worked examples

Pattern-specific worked examples are in `examples/`. Load on demand:

- `examples/incremental_to_streaming.md` — `incremental` (append) → `streaming_table`
- `examples/snapshot_to_cdc.md` — `snapshot` → `auto_cdc` SCD2 / `auto_cdc_snapshot`
- `examples/table_and_view.md` — `table` and `view` materializations
- `examples/macro_expansion.md` — custom macro expansion patterns
