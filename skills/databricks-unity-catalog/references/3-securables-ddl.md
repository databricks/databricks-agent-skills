# Securable DDL, Ownership & Metadata

`CREATE`/`ALTER`/`DROP` for the core Unity Catalog securables — catalogs, schemas, managed
vs external tables, and views — plus the metadata that governs them: comments, table
properties, ownership, and tags. Grants on these objects live in
[1-access-control.md](1-access-control.md); the external locations that external tables
sit on live in [2-external-locations.md](2-external-locations.md).

> **Out of scope (siblings own these DDLs):** metric views (`WITH METRICS LANGUAGE YAML`) →
> **databricks-metric-views**; Managed Iceberg / Uniform tables → **databricks-iceberg**.
> This file covers standard UC catalogs, schemas, Delta tables, and views.

## Catalogs

```sql
-- Create
CREATE CATALOG IF NOT EXISTS analytics
  COMMENT 'Curated analytics data';

-- Create a catalog with a managed storage location (isolates its data)
CREATE CATALOG analytics_isolated
  MANAGED LOCATION 's3://my-bucket/analytics-catalog'
  COMMENT 'Catalog with dedicated managed storage';

-- Alter
ALTER CATALOG analytics SET COMMENT 'Curated, governed analytics data';
ALTER CATALOG analytics OWNER TO `platform_admins`;
ALTER CATALOG analytics RENAME TO analytics_v2;

-- Drop (CASCADE removes contained schemas/tables — use with care)
DROP CATALOG IF EXISTS analytics_v2 CASCADE;
```

## Schemas

```sql
-- Create
CREATE SCHEMA IF NOT EXISTS analytics.gold
  COMMENT 'Gold-layer curated tables';

-- Schema with its own managed location
CREATE SCHEMA analytics.staging
  MANAGED LOCATION 's3://my-bucket/analytics/staging';

-- Alter
ALTER SCHEMA analytics.gold SET COMMENT 'Gold layer (business-ready)';
ALTER SCHEMA analytics.gold OWNER TO `gold_owners`;

-- Drop
DROP SCHEMA IF EXISTS analytics.staging CASCADE;
```

## Tables — Managed vs External

A **managed** table stores its data in the catalog/schema/metastore managed location and is
fully lifecycle-managed by UC (dropping it deletes the data). An **external** table points at
a path under a registered [external location](2-external-locations.md) and UC manages only the
metadata (dropping it leaves the files in place).

```sql
-- Managed table (no LOCATION clause → managed storage, Delta by default)
CREATE TABLE analytics.gold.customers (
  customer_id BIGINT,
  email STRING,
  signup_date DATE,
  lifetime_value DECIMAL(12, 2)
)
COMMENT 'One row per customer'
TBLPROPERTIES ('quality' = 'gold', 'pii' = 'true');

-- External table (LOCATION must sit under a registered external location)
CREATE EXTERNAL TABLE analytics.bronze.raw_events (
  event_id STRING,
  payload STRING,
  ingested_at TIMESTAMP
)
USING DELTA
LOCATION 's3://my-bucket/analytics/bronze/raw_events';

-- CTAS (managed)
CREATE TABLE analytics.gold.active_customers AS
SELECT * FROM analytics.gold.customers WHERE lifetime_value > 0;
```

### Alter tables

```sql
-- Columns
ALTER TABLE analytics.gold.customers ADD COLUMN region STRING COMMENT 'Sales region';
ALTER TABLE analytics.gold.customers ALTER COLUMN email COMMENT 'Primary contact email';
ALTER TABLE analytics.gold.customers RENAME COLUMN region TO sales_region;
ALTER TABLE analytics.gold.customers DROP COLUMN sales_region;

-- Properties
ALTER TABLE analytics.gold.customers SET TBLPROPERTIES ('reviewed' = '2026-01-01');
ALTER TABLE analytics.gold.customers UNSET TBLPROPERTIES ('reviewed');

-- Ownership + rename
ALTER TABLE analytics.gold.customers OWNER TO `gold_owners`;
ALTER TABLE analytics.gold.customers RENAME TO analytics.gold.customer_master;

-- Drop
DROP TABLE IF EXISTS analytics.gold.customer_master;
```

