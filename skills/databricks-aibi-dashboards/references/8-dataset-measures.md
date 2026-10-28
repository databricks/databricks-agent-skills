# Dataset-Level Measures and `MEASURE()`

## Defining a dataset

Two ways to define a dataset:
- **SQL query**: `{"name": "ds_x", "displayName": "...", "queryLines": ["SELECT ...", "FROM table"]}` — full control, can include `WITH` / `JOIN` / `AI_FORECAST` / etc.
- **UC asset shorthand**: `{"name": "ds_x", "asset_name": "catalog.schema.table_or_view"}` — no SQL needed. Works for tables, views, and metric views. You can still stack `columns` (measures + derived dimensions) on top: `{"name": "ds_x", "asset_name": "...", "columns": [{"displayName": "Total Revenue", "expression": "SUM(\`amount_usd\`)"}]}` — same `MEASURE()` pattern.

## Measures

Reusable measures declared on a dataset, referenced by name from any widget. Dataset rules (bare table names, one query per dataset, aliases) are in [SKILL.md § Dataset architecture](../SKILL.md#1-dataset-architecture).

Widget expressions are usually inline aggregations (`{"name": "sum(x)", "expression": "SUM(\`x\`)"}`). But you can also **declare reusable measures on the dataset itself** and reference them by name — every widget that consumes the dataset can use the same metric without redefining it.

Two ways to define measures:

1. **Dashboard-level `columns`** (works on any dataset — SQL query or `asset_name`):
   ```json
   {
     "name": "ds_support",
     "queryLines": ["SELECT * FROM support_cases"],
     "columns": [
       {"displayName": "Total Cases",     "description": "Count of cases",
        "expression": "COUNT(`case_id`)"},
       {"displayName": "Reopen Rate %",   "description": "% of reopened cases",
        "expression": "SUM(CASE WHEN `reopened_flag` THEN 1 ELSE 0 END) * 100.0 / COUNT(`case_id`)"},
       {"displayName": "Priority Level",  "description": "Sorted priority label",
        "expression": "CASE WHEN `priority`='Critical' THEN '1-Critical' ELSE '4-Low' END"}
     ]
   }
   ```

2. **Metric-view source** — if the dataset's `asset_name` (or `FROM` clause) is a UC metric view, its YAML-defined measures are already queryable. **Do not redeclare them** in `columns`. See [databricks-metric-views](../../databricks-metric-views/SKILL.md).

Either way, widgets reference the measure by name:

```json
"fields": [{"name": "measure(Total Cases)", "expression": "MEASURE(`Total Cases`)"}],
"encodings": {"value": {"fieldName": "measure(Total Cases)", "displayName": "Total Cases"}}
```

`MEASURE(\`...\`)` works in counter, table, bar, line, pie, pivot — any widget that takes a field expression. Mix it with inline aggregations freely.
