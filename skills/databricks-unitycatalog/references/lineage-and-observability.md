# Lineage & observability (metadata, tags, audit, billing)

## When to use this reference

Use this doc when you need to:

- Verify lineage exists for a table/model/dashboard/pipeline
- Bring lineage from external systems (or document gaps)
- Apply or audit tags (system vs governed)
- Investigate access and permission changes via audit logs
- Attribute costs using system billing tables

## Automated lineage (how to reason about it)

Unity Catalog can capture lineage across common compute and platform surfaces (tables, pipelines, dashboards, models). Coverage varies by feature/integration.

Checklist:

- Validate lineage on a representative object first (don’t assume global coverage).
- If lineage is missing, determine whether it’s a tooling gap, a permissions gap, or an unsupported integration path.

## External lineage (BYO)

For systems outside Databricks (BI tools, SaaS sources, external warehouses), use external lineage ingestion where available. If not possible, document:

- what lineage will remain missing
- what identifiers can be used to correlate (table names, URLs, workbook IDs, etc.)

## Tags (system vs governed)

- **System tags**: platform-generated metadata.
- **Governed tags**: curated taxonomy with controlled assignment.

When using governed tags, principals may require privileges such as:

- `APPLY TAG`
- an assignment permission (often called `ASSIGN`) depending on the governed-tag system in use

## Audit logs (`system.access.audit`)

Use audit logs to answer “who did what, when” and to diagnose unexpected permission/access patterns.

```sql
-- Recent grant/revoke-related actions
SELECT *
FROM system.access.audit
WHERE event_time >= current_timestamp() - INTERVAL 7 DAYS
  AND (
    lower(action_name) LIKE '%grant%'
    OR lower(action_name) LIKE '%revoke%'
  )
ORDER BY event_time DESC
LIMIT 200;
```

## Billing / cost attribution (`system.billing.usage`)

Use usage tables for cost attribution by workspace, identity, SKU, and time range.

```sql
SELECT *
FROM system.billing.usage
WHERE usage_start_time >= current_timestamp() - INTERVAL 30 DAYS
ORDER BY usage_start_time DESC
LIMIT 200;
```
