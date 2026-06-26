# Input Source Analysis Handlers

For each selected source the goal is the same: identify **tables, relationships, candidate dimensions, candidate measures, candidate global filters, and metadata** (comments/synonyms/display names). Below is what to pull from each source and *why* — fetch mechanics live in [cli-operations.md](cli-operations.md); use judgment to glue the rest. Then merge (see [Merging](#merging-multiple-input-sources)).

> **Metadata priority (applies everywhere):** existing descriptions are authoritative — never invent when one exists. Order: Genie column descriptions → UC column comments → KPI-file names → dashboard labels → inferred from names. Put the richest description in `comment`, a business label in `display_name`, and every other name/alias in `synonyms`. **Never discard metadata** — it all lands in one of those three fields (this is what makes the views Genie-friendly).

## Input 1: Gold schema (`catalog.schema`)

Dump it: `DESCRIBE CATALOG`/`DESCRIBE SCHEMA` for domain context, `databricks tables list <catalog> <schema>`, then `discover-schema` each table (columns, types, sample rows, null/row counts).

What to extract and why:
- **Fact vs dimension** tables (facts: numeric/date/`_id` columns, most rows; dims: descriptive columns, fewer rows, often `dim_*`).
- **Relationships** from `_id`/`_key` name matches; verify cardinality with a quick count query before trusting a join.
- **Candidate dimensions**: categorical columns (reasonable cardinality), date columns (include raw *and* `DATE_TRUNC`'d). Wrap nullable columns null-safe (`COALESCE(...)`); skip all-null columns.
- **Candidate measures**: numeric columns for `SUM`/`AVG`/`MIN`/`MAX`, `COUNT`/`COUNT(DISTINCT)`, and derived ratios.
- **Candidate global filters**: date cutoffs or status exclusions that scope most analysis.
- **Metadata to mine** (`DESCRIBE TABLE EXTENDED`, `DESCRIBE DETAIL`, `SHOW TBLPROPERTIES`, and the tag tables `system.information_schema.table_tags`/`column_tags` — skip silently if tags aren't accessible):
  - Table/column **comments** → `comment`/`display_name`/`synonyms` (start here, before inferring).
  - **Tags**: `pii` → don't expose as a dimension without approval; `deprecated` → skip; `domain` → naming/grouping.
  - **Partition/clustering keys** → strong dimension and `filter` candidates (data is physically organized by them).
  - **`refresh_frequency`/`schedule`** property → materialization hint (don't refresh faster than the source).
  - **PK/FK constraints with `RELY`** → note for join performance; **CHECK constraints** → reveal valid value sets for CASE humanization / bucketing.

## Input 2: AI/BI dashboard (ID or URL)

Dump it: `databricks lakeview get <id>` → parse `serialized_dashboard` (see [cli-operations.md](cli-operations.md), incl. the **empty-payload fallback** — empty ≠ no data).

What to extract and why:
- **Datasets** (`queryLines` → SQL): source tables (FROM/JOIN), aggregations (→ measures), GROUP BY (→ dimensions), WHERE (→ filters). `discover-schema` each source table.
- **Page titles** → how to group measures into separate views; **widget titles** (`spec.frame.title`) → measure naming; counter/stat widgets → single-value measures.
- **Parameters** (`parameters[]`) → **strong dimension candidates** (the axes users actively filter on); fixed value lists inform CASE expressions.
- Dataset/column `displayName`/`description` → `comment`/`display_name`.

## Input 3: Queries on gold tables (`.sql` file + `catalog.schema`)

Read the file (sample: [examples/sample_queries.sql](../examples/sample_queries.sql)); accept pasted SQL too. Get schema details as in Input 1.

What to extract and why:
- **SQL comments** (`--`, `/* */`) → naming context: a comment above a query → measure/dimension `comment`; inline column comments → `comment`/`display_name`; section headers → grouping.
- Per query: SELECT aggregations → measures, non-aggregated → dimensions, FROM/JOIN → tables, WHERE → filters, GROUP BY → confirm dimensions.
- **Cross-reference**: repeated aggregations across queries = DRY/standardization opportunities; common WHERE clauses = candidate global filters.

## Input 4: Genie space (Space ID)

Dump it: `databricks api get ".../genie/spaces/<id>?include_serialized_space=true"` → file → parse `serialized_space` (see [cli-operations.md](cli-operations.md) for the required param + nested-list gotchas). Understand how the space is used and which tables/queries it relies on, then pick the metrics from that.

What to extract and why:
- `title`/`description` → domain context, naming, comments.
- `data_sources.tables[]` (incl. per-column `description`/`synonyms` — prefer these over UC comments, they're tuned for NL) and any existing `data_sources.metric_views`.
- **Instructions — four types, all high-value:** `join_instructions` → use directly as YAML `joins` (author-intended paths, beat inferred FKs); `sql_instructions` → dimension/measure `expr`; `sql_query_instructions` → parse like Input 3; `text_instructions` → business rules/context.
- **Benchmark questions + their SQL answers** → what users ask (measures) and how they slice (dimensions); parse the SQL like Input 3 — these are curated, canonical patterns.

## Input 5: KPIs, measures & dimensions (`.csv`/`.yaml` file + `catalog.schema`)

Read the file (samples: [examples/sample_kpis.csv](../examples/sample_kpis.csv), [examples/sample_kpis.yaml](../examples/sample_kpis.yaml)); `definition`/`description` optional. Get schema details as in Input 1.

What to extract and why:
- Map each KPI to schema columns + aggregation type; if `definition` is omitted, infer the expr from the name. Use `description` directly as `comment`.
- **Validate** mappings with a quick `GROUP BY` test query.
- **Gaps**: KPIs needing joins to not-yet-identified dim tables, CASE/FILTER, or date bucketing.
- **Suggest complements** the user didn't list (e.g. "Total Revenue" → "Revenue per Customer"; filtered/time-based variants).

## Merging multiple input sources

Run each applicable handler, then merge:
- **Tables**: union, dedup by FQ name, record provenance.
- **Relationships**: combine join paths; prefer a join validated by a running query over inferred FK matching.
- **Dimensions/measures**: dedup by underlying *expression* (`DATE_TRUNC('MONTH', order_date)` from a dashboard == "Order Month" from a KPI file); prefer business names from KPI/Genie over raw column names; capture alternate names (esp. Genie questions) as synonyms; flag the same ad-hoc aggregation recurring across sources as a standardization win.
- **Global filters**: intersect common conditions; flag conflicts (one query excludes cancelled orders, another includes them).
- **Comments/metadata**: reconcile per the priority box at the top; richest → `comment`, business label → `display_name`, rest → `synonyms`. Flag *semantic* conflicts (UC "amount before tax" vs KPI "including tax") to the user.
- **Cross-source enrichment**: use one source to fill another — schema columns ⨯ KPI names (map business names on), dashboard/Genie filters ⨯ schema (high-value filter dimensions), Genie questions ⨯ any field (NL synonyms), repeated query patterns ⨯ KPIs (DRY).

## Common analysis patterns

**Good dimensions** — always humanize raw codes (never expose `'O'`/`'F'`/`'P'`); include raw date *and* a `DATE_TRUNC`'d version:

| Pattern | Expression |
|---|---|
| Direct categorical | `region` |
| Code humanization | `CASE WHEN o_orderstatus = 'O' THEN 'Open' WHEN 'F' THEN 'Fulfilled' ... END` |
| Date (raw + truncated) | `order_date`, `DATE_TRUNC('MONTH', order_date)` |
| Bucketing | `CASE WHEN amount > 1000 THEN 'Large' ELSE 'Small' END` |
| Joined / extracted | `customer.segment`, `EXTRACT(YEAR FROM full_date)` |

**Good measures** — define **atomic** measures first, then compose:

| Atomic | Composed (via `MEASURE()`) |
|---|---|
| `SUM(amount)`, `COUNT(1)`, `COUNT(DISTINCT customer_id)`, `AVG(amount)` | Ratio: `MEASURE(\`Total Revenue\`) / MEASURE(\`Unique Customers\`)` |
| Filtered: `SUM(amount) FILTER (WHERE status = 'OPEN')` | Rate: `MEASURE(\`Fulfilled Orders\`) / MEASURE(\`Total Orders\`)` |

Composing on atomic measures keeps ratios re-aggregating safely at any dimension grain.
