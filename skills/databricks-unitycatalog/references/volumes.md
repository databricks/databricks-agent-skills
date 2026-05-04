# Volumes (managed vs external)

## When to use this reference

Use this doc when you need UC-governed file access for:

- notebooks / jobs reading and writing files
- data ingestion/export paths governed by UC
- sharing “known-good” paths with clear permissions (instead of ad-hoc mounts)

## Managed vs external volumes (decision guide)

- **Managed volume**: simplest lifecycle; storage managed by Databricks/UC.
- **External volume**: backed by customer-owned cloud storage (via an external location); best when you must control the underlying path and lifecycle.

Default to **managed** unless you have a clear reason to control the cloud path.

## Create volumes (SQL)

```sql
-- Managed volume
CREATE VOLUME <catalog>.<schema>.<volume>;

-- External volume (location is a cloud path; cloud-specific scheme varies)
CREATE VOLUME <catalog>.<schema>.<volume>
LOCATION '<cloud-url>/<path>/';
```

## Use volumes in code: canonical paths

Prefer the `/Volumes/...` path so code is portable across notebooks/jobs:

- `/Volumes/<catalog>/<schema>/<volume>/some/file.parquet`

`dbutils.fs` can be used as an API surface, but the **path** should still typically be a `/Volumes/...` path.

## Permissions: the two-layer model (common failure source)

When something fails, check both layers:

- **Volume grants** (the UC object you read/write)
- **External location grants** (for external volumes)

### Gotchas

- **`WRITE FILES` requires `READ FILES`** (grant both).
- If users can list but not read, you may be missing file privileges or underlying external location permissions.
