# Reverse ETL with Lakebase Autoscaling

Sync data from Unity Catalog Delta tables into Lakebase as PostgreSQL tables for OLTP access patterns.

**How it works:** Synced tables create a managed copy — a Unity Catalog table (read-only, managed by sync pipeline) and a Postgres table in Lakebase (queryable by apps). Uses managed Lakeflow Spark Declarative Pipelines.

**Performance (per Autoscaling CU):**
- Continuous/Triggered: ~150 rows/sec per CU
- Snapshot: ~2,000 rows/sec per CU
- Each synced table uses up to 16 connections

## Sync Modes

| Mode | Description | CDF Required | Best For |
|------|-------------|-------------|----------|
| **Snapshot** | One-time full copy | No | Initial setup, small tables, >10% data change |
| **Triggered** | Scheduled updates | Yes | Dashboards updated hourly/daily |
| **Continuous** | Real-time (seconds latency, 15s min interval) | Yes | Live applications |

**Enable CDF on source table:**

```sql
ALTER TABLE your_catalog.your_schema.your_table
SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
```

## Creating Synced Tables

```bash
databricks database create-synced-database-table \
  --json '{
    "name": "lakebase_catalog.schema.synced_table",
    "spec": {
      "source_table_full_name": "analytics.gold.user_profiles",
      "primary_key_columns": ["user_id"],
      "scheduling_policy": "TRIGGERED",
      "new_pipeline_spec": {
        "storage_catalog": "lakebase_catalog",
        "storage_schema": "staging"
      }
    }
  }' --profile <PROFILE>
```

**Check status:**

```bash
databricks database get-synced-database-table --name "lakebase_catalog.schema.synced_table" --profile <PROFILE>
```

**Delete:** Remove from Unity Catalog (Catalog Explorer or SDK), then drop the Postgres table:

```sql
DROP TABLE your_database.your_schema.your_table;
```

## Data Type Mapping

| Unity Catalog Type | Postgres Type |
|-------------------|---------------|
| BIGINT | BIGINT |
| BINARY | BYTEA |
| BOOLEAN | BOOLEAN |
| DATE | DATE |
| DECIMAL(p,s) | NUMERIC |
| DOUBLE | DOUBLE PRECISION |
| FLOAT | REAL |
| INT | INTEGER |
| INTERVAL | INTERVAL |
| SMALLINT | SMALLINT |
| STRING | TEXT |
| TIMESTAMP | TIMESTAMP WITH TIME ZONE |
| TIMESTAMP_NTZ | TIMESTAMP WITHOUT TIME ZONE |
| TINYINT | SMALLINT |
| ARRAY, MAP, STRUCT | JSONB |

**Unsupported:** GEOGRAPHY, GEOMETRY, VARIANT, OBJECT

## Capacity Planning

- **Connections:** Each synced table uses up to 16 connections toward the endpoint limit
- **Storage:** 8 TB total across all synced tables per branch
- **Recommendation:** Keep individual tables under 1 TB if they require incremental refreshes
- **Naming:** Database, schema, and table names allow `[A-Za-z0-9_]+` only
- **Schema evolution:** Only additive changes (adding columns) for Triggered/Continuous modes

## Lakehouse Sync (Beta, AWS only)

Reverse direction: continuously streams changes **from** Lakebase Postgres **into** Unity Catalog Delta tables using CDC. Enables analytics and downstream pipelines on OLTP-written data. Azure support not yet available.

## Use Cases

**Product catalog:** Sync gold-tier product data to Lakebase for low-latency web app reads. Use Triggered mode for hourly/daily updates.

**Real-time feature serving:** Sync ML feature tables to Lakebase with Continuous mode for sub-second feature lookups during inference.

## Best Practices

1. Enable CDF on source tables before creating Triggered/Continuous syncs
2. Snapshot mode is 10x more efficient when >10% of data changes per cycle
3. Monitor sync status for failures and latency via Catalog Explorer
4. Create indexes in Postgres for your application query patterns
5. Account for the 16-connection-per-table limit when planning endpoint capacity
