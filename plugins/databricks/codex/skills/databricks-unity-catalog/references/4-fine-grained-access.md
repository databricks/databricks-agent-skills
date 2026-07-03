# Fine-Grained Access Control

Row- and column-level security in Unity Catalog: **row filters**, **column masks**, and
**dynamic views**. These layer *on top of* table grants — a principal still needs `SELECT`
(see [1-access-control.md](1-access-control.md)); fine-grained controls then restrict *which
rows* and *what column values* that principal sees.

> **Not `ai_mask`.** Databricks also ships an `ai_mask` SQL function (and `ai_classify`,
> etc.) — those are **AI transforms** that rewrite text with an LLM, **not** access-control
> primitives, and they are owned by **databricks-ai-functions**. A column **mask** here is a
> deterministic governance policy enforced by UC at query time for unauthorized users. Use
> column masks for governance; use `ai_mask` for content redaction in a transform.

## The Three Mechanisms

| Mechanism | Granularity | How it attaches | Best for |
|-----------|-------------|-----------------|----------|
| **Row filter** | Rows | A UDF returning BOOLEAN, attached via `ALTER TABLE … SET ROW FILTER` | "users only see their region's rows" |
| **Column mask** | Column values | A UDF rewriting one column, attached via `ALTER TABLE … ALTER COLUMN … SET MASK` | "redact SSN unless caller is in `pii_readers`" |
| **Dynamic view** | Rows + columns | A view whose `WHERE`/`CASE` uses `current_user()` / `is_account_group_member()` | self-contained, no UDF lifecycle; read-only |

Row filters + column masks attach directly to the **base table** (every reader is governed,
regardless of how they query it). Dynamic views govern only readers who go **through the
view**. Prefer filters/masks when you must protect the base table itself.

## Identity Functions

These built-ins identify the querying principal and power every pattern below:

| Function | Returns |
|----------|---------|
| `current_user()` | The querying user's email/identity |
| `is_account_group_member('grp')` | TRUE if the caller is in account group `grp` |
| `is_member('grp')` | TRUE if the caller is in workspace-local group `grp` (prefer the account-group form) |

## Row Filters

A row filter is a UDF returning `BOOLEAN`; rows where it returns `TRUE` are visible. The
function's parameters are bound to table columns when you attach it.

```sql
-- 1. Create the filter UDF: admins see all rows; everyone else sees only rows for
--    a region they're entitled to — here via a per-region account group
--    (e.g. members of "region_emea" see rows where region = 'EMEA').
CREATE OR REPLACE FUNCTION analytics.gold.region_row_filter(region STRING)
RETURN
  is_account_group_member('region_admins')
  OR is_account_group_member(concat('region_', lower(region)));

-- 2. Attach it to the table, binding the UDF param to a real column
ALTER TABLE analytics.gold.sales SET ROW FILTER analytics.gold.region_row_filter ON (region);

-- 3. Inspect / remove
DESCRIBE EXTENDED analytics.gold.sales;          -- shows the attached row filter
ALTER TABLE analytics.gold.sales DROP ROW FILTER;
```

A more realistic mapping joins the caller to an entitlements table:

```sql
CREATE OR REPLACE FUNCTION analytics.gold.region_row_filter(region STRING)
RETURN is_account_group_member('region_admins')
    OR EXISTS (
         SELECT 1
         FROM analytics.security.user_region_map m
         WHERE m.user_email = current_user()
           AND m.region = region
       );
```

## Column Masks

A column mask is a UDF whose first parameter is the column being masked; its return value
replaces the column for unauthorized callers.

