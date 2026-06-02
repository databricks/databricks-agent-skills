# Database connectors

SQL Server (cloud and on-prem) is the GA database connector. Postgres CDC, MySQL CDC, query-based variants, and Foreign Catalog connectors are Public Preview — production-supported but covered briefly here; see the [connector reference](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/connectors) for their setup until deep coverage lands in a follow-up.

---

## The gateway pattern

Database connectors are **not** pure serverless. They split into two pipelines:

```
          ┌───────────────────────┐
          │  Customer database    │
          │  (SQL Server, etc.)   │
          └──────────┬────────────┘
                     │  CDC / change tracking
                     ▼
          ┌───────────────────────┐
          │  Ingestion gateway    │   classic compute,
          │  (one pipeline)       │   runs in customer VPC
          └──────────┬────────────┘
                     │  change events
                     ▼
          ┌───────────────────────┐
          │  UC Volume staging    │   30-day retention by default
          └──────────┬────────────┘
                     │
                     ▼
          ┌───────────────────────┐
          │  Ingestion pipeline   │   serverless,
          │  (one pipeline)       │   applies CDC into Delta
          └──────────┬────────────┘
                     ▼
          ┌───────────────────────┐
          │  Delta tables in UC   │
          └───────────────────────┘
```

Why each piece:

- **Gateway** runs in the customer's network so the source database is never exposed to Databricks-managed compute. It reads the CDC / change-tracking stream and writes change events into a UC Volume.
- **Staging Volume** decouples the two pipelines: the gateway can run on its own cadence, and the ingestion pipeline can re-process from the Volume without re-reading the source.
- **Ingestion pipeline** is the serverless half — it applies the staged events to Delta with CDC semantics and handles schema evolution.

Trade-offs:

- Two pipelines, two pieces of state. Both must be healthy.
- Gateway is **classic compute** — billed separately from the serverless ingestion DBUs. See the [pricing page](https://www.databricks.com/product/pricing/lakeflow-connect) for current rates.
- Staging Volume retention is 30 days. Reprocessing further back requires a snapshot reload.

---

## SQL Server: change tracking vs CDC

SQL Server offers two source mechanisms; pick one per database.

**Change Tracking (CT)** — lightweight. The source tracks "which rows changed since version X" but not the actual change history. The gateway re-reads changed rows from the base table.

- Lower overhead on the source.
- Adequate when downstream only needs the latest state per PK.
- Cannot reconstruct historical change order.

**Change Data Capture (CDC)** — full change log. The source writes inserts/updates/deletes into change tables that the gateway reads directly.

- Higher overhead on the source (separate change tables, log reader job).
- Required when downstream needs per-event history (audit, SCD2 from raw deltas, etc.).

Most pipelines start with CT and switch to CDC only when audit or SCD2 demands it.

---

## SQL Server cloud setup

Prerequisites:

1. **SQL Server 2012+** (cloud-managed: Azure SQL DB, Azure SQL MI, RDS for SQL Server).
2. **A dedicated database user** for the connector's ongoing reads, granted the minimum CT/CDC privileges for the source (see the connector reference). `db_owner` is the broad, simple alternative but is over-privileged for steady-state ingestion — if you use it, keep it to a DBA enabling CDC transiently, not the connector's read account.
3. **CT or CDC enabled** on the source tables (`ALTER DATABASE ... SET CHANGE_TRACKING = ON` for CT; `sys.sp_cdc_enable_table` for CDC).
4. **Network reachability** — the gateway compute must reach the source database. For cloud SQL Server this is usually VPC peering or PrivateLink.

A DAB stub with both pipelines:

```yaml
resources:
  pipelines:
    sqlserver_gateway:
      name: sqlserver_gateway
      gateway_definition:
        connection_name: my_sqlserver_connection
        gateway_storage_catalog: ${var.catalog}
        gateway_storage_schema: ingestion_staging
        gateway_storage_name: sqlserver_gateway_storage

    sqlserver_ingestion:
      name: sqlserver_to_uc
      ingestion_definition:
        ingestion_gateway_id: ${resources.pipelines.sqlserver_gateway.id}
        objects:
          - table:
              source_catalog: sales_db
              source_schema: dbo
              source_table: orders
              destination_catalog: ${var.catalog}
              destination_schema: sqlserver_raw
```

The SDK Python equivalent uses `w.pipelines.create` twice — once with `gateway_definition`, once with `ingestion_definition` referencing the gateway's pipeline ID.

---

## SQL Server on-prem

Same setup as cloud, plus private networking from the gateway to the on-prem source:

- **Azure**: ExpressRoute or VPN gateway between the customer VNet and the on-prem network.
- **AWS**: Direct Connect or Site-to-Site VPN between the customer VPC and the on-prem network.
- **GCP**: Cloud Interconnect or Cloud VPN.

The gateway compute itself runs on Databricks-managed VPC infrastructure inside the customer's workspace, so the private link only needs to extend that far.

---

## Database-specific gotchas

| Symptom | Likely cause | Fix |
|---|---|---|
| Gateway requires an instance type unavailable in the region | Default gateway cluster shape not stocked in the target region | Apply a cluster policy override on the gateway pipeline to pin a regionally-available instance type. |
| Snapshot-only mode silently disabled | Snapshot-only is not supported for CDC sources | Use CT instead, or accept incremental mode. |
| Pipeline state diverges from source after 30+ days | Staging Volume retention expired | Resnapshot the affected tables. Increase the Volume retention if reprocessing further back is a recurring need. |
| "Continuous mode not supported" error at create | Lakeflow Connect is triggered-only (no continuous mode) | Use `continuous: false` plus a Jobs schedule. |
| Gateway pipeline succeeds but ingestion pipeline shows no new data | Staging path mismatch between the two pipelines | Confirm `gateway_storage_*` on the gateway matches the staging path the ingestion pipeline reads from. |

---

## Public Preview database connectors (brief)

The following are production-supported but ship more pattern variance than SQL Server. Use the [connector reference](https://docs.databricks.com/aws/en/ingestion/lakeflow-connect/connectors) for current setup steps:

- **Postgres CDC, MySQL CDC** — same gateway pattern as SQL Server; logical decoding (Postgres) or binlog (MySQL) replaces CT/CDC.
- **Oracle / Teradata / SQL Server / Postgres / MySQL query-based** — no gateway; the connector issues periodic queries instead of reading a change feed. Trade-off: simpler, but higher source load and no per-event history.
- **Snowflake / Redshift / Synapse / BigQuery (Foreign Catalog)** — Lakeflow Connect creates the foreign catalog and materializes the queried subset to Delta. Most useful for warehouse-to-lakehouse migration scenarios.

Deep coverage for these connectors will land as they stabilize.
