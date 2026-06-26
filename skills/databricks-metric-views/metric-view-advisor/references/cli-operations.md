# CLI & API Operations

All operations in this skill run through the **Databricks CLI** (>= v1.0.0), authenticated to a workspace profile. To create a **new** profile, run `databricks auth login --host <workspace-url> --profile <PROFILE>`; to re-authenticate an **existing** profile, just run `databricks auth login --profile <PROFILE>` (the host is already stored — passing `--host` again is unnecessary and can error on a mismatch). This file documents the specific commands the workflow relies on.

> **Never use `databricks sql execute` or `databricks execute-statement` — those commands do not exist.** Use the `aitools` query tool or the `aitools` statement command below.

## Contents

- [Executing SQL](#executing-sql)
- [Discovering table schema](#discovering-table-schema)
- [Managing metric views](#managing-metric-views)
- [Fetching an AI/BI dashboard](#fetching-an-aibi-dashboard)
- [Fetching a Genie space](#fetching-a-genie-space)

## Executing SQL

### Short / ad-hoc queries — the AI tools query command

For `SHOW`, `DESCRIBE`, `SELECT`, and other short statements, use the AI tools query command (it auto-picks the default warehouse):

```bash
databricks experimental aitools tools query "SELECT 1" --profile <PROFILE>
```

To pin a specific warehouse, set `DATABRICKS_WAREHOUSE_ID` or pass `--warehouse <ID>`.

### Long DDL (CREATE OR REPLACE VIEW ...) — the AI tools statement command

Long metric-view DDL contains `$$ ... $$` token-quoting and embedded YAML that is fragile in shell heredocs and JSON escaping. Write the statement to a `.sql` file and submit it with the `aitools` statement command — `submit` takes a file path, so there is no heredoc/JSON-escaping to get wrong:

```bash
# 1. Write the full CREATE OR REPLACE VIEW ... statement to a file (e.g. /tmp/metric_view.sql)

# 2. Submit asynchronously — returns a statement_id immediately
databricks experimental aitools tools statement submit --file /tmp/metric_view.sql \
  --warehouse <warehouse_id> --profile <PROFILE>

# 3. Block until the statement reaches a terminal state and emit the result
databricks experimental aitools tools statement get <statement_id> --profile <PROFILE>
```

`submit` returns a JSON object with `statement_id` and `state`. `get` blocks until the statement is terminal, then emits columns and rows on success or an error object on failure. (Set `DATABRICKS_WAREHOUSE_ID` instead of `--warehouse` to pin a warehouse globally.)

To peek at the state without blocking, use `statement status <statement_id>`; to terminate a long-running statement, use `statement cancel <statement_id>`. For "I want results now" on a short statement, use `aitools tools query` instead (see above).

### Discover a warehouse

```bash
databricks experimental aitools tools get-default-warehouse --profile <PROFILE>
```

Or list warehouses and pick the first one with `"state": "RUNNING"`:

```bash
databricks warehouses list --profile <PROFILE> --output json
```

The output is a **plain JSON array** (NOT `{"warehouses": [...]}`).

## Discovering table schema

Use the AI tools `discover-schema` command — one call returns columns, types, sample rows, null counts, and row count:

```bash
databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <PROFILE>
```

For deeper metadata, run SQL via the methods above:
- `DESCRIBE TABLE EXTENDED <table>` — columns, types, comments, constraints
- `DESCRIBE DETAIL <table>` — partition/clustering columns
- `SHOW TBLPROPERTIES <table>` — table properties
- `SELECT COUNT(*) FROM <table>` — row count
- `SELECT * FROM <table> LIMIT 5` — sample data

## Managing metric views

There is no dedicated metric-view CLI verb — operate via SQL:

- **Create / replace:** execute the full `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$` statement using the **`aitools tools statement submit --file`** path above.
- **Get definition:** `DESCRIBE TABLE EXTENDED <full_name> AS JSON` — the response includes `view_text` (the YAML definition) and column metadata with `is_measure` flags.
- **List in a schema:** metric views appear in `information_schema.tables` with `table_type = 'METRIC_VIEW'` (they do NOT show in `SHOW VIEWS`):
  ```sql
  SELECT table_name FROM <catalog>.information_schema.tables
  WHERE table_schema = '<schema>' AND table_type = 'METRIC_VIEW'
  ```
- **Query:** execute a standard `SELECT` using `MEASURE()` syntax (every measure wrapped in `MEASURE()`, every dimension in `GROUP BY`).
- **Grant (least privilege):** `GRANT SELECT ON VIEW <full_name> TO <principal>`.

## Fetching an AI/BI dashboard

Use the dedicated Lakeview command — it returns the **draft** definition, which carries the full `serialized_dashboard` (datasets + widgets):

```bash
databricks lakeview get <dashboard_id> --profile <PROFILE>
# equivalent raw call:  databricks api get /api/2.0/lakeview/dashboards/<dashboard_id> --profile <PROFILE>
```

> **Do NOT use `/api/2.0/sql/dashboards/<id>`** — that endpoint does not exist and returns 404.

### Empty payload? Don't conclude the dashboard is empty — follow this fallback chain

Some host agents (e.g. Genie Code) have a **native dashboard/asset reader** (a `readAssetById`-style tool) that fetches the **published** serialization. That payload is frequently **empty** (`datasets: []` / `pages: []`, i.e. `datasetsCount: 0`, `pagesCount: 0`) — common for dashboards authored in the newer editor, or published without embedded dataset definitions. An empty result is a *fetch-method* problem, not an empty dashboard. When datasets/pages come back empty:

1. **Re-fetch the draft via the CLI** — `databricks lakeview get <id>` (not a native published-asset reader). The draft usually contains the datasets.
2. **Try the published variant** if the draft is empty — `databricks lakeview get-published <id> --profile <PROFILE>`.
3. **If both are still empty** (e.g. a v3-editor dashboard that serializes differently), **fall back to Input 3**: ask the user to export the dashboard's widget SQL into a `.sql` file (Datasets panel → copy each query, or the SQL behind each widget). Those queries capture the same analytical patterns reliably. See `input-handlers.md` → Input 3.

### Parsing `serialized_dashboard`

The response includes `serialized_dashboard` (a JSON string to parse). Parsing notes:
- `datasets` is a **list** of objects (NOT a dict keyed by name). Iterate with `for ds in datasets`.
- Each dataset: `name` (id), `displayName`, `catalog`, `schema`, and `queryLines` — the SQL as a **list of strings**. Reconstruct with `"\n".join(ds["queryLines"])`.
- `columns` (optional) — computed columns with `displayName`/`description`.

```python
import json
dash = json.loads(serialized_dashboard)
if not dash.get("datasets"):
    # empty — use get-published, then fall back to Input 3 (SQL file). Do not assume the dashboard has no data.
    ...
for ds in dash.get("datasets", []):    # iterate list, NOT .items()
    query = "\n".join(ds.get("queryLines", []))
    display_name = ds.get("displayName", "")
```

## Fetching a Genie space

**CRITICAL — fetch to a temp file, then parse.** The response with `include_serialized_space=true` is large and deeply nested. Save it first; never pipe the API output directly into an inline Python script (the pipe + heredoc conflict makes `json.load(sys.stdin)` read an empty stream).

```bash
# Step 1: save to a temp file (the query param is REQUIRED to get tables, questions, instructions)
databricks api get "/api/2.0/genie/spaces/<space_id>?include_serialized_space=true" --profile <PROFILE> > /tmp/genie_space.json

# Step 2: parse from the file
python3 << 'PYEOF'
import json
with open("/tmp/genie_space.json") as f:
    resp = json.load(f)
space = json.loads(resp.get("serialized_space", "") or "{}")
# ... parsing logic ...
PYEOF
```

**Nested-list structures to handle defensively (always use `isinstance()` checks):**
- `instructions.text_instructions[]` — each element is a **list of strings** (one per line) OR a dict with `.content`. Normalize: `"\n".join(item) if isinstance(item, list) else item.get("content", "")`.
- `instructions.join_instructions`, `sql_instructions`, `sql_query_instructions` — same nested list-of-strings structure.
- `benchmarks.questions[]` — each has `.question` (a **list** with one string; access `q["question"][0]`) and `.answer` (a **list** of objects, each with `.format` and `.content` as a **list of strings** to join: `"".join(q["answer"][0]["content"])`).
- `data_sources.tables[].identifier` — fully qualified table name (a plain string).

```python
import json
with open("/tmp/genie_space.json") as f:
    resp = json.load(f)
space = json.loads(resp.get("serialized_space", "") or "{}")

for item in space.get("instructions", {}).get("text_instructions", []):
    text = "\n".join(str(x) for x in item) if isinstance(item, list) \
        else (item.get("content", "") if isinstance(item, dict) else str(item))

for bq in space.get("benchmarks", {}).get("questions", []):
    q_raw = bq.get("question", [""])
    question = q_raw[0] if isinstance(q_raw, list) else q_raw
    ans = ""
    if bq.get("answer"):
        content = bq["answer"][0].get("content", [])
        ans = "".join(str(x) for x in content) if isinstance(content, list) else str(content)
```
