# Metric Views (Governed Semantic Layer)

Query a **Unity Catalog Metric View** — a governed semantic object whose measures and
dimensions are defined once in UC — from an analytics app. Reach for this instead of
hand-written `config/queries/*.sql` when the app should read **pre-defined, governed
metrics** (consistent aggregations, a shared semantic layer) rather than ad-hoc SQL.

**Requires AppKit ≥ 0.59.0** and the `analytics` plugin. Metric views ride the analytics
plugin — there is **no separate `--features` flag and no extra resource**; they reuse the
analytics SQL warehouse (`--set analytics.sql-warehouse.id=<ID>`).

> **Metric view vs `config/queries/` SQL** — use a **metric view** when the metric is a
> governed UC object with `MEASURE()`-based semantics you want to stay consistent
> everywhere; use **`config/queries/`** (`useAnalyticsQuery`) for app-specific ad-hoc SQL.
> Both run on the same analytics warehouse. See [SQL Queries](sql-queries.md).

## 1. Register the metric view

An analytics app scaffolds `config/metric-views/definitions.json` (empty by default). Add
one entry per metric view under `metricViews`:

```json
{
  "$schema": "https://databricks.github.io/appkit/schemas/metric-source.schema.json",
  "metricViews": {
    "orders": {
      "source": "main.analytics.order_metrics",
      "executor": "app_service_principal"
    }
  }
}
```

- **Metric key** (`"orders"`) — an identifier matching `^[a-zA-Z_][a-zA-Z0-9_]*$`. It is the
  `useMetricView("<key>", …)` argument and the route key.
- **`source`** (required) — the three-part Unity Catalog FQN of the metric view:
  `<catalog>.<schema>.<metric_view>`.
- **`executor`** — who the view is queried as. **For a multi-user app, prefer `"user"`**
  (on-behalf-of the requesting user, per-user cache): results follow each end user's UC
  permissions. Use `"app_service_principal"` for shared access to aggregate or
  non-restricted data (queries as the app service principal, one shared cache). The field's
  own default is `"app_service_principal"`, so set `"user"` explicitly when you want OBO.

**Do NOT guess the FQN.** Discover metric views with the parent `databricks-core` skill —
they appear with `table_type = 'METRIC_VIEW'` in `information_schema`.

## 2. Regenerate types

Run `npm run typegen` after editing `definitions.json`. It regenerates the analytics types
for **both** `config/queries/` and `config/metric-views/`, so a metric view's `measures`
and `dimensions` are type-checked against the actual view. Confirm hook and option shapes
with `npx @databricks/appkit docs` — the docs are the authority.

## 3. Query with `useMetricView`

```typescript
import { useMetricView } from '@databricks/appkit-ui/react';

const { data, loading, error, errorCode, metadata, warehouseStatus } =
  useMetricView('orders', {
    measures: ['revenue'],                                       // required, ≥ 1
    dimensions: ['region'],
    filter: { member: 'region', operator: 'in', values: ['EMEA', 'APAC'] },
    orderBy: [{ field: 'revenue', direction: 'DESC' }],
    limit: 10,
  });
// data: Array<{ revenue: string | null; region: string | null }> | null
```

Returns `{ data, loading, error, errorCode, metadata, warehouseStatus }`. Once types are
generated (Step 2), `measures` and `dimensions` are checked against the registered view.

**For the full request shape — every option, the filter operators, and the field limits —
see `npx @databricks/appkit docs ./docs/plugins/analytics.md`.** It ships with the installed
AppKit and is the authority; don't hand-copy those values here, since they drift as AppKit
changes. This page keeps only the gotchas below.

### Gotchas

- **Numeric cells are strings or `null`** (JSON_ARRAY). Always `Number(row.revenue)` before
  math or formatting — the same rule as `config/queries/` results (see [SQL Queries](sql-queries.md)).
- **`orderBy.field` must be a selected measure or dimension.** A measure is ordered by its
  alias (Spark rejects `ORDER BY MEASURE(...)`; AppKit handles the aliasing — you just name
  the measure). With `limit`, `orderBy` picks WHICH rows (top-N) and AppKit stabilizes the
  rest; without `limit` it is presentation order only.
- **`timeGrain` needs a `timeDimension`** that is itself one of your `dimensions`.
- **Defer a query with `autoStart: false`** — there is no `enabled` option (same as
  `useAnalyticsQuery`).

## What lives where

- **Measure/dimension definitions, joins, and formatting live in the metric view YAML in
  Unity Catalog** — not in the app. You cannot `SELECT *` a metric view or join it to
  another table at query time; the app only picks measures/dimensions and filters.
- The app holds only the **binding** (`config/metric-views/definitions.json`) and the
  **query** (`useMetricView`).

## ⚠️ Do NOT

- ❌ Query a metric view through `config/queries/` raw SQL or a custom endpoint — use
  `useMetricView`, which handles `MEASURE()` compilation, deterministic limits, and caching.
- ❌ Use `useAnalyticsQuery` for a metric view (it targets `config/queries/` SQL), or
  `useMetricView` for a plain table.