## Views

```sql
-- Standard view
CREATE OR REPLACE VIEW analytics.gold.customer_summary
  COMMENT 'Per-customer rollup'
AS
SELECT customer_id, COUNT(*) AS order_count, SUM(lifetime_value) AS total_value
FROM analytics.gold.customers
GROUP BY customer_id;

ALTER VIEW analytics.gold.customer_summary OWNER TO `gold_owners`;
DROP VIEW IF EXISTS analytics.gold.customer_summary;
```

> Dynamic views that restrict rows/columns by the querying user (`current_user()`,
> `is_account_group_member()`) are an access-control pattern — see
> [4-fine-grained-access.md](4-fine-grained-access.md).

## Comments (COMMENT ON)

```sql
COMMENT ON CATALOG analytics IS 'Curated analytics data';
COMMENT ON SCHEMA analytics.gold IS 'Gold layer';
COMMENT ON TABLE analytics.gold.customers IS 'One row per customer';
COMMENT ON COLUMN analytics.gold.customers.email IS 'Primary contact email (PII)';
```

## Tags (SET TAGS)

Tags are key/value metadata used for discovery, cost attribution, and governed policies.
Setting/removing tags requires `APPLY TAG` (see [1-access-control.md](1-access-control.md)).

```sql
-- Object tags
ALTER TABLE analytics.gold.customers SET TAGS ('domain' = 'crm', 'pii' = 'true');
ALTER TABLE analytics.gold.customers UNSET TAGS ('pii');

-- Schema / catalog tags
ALTER SCHEMA analytics.gold SET TAGS ('layer' = 'gold');

-- Column tags
ALTER TABLE analytics.gold.customers ALTER COLUMN email SET TAGS ('classification' = 'pii');

-- Query tags via information_schema
SELECT catalog_name, schema_name, table_name, tag_name, tag_value
FROM system.information_schema.table_tags
WHERE schema_name = 'gold';
```

## Python SDK & CLI

Most DDL is cleanest as SQL on a warehouse, but the SDK/CLI manage the same objects:

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import SchemaInfo

w = WorkspaceClient()

# Create a schema
w.schemas.create(name="gold", catalog_name="analytics", comment="Gold layer")

# Update (comment / owner)
w.schemas.update(full_name="analytics.gold", comment="Gold layer (business-ready)")

# List tables in a schema
for t in w.tables.list(catalog_name="analytics", schema_name="gold"):
    print(t.full_name, t.table_type)
```

```bash
# Create via --json (order-independent, version-stable)
databricks schemas create --json '{"name": "gold", "catalog_name": "analytics"}'

# Inspect
databricks tables get analytics.gold.customers
```

> **CLI surface varies by version.** Prefer SQL DDL or the SDK when a `databricks` subcommand
> or flag is absent in your install.

## Best Practices

1. **Default to managed tables** — UC handles storage, optimization, and cleanup; reach for external only when an external engine or pre-existing path requires it.
2. **Comment everything** — catalogs, schemas, tables, and PII columns; ungoverned objects show up as gaps in [5-system-tables.md](5-system-tables.md) queries.
3. **Tag for policy and cost** — `pii`, `domain`, `layer` tags drive discovery and (later) governed-tag policies.
4. **Own with groups** — `ALTER … OWNER TO` a group, not a person.
5. **`DROP … CASCADE` is destructive on managed objects** — it deletes data; double-check before running.

## Related

- [1-access-control.md](1-access-control.md) — grants on the objects created here
- [2-external-locations.md](2-external-locations.md) — where external tables live
- [4-fine-grained-access.md](4-fine-grained-access.md) — row/column controls on these tables
- **databricks-metric-views** — metric view DDL · **databricks-iceberg** — Iceberg/Uniform DDL
