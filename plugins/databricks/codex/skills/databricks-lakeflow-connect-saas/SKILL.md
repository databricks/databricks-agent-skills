---
name: databricks-lakeflow-connect-saas
description: "Lakeflow Connect ingestion from SaaS apps (Salesforce, Workday, ServiceNow, HubSpot, SharePoint, Google Drive, OneDrive, Jira, ads, audit logs, 70+ more) and Kafka or RabbitMQ into Unity Catalog. Use when finding a connector, creating its connection and pipeline, scheduling or debugging it."
compatibility: Requires databricks CLI (>= v1.23.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Lakeflow Connect: SaaS connectors

**FIRST**: use the parent `databricks-core` skill for CLI install, authentication, and profile selection.

| Source | Skill |
|---|---|
| A SaaS application, a RabbitMQ queue, or a Kafka topic with the managed connector (Beta) | this skill |
| A Kafka topic whose messages need more than the key and value formats the [Kafka pipeline](https://docs.databricks.com/ingestion/lakeflow-connect/kafka-pipeline) page lists | `read_kafka` in **databricks-pipelines**, or **databricks-spark-structured-streaming** |
| A database (SQL Server, PostgreSQL, MySQL, Oracle, query-based) | **databricks-lakeflow-connect** |
| An app or device that pushes events | **databricks-zerobus-ingest** |
| Files on cloud object storage | Auto Loader, **databricks-pipelines** |
| Files on an SFTP server | SFTP file connector on Auto Loader: [file-connectors.md](references/file-connectors.md) |
| A stream with no managed connector (Kinesis, Pub/Sub, Pulsar) | **databricks-spark-structured-streaming** |
| A source with no managed connector | a [custom connector](https://docs.databricks.com/ingestion/custom-connectors) (Beta) or a [community connector](https://docs.databricks.com/ingestion/community-connectors) |

## Find the connector's pages

Connectors and options change faster than this skill: read the connector's docs pages instead of answering from memory. When a page and this skill disagree, the page wins.

- Connector keys: the links on [SaaS connectors](https://docs.databricks.com/ingestion/lakeflow-connect/saas-overview), [streaming connectors](https://docs.databricks.com/ingestion/lakeflow-connect/streaming-overview) (Kafka, RabbitMQ) and [file connectors](https://docs.databricks.com/ingestion/lakeflow-connect/file-connectors-overview). Say a connector isn't available only when none of them lists it.
- Keys on those pages as of 2026-11 (newer ones may be there): 1password-event-logs, aha, akamai-waf, amplitude, anaplan, anthropic, anysphere-audit-logs, anysphere-organization, asana, atlassian-audit-logs, azure-devops, box-audit-logs, celigo, confluence, cribl, crowdstrike-falcon-event-stream, d365, github, gitlab, glean, gmail, google-ads, google-analytics, google-analytics-aggregated, google-drive, google-search-console, google-workspace, hubspot, jira, kafka, linkedin-ads, marketo, meta-ads, microsoft-365, microsoft-entra-id, microsoft-graph-logs, monday-com, netskope-logs, netsuite, notion, okta, okta-system-logs, onedrive, openai, oracle-eloqua, outlook, pagerduty, paypal, pendo, productboard, quickbooks, rabbitmq, reddit-ads, salesforce, sendgrid, servicenow, sfmc, sharepoint, shopify, smartsheet, square, strac, surveymonkey, tiktok-ads, veeva-vault, verkada, vimeo, wiz-audit-logs, workday-activity-logging, workday-hcm, workday-reports, workiva, xero, zendesk-support, zip, zoho-books, zoho-crm.
- Pages: `https://docs.databricks.com/ingestion/lakeflow-connect/<key>` (or `<key>-overview`), then `-source-setup`, `-connection`, `-pipeline`, `-reference`, `-limits`, `-troubleshoot` (not every connector has each).
- Read pages with the web-fetch tool or the **databricks-docs** skill. If neither is available, give the user the page links and ask what they show; don't fetch another way.
- Read `-reference` before naming a source table or saying which tables are incremental; `-limits` before sizing.
- Notes to read before the steps: Google, Meta, LinkedIn, Reddit, TikTok Ads → [ads.md](references/ads.md); SharePoint, Google Drive, OneDrive, SFTP → [file-connectors.md](references/file-connectors.md); Kafka, RabbitMQ → [streaming.md](references/streaming.md); the rest → [connector-notes.md](references/connector-notes.md).

## Workflow

Ask for every missing input in one message (connector, objects, destination catalog and schema, schedule), list what you'll create, and wait for one "yes".

1. **Previews toggle.** When the page's Beta note mentions the **Previews** page, a workspace admin turns that preview on first. Beta has no production SLA: say so.
2. **Source setup.** Follow `-source-setup` on the SaaS side (app registration, API user, scopes). Connectors with several auth methods have one setup page each.
3. **Connection.** Created in Catalog Explorer (the `-connection` page has the exact path), often with a browser sign-in. Ask the user to create it from the `-connection` page and give you its name; don't guess `connection_type` or option names for `databricks connections create`. Grants: **databricks-unity-catalog**.
4. **Pipeline.** Copy the object shape from the `-pipeline` page examples. `source_schema` is usually `default`, the account ID for ads, `objects` for Salesforce; never a placeholder.
5. **Run and schedule.** Start one update and check it, then schedule a Jobs `pipeline_task` (**databricks-pipelines**, **databricks-jobs**). Anything kept: a bundle `pipelines` resource with this `ingestion_definition` plus a job with a `pipeline_task` (**databricks-dabs**). Kafka and RabbitMQ run continuously, with no job.

```json
{
  "name": "jira_ingest",
  "catalog": "main",
  "schema": "jira_raw",
  "ingestion_definition": {
    "connection_name": "<jira-connection>",
    "objects": [
      {"table": {"source_schema": "default", "source_table": "issues",
                 "destination_catalog": "main", "destination_schema": "jira_raw"}}
    ]
  }
}
```

- `connection_name` is the UC connection's name, not its ID.
- `objects[].table` per table, `objects[].schema` for every table of a source schema, or `objects[].report` with `source_url` (Workday Reports).
- `connector_options` carries connector settings (lookback windows, report levels, URLs); the keys don't follow the connector key (Google Drive is `gdrive_options`): take them from `databricks bundle schema` (`pipelines.ConnectorOptions`).
- `table_configuration` carries per-table settings such as `scd_type: SCD_TYPE_2`, where the overview's feature table allows it.
- `channel: PREVIEW` only where the docs examples set it: SharePoint (GA), Google Drive, OneDrive, Kafka, RabbitMQ.

## Important

- **An ingestion pipeline has `ingestion_definition`, never `libraries`.**
- Ask before reusing a destination schema: a source table whose name matches an existing destination table fails the update.
- Two tables with the same name can't share a pipeline, even from different source schemas: set `destination_table` on one, or split. A renamed table, or several destination catalogs or schemas, make the pipeline API-only.
- A column selected after the pipeline started isn't backfilled. A full refresh backfills it but clears the table and its state and reloads from the source: SCD type 2 history, rows deleted at the source and data the source no longer keeps are lost. Say so and ask before running one.
- A table deleted at the source keeps its destination table.

## Troubleshooting

Read the pipeline's event log (**databricks-pipelines**), then the connector's `-troubleshoot` page.

| Symptom | Cause | Fix |
|---|---|---|
| `DUPLICATE_KEY_VIOLATION` | The key the source reports isn't unique per row (NetSuite's line-level tables report `transactionid`) | Set `table_configuration.primary_keys` to a key that is unique per row, as the connector's `-pipeline` page names it (NetSuite: `transactionid` and `line`), then full refresh that table (ask first) |
| A working connection fails auth | Refresh token revoked or expired | Reauthorize the connection in Catalog Explorer |
| Create fails or the connector isn't found | Previews toggle off, or `channel: PREVIEW` missing | Check the page's Beta note and examples |
| Every update re-reads a whole table | No cursor (entity tables, formula fields, report snapshots) | Expected; Salesforce formula fields can be ingested incrementally (Beta) in a new pipeline, API only: [Ingest formula fields incrementally](https://docs.databricks.com/ingestion/lakeflow-connect/salesforce-formula-fields) |
| Too many tables | Per-pipeline cap on `-limits` (250 where stated, NetSuite 200, Outlook 1) | Split the pipeline |

## Reference Files

- [ads.md](references/ads.md): ads entity vs report tables, account-ID schemas, options.
- [file-connectors.md](references/file-connectors.md): SharePoint, Google Drive, OneDrive, SFTP.
- [streaming.md](references/streaming.md): Kafka and RabbitMQ.
- [connector-notes.md](references/connector-notes.md): traps for other connectors, A to Z.
