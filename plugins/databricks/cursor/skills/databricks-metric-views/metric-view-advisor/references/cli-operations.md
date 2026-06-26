# CLI & API Operations (advisor-specific)

Auth, profiles, warehouse discovery, and the basics of running SQL via the CLI are covered by the **`databricks-core`** skill — use it for `databricks auth login` / `auth describe`, listing profiles, and picking a warehouse. This file lists only the commands specific to building metric views from assets.

> **No `databricks sql execute` / `execute-statement`** — those commands don't exist. Use the `aitools` query/statement commands below.

## Running SQL

- **Short statements** (`SHOW`/`DESCRIBE`/`SELECT`): `databricks experimental aitools tools query "<SQL>" --profile <PROFILE>` (auto-picks the default warehouse).
- **Long DDL** (`CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$...$$`): write it to a `.sql` file and submit — this avoids the heredoc/JSON-escaping traps of `$$`-quoted embedded YAML:
  ```bash
  databricks experimental aitools tools statement submit --file view.sql --warehouse <ID> --profile <PROFILE>
  databricks experimental aitools tools statement get <statement_id> --profile <PROFILE>   # blocks until terminal
  ```
- **Inspect a table**: `databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <PROFILE>` (one call → columns, types, sample rows, null/row counts).

## Metric views (no dedicated CLI verb — operate via SQL)

- **Get definition**: `DESCRIBE TABLE EXTENDED <full_name> AS JSON` → returns the YAML definition + per-column `is_measure` flags.
- **List in a schema**: metric views live in `information_schema.tables` with `table_type = 'METRIC_VIEW'` (they do **not** show in `SHOW VIEWS`).
- **Grant** (least privilege): `GRANT SELECT ON VIEW <full_name> TO <principal>`.

## Fetch an AI/BI dashboard

`databricks lakeview get <dashboard_id> --profile <PROFILE>` → the **draft** `serialized_dashboard` (a JSON string). Parse `datasets` as a **list**; each dataset's SQL is `queryLines` (a list of strings — join with newlines).

> Don't use `/api/2.0/sql/dashboards/<id>` (404). **If `datasets`/`pages` come back empty** — common with a native published-asset reader or v3-editor dashboards — that's a fetch-method artifact, not an empty dashboard. Try in order: `lakeview get` (draft) → `lakeview get-published <id>` → fall back to Input 3 (ask for the widget SQL as a `.sql` file).

## Fetch a Genie space

Save to a file first, then parse — the payload is large, and piping it into inline Python makes `json.load(sys.stdin)` read an empty stream:

```bash
databricks api get "/api/2.0/genie/spaces/<space_id>?include_serialized_space=true" --profile <PROFILE> > /tmp/genie.json
```

Parse `serialized_space` (a JSON string). **Non-obvious gotcha — several fields are nested lists of strings, not plain strings**: `instructions.text_instructions[]`, `join_instructions`, `sql_instructions`; and `benchmarks.questions[]` has `.question` as a 1-element list and `.answer[].content` as a list of strings. Use `isinstance()` checks and join. `data_sources.tables[].identifier` is the fully-qualified table name.
