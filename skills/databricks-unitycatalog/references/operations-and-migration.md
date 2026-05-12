# Operations & migration (maintenance, time travel, constraints, clone)

## When to use this reference

Use this doc for day-2 table operations and migrations:

- maintenance (`OPTIMIZE`, `VACUUM`, clustering)
- time travel for debugging/recovery
- migration of legacy (Hive) tables into UC
- constraints and cloning strategies

## Maintenance operations (what to be careful about)

Common operations:

- `OPTIMIZE`: improves data layout / compacts files for performance.
- `VACUUM`: deletes old data files; **verify retention/compliance** before changing defaults.
- liquid clustering / auto-clustering: capability varies; confirm the workspace’s current behavior and defaults.

## Time travel (debugging + recovery)

Be mindful of retention and any runtime-specific limitations.

```sql
-- version-based
SELECT *
FROM <catalog>.<schema>.<table> VERSION AS OF 123;

-- timestamp-based
SELECT *
FROM <catalog>.<schema>.<table> TIMESTAMP AS OF '2026-01-01T00:00:00Z';
```

Debug checklist:

- Confirm the queried version/timestamp is within retention.
- If results differ across environments, check table properties and retention configuration.

## Predictive optimization

Enablement may be per-table, per-schema, or per-catalog depending on workspace defaults and policy. Verify what’s enabled before assuming optimizations will occur automatically.

## Migrating Hive tables to Unity Catalog (SYNC workflow)

Treat migrations as a controlled change:

- Validate schema compatibility.
- Map permissions intentionally (don’t assume inheritance matches legacy ACLs).
- Inventory downstream dependencies (jobs, dashboards, notebooks, apps).
- Migrate a small subset first, then expand.

## Constraints (validate support + enforcement)

Common constraint types:

- `NOT NULL`, `CHECK`
- `PRIMARY KEY`, `FOREIGN KEY`

Support and enforcement semantics can vary; validate behavior in the target workspace before depending on constraint enforcement.

## CLONE (deep vs shallow)

- **Shallow clone**: fast; depends on source data retention and access to underlying files.
- **Deep clone**: copies data; safer isolation, higher cost.

Pick based on isolation and retention guarantees you need.