```sql
-- 1. Create the mask UDF: pii_readers see the real value; everyone else sees it redacted
CREATE OR REPLACE FUNCTION analytics.gold.ssn_mask(ssn STRING)
RETURN CASE
  WHEN is_account_group_member('pii_readers') THEN ssn
  ELSE 'XXX-XX-' || RIGHT(ssn, 4)
END;

-- 2. Attach to a column
ALTER TABLE analytics.gold.customers ALTER COLUMN ssn SET MASK analytics.gold.ssn_mask;

-- 3. Masks can take extra args from other columns (USING COLUMNS)
CREATE OR REPLACE FUNCTION analytics.gold.email_mask(email STRING, tier STRING)
RETURN CASE
  WHEN is_account_group_member('pii_readers') THEN email
  WHEN tier = 'public' THEN email
  ELSE regexp_replace(email, '^[^@]+', '****')
END;

ALTER TABLE analytics.gold.customers
  ALTER COLUMN email SET MASK analytics.gold.email_mask USING COLUMNS (tier);

-- 4. Remove
ALTER TABLE analytics.gold.customers ALTER COLUMN ssn DROP MASK;
```

> The mask/filter UDF runs with the **table owner's** authority, so the owner needs access to
> anything the UDF reads (e.g. the entitlements table). Grant callers `EXECUTE` is **not**
> required — UC invokes the policy automatically.

## Dynamic Views

When you cannot (or do not want to) attach policies to the base table, expose a view that
self-censors based on the caller. Grant `SELECT` on the **view**, not the base table.

```sql
CREATE OR REPLACE VIEW analytics.gold.customers_secure AS
SELECT
  customer_id,
  -- column-level: redact PII unless the caller is entitled
  CASE WHEN is_account_group_member('pii_readers')
       THEN email ELSE '****@****' END AS email,
  CASE WHEN is_account_group_member('pii_readers')
       THEN ssn ELSE 'XXX-XX-' || RIGHT(ssn, 4) END AS ssn,
  region,
  lifetime_value
FROM analytics.gold.customers
-- row-level: non-admins only see their own region
WHERE is_account_group_member('region_admins')
   OR region IN (
        SELECT region
        FROM analytics.security.user_region_map
        WHERE user_email = current_user()
      );
```

Then:

```sql
GRANT SELECT ON VIEW analytics.gold.customers_secure TO `analysts`;
-- and do NOT grant SELECT on analytics.gold.customers to `analysts`
```

## Choosing Between Them

- **Protect the base table for all readers** → row filter + column mask (enforced no matter how the table is queried).
- **No table-owner UDF lifecycle, read-only consumers** → dynamic view (logic lives in the view; simplest to ship, but only governs view readers).
- **Need both row and column rules with reusable logic across tables** → filter/mask UDFs (define once, attach to many tables).

## Troubleshooting / Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| Everyone still sees all rows | Filter created but not attached, or attached to the wrong column | `DESCRIBE EXTENDED <table>` to confirm; re-run `SET ROW FILTER … ON (col)` |
| `FUNCTION_PARAMETER_TYPE_MISMATCH` on attach | UDF param type ≠ column type | Match the UDF signature to the bound column's type |
| Mask UDF errors reading an entitlements table | Table **owner** lacks access to that table | Grant the owner `SELECT` on the entitlements table |
| Authorized users also see masked values | `is_account_group_member` checks a **workspace-local** group, or wrong group name | Use account groups; verify membership with `SELECT is_account_group_member('grp')` |
| View leaks data | Consumers were also granted `SELECT` on the base table | Revoke base-table `SELECT`; grant only the view |

## Best Practices

1. **Grants first, then fine-grained** — `SELECT` is still required; filters/masks narrow, they don't grant.
2. **Use account groups** in `is_account_group_member()`, not individual users or workspace-local groups.
3. **Centralize entitlements** — drive predicates from a maintained `user_region_map`-style table rather than hardcoded emails.
4. **Prefer base-table filters/masks** when the table itself must be protected; reserve dynamic views for read-only, view-only consumption.
5. **Test as a non-privileged user** — verify masked/filtered output with an account that is *not* in the privileged group.

## Related

- [1-access-control.md](1-access-control.md) — the underlying grants these controls layer on
- [3-securables-ddl.md](3-securables-ddl.md) — creating the tables/views governed here
- **databricks-ai-functions** — `ai_mask` / `ai_classify` (AI transforms, **not** access control)
