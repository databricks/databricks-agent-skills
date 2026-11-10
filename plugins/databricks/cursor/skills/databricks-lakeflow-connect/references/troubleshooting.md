# Troubleshooting

Read the source's troubleshoot page first; source errors: [sources.md](sources.md). Event-log conventions: **databricks-pipelines**.

## Where to look

```sql
SELECT timestamp, event_type, level, message, error FROM event_log('<pipeline-id>')
WHERE level IN ('ERROR', 'WARN') AND timestamp > current_timestamp() - INTERVAL 1 DAY
ORDER BY timestamp DESC LIMIT 50
```

- From the CLI: `databricks api get "/api/2.0/pipelines/<pipeline-id>/events?max_results=100"` has `details`; `pipelines list-pipeline-events` leaves them out.
- Across pipelines or back in time: the [pipeline events system table](https://docs.databricks.com/admin/system-tables/pipeline-events) (`system.lakeflow_pipeline_events_preview.pipeline_events`).
- Standard CDC has two event logs: read both.
- **Each update can run on a different runtime** (pipelines are versionless): before comparing two updates, read each one's `runtime_details` event (`details:runtime_details.runtime_version.dbr_version`).

## Errors across modes

| Error / symptom | Fix |
|---|---|
| `APPLY_CHANGES_FROM_SNAPSHOT_ERROR.DUPLICATE_KEY_VIOLATION` | The declared key isn't unique at the source: fix the duplicates or declare a unique key |
| SCD2 row count doesn't match the source | One row per version: count `__END_AT IS NULL` |
| Lag looks healthy, destination empty | Count rows; `DESCRIBE HISTORY` shows `numTargetRowsInserted` per MERGE |
| "The number of tables in this pipeline ... exceeds the quota of ... tables per pipeline" | Keep the pipeline under the quota the message gives and within the source's limits page; split the rest |
| `INGESTION_GATEWAY_INTERNAL_ERROR` | Check `list-updates`: the pipeline often retries and recovers; if not, report the update IDs |
| "Failed to resolve flow" or `INGESTION_GATEWAY_TABLE_DROPPED` | A source table was dropped: remove it from the pipeline |
| Purged change log (CDC or change-tracking retention, binlog expiry) | Full refresh; schedule well inside retention |
| A connector requires `channel: PREVIEW` | Set it where the docs say so; otherwise omit it |
