# Creating Genie Spaces

This guide covers creating and managing Genie Spaces for SQL-based data exploration.

> **CLI is the default.** The canonical, environment-agnostic commands (`databricks genie create-space`, `update-space`, `get-space`, `trash-space`) live in the parent [SKILL.md](../SKILL.md). This reference documents the **MCP tool surface** (`manage_genie`, `get_table_stats_and_schema`) — use it when the Databricks MCP server is configured (e.g. inside an IDE) and you prefer one-call shortcuts over CLI + `jq`. The [Exact Field Schemas](#exact-field-schemas-verified-against-the-genie-api) section is **tool-agnostic** — the same `serialized_space` shapes apply whether you push them via CLI or MCP.

## What is a Genie Space?

A Genie Space connects to Unity Catalog tables and translates natural language questions into SQL — understanding schemas, generating queries, executing them on a SQL warehouse, and presenting results conversationally.

## Creation Workflow

### Step 1: Inspect Table Schemas (Required)

**Before creating a Genie Space, you MUST inspect the table schemas** to understand what data is available:

```python
get_table_stats_and_schema(
    catalog="my_catalog",
    schema="sales",
    table_stat_level="SIMPLE"
)
```

This returns:
- Table names and row counts
- Column names and data types
- Sample values and cardinality
- Null counts and statistics

### Step 2: Analyze and Plan

Based on the schema information:

1. **Select relevant tables** - Choose tables that support the user's use case
2. **Identify key columns** - Note date columns, metrics, dimensions, and foreign keys
3. **Understand relationships** - How do tables join together?
4. **Plan sample questions** - What questions can this data answer?

### Step 3: Create the Genie Space

Create the space with content tailored to the actual data:

```python
manage_genie(
    action="create_or_update",
    display_name="Sales Analytics",
    table_identifiers=[
        "my_catalog.sales.customers",
        "my_catalog.sales.orders",
        "my_catalog.sales.products"
    ],
    description="""Explore retail sales data with three related tables:
- customers: Customer demographics including region, segment, and signup date
- orders: Transaction history with order_date, total_amount, and status
- products: Product catalog with category, price, and inventory

Tables join on customer_id and product_id.""",
    sample_questions=[
        "What were total sales last month?",
        "Who are our top 10 customers by total_amount?",
        "How many orders were placed in Q4 by region?",
        "What's the average order value by customer segment?",
        "Which product categories have the highest revenue?",
        "Show me customers who haven't ordered in 90 days"
    ]
)
```

## Why This Workflow Matters

**Sample questions that reference actual column names** help Genie:
- Learn the vocabulary of your data
- Generate more accurate SQL queries
- Provide better autocomplete suggestions

**A description that explains table relationships** helps Genie:
- Understand how to join tables correctly
- Know which table contains which information
- Provide more relevant answers

## Auto-Detection of Warehouse

When `warehouse_id` is not specified, the tool:

1. Lists all SQL warehouses in the workspace
2. Prioritizes by:
   - **Running** warehouses first (already available)
   - **Starting** warehouses second
   - **Smaller sizes** preferred (cost-efficient)
3. Returns an error if no warehouses exist

To use a specific warehouse, provide the `warehouse_id` explicitly.

## Table Selection

Choose tables carefully for best results:

| Layer | Recommended | Why |
|-------|-------------|-----|
| Bronze | No | Raw data, may have quality issues |
| Silver | Yes | Cleaned and validated |
| Gold | Yes | Aggregated, optimized for analytics |

### Tips for Table Selection

- **Include related tables**: If users ask about customers and orders, include both
- **Use descriptive column names**: `customer_name` is better than `cust_nm`
- **Add table comments**: Genie uses metadata to understand the data

## Sample Questions

Sample questions help users understand what they can ask:

**Good sample questions:**
- "What were total sales last month?"
- "Who are our top 10 customers by revenue?"
- "How many orders were placed in Q4?"
- "What's the average order value by region?"

These appear in the Genie UI to guide users.

## Best Practices

### Table Design for Genie

1. **Descriptive names**: Use `customer_lifetime_value` not `clv`
2. **Add comments**: `COMMENT ON TABLE sales.customers IS 'Customer master data'`
3. **Primary keys**: Define relationships clearly
4. **Date columns**: Include proper date/timestamp columns for time-based queries

### Description and Context

Provide context in the description:

```
Explore retail sales data from our e-commerce platform. Includes:
- Customers: demographics, segments, and account status
- Orders: transaction history with amounts and dates
- Products: catalog with categories and pricing

Time range: Last 6 months of data
```

### Sample Questions

Write sample questions that:
- Cover common use cases
- Demonstrate the data's capabilities
- Use natural language (not SQL terms)

## Querying Metric Views in Genie

When a Genie Space's data source is a **metric view** (not a plain table), all SQL — Genie-generated, in `example_question_sqls`, or in `text_instructions` — must follow the metric-view query rules. Getting them wrong produces `MISSING_AGGREGATION` errors that silently degrade answer quality. The short version:

- A dimension inside a `CASE` that also calls `MEASURE()` must be in `GROUP BY` — use a CTE with `GROUP BY ALL`, then aggregate in the outer query.
- Prefer a pre-built composed measure (e.g. `MEASURE(blended_spread)`) over rebuilding its branching with `CASE WHEN`.
- Never put a measure in `WHERE` or `GROUP BY` — filter measure results with `HAVING` or an outer query/CTE.

Author these into the space's example SQL and instructions so Genie writes correct SQL. Full rules, examples, and rationale live with the metric-view skill, since they apply to any query (dashboards, ad-hoc SQL, Genie): see [databricks-metric-views/query-patterns.md](../../databricks-metric-views/references/query-patterns.md). For designing metric views so Genie reasons well over them, see [databricks-metric-views/genie-integration.md](../../databricks-metric-views/references/genie-integration.md).

## Updating a Genie Space

`manage_genie(action="create_or_update")` handles both create and update automatically. There are two ways it locates an existing space to update:

- **By `space_id`** (explicit, preferred): pass `space_id=` to target a specific space.
- **By `display_name`** (implicit fallback): if `space_id` is omitted, the tool searches for a space with a matching name and updates it if found; otherwise it creates a new one.

### Simple field updates (tables, questions, warehouse)

To update metadata without a serialized config:

```python
manage_genie(
    action="create_or_update",
    display_name="Sales Analytics",
    space_id="01abc123...",           # omit to match by name instead
    table_identifiers=[               # updated table list
        "my_catalog.sales.customers",
        "my_catalog.sales.orders",
        "my_catalog.sales.products",
    ],
    sample_questions=[                # updated sample questions
        "What were total sales last month?",
        "Who are our top 10 customers by revenue?",
    ],
    warehouse_id="abc123def456",      # omit to keep current / auto-detect
    description="Updated description.",
)
```

### Full config update via `serialized_space`

To push a complete serialized configuration to an existing space (the dict contains all regular table metadata, plus it preserves all instructions, SQL examples, join specs, etc.):

```python
manage_genie(
    action="create_or_update",
    display_name="Sales Analytics",   # overrides title embedded in serialized_space
    table_identifiers=[],             # ignored when serialized_space is provided
    space_id="01abc123...",           # target space to overwrite
    warehouse_id="abc123def456",      # overrides warehouse embedded in serialized_space
    description="Updated description.",  # overrides description embedded in serialized_space; omit to keep the one in the payload
    serialized_space=remapped_config, # JSON string from manage_genie(action="export") (after catalog remap if needed)
)
```

> **Note:** When `serialized_space` is provided, `table_identifiers` and `sample_questions` are ignored — the full config comes from the serialized payload. However, `display_name`, `warehouse_id`, and `description` are still applied as top-level overrides on top of the serialized payload. Omit any of them to keep the values embedded in `serialized_space`.

## Export, Import & Migration

`manage_genie(action="export")` returns a dictionary with four top-level keys:

| Key | Description |
|-----|-------------|
| `space_id` | ID of the exported space |
| `title` | Display name of the space |
| `description` | Description of the space |
| `warehouse_id` | SQL warehouse associated with the space (workspace-specific — do **not** reuse across workspaces) |
| `serialized_space` | JSON-encoded string with the full space configuration (see below) |

This envelope enables cloning, backup, and cross-workspace migration. Use `manage_genie(action="export")` and `manage_genie(action="import")` for all export/import operations — no direct REST calls needed.

### What is `serialized_space`?

`serialized_space` is a JSON string (version 2) embedded inside the export envelope. Its top-level keys are:

| Key | Contents |
|-----|----------|
| `version` | Schema version (currently `2`) |
| `config` | Space-level config: `sample_questions` shown in the UI |
| `data_sources` | `tables` array — each entry has a fully-qualified `identifier` (`catalog.schema.table`) and optional `column_configs` (per-column descriptions, synonyms, format assistance, entity matching, and hidden fields — see [§Exact Field Schemas](#exact-field-schemas-verified-against-the-genie-api)) |
| `instructions` | `example_question_sqls` (certified Q&A pairs), `join_specs` (join relationships between tables), `sql_snippets` (`filters` and `measures` with display names and usage instructions) |
| `benchmarks` | Evaluation Q&A pairs used to measure space quality |

Catalog names appear **everywhere** inside `serialized_space` — in `data_sources.tables[].identifier`, SQL strings in `example_question_sqls`, `join_specs`, and `sql_snippets`. A single `.replace(src_catalog, tgt_catalog)` on the whole string is sufficient for catalog remapping.

Minimum structure:
```json
{"version": 2, "data_sources": {"tables": [{"identifier": "catalog.schema.table"}]}}
```

### Exact Field Schemas (verified against the Genie API)

The API is strictly schema-validated and the protobuf shapes are not obvious. The errors you'll see when shapes are wrong include `Expected an array for <field>`, `Unknown field`, `<field> must be sorted by id`, and the cryptic `Invalid JSON in field 'serialized_space': Expected 'START_OBJECT' not 'VALUE_STRING'` (which actually means a sub-field has the wrong shape — typically a string where an array is expected).

The verified shapes are below. Use them either by hand-constructing JSON with care, or by adapting the self-contained Python helper at the end of this section.

**`data_sources.tables[].column_configs`** — per-column GenAI context: column descriptions, synonyms, format assistance, entity matching (a.k.a. prompt matching), and hidden fields. **Optional and selective** — only add an entry for a column that needs one; omit `column_configs` entirely when no column needs tuning. Each entry keys on `column_name`; the other fields are independent and any combination may appear:

```json
{
  "data_sources": {
    "tables": [
      {
        "identifier": "catalog.schema.table",
        "column_configs": [
          {
            "column_name": "asset_type",
            "enable_format_assistance": true,
            "enable_entity_matching": true
          },
          {
            "column_name": "blended_spread",
            "description": ["Blended spread: zdm3yr for loans, OAS for everything else."],
            "synonyms": ["spread", "avg spread", "blended spread"]
          },
          {
            "column_name": "bloomberg_global_id",
            "exclude": true
          }
        ]
      }
    ]
  }
}
```

| Sub-field | Type | Purpose |
|-----------|------|---------|
| `column_name` | string | Required key; the column this entry configures. |
| `description` | array of strings | Column-level business description (same array-of-strings shape as `text_instructions[].content`). |
| `synonyms` | array of strings | Business terms that map to this column. |
| `enable_format_assistance` | bool | Format assistance for the column's values. |
| `enable_entity_matching` | bool | Entity matching / prompt matching — enable only for stable low/medium-cardinality strings users name directly. |
| `exclude` | bool | Hides the column from end-user context (the "hidden fields" surface). |

Enable `enable_format_assistance` / `enable_entity_matching` **selectively** — only on useful categorical dimensions and filters. Do **not** blanket-enable them on every column (IDs, hashes, free text, lat/long, raw measures): that adds noise and is the over-enabling the design guide warns against.

**`config.sample_questions`** — user-visible suggested questions:

```json
{
  "config": {
    "sample_questions": [
      {"id": "<32-hex>", "question": ["What were Q1 sales?"]}
    ]
  }
}
```

**`instructions.text_instructions`** — free-text rules. **Max 1 item** at the top level; put multiple rules as elements of the inner `content` array:

```json
{
  "instructions": {
    "text_instructions": [
      {
        "id": "<32-hex>",
        "content": [
          "Rule 1: ...",
          "Rule 2: ...",
          "Rule 3: ..."
        ]
      }
    ]
  }
}
```

**`instructions.example_question_sqls`** — saved certified Q&A pairs. `question` and `sql` are both arrays of strings:

```json
{
  "instructions": {
    "example_question_sqls": [
      {
        "id": "<32-hex>",
        "question": ["What were Q1 sales?"],
        "sql": ["SELECT SUM(amount) FROM sales WHERE quarter = '2026-Q1'"]
      }
    ]
  }
}
```

**`benchmarks.questions`** — evaluation prompts. Note: `benchmarks` is an **object containing** `questions`, not an array itself. Each answer has a `format` (`SQL` or `TEXT`) and `content` array:

```json
{
  "benchmarks": {
    "questions": [
      {
        "id": "<32-hex>",
        "question": ["What were Q1 sales?"],
        "answer": [
          {
            "format": "SQL",
            "content": ["SELECT SUM(amount) FROM sales WHERE quarter = '2026-Q1'"]
          }
        ]
      }
    ]
  }
}
```

### Hard Constraints

| Rule | What happens if violated |
|------|--------------------------|
| All `id` values must be lowercase 32-hex without hyphens (e.g., `uuid.uuid4().hex`) | `sample_question.id must be provided and non-empty. Expected lowercase 32-hex UUID without hyphens.` |
| `text_instructions` array must have at most one item | `instructions.text_instructions must contain at most one item` |
| Arrays of id-keyed items must be sorted by `id` (covers `text_instructions`, `example_question_sqls`, `benchmarks.questions`, `join_specs`, `sql_functions`) | `instructions.example_question_sqls must be sorted by id` |
| `data_sources.tables` should be sorted by `identifier` | The builder sorts this automatically in `to_dict()` |
| String-valued sub-fields that are actually array-typed (`question`, `sql`, `content`, `text_instructions[].content`) | `Expected an array for <field> but found "<value>"` |
| Sub-field with wrong shape (e.g., string where object/array is expected) | `Invalid JSON in field 'serialized_space': Expected 'START_OBJECT' not 'VALUE_STRING' (line 1)` — misleading; check sub-field shapes |
| Unknown field name | `Unknown field 'X'` — common pitfalls: using `text` instead of `content`, `expected_sql`/`ground_truth_sql` instead of `answer[].content`, `benchmarks: [...]` instead of `benchmarks: {questions: [...]}` |

### Self-Contained Python Helper

Copy this into a script. It produces a correctly-shaped `serialized_space` for the common case (one metric view, instructions, example SQLs, benchmarks, sample questions) and handles the id-sorting and max-1 constraints automatically.

```python
import json
import uuid

def newid():
    """Lowercase 32-hex UUID without hyphens."""
    return uuid.uuid4().hex

def build_serialized_space(
    metric_view_or_table: str,
    sample_questions: list[str] | None = None,
    instruction_rules: list[str] | None = None,
    example_sqls: list[tuple[str, str]] | None = None,    # (question, sql) pairs
    benchmarks: list[tuple[str, str]] | None = None,      # (question, expected_sql) pairs
    column_configs: list[dict] | None = None,             # per-column GenAI context (see below)
) -> str:
    table = {"identifier": metric_view_or_table}
    if column_configs:
        # Each dict: {"column_name": str, and any of "description": [str],
        # "synonyms": [str], "enable_format_assistance": bool,
        # "enable_entity_matching": bool, "exclude": bool}. Add entries only
        # for columns that need tuning; enable format/entity matching selectively.
        table["column_configs"] = sorted(column_configs, key=lambda c: c["column_name"])
    payload = {
        "version": 2,
        "data_sources": {"tables": [table]},
    }

    if sample_questions:
        payload.setdefault("config", {})["sample_questions"] = sorted(
            [{"id": newid(), "question": [q]} for q in sample_questions],
            key=lambda x: x["id"],
        )

    instructions = {}
    if instruction_rules:
        # text_instructions has max 1 item; pack all rules into the inner content array.
        instructions["text_instructions"] = [{"id": newid(), "content": list(instruction_rules)}]
    if example_sqls:
        instructions["example_question_sqls"] = sorted(
            [{"id": newid(), "question": [q], "sql": [s]} for q, s in example_sqls],
            key=lambda x: x["id"],
        )
    if instructions:
        payload["instructions"] = instructions

    if benchmarks:
        payload["benchmarks"] = {
            "questions": sorted(
                [
                    {
                        "id": newid(),
                        "question": [q],
                        "answer": [{"format": "SQL", "content": [sql]}],
                    }
                    for q, sql in benchmarks
                ],
                key=lambda x: x["id"],
            )
        }

    return json.dumps(payload)

# --- Example usage ---
serialized = build_serialized_space(
    metric_view_or_table="main.sales.global_sales_metrics",
    sample_questions=[
        "What were Q1 sales for North America?",
        "Top firms driving sales?",
    ],
    instruction_rules=[
        "When user asks about FYTD, filter `Fiscal Year` = 2026.",
        "When user mentions 'North America', filter `Region` = 'NA'.",
    ],
    example_sqls=[
        ("Q1 North America sales",
         "SELECT MEASURE(`Net Sales`) FROM main.sales.global_sales_metrics WHERE `Region`='NA' AND `Fiscal Year`=2026"),
    ],
    benchmarks=[
        # 2-4 phrasings per question, same ground-truth SQL each
        ("What were FYTD sales for NA?",
         "SELECT MEASURE(`Net Sales`) FROM main.sales.global_sales_metrics WHERE `Region`='NA' AND `Fiscal Year`=2026"),
        ("Show me North America FYTD sales",
         "SELECT MEASURE(`Net Sales`) FROM main.sales.global_sales_metrics WHERE `Region`='NA' AND `Fiscal Year`=2026"),
    ],
    column_configs=[
        # Selective: format/entity matching only on categorical filters users name.
        {"column_name": "Region", "enable_format_assistance": True, "enable_entity_matching": True,
         "synonyms": ["geo", "geography"]},
        {"column_name": "internal_hash_id", "exclude": True},
    ],
)

# Push via the MCP tool:
manage_genie(
    action="create_or_update",
    space_id="01abc123...",
    serialized_space=serialized,
)

# Or via the Databricks CLI:
# Write the patch envelope to a file then:
#   databricks api patch /api/2.0/genie/spaces/01abc123... --json @patch.json
```

**Workflow tip:** When updating an existing space, fetch its current `serialized_space` first (via `manage_genie(action="get", include_serialized_space=True)`), parse it, mutate the fields you care about, and push back. This preserves any fields the helper above doesn't model (`join_specs`, `sql_snippets`, etc.). The helper *does* model `column_configs` (above) — pass it explicitly on create so a new space ships with per-column context instead of an empty default.

> **Databricks-internal note:** If you have access to the internal `fe-internal-tools` plugin, its `GenieSpaceBuilder` (in `resources/genie_space_builder.py` of the `genie-rooms` skill) provides chainable helpers (`set_instructions`, `add_example_sql`, `add_benchmark`, `add_metric_view`, etc.) that wrap the same shape construction. External users should use the self-contained helper above.

### Exporting a Space

Use `manage_genie(action="export")` to export the full configuration (requires CAN EDIT permission):

```python
exported = manage_genie(action="export", space_id="01abc123...")
# Returns:
# {
#   "space_id": "01abc123...",
#   "title": "Sales Analytics",
#   "description": "Explore sales data...",
#   "warehouse_id": "abc123def456",
#   "serialized_space": "{\"version\":2,\"data_sources\":{...},\"instructions\":{...}}"
# }
```

You can also get `serialized_space` inline via `manage_genie(action="get")`:

```python
details = manage_genie(action="get", space_id="01abc123...", include_serialized_space=True)
serialized = details["serialized_space"]
```

### Cloning a Space (Same Workspace)

```python
# Step 1: Export the source space
source = manage_genie(action="export", space_id="01abc123...")

# Step 2: Import as a new space
manage_genie(
    action="import",
    warehouse_id=source["warehouse_id"],
    serialized_space=source["serialized_space"],
    title=source["title"],  # override title; omit to keep original
    description=source["description"],
)
# Returns: {"space_id": "01def456...", "title": "Sales Analytics (Dev Copy)", "operation": "imported"}
```

### Migrating Across Workspaces with Catalog Remapping

When migrating between environments (e.g. prod → dev), Unity Catalog names are often different. The `serialized_space` string contains the source catalog name **everywhere** — in table identifiers, SQL queries, join specs, and filter snippets. You must remap it before importing.

**Agent workflow (3 steps):**

**Step 1 — Export from source workspace:**
```python
exported = manage_genie(action="export", space_id="01f106e1239d14b28d6ab46f9c15e540")
# exported keys: warehouse_id, title, description, serialized_space
# exported["serialized_space"] contains all references to source catalog
```

**Step 2 — Remap catalog name in `serialized_space`:**

The agent does this as an inline string substitution between the two MCP calls:
```python
modified_serialized = exported["serialized_space"].replace(
    "source_catalog_name",     # e.g. "healthverity_claims_sample_patient_dataset"
    "target_catalog_name"      # e.g. "healthverity_claims_sample_patient_dataset_dev"
)
```
This replaces all occurrences — table identifiers, SQL FROM clauses, join specs, and filter snippets.

**Step 3 — Import to target workspace:**
```python
manage_genie(
    action="import",
    warehouse_id="<target_warehouse_id>",   # from manage_warehouse(action="list") on target
    serialized_space=modified_serialized,
    title=exported["title"],
    description=exported["description"]
)
```

### Batch Migration of Multiple Spaces

To migrate several spaces at once, loop through space IDs. The agent exports, remaps the catalog, then imports each:

```
For each space_id in [id1, id2, id3]:
  1. exported = manage_genie(action="export", space_id=space_id)
  2. modified  = exported["serialized_space"].replace(src_catalog, tgt_catalog)
  3. result    = manage_genie(action="import", warehouse_id=wh_id, serialized_space=modified, title=exported["title"], description=exported["description"])
  4. record result["space_id"] for updating databricks.yml
```

After migration, update `databricks.yml` with the new dev `space_id` values under the `dev` target's `genie_space_ids` variable.

### Updating an Existing Space with New Config

To push a serialized config to an already-existing space (rather than creating a new one), use `manage_genie(action="create_or_update")` with `space_id=` and `serialized_space=`. The export → remap → push pattern is identical to the migration steps above; just replace `manage_genie(action="import")` with `manage_genie(action="create_or_update", space_id=TARGET_SPACE_ID, ...)` as the final call.

### Permissions Required

| Operation | Required Permission |
|-----------|-------------------|
| `manage_genie(action="export")` / `manage_genie(action="get", include_serialized_space=True)` | CAN EDIT on source space |
| `manage_genie(action="import")` | Can create items in target workspace folder |
| `manage_genie(action="create_or_update")` with `serialized_space` (update) | CAN EDIT on target space |

## Example End-to-End Workflow

1. **Generate synthetic data** using `databricks-synthetic-data-gen` skill:
   - Creates parquet files in `/Volumes/catalog/schema/raw_data/`

2. **Create tables** using `databricks-spark-declarative-pipelines` skill:
   - Creates `catalog.schema.bronze_*` → `catalog.schema.silver_*` → `catalog.schema.gold_*`

3. **Inspect the tables**:
   ```python
   get_table_stats_and_schema(catalog="catalog", schema="schema")
   ```

4. **Create the Genie Space**:
   - `display_name`: "My Data Explorer"
   - `table_identifiers`: `["catalog.schema.silver_customers", "catalog.schema.silver_orders"]`

5. **Add sample questions** based on actual column names

6. **Test** in the Databricks UI

## Troubleshooting

### No warehouse available

- Create a SQL warehouse in the Databricks workspace
- Or provide a specific `warehouse_id`

### Queries are slow

- Ensure the warehouse is running (not stopped)
- Consider using a larger warehouse size
- Check if tables are optimized (OPTIMIZE, Z-ORDER)

### Poor query generation

- Use descriptive column names
- Add table and column comments
- Include sample questions that demonstrate the vocabulary
- Add instructions via the Databricks Genie UI

### `manage_genie(action="export")` returns empty `serialized_space`

Requires at least **CAN EDIT** permission on the space.

### `manage_genie(action="import")` fails with permission error

Ensure you have CREATE privileges in the target workspace folder.

### Tables not found after migration

Catalog name was not remapped — replace the source catalog name in `serialized_space` before calling `manage_genie(action="import")`. The catalog appears in table identifiers, SQL FROM clauses, join specs, and filter snippets; a single `.replace(src_catalog, tgt_catalog)` on the whole string covers all occurrences.

### `manage_genie` lands in the wrong workspace

Each MCP server is workspace-scoped. Set up two named MCP server entries (one per profile) in your IDE's MCP config instead of switching a single server's profile mid-session.

### MCP server doesn't pick up profile change

The MCP process reads `DATABRICKS_CONFIG_PROFILE` once at startup — editing the config file requires an IDE reload to take effect.

### `manage_genie(action="import")` fails with JSON parse error

The `serialized_space` string may contain multi-line SQL arrays with `\n` escape sequences. Flatten SQL arrays to single-line strings before passing to avoid double-escaping issues.
