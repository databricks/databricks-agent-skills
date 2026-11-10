# Rows per table per run

What each run did per table (snapshot, upserts, appends, deletes; snapshot, full refresh or incremental), for query-based, integrated CDC and standard CDC ingestion pipelines.

Run the SQL in `scripts/rows_per_run.sql` with the pipeline ID as its `:pipeline_id` parameter.

Columns: `update_id` (full, for `databricks pipelines get-update`), `catalog_name`, `schema_name`, `table_name`, `pipeline_mode`, `run_type` (`snapshot`, `snapshot + changes`, `incremental`, `full refresh`, `full load`, `no new data`), `snapshot_inserted`, `upserted`, `appended`, `deleted`. The script reads flow names (`<catalog>.<schema>.[applier_]<catalog>_<schema>_<table>_{snapshot|cdc}_flow`, `..._upsert`, `..._delete`; a no-cursor table's flow is `<catalog>.<schema>.<table>` with no counts); names it doesn't match show as `full load`: read `origin.flow_name` and adapt it. The kind and table come from those suffixes, so an `APPEND_ONLY` table whose name ends in `_delete` or `_upsert` is misread.

Tell the user:
- A running integrated CDC update reports partial counts: re-run after it completes.
- Under CDC, a table without a key is keyed on all columns, so identical rows collapse and the snapshot can be below the source count.
- Query-based SCD1/SCD2 with a timestamp cursor re-read a short lookback window, so `upserted` can include unchanged rows.

**Query-based SCD2 changes, counted from the table** (`__START_AT` / `__END_AT` hold the cursor value):

```sql
WITH k AS (
  SELECT <key> AS key, min(__START_AT) AS first_start,
         count_if(__START_AT >= TIMESTAMP '<since>') AS started,
         count_if(__END_AT IS NULL) AS open_now,
         count_if(__END_AT >= TIMESTAMP '<since>') AS closed
  FROM <catalog>.<schema>.<table> GROUP BY <key>)
SELECT count_if(first_start >= TIMESTAMP '<since>') AS inserted,
       count_if(first_start < TIMESTAMP '<since>' AND started > 0) AS updated,
       count_if(closed > 0 AND open_now = 0) AS deleted
FROM k
```
