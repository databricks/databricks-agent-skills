# Connector notes

What the docs pages don't make obvious. Pages: `https://docs.databricks.com/ingestion/lakeflow-connect/<key>-<page>`.

- **Dynamics 365** (`d365`): reads through Azure Synapse Link (CSV, or Parquet in Beta with a Synapse Spark pool); only Synapse Link exports are read.
- **GitHub**: `source_schema` is the organization name.
- **Gmail**: one mailbox per connection. For Gmail audit activity (sent, deleted, forwarded) use Google Workspace's `gmail` table.
- **Google Analytics Raw Data** (`google-analytics`): reads the GA4 **BigQuery export**, not the GA4 API; turn the export on first. `source_schema` is the `analytics_<property-id>` dataset. A service-account key is the **Username and password** auth type in the connection dialog. The user or service account needs `BigQuery Data Viewer`, `BigQuery Job User` and `BigQuery Read Session User`. Aggregated GA4 report metrics are the separate `google-analytics-aggregated` connector.
- **Google Workspace**: tables are named after the app they audit (`gmail`, `drive`, `login`, ...; `source_schema: default`). `gmail` and `drive` hold Admin SDK audit activity, not mail or files.
- **NetSuite**: token-based authentication only; needs the SuiteAnalytics JDBC license and the NetSuite2.com data source (not netsuite.com).
- **Outlook**: 1 table per pipeline.
- **Salesforce**: `source_schema: objects`. OAuth (browser sign-in) or mTLS; a sandbox org needs its own connection. Formula fields are re-read in full on every update unless [incremental formula field ingestion](https://docs.databricks.com/ingestion/lakeflow-connect/salesforce-formula-fields) (Beta, API only) is turned on for a new pipeline.
- **ServiceNow**: only tables with a `sys_id` column can be ingested. A reference field lands as a struct of `link` and `value` (the referenced `sys_id`): join downstream.
- **Veeva Vault**: Veeva keeps incremental archives for 10 days; a pipeline further behind needs a full refresh (two updates; ask first, it clears the tables).
- **Workday HCM** (`workday-hcm`): standard objects such as `workers`, `source_schema: default`.
- **Workday Reports** (`workday-reports`): custom reports (RaaS) built in Workday first; each object is `report: {source_url: <report URL>?format=json, destination_...}`. [Incremental](https://docs.databricks.com/ingestion/lakeflow-connect/workday-reports-incremental) (Beta) needs a cursor column (`sequence_by`) and `workday_report_parameters`; `primary_keys` alone doesn't make it incremental. For standard objects use Workday HCM.
