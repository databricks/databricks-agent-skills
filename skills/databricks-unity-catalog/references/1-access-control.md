# Access Control & the Privilege Model

The authoritative reference for **who can do what** in Unity Catalog: the securable
hierarchy, the full privilege list, `GRANT`/`REVOKE`, ownership, and privilege inheritance.
Volume-specific grants in [6-volumes.md](6-volumes.md) and system-table grants in
[5-system-tables.md](5-system-tables.md) are special cases of the model described here.

## Securable Hierarchy

Unity Catalog secures objects in a containment tree. A privilege granted on a parent can
be **inherited** by its children (see [Inheritance](#privilege-inheritance)).

```
metastore
└── catalog
    └── schema (database)
        ├── table
        ├── view
        ├── volume
        ├── function
        └── model
```

To *use* a child you generally need traversal privileges on every ancestor: `USE CATALOG`
on the catalog **and** `USE SCHEMA` on the schema, **plus** the action privilege (e.g.
`SELECT`) on the object itself. Granting `SELECT` on a table without `USE SCHEMA`/`USE CATALOG`
leaves the grantee unable to reach it.

## Privilege Reference

| Privilege | Applies to | Grants the ability to |
|-----------|------------|------------------------|
| `USE CATALOG` | catalog | Traverse/reference a catalog (does **not** grant data access) |
| `USE SCHEMA` | schema | Traverse/reference a schema |
| `SELECT` | table, view | Read rows |
| `MODIFY` | table | Insert/update/delete/merge rows |
| `CREATE` | catalog, schema | Create child objects (also `CREATE SCHEMA`, `CREATE TABLE`, `CREATE FUNCTION`, `CREATE MATERIALIZED VIEW`, `CREATE MODEL`) |
| `CREATE TABLE` | schema | Create tables in the schema |
| `CREATE VOLUME` | schema | Create volumes in the schema |
| `CREATE FUNCTION` | schema | Create UDFs in the schema |
| `EXECUTE` | function | Invoke a UDF |
| `READ VOLUME` | volume | List/read files in a volume |
| `WRITE VOLUME` | volume | Write/delete files in a volume |
| `READ FILES` / `WRITE FILES` | external location | Read/write paths under an external location |
| `CREATE EXTERNAL TABLE` / `CREATE EXTERNAL VOLUME` | external location / storage credential | Create externals on that location |
| `BROWSE` | catalog, schema | See object metadata in the catalog explorer **without** data access |
| `APPLY TAG` | catalog, schema, table | Add/remove governed tags |
| `MANAGE` | any securable | Manage grants on the object (delegated admin without ownership) |
| `ALL PRIVILEGES` | any securable | Shorthand for every applicable privilege (expanded at grant time) |

> `USE CATALOG` / `USE SCHEMA` are **traversal** privileges, not data privileges. `BROWSE`
> exposes metadata only. Data access always requires the action privilege (`SELECT`,
> `MODIFY`, `READ VOLUME`, …) **in addition to** traversal on the ancestors.

## GRANT / REVOKE (SQL)

```sql
-- Read access to a single table (requires traversal on ancestors too)
GRANT USE CATALOG ON CATALOG analytics TO `data_readers`;
GRANT USE SCHEMA ON SCHEMA analytics.gold TO `data_readers`;
GRANT SELECT ON TABLE analytics.gold.customers TO `data_readers`;

-- Read access to every current and future table in a schema (inherited)
GRANT SELECT ON SCHEMA analytics.gold TO `data_readers`;

-- Write access
GRANT MODIFY ON TABLE analytics.silver.orders TO `etl_writers`;

-- Let a team create objects in a schema
GRANT CREATE TABLE, CREATE VOLUME ON SCHEMA analytics.bronze TO `data_engineers`;

-- Execute a UDF
GRANT EXECUTE ON FUNCTION analytics.gold.mask_email TO `analysts`;

-- Metadata-only visibility (no data access)
GRANT BROWSE ON CATALOG analytics TO `all_users`;

-- Delegate grant management without transferring ownership
GRANT MANAGE ON SCHEMA analytics.gold TO `gold_stewards`;

-- Revoke
REVOKE SELECT ON TABLE analytics.gold.customers FROM `data_readers`;
REVOKE ALL PRIVILEGES ON SCHEMA analytics.gold FROM `contractors`;
```

Principals are account-level users (`'alice@example.com'`), groups (backticked:
`` `data_readers` ``), or service principals (the application ID).

## Inspecting Grants — SHOW GRANTS

```sql
-- All grants on an object
SHOW GRANTS ON TABLE analytics.gold.customers;
SHOW GRANTS ON SCHEMA analytics.gold;
SHOW GRANTS ON CATALOG analytics;

-- What does a specific principal have on an object?
SHOW GRANTS `data_readers` ON SCHEMA analytics.gold;

-- "Who can read this table?" — combine direct + inherited grants via information_schema
SELECT grantee, privilege_type, inherited_from
FROM system.information_schema.table_privileges
WHERE table_catalog = 'analytics'
  AND table_schema = 'gold'
  AND table_name = 'customers'
ORDER BY grantee;
```

## Ownership

Every securable has exactly one **owner** (a user, group, or service principal). The owner
implicitly has all privileges on the object and can grant/revoke on it. Transfer ownership
with `ALTER … OWNER TO`:

```sql
ALTER TABLE analytics.gold.customers OWNER TO `gold_owners`;
ALTER SCHEMA analytics.gold OWNER TO `gold_owners`;
ALTER CATALOG analytics OWNER TO `platform_admins`;
ALTER VOLUME analytics.gold.exports OWNER TO `gold_owners`;
```

> Prefer **group ownership** over individual users so access does not break when a person
> leaves. Use `MANAGE` to delegate grant administration without changing the owner.

## Privilege Inheritance

A privilege granted on a parent securable applies to all current **and future** children of
the same applicable type:

- `GRANT SELECT ON CATALOG c TO g` → `g` can `SELECT` from every table/view in every schema of `c`.
- `GRANT SELECT ON SCHEMA c.s TO g` → `g` can `SELECT` from every table/view in `c.s`.
- `GRANT READ VOLUME ON SCHEMA c.s TO g` → `g` can read every volume in `c.s`.

`SHOW GRANTS` and `information_schema.*_privileges` expose an `inherited_from` column so you
can tell a direct grant from an inherited one. To lock down a single child while a broad
parent grant exists, narrow the parent grant — there is no per-object "deny" that overrides
inheritance (UC has no explicit DENY; absence of a grant is the deny).

## Python SDK (`w.grants`)

The SDK mirrors `GRANT`/`REVOKE` via `PermissionsChange` on a securable.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import (
    SecurableType,
    PermissionsChange,
    Privilege,
)

w = WorkspaceClient()

# Grant SELECT on a schema to a group (and revoke MODIFY in the same call)
w.grants.update(
    securable_type=SecurableType.SCHEMA,
    full_name="analytics.gold",
    changes=[
        PermissionsChange(
            principal="data_readers",
            add=[Privilege.USE_SCHEMA, Privilege.SELECT],
            remove=[Privilege.MODIFY],
        )
    ],
)

# Read effective grants on the object
grants = w.grants.get(
    securable_type=SecurableType.SCHEMA,
    full_name="analytics.gold",
)
for assignment in grants.privilege_assignments or []:
    print(assignment.principal, assignment.privileges)

# Read the full effective permission set (including inherited)
effective = w.grants.get_effective(
    securable_type=SecurableType.TABLE,
    full_name="analytics.gold.customers",
)
for assignment in effective.privilege_assignments or []:
    print(assignment.principal, assignment.privileges)
```

## CLI (`databricks grants`)

```bash
# Show grants on a securable (SECURABLE_TYPE FULL_NAME are positional)
databricks grants get schema analytics.gold

# Effective grants (includes inherited)
databricks grants get-effective table analytics.gold.customers

# Update grants — use --json for the change set (order-independent, version-stable)
databricks grants update schema analytics.gold --json '{
  "changes": [
    {"principal": "data_readers", "add": ["USE_SCHEMA", "SELECT"]}
  ]
}'
```

> **CLI surface varies by version.** If `databricks grants` is missing or a flag is
> rejected, use the SQL `GRANT`/`REVOKE`/`SHOW GRANTS` forms or the `w.grants` SDK above.

## Troubleshooting / Common Issues

Most access problems are a **missing traversal privilege** or an **inheritance/ownership**
surprise rather than a bug — the table below maps the symptom to the cause.

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PERMISSION_DENIED` / "does not have USE SCHEMA" reaching a table you granted `SELECT` on | `SELECT` was granted, but the grantee lacks `USE CATALOG`/`USE SCHEMA` on the ancestors | Also `GRANT USE CATALOG` on the catalog **and** `USE SCHEMA` on the schema — data access needs traversal too |
| Grantee sees the object in the explorer but cannot read it | They have `BROWSE` (metadata only), not `SELECT` | Grant the action privilege (`SELECT`/`MODIFY`/`READ VOLUME`, …) in addition to `BROWSE` |
| `REVOKE` ran but the principal still has access | Access is **inherited** from a broader parent grant (catalog/schema), not the object | `SHOW GRANTS` and check `inherited_from`; narrow the **parent** grant (there is no per-object DENY) |
| Grant appears to do nothing | Named a **workspace-local** group, or a group name typo | Use account groups; confirm the exact name + membership with `SHOW GRANTS` and `is_account_group_member('grp')` |
| `User is not an owner of ...` when running GRANT/ALTER | Not the owner and lacking `MANAGE` | Have the owner grant you `MANAGE`, or transfer ownership with `ALTER … OWNER TO` |
| Access breaks after an employee leaves | Object owned by an individual user, not a group | `ALTER … OWNER TO` a group; own securables with groups |

## Best Practices

1. **Grant to groups, not users** — account groups keep access stable across staff changes.
2. **Grant at the narrowest securable that works** — least privilege; prefer schema-level over catalog-level when a team only needs one schema.
3. **Use inheritance deliberately** — a schema-level `SELECT` covers future tables; a table-level grant does not.
4. **Own with groups** — `ALTER … OWNER TO` a group; delegate day-to-day grant admin with `MANAGE`.
5. **Audit grants regularly** — query `system.information_schema.*_privileges` and watch `GRANT`/`REVOKE` events in [5-system-tables.md](5-system-tables.md).

## Related

- [2-external-locations.md](2-external-locations.md) — `READ FILES`/`WRITE FILES` and external-location grants
- [3-securables-ddl.md](3-securables-ddl.md) — creating the securables you grant on
- [4-fine-grained-access.md](4-fine-grained-access.md) — row/column-level controls layered on top of grants
- [6-volumes.md](6-volumes.md) — `READ VOLUME`/`WRITE VOLUME` specifics
