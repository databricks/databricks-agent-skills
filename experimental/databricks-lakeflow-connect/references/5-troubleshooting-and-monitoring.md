# Troubleshooting and monitoring

This reference covers what to check when an ingestion pipeline misbehaves: where the logs live, the common error shapes, and the escalation path.

---

## Where to look first

Every Lakeflow Connect pipeline emits a structured event log. For SaaS pipelines that's the only artifact; for database pipelines you'll also want to inspect the gateway pipeline's events.

The event log is a Delta table on the pipeline. Query it through SQL:

```sql
SELECT timestamp, level, message, error
FROM event_log("<pipeline-id>")
WHERE level IN ('ERROR', 'WARN')
  AND timestamp > current_timestamp() - INTERVAL 1 DAY
ORDER BY timestamp DESC
LIMIT 50;
```

For event-log table conventions (filtering by `event_type`, joining with metrics, etc.), see **databricks-pipelines**.

**Database pipelines have two event logs** — one for the gateway, one for the ingestion pipeline. A symptom on the ingestion side often has its root cause in the gateway side. When debugging database connectors, query both.

---

## Common errors and resolutions

| Error / symptom | Likely cause | Resolution |
|---|---|---|
| `APPLY_CHANGES_FROM_SNAPSHOT_ERROR.DUPLICATE_KEY_VIOLATION` | Source snapshot contains duplicate values on the declared primary key. | Inspect the source for duplicate PKs (often a merged record or composite-key surprise). The connector won't auto-resolve — fix at the source or change the PK declaration. |
| `validate_only` update appears in pipeline run history | Expected. A dry-run validation run is logged alongside actual runs. | Filter `event_log` on `details:flow_progress.status != 'VALIDATING'` if the dry-runs are noisy. |
| SCD2 row count doesn't match raw source count | Expected. SCD2 multiplies rows per change (one row per version), so SCD2 row count >> source row count is normal. | Compare on PK count with `current = true` instead of total row count. |
| `NULL` values appear after switching SCD1 -> SCD2 | Expected. Pre-switch history is reconstructed as a single open version with `NULL`s for unknown deltas. | Re-snapshot the table if a clean SCD2 history is required from a specific point. |
| `GB ingested` >> source row size in the metrics | Expected for CDC sources. Change log columns, schema metadata, and per-batch overhead inflate ingested bytes. | Use source row count, not GB ingested, as the workload sizing signal. |
| Gateway pipeline fails: instance type unavailable in region | Default gateway cluster shape isn't stocked in the target region. | Apply a cluster policy override on the gateway pipeline to pin a regionally-available instance type. |
| Pipeline runs but the destination table never updates | UC `CONNECTION` not in `READY` state, OR destination schema missing. | `DESCRIBE CONNECTION <name>` — state must be `READY`. Verify the destination schema exists and the pipeline's service principal has `CREATE TABLE` + `MODIFY`. |
| OAuth U2M connection refreshes fail after weeks of working | Refresh token expired or revoked at the SaaS source. | Re-open the connection in Catalog Explorer and re-authorize. Plan for periodic re-auth if the SaaS source enforces a refresh-token lifetime. |
| Connector requires `channel: PREVIEW` at pipeline create | The connector runs only on the preview SDP runtime channel. | Set `channel: PREVIEW` as the connector's docs instruct — it selects the runtime channel, not the connector's GA status. GA connectors run on `CURRENT` (omit it); if gateway startup is slow, `CURRENT` is faster where supported. |

---

## Escalation pointers

When the event log doesn't explain a failure:

1. **Public docs hub** — [Lakeflow Connect overview](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect) covers concepts and links to per-connector pages.
2. **Connector reference** — [per-connector setup](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/connectors) is the canonical source for current auth, limits, and supported objects per source.
3. **Workspace support** — file a support case from Help -> Contact Support inside the workspace; attach the pipeline ID and a relevant `event_log` extract.

For monitoring patterns beyond event-log queries (dashboards, alerting on pipeline state, SLAs), see **databricks-pipelines**.
