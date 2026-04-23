# Synced Tables

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

## Prerequisites

Before creating synced tables, register a UC catalog for your Lakebase database:

```bash
databricks postgres create-catalog <CATALOG_NAME> \
  --json '{
    "spec": {
      "postgres_database": "<POSTGRES_DATABASE>",
      "branch": "projects/<PROJECT_ID>/branches/<BRANCH_ID>"
    }
  }' --profile <PROFILE>
```

The `<POSTGRES_DATABASE>` is the Postgres database name (default: `databricks_postgres`), not the resource path.

## Creating Synced Tables

```bash
databricks postgres create-synced-table <LAKEBASE_CATALOG>.<SCHEMA>.<TABLE> \
  --json '{
    "spec": {
      "source_table_full_name": "analytics.gold.user_profiles",
      "primary_key_columns": ["user_id"],
      "scheduling_policy": "TRIGGERED",
      "branch": "projects/<PROJECT_ID>/branches/production",
      "postgres_database": "databricks_postgres",
      "create_database_objects_if_missing": true,
      "new_pipeline_spec": {
        "storage_catalog": "<REGULAR_UC_CATALOG>",
        "storage_schema": "default"
      }
    }
  }' --profile <PROFILE>
```

| Field | Required | Description |
|-------|----------|-------------|
| `source_table_full_name` | Yes | Full Unity Catalog name of the source table |
| `primary_key_columns` | Yes | Column(s) forming the primary key |
| `scheduling_policy` | Yes | `SNAPSHOT`, `TRIGGERED`, or `CONTINUOUS` |
| `branch` | Yes | Target Lakebase branch (`projects/<PROJECT_ID>/branches/<BRANCH_ID>`) |
| `postgres_database` | Yes | Postgres database name (default: `databricks_postgres`), not the resource path |
| `create_database_objects_if_missing` | No | Auto-create Postgres schema/database if missing (default: `false`) |
| `new_pipeline_spec.storage_catalog` | Yes | A **regular** UC catalog for DLT pipeline metadata (NOT the Lakebase catalog) |
| `new_pipeline_spec.storage_schema` | Yes | Schema in the storage catalog for pipeline metadata (e.g. `default`) |

> **Important:** `new_pipeline_spec.storage_catalog` must be a regular Unity Catalog managed catalog, not the Lakebase catalog. Using the Lakebase catalog causes pipeline failures because DLT cannot create event log tables in Postgres-backed schemas.

Long-running operation; CLI waits by default. Use `--no-wait` to return immediately.

**Supported source types:** managed/external Delta tables, managed/external Iceberg tables, views, and materialized views.

**Check status:**

```bash
databricks postgres get-synced-table "synced_tables/<LAKEBASE_CATALOG>.<SCHEMA>.<TABLE>" --profile <PROFILE>
```

**Delete:**

```bash
databricks postgres delete-synced-table "synced_tables/<LAKEBASE_CATALOG>.<SCHEMA>.<TABLE>" --profile <PROFILE>
```

## Example: Sync NYC Taxi Data to Lakebase

Sync the `samples.nyctaxi.trips` sample table into Lakebase for low-latency app queries.

**1. Register a UC catalog** (if not already done):

```bash
databricks postgres create-catalog <CATALOG_NAME> \
  --json '{
    "spec": {
      "postgres_database": "databricks_postgres",
      "branch": "projects/<PROJECT_ID>/branches/production"
    }
  }' --profile <PROFILE>
```

**2. Create the synced table (Snapshot mode):**

```bash
databricks postgres create-synced-table <LAKEBASE_CATALOG>.public.nyc_trips \
  --json '{
    "spec": {
      "source_table_full_name": "samples.nyctaxi.trips",
      "primary_key_columns": ["tpep_pickup_datetime", "tpep_dropoff_datetime", "pickup_zip", "dropoff_zip"],
      "scheduling_policy": "SNAPSHOT",
      "branch": "projects/<PROJECT_ID>/branches/production",
      "postgres_database": "databricks_postgres",
      "create_database_objects_if_missing": true,
      "new_pipeline_spec": {
        "storage_catalog": "<REGULAR_UC_CATALOG>",
        "storage_schema": "default"
      }
    }
  }' --profile <PROFILE>
```

> **Note:** `samples.nyctaxi.trips` has no single unique column, so a composite primary key is used. Snapshot mode is chosen here — Triggered/Continuous require CDF enabled on the source table.

**3. Check sync status:**

```bash
databricks postgres get-synced-table "synced_tables/<LAKEBASE_CATALOG>.public.nyc_trips" --profile <PROFILE>
```

**4. Query from Postgres once synced:**

```sql
SELECT pickup_zip, COUNT(*) AS trip_count, AVG(fare_amount) AS avg_fare
FROM public.nyc_trips
GROUP BY pickup_zip
ORDER BY trip_count DESC
LIMIT 10;
```

**5. Clean up:**

```bash
databricks postgres delete-synced-table "synced_tables/<LAKEBASE_CATALOG>.public.nyc_trips" --profile <PROFILE>
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
