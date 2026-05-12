# Access control (grants, privileges, RLS/CLS)

## When to use this reference

Use this doc for:

- Grant/revoke workflows (`GRANT`, `REVOKE`, `SHOW GRANTS`)
- “I can’t see the table” vs “I can’t query the table” debugging
- Permissions on volumes / external locations (file privileges)
- Row and column-level security (row filters, column masks)

## Core concepts (keep straight)

- **Privileges** are granted on UC securables (catalogs, schemas, tables/views, volumes, external locations, functions, etc.).
- **Discovery** can be separated from data access via `BROWSE`.
- **Namespace traversal** often requires `USE CATALOG` + `USE SCHEMA` even when `SELECT` exists.
- **Ownership** is not the same as `MANAGE` (workspaces differ on what each enables).
- **File privileges gotcha**: **`WRITE FILES` requires `READ FILES`**.

## Quick checklist: “why can’t user X query object Y?”

1. Confirm the user/principal identity (`<principal>`).
2. Check grants on:
   - catalog + schema (traversal / discovery)
   - the target object (table/view/volume/external location)
3. If the error mentions files/paths, verify file privileges (`READ FILES`, `WRITE FILES`) and underlying external location grants.
4. If the query returns fewer rows or masked values, check row filters / column masks.

## Common SQL patterns

```sql
-- Inspect grants (examples)
SHOW GRANTS ON CATALOG <catalog>;
SHOW GRANTS ON SCHEMA <catalog>.<schema>;
SHOW GRANTS ON TABLE <catalog>.<schema>.<table>;
SHOW GRANTS ON VIEW <catalog>.<schema>.<view>;
SHOW GRANTS ON VOLUME <catalog>.<schema>.<volume>;

-- Minimal traversal + discovery (lets users find objects)
GRANT USE CATALOG ON CATALOG <catalog> TO `<principal>`;
GRANT USE SCHEMA  ON SCHEMA  <catalog>.<schema> TO `<principal>`;
GRANT BROWSE      ON CATALOG <catalog> TO `<principal>`;

-- Data access
GRANT SELECT ON TABLE <catalog>.<schema>.<table> TO `<principal>`;

-- Revoke
REVOKE SELECT ON TABLE <catalog>.<schema>.<table> FROM `<principal>`;
```

### Troubleshooting: “not found” vs “permission denied”

- **“Not found” / can’t list** often means missing `USE CATALOG` / `USE SCHEMA` and/or `BROWSE`.
- **“Permission denied” on query** usually means missing `SELECT`, or a denied row/column policy, or file privileges on underlying storage paths.

## `ALL PRIVILEGES` notes

Treat `ALL PRIVILEGES` as a convenience that depends on object type and platform semantics. Prefer granting only what is required and verifying with `SHOW GRANTS`.

## Ownership vs `MANAGE`

Document which operations require ownership vs `MANAGE` in your environment. Do not assume one implies the other.

## RLS/CLS: row filters + column masks

Unity Catalog can enforce:

- **Row filters**: restrict which rows a principal can see
- **Column masks**: redact/transform specific columns

Debug workflow:

- Start with a minimal query selecting non-sensitive columns
- If results differ by principal, inspect applicable row/column policies
- Confirm base privileges first (`USE CATALOG`, `USE SCHEMA`, `SELECT`)
