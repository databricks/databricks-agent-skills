# SaaS connectors

The six GA SaaS connectors (Salesforce, Workday Reports, ServiceNow, Google Analytics 4, HubSpot, Confluence) all share the same authoring pattern. This reference covers the unified flow once, then captures per-connector deltas.

---

## The unified SaaS pattern

Three steps for every SaaS connector:

1. **Create a UC `CONNECTION`** that owns the source credentials.
   - **OAuth U2M** connections (Salesforce, ServiceNow, HubSpot, Confluence) must be created in Catalog Explorer — the OAuth handshake requires a browser. CLI and DAB cannot bootstrap U2M.
   - **API-key / basic / refresh-token** connections (Workday Reports, GA4 via service account, ServiceNow basic) can be created with `databricks connections create` or a DAB resource.
2. **Create the ingestion pipeline** with `databricks pipelines create --json` (or DAB). The pipeline carries the `ingestion_definition` block that names the connection and lists the source objects to land.
3. **Schedule the pipeline**. Lakeflow Connect supports triggered runs only — schedule with a Jobs `pipeline_task` (cron or interval). The pipeline's `continuous: false` setting selects triggered mode but does not itself carry a schedule.

A minimal pipeline JSON:

```json
{
  "name": "salesforce_to_uc",
  "ingestion_definition": {
    "connection_name": "my_salesforce_oauth_connection",
    "objects": [
      {"table": {"source_schema": "salesforce", "source_table": "Account",
                 "destination_catalog": "main", "destination_schema": "salesforce_raw"}}
    ]
  }
}
```

Keys to know:

- `ingestion_definition.connection_name` — the UC connection name (not URL, not ID).
- `objects[].table` — one entry per source table. Use `objects[].schema` to ingest a whole source schema in one block.
- `channel` — selects the SDP runtime release channel (`CURRENT` = default GA runtime; `PREVIEW` = preview runtime). Some preview/beta connectors run only on the preview runtime, so their docs require `channel: PREVIEW`. GA connectors run on `CURRENT`, so omit `channel`. It selects a runtime, not a connector's GA status — preview-channel builds also have longer startup times.

---

## Salesforce

- **Auth**: OAuth U2M only. No machine-to-machine, no basic auth, no API key. The connection must be created in Catalog Explorer with a browser-based login.
- **Limit**: 250 tables per pipeline. Split larger workloads into multiple pipelines partitioned by object family.
- **Formula fields**: ingested as full snapshots only — incremental CDC is not available for computed columns. Plan for higher DBU usage on objects with many formula fields.
- **Data-type changes**: source data-type changes are not auto-handled. A reload from snapshot is required when the source column type changes.
- **Sandboxes**: a separate UC connection per sandbox vs production org. Don't reuse connections across orgs.

---

## Workday Reports (RaaS)

The Workday connector is **Report-as-a-Service** — it ingests Workday custom reports, not raw HCM tables. Workday HCM is a separate (Beta) connector.

- **Auth**: OAuth refresh token (recommended for production) or HTTP basic. The refresh token must be minted in Workday and stored in the UC connection.
- **Source objects**: each "table" is a Workday custom report. Configure the report in Workday first, then reference it by name in the pipeline.
- **Limits**: same 250-table-per-pipeline cap; per-report row limits inherit from the Workday report itself.
- **No auto data-type evolution**: report schema changes require a pipeline edit + reload.

---

## ServiceNow

- **Auth**: OAuth U2M (recommended) or HTTP basic. OAuth requires a registered ServiceNow OAuth application; basic auth requires a service account with read access to the target tables.
- **Source objects**: ServiceNow table names (e.g., `incident`, `change_request`). Reference fields (sys_id -> related record) are kept as `sys_id` strings — joins happen downstream.
- **Limits**: 250 tables per pipeline. Long-running ServiceNow instances with custom tables may need multiple pipelines.
- **Pagination**: handled by the connector; no client-side configuration needed.

---

## Google Analytics 4

GA4 ingestion goes **via BigQuery** — Lakeflow Connect reads from the GA4 BigQuery export, not from the GA4 API directly. The customer must enable BigQuery export in their GA4 property before the connector can run.

- **Auth**: GCP service-account JSON key. The service account needs `BigQuery Data Viewer` on the GA4 export dataset.
- **Prereq**: GA4 -> BigQuery export must be enabled (Admin -> BigQuery Links). Daily export is the typical setup; streaming export is supported.
- **Source objects**: the `events_*` tables in the GA4 export dataset. The connector handles the daily-shard pattern transparently.
- **Latency**: bounded by the GA4 -> BigQuery export cadence (typically next-day for daily export).

---

## HubSpot

- **Auth**: OAuth U2M.
- **Source objects**: HubSpot CRM objects (Contacts, Companies, Deals, Tickets, etc.) plus engagements. Check the connector reference for the current object list.
- **Status caveat**: status may differ by region — check the [connector reference](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/connectors) to confirm GA in your region before relying on production SLAs.

---

## Confluence

- **Auth**: OAuth U2M.
- **Source objects**: spaces, pages, comments. Markup is preserved in the page body column.
- **Status caveat**: same as HubSpot — confirm regional availability in the connector reference.

---

## DAB pattern for SaaS connectors

The production authoring path is a Declarative Automation Bundle resource. A minimal pipeline resource:

```yaml
resources:
  pipelines:
    salesforce_ingestion:
      name: salesforce_to_uc
      ingestion_definition:
        connection_name: my_salesforce_oauth_connection
        objects:
          - table:
              source_schema: salesforce
              source_table: Account
              destination_catalog: ${var.catalog}
              destination_schema: salesforce_raw
          - table:
              source_schema: salesforce
              source_table: Opportunity
              destination_catalog: ${var.catalog}
              destination_schema: salesforce_raw
```

Schedule it via a Jobs resource with a `pipeline_task` pointing at this pipeline. See **databricks-dabs** for bundle structure, target overrides, and the recommended layout for multi-pipeline bundles.

---

## Common SaaS gotchas

| Symptom | Likely cause | Fix |
|---|---|---|
| Watermark not advancing on an object | Cursor field misconfigured for that source object | Check the per-connector cursor-column docs; some objects need an explicit cursor override. |
| Duplicate-key error after a snapshot reload | Source has duplicate PKs (Salesforce composite keys, ServiceNow merged records) | Inspect the source for the duplicates; the connector won't auto-resolve. |
| New source column missing from the target | Schema evolution disabled or not yet propagated | Re-enable schema evolution on the destination table and trigger a snapshot run. |
| OAuth connection stuck in `PENDING` | U2M authorization not completed in Catalog Explorer | Re-open the connection in Catalog Explorer and complete the browser flow. |
| Connector requires `channel: PREVIEW` at create time | The connector runs only on the preview SDP runtime channel | Set `channel: PREVIEW` as the connector's docs instruct. `channel` picks the runtime, not the connector's GA status; GA connectors run on `CURRENT` (omit it). If gateway startup is slow, `CURRENT` is faster where the connector supports it. |
| Pipeline succeeds but no rows land | Destination schema missing, or the connection account lacks read on the source object | Check the event log; pre-flight errors are surfaced there. |
