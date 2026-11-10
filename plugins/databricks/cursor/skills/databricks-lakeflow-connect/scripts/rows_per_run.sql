-- Rows per table per run: snapshot inserts, upserts, appends, deletes, for one Lakeflow Connect pipeline
-- (query-based, integrated CDC, or the ingestion pipeline of standard CDC). Reads only the event log.
--   databricks experimental aitools tools query --file scripts/rows_per_run.sql --param pipeline_id=<pipeline-id> --profile <PROFILE>
-- Column meanings and the flow-name patterns: references/rows-per-run.md.
WITH ev AS (
  SELECT * FROM event_log(:pipeline_id)
),
runs AS (
  SELECT origin.update_id,
         min(timestamp) AS started,
         max_by(details:update_progress.state::string, timestamp)
           FILTER (WHERE event_type = 'update_progress') AS state,
         max(details:create_update.full_refresh::boolean) AS full_refresh_all,
         max(details:create_update.full_refresh_selection::string) AS full_refresh_sel
  FROM ev
  WHERE event_type IN ('create_update', 'update_progress')
  GROUP BY 1
),
flow_rows AS (
  -- Per-table flows, by pipeline type:
  --   query-based:     <catalog>.<schema>.<catalog>_<schema>_<table>[_upsert]   (_upsert = SCD1/SCD2, none = APPEND_ONLY)
  --   integrated CDC:  <catalog>.<schema>.applier_<catalog>_<schema>_<table>_{snapshot|cdc}_flow
  --   standard CDC:    <catalog>.<schema>.<catalog>_<schema>_<table>_{snapshot|cdc}_flow   (ingestion pipeline)
  --   query-based, no cursor (full load each run): <catalog>.<schema>.<table>; records no row counts
  --   query-based hard-delete tracking: <catalog>.<schema>.<catalog>_<schema>_<table>_delete (counted into <table>)
  -- Skips _staging, extractor_*, cdc_staging_table, and internal timing-only flows.
  -- Note: if flow names use hyphens or backticks, the prefix pattern may not match and they show as "full load".
  --       Inspect origin.flow_name in the raw event log to see the actual pattern, then adapt the patterns.
  SELECT origin.update_id, origin.flow_name,
         element_at(split(origin.flow_name, '\\.'), 1) AS cat,   -- destination catalog and schema: same-name tables stay apart
         element_at(split(origin.flow_name, '\\.'), 2) AS sch,
         -- the table: the last name part, without the [applier_]<catalog>_<schema>_ prefix and the flow suffix
         CASE WHEN element_at(split(origin.flow_name, '\\.'), 3) RLIKE concat('^(applier_)?',
                     element_at(split(origin.flow_name, '\\.'), 1), '_', element_at(split(origin.flow_name, '\\.'), 2), '_')
              THEN regexp_replace(regexp_replace(element_at(split(origin.flow_name, '\\.'), 3),
                     concat('^(applier_)?', element_at(split(origin.flow_name, '\\.'), 1), '_',
                            element_at(split(origin.flow_name, '\\.'), 2), '_'), ''),
                     '_(snapshot_flow|cdc_flow|upsert|delete)$', '')
              ELSE element_at(split(origin.flow_name, '\\.'), 3) END AS tbl,
         origin.flow_name RLIKE '\\.applier_' AS is_integrated,
         CASE WHEN NOT origin.flow_name RLIKE '^([^.]+)\\.([^.]+)\\.(applier_)?\\1_\\2_.+$' THEN 'full load'
              WHEN origin.flow_name LIKE '%\\_snapshot\\_flow' THEN 'cdc snapshot'
              WHEN origin.flow_name LIKE '%\\_delete' THEN 'hard delete'
              WHEN origin.flow_name LIKE '%\\_cdc\\_flow' THEN 'cdc changes'
              WHEN origin.flow_name LIKE '%\\_upsert' THEN 'upsert'
              ELSE 'append' END AS kind,
         coalesce(details:flow_progress.metrics.num_upserted_rows::bigint, 0) AS upserted,
         coalesce(details:flow_progress.metrics.num_output_rows::bigint, 0) AS output_rows,
         coalesce(details:flow_progress.metrics.num_deleted_rows::bigint, 0) AS deleted
  FROM ev
  WHERE event_type = 'flow_progress'
    AND origin.flow_name NOT LIKE '%\\_staging'                        -- per-table staging flows: timings only
    AND (origin.flow_name RLIKE '^([^.]+)\\.([^.]+)\\.(applier_)?\\1_\\2_.+$'
         OR (origin.flow_name RLIKE '^[^.]+\\.[^.]+\\.[^.]+$'                 -- no-cursor full-load flow
             AND origin.flow_name NOT LIKE 'pipelines.%'
             AND origin.flow_name NOT LIKE '%.cdc\\_staging\\_table'
             AND NOT origin.flow_name RLIKE '\\.(applier|extractor)_'))
),
qbc_offsets AS (
  -- query-based only: the first batch's start offset; no incrementalOffset means a snapshot
  SELECT origin.update_id, origin.flow_name,
         min_by(get_json_object(details:stream_progress.progress_json::string,
                                '$.sources[0].startOffset.incrementalOffset'), timestamp) AS start_cursor
  FROM ev
  WHERE event_type = 'stream_progress'
  GROUP BY 1, 2
),
per_table AS (
  SELECT f.update_id, f.cat, f.sch, f.tbl,
         max(f.kind IN ('cdc snapshot', 'cdc changes')) AS is_cdc,
         max(f.is_integrated) AS is_integrated,
         max(f.kind = 'append') AS is_append,
         max(f.kind = 'full load') AS is_full_load,
         -- query-based: did any batch run, and did it start without a saved cursor?
         max(o.flow_name IS NOT NULL AND f.kind <> 'hard delete') AS qbc_batch,
         max(o.flow_name IS NOT NULL AND o.start_cursor IS NULL AND f.kind <> 'hard delete') AS qbc_snapshot,
         sum(CASE WHEN f.kind = 'cdc snapshot' THEN f.upserted ELSE 0 END) AS cdc_snapshot_rows,
         sum(CASE WHEN f.kind IN ('cdc changes', 'upsert') THEN f.upserted ELSE 0 END) AS upserted,
         sum(CASE WHEN f.kind = 'append' THEN f.output_rows ELSE 0 END) AS appended,
         sum(f.deleted) AS deleted
  FROM flow_rows f
  LEFT JOIN qbc_offsets o ON o.update_id = f.update_id AND o.flow_name = f.flow_name
  GROUP BY 1, 2, 3, 4
),
labeled AS (
  SELECT r.started, r.update_id, r.state,
         t.cat, t.sch, t.tbl, t.is_cdc, t.is_integrated, t.is_append, t.is_full_load, t.qbc_batch, t.qbc_snapshot,
         t.cdc_snapshot_rows, t.upserted, t.appended, t.deleted,
         coalesce(r.full_refresh_all, false)
           OR coalesce(array_contains(from_json(r.full_refresh_sel, 'array<string>'), t.tbl), false) AS is_full_refresh
  FROM runs r
  LEFT JOIN per_table t ON t.update_id = r.update_id   -- keep runs that failed before any table started
)
SELECT date_format(started, 'yyyy-MM-dd HH:mm:ss') AS run_started,
       update_id,
       state,
       cat AS catalog_name,
       sch AS schema_name,
       coalesce(tbl, '(no table ran)') AS table_name,
       CASE WHEN tbl IS NULL THEN NULL
            WHEN is_cdc AND is_integrated THEN 'integrated cdc'
            WHEN is_cdc THEN 'standard cdc'
            WHEN is_append THEN 'query-based append'
            WHEN is_full_load THEN 'query-based full load'
            ELSE 'query-based upsert' END AS pipeline_mode,
       CASE WHEN tbl IS NULL THEN 'none'
            WHEN is_full_refresh THEN 'full refresh'
            WHEN is_full_load THEN 'full load (no cursor; no row counts in the event log)'
            WHEN is_cdc AND cdc_snapshot_rows > 0 AND upserted + deleted > 0 THEN 'snapshot + changes'
            WHEN is_cdc AND cdc_snapshot_rows > 0 THEN 'snapshot'
            WHEN is_cdc AND upserted + deleted > 0 THEN 'incremental'
            WHEN is_cdc THEN 'no new data'
            WHEN NOT qbc_batch THEN 'no new data'
            WHEN qbc_snapshot THEN 'snapshot'
            ELSE 'incremental' END AS run_type,
       -- query-based snapshots and full refreshes count their rows as snapshot inserts
       CASE WHEN is_full_load THEN NULL
            WHEN is_cdc THEN cdc_snapshot_rows
            WHEN is_full_refresh OR qbc_snapshot THEN upserted + appended
            ELSE 0 END AS snapshot_inserted,
       CASE WHEN is_full_load THEN NULL WHEN NOT is_cdc AND (is_full_refresh OR qbc_snapshot) THEN 0 ELSE upserted END AS upserted,
       CASE WHEN is_full_load THEN NULL WHEN NOT is_cdc AND (is_full_refresh OR qbc_snapshot) THEN 0 ELSE appended END AS appended,
       CASE WHEN is_full_load THEN NULL ELSE deleted END AS deleted
FROM labeled
ORDER BY started, catalog_name, schema_name, table_name
