# Medallion Architecture from CDC History Tables

Build Silver and Gold analytics layers from Lakehouse Sync CDC history tables using Lakeflow Declarative Pipelines.

## When to Use

- You have Lakehouse Sync CDC history tables (`lb_<table>_history`) in Unity Catalog
- You want Bronze → Silver → Gold layers on top of operational data
- You need clean current-state views, deduplication, and business aggregations for BI, ML, or Genie

## Layer Mapping

| Layer | Purpose | Source | Output |
|-------|---------|--------|--------|
| **Bronze** | Raw CDC records with full history | Lakehouse Sync `lb_<table>_history` tables | No transformation needed; already exist |
| **Silver** | Current state, deduplicated and cleaned | Bronze history tables | One materialized view per entity |
| **Gold** | Business aggregations and KPIs | Silver tables | Materialized views with aggregations |

## 1. Scaffold a Pipeline Project

```bash
databricks bundle init lakeflow-pipelines \
  --config-file <(echo '{"project_name": "operational_analytics", "language": "sql", "serverless": "yes"}') \
  --profile <PROFILE> < /dev/null
cd operational_analytics
```

## 2. Configure Pipeline Catalog and Schema

Edit `resources/operational_analytics.pipeline.yml`:

```yaml
resources:
  pipelines:
    operational_analytics:
      name: operational_analytics
      catalog: <CATALOG_NAME>
      schema: <SCHEMA_NAME>
      serverless: true
      libraries:
        - file:
            path: src/
```

## 3. Silver Layer: Current State from CDC

For each entity, create `src/silver_<entity>.sql`:

```sql
CREATE OR REFRESH MATERIALIZED VIEW silver_<entity>
COMMENT "Current state of <entity> records, deduplicated from CDC history"
AS
SELECT * EXCEPT (rn, _pg_change_type, _pg_lsn, _pg_xid, _timestamp, _sort_by)
FROM (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY <primary_key>
      ORDER BY _pg_lsn DESC
    ) AS rn
  FROM <CATALOG_NAME>.<BRONZE_SCHEMA>.lb_<entity>_history
  WHERE _pg_change_type IN ('insert', 'update_postimage', 'delete')
)
WHERE rn = 1
  AND _pg_change_type != 'delete'
```

Replace `<primary_key>`, `<CATALOG_NAME>.<BRONZE_SCHEMA>`, and `<entity>` with your values.

## 4. Gold Layer: Business Aggregations

Create `src/gold_<metric>.sql`:

```sql
CREATE OR REFRESH MATERIALIZED VIEW gold_daily_order_summary
COMMENT "Daily order counts and revenue by status"
AS
SELECT
  DATE_TRUNC('day', created_at) AS order_date,
  status,
  COUNT(*) AS order_count,
  SUM(total_amount) AS total_revenue
FROM silver_orders
GROUP BY DATE_TRUNC('day', created_at), status
```

Gold tables read from silver tables within the same pipeline.

## 5. Data Quality Expectations

Add constraints to silver or gold tables:

```sql
CREATE OR REFRESH MATERIALIZED VIEW silver_<entity> (
  CONSTRAINT valid_primary_key EXPECT (<primary_key> IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_timestamp EXPECT (created_at IS NOT NULL) ON VIOLATION DROP ROW
)
COMMENT "Current state of <entity> records with quality enforcement"
AS
SELECT ...
```

## 6. Deploy and Run

```bash
databricks bundle validate --profile <PROFILE>
databricks bundle deploy -t dev --profile <PROFILE>
databricks bundle run operational_analytics -t dev --profile <PROFILE>
```

## 7. Schedule Ongoing Refreshes

Create `resources/operational_analytics_job.job.yml`:

```yaml
resources:
  jobs:
    operational_analytics_job:
      trigger:
        periodic:
          interval: 1
          unit: HOURS
      tasks:
        - task_key: refresh_pipeline
          pipeline_task:
            pipeline_id: ${resources.pipelines.operational_analytics.id}
```

Deploy: `databricks bundle deploy -t dev --profile <PROFILE>`

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Silver table returns no rows | Verify bronze history table has data: `SELECT COUNT(*) FROM lb_<entity>_history` |
| `TABLE_OR_VIEW_NOT_FOUND` for bronze table | Use fully-qualified name: `<CATALOG>.<SCHEMA>.lb_<entity>_history` |
| Gold aggregation includes deleted records | Confirm silver layer filters `_pg_change_type != 'delete'` |
| Pipeline fails on deploy | Run `databricks bundle validate` first to catch config errors |
| Incremental refresh not picking up changes | Verify Lakehouse Sync is active and bronze table is updating |

## Cross-references

- For Lakehouse Sync setup, see [lakehouse-sync.md](lakehouse-sync.md)
- For synced tables (UC → Lakebase direction), see [synced-tables.md](synced-tables.md)
