# Input Source Analysis Handlers

Detailed instructions for analyzing each input source type. The goal is always the same: identify tables, relationships, candidate dimensions, and candidate measures.

## Contents

- [Input 1: Gold Schema](#input-1-gold-schema)
- [Input 2: AI/BI Dashboard](#input-2-aibi-dashboard)
- [Input 3: Queries + Schema](#input-3-queries--schema)
- [Input 4: Genie Space](#input-4-genie-space)
- [Input 5: KPIs, Measures and Dimensions + Schema](#input-5-kpis-measures-and-dimensions--schema)
- [Merging Multiple Input Sources](#merging-multiple-input-sources)
- [Common Analysis Patterns](#common-analysis-patterns)

## Input 1: Gold Schema

**What you need:** `catalog.schema`

### Steps

1. **Get catalog and schema descriptions:**

   Before inspecting tables, fetch the catalog-level and schema-level comments for domain context:

```sql
DESCRIBE CATALOG <catalog>
```

```sql
DESCRIBE SCHEMA <catalog>.<schema>
```

   Extract the `comment` field from each. These provide high-level context about the data domain (e.g., *"Production analytics catalog"* or *"Gold layer tables for e-commerce order analytics"*). Use them to inform metric view naming and the top-level `comment` field.

2. **Get all tables in the schema, then inspect each:**

```bash
# list tables in the schema
databricks tables list <catalog> <schema> --profile <PROFILE>

# inspect each table (columns, types, sample rows, null counts, row count)
databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <PROFILE>
```

3. **Classify tables** as fact or dimension:
   - **Fact tables**: Have numeric columns (amounts, counts, prices), date/timestamp columns, foreign key-like columns (ending in `_id`, `_key`). Usually have the most rows.
   - **Dimension tables**: Have descriptive/categorical columns (names, types, statuses, regions). Usually have fewer rows. Often named `dim_*`.

4. **Identify relationships** by matching column names across tables:
   - Look for `<table>_id` or `<table>_key` patterns
   - Run sample queries to verify joins produce expected cardinality:

```sql
SELECT COUNT(*) AS fact_rows,
       COUNT(DISTINCT f.<fk_column>) AS distinct_fk,
       (SELECT COUNT(*) FROM <dim_table>) AS dim_rows
FROM <fact_table> f
```

5. **Sample data** from each table to understand value distributions:

```sql
SELECT * FROM <catalog.schema.table> LIMIT 5
```

6. **Identify candidate dimensions:**
   - String/categorical columns with reasonable cardinality (< 1000 distinct values)
   - Date/timestamp columns (for time-based dimensions)
   - Columns from dimension tables that would be useful for slicing
   - **Check nullability** — if a column has a significant null rate, wrap it in a null-safe expression: `COALESCE(region, 'Unknown')` or `CASE WHEN region IS NULL THEN 'Unspecified' ELSE region END`. Columns that are entirely NULL should be skipped.

```sql
SELECT '<column>' AS col, COUNT(DISTINCT <column>) AS distinct_vals
FROM <table>
UNION ALL ...
```

7. **Identify candidate measures:**
   - Numeric columns suitable for SUM, AVG, MIN, MAX
   - Columns that make sense as COUNT or COUNT DISTINCT
   - Derived ratios (revenue/customers, amount/quantity)

8. **Identify candidate global filters:**
   - Date ranges that should permanently scope the data (e.g., exclude historical data before a cutoff)
   - Status values that should always be excluded (e.g., test records, cancelled orders)
   - Common WHERE clauses that appear in most queries against these tables

9. **Extract table and column comments:**

   The `discover-schema` output includes table-level and column-level comments when they exist. Additionally, run `DESCRIBE TABLE EXTENDED <table>` for each table to capture the full metadata:

```sql
DESCRIBE TABLE EXTENDED <catalog.schema.table>
```

   From the results, extract:
   - **Table-level comment** — the `comment` field in the table metadata. Use this as the basis for the metric view's top-level `comment` field and to understand the table's business purpose.
   - **Column-level comments** — the `comment` column in the schema output for each column. These are authoritative descriptions written by data engineers and should be:
     - Used directly as `comment` fields on the corresponding dimensions/measures in the generated metric view
     - Mined for `synonyms` — if a column comment says *"Total order amount in USD (also known as order value)"*, extract "order value" as a synonym
     - Used to infer `display_name` — if a column comment provides a business-friendly label, use it

   **Priority rule:** Column comments from Unity Catalog are the most authoritative metadata source. When generating `comment`, `display_name`, and `synonyms` fields for dimensions and measures, always start with existing column comments before inferring from column names or types.

   Present discovered comments in the analysis summary:

   | Table | Comment |
   |-------|---------|
   | orders | "Gold table: fulfilled customer orders, refreshed daily" |
   | customers | "Dimension table: customer master data with segments" |

   | Table | Column | Column Comment |
   |-------|--------|---------------|
   | orders | amount | "Total order amount in USD including tax" |
   | orders | order_date | "Date the order was placed" |
   | customers | lifetime_value | "Cumulative spend since first purchase" |

10. **Check for PK/FK constraints:**
   - From the same `DESCRIBE TABLE EXTENDED` output (already fetched in step 9), check for existing primary/foreign key constraints
   - If constraints exist with `RELY`, note this for optimal join performance
   - If constraints are missing, recommend adding them in the Next Steps

11. **Extract Unity Catalog tags:**

   Check for tags on tables and columns that provide governance and classification context:

```sql
SELECT tag_name, tag_value FROM system.information_schema.table_tags
WHERE catalog_name = '<catalog>' AND schema_name = '<schema>'
```

```sql
SELECT table_name, column_name, tag_name, tag_value FROM system.information_schema.column_tags
WHERE catalog_name = '<catalog>' AND schema_name = '<schema>'
```

   Use tags to inform metric view design:
   - **`pii:true`** or similar privacy tags → flag the column as sensitive; it should NOT be a dimension unless the user explicitly approves, or it needs masking/hashing
   - **`domain:*`** tags → helps with metric view naming and grouping
   - **`tier:gold`** / `tier:silver` → confirms table readiness for metric views
   - **`deprecated:true`** → skip the column/table entirely
   - Any other classification tags → note them in the analysis summary for context

   If the `system.information_schema.table_tags` query fails (permissions or System Tables not enabled), skip silently and continue — tags are enrichment, not required.

12. **Check partitioning and clustering keys:**

   Run `DESCRIBE DETAIL <catalog.schema.table>` for each fact table to discover:

```sql
DESCRIBE DETAIL <catalog.schema.table>
```

   From the results, extract:
   - **`partitionColumns`** — Hive-style partition columns. These are always strong dimension candidates because the data is physically organized by them.
   - **`clusteringColumns`** — Liquid clustering keys. These indicate frequently filtered/joined columns and are strong dimension or filter candidates.

   Partitioned and clustered columns should be prioritized as dimensions and considered for the metric view `filter` field (e.g., if data is partitioned by `event_date`, a date-based filter is natural).

13. **Extract table properties and CHECK constraints:**

```sql
SHOW TBLPROPERTIES <catalog.schema.table>
```

   From the results, look for useful custom properties:
   - **`refresh_frequency`** or **`schedule`** — indicates how often the table is updated; useful context if the user later wants materialization (e.g., don't materialize more frequently than the source refreshes)
   - **`data_owner`** or **`owner`** — who to ask about the data if questions arise
   - **`quality_score`** or **`data_quality`** — confidence level in the data
   - Any other domain-specific properties — note them in the analysis summary

   Also check for CHECK constraints from the `DESCRIBE TABLE EXTENDED` output (already fetched in step 9):
   - CHECK constraints like `CHECK (amount > 0)` or `CHECK (status IN ('O','F','P'))` reveal valid value ranges
   - Use these to inform CASE dimension expressions — if a constraint defines the valid set of status codes, use those exact values in the CASE expression for humanization
   - Use numeric constraints to inform bucketing boundaries for dimension expressions

## Input 2: AI/BI Dashboard

**What you need:** Dashboard ID (extract from URL: `https://<workspace>/sql/dashboardsv3/<dashboard_id>`)

### Steps

1. **Get dashboard definition** (see [cli-operations.md](cli-operations.md) for the full fetch + parsing details):

API docs: https://docs.databricks.com/api/workspace/lakeview/get

```bash
databricks lakeview get <dashboard_id> --profile <PROFILE>
```

The response includes a `serialized_dashboard` field — a JSON string that must be parsed to access datasets and widgets.

> **If `datasets`/`pages` come back empty** (`datasetsCount: 0`, `pagesCount: 0`) — which happens when a native asset reader returns the *published* serialization, or for newer-editor dashboards — do NOT treat the dashboard as empty. Follow the fallback chain in [cli-operations.md](cli-operations.md): `lakeview get` (draft) → `lakeview get-published` → otherwise fall back to **Input 3** (ask the user for the dashboard's widget SQL as a `.sql` file).

2. **Extract dashboard-level metadata** from the top-level response:
   - `display_name` — the dashboard title (e.g., *"Executive Revenue Dashboard"*). Use this to understand the business domain and inform metric view naming.
   - Any dashboard description or tags if present. These provide high-level context about what the dashboard is designed to answer.

3. **Extract from the parsed `serialized_dashboard`:**

   **IMPORTANT:** `datasets` is a **list** of objects (NOT a dict keyed by name). Iterate with `for ds in datasets`, NOT `for name, ds in datasets.items()`. Each dataset object has:
   - `name` — dataset ID string (e.g., `"b1f080d9"`)
   - `displayName` — human-readable label (e.g., `"Orders with Customer"`)
   - `queryLines` — the SQL query as a **list of strings** (NOT a single string). Reconstruct the full SQL by joining: `"\n".join(ds["queryLines"])`. Example: `["SELECT\n", "  o.o_totalprice,\n", "  c.c_mktsegment\n", "FROM\n", "  orders o\n", ...]`
   - `catalog` and `schema` — default catalog/schema context for the query
   - `columns` (optional) — list of computed columns, each with `displayName`/`description`
   - `description` (optional) — dataset-level description

   Other `serialized_dashboard` fields:
   - `pages[].name` — **page titles** (e.g., "Revenue Overview", "Customer Analysis"). Multi-page dashboards group related visualizations — use page titles to inform how to group measures into separate metric views. If a dashboard has pages for different domains, each page may warrant its own metric view.
   - `pages[].layout[].widget` — visualizations with `queries[].query` (containing `datasetName`, `fields`, `groupBy`) and `spec.frame.title`

   **Dataset-level metadata:** For each dataset, check for `displayName` and `description` fields. Dataset authors may have documented what each dataset represents — map these to metric view comments or measure names. If computed columns have `displayName` or `description`, use those as the basis for dimension/measure `comment` and `display_name` fields.

4. **Parse each dataset query** to identify:
   - Source tables (FROM and JOIN clauses)
   - Existing aggregations (SUM, COUNT, AVG in SELECT)
   - GROUP BY columns (these become candidate dimensions)
   - WHERE/FILTER conditions (may become global filters or filtered measures)

5. **Get table details** for each source table found:

```bash
databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <PROFILE>
```

6. **Extract dashboard parameters:**

   Check for `parameters[]` in the `serialized_dashboard`. Dashboard parameters represent user-facing filter controls (dropdowns, date pickers, text inputs). Each parameter typically has:
   - `name` — the parameter name (e.g., "region_filter", "date_range")
   - `type` — the parameter type (e.g., "text", "date", "enum")
   - `values` or `query` — the allowed values or query that populates a dropdown

   Dashboard parameters are **strong dimension candidates** — they represent the axes users actively filter on. Map each parameter to a dimension in the metric view. If a parameter has a fixed list of values, these can inform CASE expressions for dimension value humanization.

7. **Map dashboard widgets to metric view concepts:**
   - Each chart's X-axis → candidate dimension
   - Each chart's Y-axis/values → candidate measures
   - Filters/parameters → candidate dimensions or **candidate global filters**
   - Multiple charts using the same tables → single metric view
   - Common WHERE clauses across datasets → candidate global filters
   - **Widget titles** (`spec.frame.title`) → inform measure naming (e.g., a chart titled "Revenue by Region" suggests a "Total Revenue" measure and "Region" dimension)
   - **Counter/stat widgets** → single-value measures (e.g., a KPI card showing "Total Orders" is a measure candidate)
   - **Table widgets** → all columns are dimension/measure candidates; aggregated columns → measures, non-aggregated → dimensions

## Input 3: Queries + Schema

**What you need:** A `.sql` file path containing one or more SQL queries + `catalog.schema`

### Accepting Input

Ask the user for a **file path** to a `.sql` file. The file should contain one or more SQL queries separated by semicolons (`;`) or double newlines. Read the file using the `Read` tool. A ready-to-use sample is provided at [examples/sample_queries.sql](../examples/sample_queries.sql).

**Expected file format:**
```sql
-- Query 1: Monthly revenue by region
SELECT region, DATE_TRUNC('MONTH', order_date) AS month, SUM(amount) AS revenue
FROM catalog.schema.orders
GROUP BY 1, 2;

-- Query 2: Top customers by spend
SELECT customer_id, SUM(amount) AS total_spend, COUNT(*) AS order_count
FROM catalog.schema.orders
GROUP BY 1
ORDER BY 2 DESC;
```

If the user provides queries inline (pasted into chat) instead of a file path, accept those too — but prefer the file-based approach for traceability.

### Steps

1. **Read the SQL file** and split into individual queries

2. **Extract SQL comments** — before parsing the SQL, extract all `--` single-line comments and `/* ... */` block comments. These often contain business context:
   - Comments preceding a query (e.g., `-- Monthly revenue by region`) describe the query's intent → use as the basis for measure/dimension `comment` fields
   - Inline comments next to columns (e.g., `SUM(amount) -- total revenue in USD`) provide column-level descriptions → use as `comment` and `display_name`
   - Section headers (e.g., `-- === Customer Metrics ===`) suggest metric view grouping

3. **Get schema details** (same as Input 1, step 2)

4. **Analyze each provided query:**
   - Parse SELECT columns: aggregated ones → measures, non-aggregated → dimensions
   - Parse FROM/JOIN: identify source and dimension tables
   - Parse WHERE: identify common filters
   - Parse GROUP BY: confirm dimensions
   - Associate each query with its preceding SQL comment (from step 2) for naming context

5. **Cross-reference queries with schema:**
   - Which tables are used most frequently?
   - Which columns appear in multiple queries?
   - Are there aggregation patterns that repeat?

6. **Identify metrics being computed** that aren't yet formalized:
   - Same aggregation logic appearing in multiple queries (DRY opportunity)
   - Complex expressions that should be named and standardized
   - Ratios computed ad-hoc that would benefit from metric view safety

7. **Identify candidate global filters** from common WHERE clauses:
   - Date range filters that appear in most or all queries
   - Status exclusions (e.g., `WHERE status != 'CANCELLED'`) common across queries

## Input 4: Genie Space

**What you need:** Space ID

### Steps

1. **Get Genie space configuration:**

API docs: https://docs.databricks.com/api/workspace/genie/getspace

**Important:** You must pass the query parameter `include_serialized_space=true` (default is `false`). Without it, the response only contains basic metadata (title, description, warehouse_id) — no tables, questions, or instructions. **Save the response to a temp file and parse from the file** (see [cli-operations.md](cli-operations.md) — the response is large and deeply nested):

```bash
databricks api get "/api/2.0/genie/spaces/<space_id>?include_serialized_space=true" --profile <PROFILE> > /tmp/genie_space.json
```

The response includes a `serialized_space` field — a JSON string that must be parsed to access tables, instructions, and benchmarks.

2. **Extract space-level metadata** from the top-level response:
   - `title` — the Genie space name (e.g., *"Sales Analytics"*). Use this to understand the business domain and inform metric view naming and comments.
   - `description` — the space description (e.g., *"Answers questions about revenue, orders, and customer behavior across regions"*). This provides high-level business context about what metrics users care about.

3. **Extract from the parsed `serialized_space`:**

   **Data sources:**
   - `data_sources.tables[].identifier` — the fully qualified tables the Genie space uses
   - `data_sources.tables[].columns[]` — per-table column metadata; check each column for custom `description`, `display_name`, or `synonyms` fields. Genie spaces allow custom per-column descriptions that may be more user-friendly than Unity Catalog column comments. If present, these should:
     - Be used as the basis for dimension/measure `comment` fields (prefer Genie descriptions over raw UC column comments when both exist, since Genie descriptions are tuned for natural language understanding)
     - Be captured as `synonyms` — any alternative names mentioned in the description
     - Inform `display_name` values
   - `data_sources.metric_views` — any metric views already configured in the space

   **Benchmarks (Common questions):**

   **IMPORTANT — nested list structures:** The Genie API returns several fields as nested lists. Handle them defensively:

   - `benchmarks.questions[]` — benchmark Q&A pairs. Each question object has:
     - `.question` — a **list** containing a single string (NOT a bare string). Access: `q["question"][0] if isinstance(q["question"], list) else q["question"]`
     - `.answer` — a **list** of objects, each with `.format` (string, e.g., `"SQL"`) and `.content` (a **list of strings** representing lines of SQL). Reconstruct: `"".join(q["answer"][0]["content"])`

   **Instructions — extract ALL four instruction types** (these map to the four sub-tabs in the Genie UI):

   **IMPORTANT — nested list structures:** Each instruction element can be either a **list of strings** (one per line) or a **dict with a `.content` field**. Always check the type before accessing. To normalize: `text = "\n".join(item) if isinstance(item, list) else (item.get("content", "") if isinstance(item, dict) else str(item))`

   - `instructions.text_instructions[]` — **Text tab**: General business context and query guidelines. Each element is a list of strings or an object with `.content`. Use these to understand the domain, naming conventions, and business rules that should inform metric view design.

   - `instructions.join_instructions[]` — **Joins tab**: Explicit join definitions between tables (e.g., *"Join orders to customers on o_custkey = c_custkey"*). These are **high-value signals** — they define the exact join paths the Genie author intended. Use them directly as `joins` in the metric view YAML. If a join instruction specifies a relationship, prefer it over inferred FK matching from schema inspection.

   - `instructions.sql_instructions[]` — **SQL Expressions tab**: SQL expression definitions (computed columns, CASE expressions, formulas). These define how raw columns should be transformed or computed — they should map directly to dimension `expr` or measure `expr` values. For example, *"Market Segment = CASE WHEN c_mktsegment = 'BUILDING' THEN 'Construction' ... END"* becomes a dimension expression.

   - `instructions.sql_query_instructions[]` — **SQL Queries tab**: Full reference SQL queries that define canonical ways to query the data. Parse these using the same approach as Input 3 (extract SELECT aggregations → measures, FROM/JOIN → tables, WHERE → filters, GROUP BY → dimensions). These queries are curated by the Genie author and represent verified analytical patterns.

   **Tags:**
   - Extract `tags` from the top-level response if present. Genie space tags provide classification context (e.g., "finance", "executive", "daily-reporting") that can inform metric view naming and grouping.

4. **Get table details** for each table in the space:

```bash
databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <PROFILE>
```

5. **Analyze benchmark questions and their SQL answers** to identify:
   - What metrics users ask about → candidate measures
   - How they slice data (by region, by month, etc.) → candidate dimensions
   - Keywords like "total", "average", "count", "per" → aggregation types

   **Parse each benchmark SQL answer** using the same approach as Input 3 (Queries + Schema):
   - Parse SELECT columns: aggregated ones → measures, non-aggregated → dimensions
   - Parse FROM/JOIN: identify source tables and join relationships
   - Parse WHERE: identify common filters and filter conditions
   - Parse GROUP BY: confirm dimensions
   - Parse ORDER BY: identify ranking patterns that suggest Top-N measures

   This is critical because benchmark SQL answers are curated, verified queries — they represent the canonical way the Genie space author expects data to be queried. Aggregation patterns, join paths, and filter conditions found here are strong candidates for standardization into metric views.

6. **Design metric views that improve Genie answers:**
   - Metric views with clear `comment` fields help Genie understand metrics
   - Named dimensions with business-friendly labels reduce ambiguity
   - Pre-defined ratios prevent Genie from computing them incorrectly
   - Use the space `title` and `description` (from step 2) to inform metric view naming and top-level comments
   - Use Genie column descriptions (from step 3) as the basis for `comment`, `display_name`, and `synonyms` on dimensions and measures
   - **Use join instructions** (from step 3) directly as metric view `joins` — these are the Genie author's intended join paths
   - **Use SQL expression instructions** (from step 3) as dimension/measure `expr` values — these are canonical computed column definitions
   - **Use SQL query instructions** (from step 3) to identify full analytical patterns — parse them the same way as Input 3 queries to extract measures, dimensions, filters, and join relationships
   - Use space `tags` to inform metric view grouping and naming conventions

## Input 5: KPIs, Measures and Dimensions + Schema

**What you need:** A `.csv` or `.yaml` file path containing KPI definitions + `catalog.schema`

### Accepting Input

Ask the user for a **file path** to a `.csv` or `.yaml` file. Read the file using the `Read` tool. Ready-to-use samples are provided at [examples/sample_kpis.csv](../examples/sample_kpis.csv) and [examples/sample_kpis.yaml](../examples/sample_kpis.yaml).

**Expected CSV format:**
```csv
type,name,definition,description
measure,Total Revenue,"SUM(amount)","Total order revenue in USD including tax"
measure,Order Count,"COUNT(1)","Number of orders placed"
measure,Unique Customers,"COUNT(DISTINCT customer_id)","Distinct customers who placed orders"
measure,Avg Order Value,"AVG(amount)",
dimension,Region,region,"Sales region"
dimension,Order Month,"DATE_TRUNC('MONTH', order_date)",
dimension,Customer Segment,"CASE WHEN lifetime_value > 10000 THEN 'Enterprise' ELSE 'SMB' END","Segment based on lifetime spend"
```

**Expected YAML format:**
```yaml
measures:
  - name: Total Revenue
    definition: "SUM(amount)"
    description: "Total order revenue in USD including tax"
  - name: Order Count
    definition: "COUNT(1)"
  - name: Unique Customers
    definition: "COUNT(DISTINCT customer_id)"

dimensions:
  - name: Region
    definition: region
    description: "Sales region"
  - name: Order Month
    definition: "DATE_TRUNC('MONTH', order_date)"
```

The `definition` and `description` fields are both optional. If `definition` is omitted, the skill will infer the expression by mapping the KPI name to schema columns. If `description` is provided, use it directly as the `comment` field on the corresponding dimension/measure in the metric view. If the user provides KPI descriptions inline (pasted into chat) instead of a file path, accept those too.

### Steps

1. **Read the KPI file** and parse entries by type (measure vs dimension)

2. **Get schema details** (same as Input 1, step 2 — list tables, then `discover-schema` each to get columns/types)

3. **Map each user-provided KPI to schema columns:**
   - For each KPI/measure: identify the source column(s) and aggregation type
   - For each dimension: identify the source column and any transformations needed

4. **Validate mappings** by running test aggregations:

```sql
SELECT <dimension_expr> AS dim,
       <measure_expr> AS measure
FROM <source_table>
GROUP BY 1
LIMIT 5
```

5. **Identify gaps:**
   - KPIs that require joins to dimension tables not yet identified
   - Measures that need CASE expressions or FILTER clauses
   - Dimensions that need bucketing or date truncation

6. **Suggest additional metrics** the user may not have listed:
   - Standard complements (if they want "Total Revenue", suggest "Revenue per Customer")
   - Filtered variants (if they want "Order Count", suggest "Open Order Count")
   - Time-based variants (monthly, quarterly breakdowns)

## Merging Multiple Input Sources

When the user selects more than one input source, run each applicable handler above, then merge findings using these rules:

### 1. Merge Tables

- **Union** all tables discovered across all sources (schema inspection, dashboard queries, Genie space tables, query FROM clauses)
- **Deduplicate** by fully qualified table name (`catalog.schema.table`)
- If a table appears in multiple sources, note all sources in the provenance (e.g., "from schema + dashboard dataset 2")

### 2. Merge Relationships

- Combine join paths discovered from schema FK analysis, dashboard JOIN clauses, and query JOIN clauses
- If two sources suggest different join conditions for the same table pair, prefer the one validated by a running query (dashboard/query source) over inferred FK matching (schema source)

### 3. Merge Dimensions

- Collect candidate dimensions from all sources
- **Deduplicate** by underlying expression — e.g., `DATE_TRUNC('MONTH', order_date)` from a dashboard query and `Order Month` from a KPI file are the same dimension
- **Prefer business names** from KPI/Genie sources over raw column names from schema inspection
- **Enrich synonyms** — if Genie sample questions reference a dimension by a different name, capture that as a synonym
- Note provenance: which source(s) contributed each dimension

### 4. Merge Measures

- Collect candidate measures from all sources
- **Deduplicate** by underlying aggregate expression — e.g., `SUM(amount)` found in a dashboard query and `Total Revenue: SUM(amount)` from a KPI file are the same measure
- **Prefer named/labeled measures** from KPI definitions over anonymous aggregations from queries
- **Capture synonyms** from Genie sample questions (e.g., users asking "total sales" → synonym for "Total Revenue")
- **Identify standardization opportunities** — the same aggregation appearing in multiple queries or dashboards is a strong candidate for a named measure
- Note provenance: which source(s) contributed each measure

### 5. Merge Global Filters

- Collect candidate filters from all sources (dashboard WHERE clauses, query WHERE clauses, schema analysis)
- **Intersect** common conditions — if most queries filter by `order_date > '2020-01-01'`, suggest this as a persistent metric view filter
- Flag any conflicting filters to the user (e.g., one query uses `status != 'CANCELLED'` while another includes cancelled orders)

### 6. Merge Comments & Descriptions

When multiple sources provide comments or descriptions for the same table or column, reconcile them using this priority order:

**For table-level comments (→ metric view `comment`):**
1. Genie space `description` + `title` — most user-facing and business-oriented
2. Unity Catalog table `comment` — authoritative, maintained by data engineers
3. Dashboard `display_name` — provides domain context
4. Catalog/schema `comment` — provides domain-level context
5. Inferred from column names/types — last resort

**For column-level comments (→ dimension/measure `comment`, `display_name`, `synonyms`):**
1. Genie space column descriptions — tuned for natural language understanding
2. Unity Catalog column comments — authoritative metadata from data engineers
3. KPI file descriptions/names — business-defined labels
4. Dashboard dataset column `displayName`/`description` — visualization-oriented labels
5. Inferred from column names — last resort

**Reconciliation rules:**
- **Use the most detailed description as `comment`** — pick the longest, most informative description from any source
- **Use shorter variants as `synonyms`** — if UC says "Total order amount in USD" and a KPI file calls it "Total Revenue" and Genie users ask about "total sales", the `comment` is the UC description, `display_name` is "Total Revenue", and `synonyms` include "total sales"
- **Flag true conflicts** — if two sources define semantically different meanings for the same column (e.g., UC says "amount before tax" but KPI says "amount including tax"), flag to the user and ask which is correct
- **Never discard metadata** — every description, label, and name from every source should end up in either `comment`, `display_name`, or `synonyms`

### 7. Cross-Source Enrichment

After merging, look for these enrichment opportunities:

| Source A | Source B | Enrichment |
|----------|----------|------------|
| Schema (raw columns) | KPIs (business names) | Map business names onto schema columns |
| Schema (raw columns) | Queries (aggregations) | Identify which columns are actually used and how |
| Dashboard (visualizations) | Schema (all columns) | Discover columns the dashboard doesn't use but could |
| Genie (sample questions) | Any measure/dimension | Add natural-language synonyms to improve discoverability |
| Queries (repeated patterns) | KPIs (defined measures) | Flag DRY opportunities — repeated ad-hoc aggregations that match a KPI |
| Dashboard (filters) | Schema (columns) | Identify high-value filter dimensions users actively slice by |
| UC column comments | Dimensions/measures | Use authoritative column descriptions as `comment` fields |
| UC table comments | Metric view top-level | Use table descriptions as metric view `comment` |
| Genie column descriptions | UC column comments | Prefer Genie descriptions (more user-friendly); use UC as fallback |
| Genie space title/description | Metric view naming | Inform metric view names and top-level comments |
| Dashboard title | Metric view grouping | Understand which metrics belong together by dashboard purpose |
| Dashboard dataset descriptions | Measure/dimension comments | Use dataset-level labels as `display_name` or `synonyms` |
| Dashboard parameters | Dimensions | Parameters are explicit user-facing filter axes → strong dimension candidates |
| Catalog/schema comments | Metric view top-level | Domain-level context for naming and `comment` fields |
| UC tags (table/column) | Governance + dimensions | Skip `pii` columns, use `domain` tags for naming, skip `deprecated` |
| Partition/clustering keys | Dimensions + filters | Physically organized columns are strong dimension/filter candidates |
| Genie join instructions | Metric view joins | Author-intended join paths → use directly as YAML `joins` |
| Genie SQL expressions | Dimension/measure expr | Canonical computed column definitions → use as `expr` values |
| Genie SQL query instructions | Measures + dimensions | Full analytical patterns → parse for aggregations, joins, filters |

### 8. Conflict Resolution

- If a KPI file defines `Total Revenue = SUM(price * quantity)` but a dashboard query uses `SUM(amount)`, **flag both to the user** and ask which expression is canonical
- If a Genie space uses different tables than the provided schema, include both table sets and note the discrepancy
- If a query file references tables not in the provided schema, inspect those tables too (they may be in a different schema)

## Common Analysis Patterns

### Identifying Good Dimensions

| Pattern | Example | Dimension Expression |
|---------|---------|---------------------|
| Direct categorical | `region` | `region` |
| **Code humanization** | `o_orderstatus` | `CASE WHEN o_orderstatus = 'O' THEN 'Open' WHEN o_orderstatus = 'F' THEN 'Fulfilled' WHEN o_orderstatus = 'P' THEN 'Processing' END` |
| Granular date | `order_date` | `order_date` (always include raw date) |
| Date truncation | `order_date` | `DATE_TRUNC('MONTH', order_date)` (include alongside granular) |
| CASE bucketing | `amount` | `CASE WHEN amount > 1000 THEN 'Large' ELSE 'Small' END` |
| Joined attribute | `customer.segment` | `customer.segment` (via join) |
| Extracted part | `full_date` | `EXTRACT(YEAR FROM full_date)` |

**Best practice:** Always standardize raw codes into business-friendly names. Never expose cryptic database values (like 'O', 'F', 'P') to end users.

### Identifying Good Measures

**Atomic measures** (define these first):

| Pattern | Example | Measure Expression |
|---------|---------|-------------------|
| Simple sum | Revenue | `SUM(amount)` |
| Count | Order count | `COUNT(1)` |
| Distinct count | Unique customers | `COUNT(DISTINCT customer_id)` |
| Average | Avg order value | `AVG(amount)` |
| Filtered | Open revenue | `SUM(amount) FILTER (WHERE status = 'OPEN')` |
| Filtered count | Fulfilled orders | `COUNT(1) FILTER (WHERE status = 'DONE')` |

**Composed measures** (reference atomic measures via `MEASURE()`):

| Pattern | Example | Measure Expression |
|---------|---------|-------------------|
| Ratio | Rev per customer | `MEASURE(\`Total Revenue\`) / MEASURE(\`Unique Customers\`)` |
| Rate | Fulfillment rate | `MEASURE(\`Fulfilled Orders\`) / MEASURE(\`Total Orders\`)` |
| AOV | Avg order value | `MEASURE(\`Total Revenue\`) / MEASURE(\`Order Count\`)` |

**Best practice:** Always define atomic measures first, then build complex measures using composability. This ensures ratios re-aggregate safely at any dimension grain.
