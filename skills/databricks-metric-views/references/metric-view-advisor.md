# Metric View Advisor — multi-source build workflow

Create Unity Catalog metric views from existing Databricks assets — gold/fact
schemas, AI/BI dashboards, SQL queries, Genie Agents, or KPI files. This workflow
analyzes those sources, synthesizes them into richer, deduplicated suggestions,
checks for overlap with views that already exist, and walks deployment end to end.

Use this reference when the user wants a guided, multi-source build (intent like
"formalize our KPIs," "build a metric/semantic layer," "define measures and
dimensions from our tables," "standardize aggregations so other teams can reuse
them," or "turn our ad-hoc queries into reusable metrics"). Do **not** use it for
querying or altering an already-existing metric view, comparing metric-view
frameworks, creating regular UC tables/schemas, or MLflow/model tracking.

> **The metric-view *spec* lives in [`create-patterns.md`](create-patterns.md)** — patterns, YAML field reference, formatting gotchas, deployment errors, and the Genie Design Rules. **Read it first.** This file owns the *advisor workflow*: the multi-source build flow, its interactive steps, and the **execution mechanics that flow needs** (CLI & API operations, the deploy step). The spec is not restated here.

## Prerequisites & tooling

1. A working **Databricks CLI (>= v1.0.0)** authenticated to a workspace profile. All operations run through the CLI; the commands and fetch/parse details are in [CLI & API operations](#cli--api-operations) below. Auth, profiles, and warehouse selection are covered by the **`databricks-core`** skill.

> **If the host agent has native asset readers** (a `readAssetById`-style tool), it may use them — but **verify the result is non-empty** and fall back to the CLI fetches below if it isn't.

## How this advisor works

This advisor is **information-driven, not a fixed interview.** The steps below
describe *what* to produce and the order that makes sense — but you decide, from
context, how to get there. Do not march through a scripted list of questions or
stop after every micro-step.

**Operating principles:**
- **Gather, don't interrogate.** Read the user's request first. If they already named a profile, sources, identifiers, or a target schema, use them — don't re-ask. Batch any genuinely-missing inputs into a single, clear request rather than one question at a time.
- **Decide with judgment.** When you have enough to take the next useful action, take it. When something is ambiguous or missing, ask. When it is discoverable (schemas, existing views, warehouse), fetch it instead of asking.
- **Checkpoint where it matters.** Pause for the user before consequential or hard-to-undo actions — creating a schema, deploying, and replacing/dropping an existing view — and whenever they asked to review first. You don't need to pause after routine analysis or read-only discovery.
- **Be transparent.** Summarize what you found and what you're about to do, so the user can redirect.

### Information this advisor needs (and why)

Read what you can from the user's message. If mandatory items below are missing, ask for all of them in a **single prompt**.

| Information | Mandatory? | How to obtain it |
|---|---|---|
| **Workspace / CLI profile** | Yes — never auto-select | List with `databricks auth profiles` (show workspace URLs) and let the user choose — even if only one exists. Validate with `databricks auth describe --profile <PROFILE>`; if stale, re-auth with `databricks auth login --profile <PROFILE>`. |
| **Input source(s)** | Yes — ask if missing | Use whatever the user provides. See input-source table below. |
| **Source identifiers** | Yes — follow up once source type is known | Sources 3 and 5 also need a `catalog.schema` if source 1 wasn't given; if several sources share one schema, resolve it once. |
| **Target `catalog.schema`** | Yes — ask if not given; may differ from the source | Validate with `SHOW SCHEMAS IN <catalog> LIKE '<schema>'`. If missing, ask whether to create it (`CREATE SCHEMA IF NOT EXISTS` — a checkpoint) or use a different target. |
| **SQL warehouse** | No — auto-discover | `databricks experimental aitools tools get-default-warehouse --profile <PROFILE>`. `query`/`discover-schema` auto-pick it; capture the id explicitly for deploys — the Statement Execution API needs it as `warehouse_id` in the payload. Honor any warehouse the user names. |
| **Review preference** | No — default to review-first | **Review-first:** save `suggestions.yaml`, show suggestions, and confirm before generating definitions; checkpoint at the consequential steps. The user can opt into **auto-create**: still save `suggestions.yaml`, but go through suggestions → definitions → deploy without per-step approval. Still ask about materialization (it changes the definition) and about any 40–69% overlap, and still confirm before deploying. The user can also ask not to save SQL files (Steps 4 and 6). |

**Input sources** (combine any):

| # | Input Source | Locator needed | Needs a `catalog.schema`? |
|---|-------------|---------------|-----------------|
| 1 | **Gold schema** | `catalog.schema` | — (is a schema) |
| 2 | **AI/BI dashboard** | Dashboard ID or URL | No |
| 3 | **Queries on gold tables** | `.sql` file path | Yes |
| 4 | **Genie Agent** | Space ID | No |
| 5 | **KPIs, Measures & Dimensions** | `.csv`/`.yaml` file path | Yes |

## CLI & API operations

> **No `databricks sql execute` / `execute-statement`** — those commands don't exist. The `databricks experimental aitools tools` commands are **experimental** and their surface can shift between CLI versions — confirm a subcommand with `databricks experimental aitools tools --help` before relying on it.
>
> **Do NOT deploy metric-view DDL through `aitools tools query` or `aitools tools statement submit`.** Both flatten the leading indentation of the `$$…$$` YAML body in transit, so the server rejects a valid definition with `METRIC_VIEW_INVALID_VIEW_DEFINITION` — *"Failed to parse YAML: Missing required creator property 'expr'"* or *"expected `<block end>`, but found `'-'`"*. This bites the canonical example too. Deploy metric views through the stable **Statement Execution API** (`databricks api post /api/2.0/sql/statements/` — note: **no** `/execute` suffix), which sends the body verbatim. Verified 2026-08 on CLI v1.12.1. The `aitools` tools remain correct for the short read statements below and `discover-schema`.

**Running SQL:**
- **Short statements** (`SHOW`/`DESCRIBE`/`SELECT`/`DROP`): `databricks experimental aitools tools query "<SQL>" --profile <PROFILE>` (auto-picks the default warehouse).
- **Deploy metric-view DDL** (`CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$...$$`): write it to a `.sql` file, then JSON-encode the file into the API payload with `jq -Rs` — this preserves the YAML indentation exactly and sidesteps the heredoc/JSON-escaping traps of hand-editing `$$`-quoted YAML:
  ```bash
  # view.sql holds the full CREATE OR REPLACE VIEW ... $$ ... $$ statement
  jq -Rs --arg wh "<WAREHOUSE_ID>" '{warehouse_id: $wh, statement: ., wait_timeout: "30s"}' view.sql > /tmp/mv_payload.json
  databricks api post /api/2.0/sql/statements/ --json @/tmp/mv_payload.json --profile <PROFILE>
  # if the response state is PENDING, poll until terminal:
  # databricks api get /api/2.0/sql/statements/<statement_id> --profile <PROFILE>
  ```
- **Inspect a table**: `databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <PROFILE>` (one call → columns, types, sample rows, null/row counts).

**Metric views (no dedicated CLI verb — operate via SQL):**
- **Get definition**: `DESCRIBE TABLE EXTENDED <full_name> AS JSON` → returns the YAML definition + per-column `is_measure` flags.
- **List in a schema**: see Step 1 below (metric views do **not** show in `SHOW VIEWS`).
- **Grant** (least privilege): `GRANT SELECT ON VIEW <full_name> TO <principal>`.

**Fetch an AI/BI dashboard:**
`databricks lakeview get <dashboard_id> --profile <PROFILE>` → the **draft** `serialized_dashboard` (a JSON string). Parse `datasets` as a **list**; each dataset's SQL is `queryLines` (a list of strings — join with newlines).

> Don't use `/api/2.0/sql/dashboards/<id>` (404). **If `datasets`/`pages` come back empty** — common with a native published-asset reader or v3-editor dashboards — that's a fetch-method artifact, not an empty dashboard. Try in order: `lakeview get` (draft) → `lakeview get-published <id>` → fall back to Input 3 (ask for the widget SQL as a `.sql` file).

**Fetch a Genie Agent:**
Save to a file first, then parse — the payload is large, and piping it into inline Python makes `json.load(sys.stdin)` read an empty stream:

```bash
databricks genie get-space <space_id> --include-serialized-space --profile <PROFILE> -o json > /tmp/genie.json
```

Parse `serialized_space` (a JSON string). **Non-obvious gotcha — several fields are nested lists of strings, not plain strings**: `instructions.text_instructions[]`, `join_instructions`, `sql_instructions`; and `benchmarks.questions[]` has `.question` as a 1-element list and `.answer[].content` as a list of strings. Use `isinstance()` checks and join. `data_sources.tables[].identifier` is the fully-qualified table name.

## Workflow

### Step 1 — Discover existing metric views (do this FIRST, always)

Do this **before analyzing any source table or generating suggestions** — even when the user points you directly at a table ("analyze table X") or names the source. Naming a source does **not** remove this step. Once the target schema is known, **automatically** check what metric views already exist there — it is read-only discovery, and it prevents duplicate/overlapping views accumulating across runs.

1. **List existing metric views**: they have `table_type` `METRIC_VIEW` (they don't show in `SHOW VIEWS`). List the schema with the Unity Catalog API, which is fast even on a large catalog where `information_schema.tables` can take minutes. `--include-browse` also lists views you can see but not query:

```bash
databricks tables list <target_catalog> <target_schema> --include-browse --omit-columns --omit-properties --profile <PROFILE> -o json \
  | jq -r '.[] | select(.table_type == "METRIC_VIEW") | "\(.full_name)\tbrowse_only=\(.browse_only // false)"'
```

2. **If none exist** (empty result, the CLI reports that the schema does not exist, or you just created it) → note "fresh schema, nothing to overlap-check" and move on. Any other error (permissions, expired auth) means the check didn't run: report it instead of treating the schema as fresh.
3. **If some exist**, fetch each definition with `DESCRIBE TABLE EXTENDED <full_name> AS JSON`, backtick-quoting any name part with special characters (see [CLI & API operations](#cli--api-operations)) and extract a **structural fingerprint**: source table (fully qualified), dimensions `(name, expr)`, measures `(name, expr)`, joined tables. If describe fails for any view (for example a `browse_only=true` view you can't query), list it as not checked rather than skipping it silently. Keep this inventory for the [overlap check](overlap-check.md) in Step 3.
4. **Briefly summarize** what's already there (a short table of view / source / dim count / measure count) so the user has context, then continue.

### Step 2 — Analyze the inputs

For **each** selected input source, run its handler below, then **merge** findings into a single combined analysis.

> **Metadata priority (applies everywhere):** existing descriptions are authoritative — never invent when one exists. Order: Genie column descriptions → UC column comments → KPI-file names → dashboard labels → inferred from names. Put the richest description in `comment` (DBR 17.2+), a business label in `display_name` (DBR 17.3+, max 255 chars), and every other name/alias in `synonyms` (DBR 17.3+, up to 10). **Never discard metadata** — it all lands in one of those three fields. Adding `synonyms` is the highest-impact thing you can do for Genie quality. When saving a v1.1 metric view, single-line YAML comments (`#`) are removed — put meaningful content in `comment` fields, not YAML comments. **Completeness is mandatory: every dimension and measure MUST end with a non-empty `comment` and `display_name`** — when nothing described it, infer a concise business-friendly value from the name; do not leave them blank (`synonyms` may be omitted only when there are no genuine alternates).

**Input 1: Gold schema (`catalog.schema`)**

Dump it: `DESCRIBE CATALOG`/`DESCRIBE SCHEMA` for domain context, `databricks tables list <catalog> <schema>`, then `discover-schema` each table.

What to extract and why:
- **Fact vs dimension** tables (facts: numeric/date/`_id` columns, most rows; dims: descriptive columns, fewer rows, often `dim_*`).
- **Relationships** from `_id`/`_key` name matches; verify cardinality with a quick count query before trusting a join.
- **Candidate dimensions**: categorical columns (reasonable cardinality), date columns (include raw *and* `DATE_TRUNC`'d). Wrap nullable columns null-safe (`COALESCE(...)`); skip all-null columns.
- **Candidate measures**: numeric columns for `SUM`/`AVG`/`MIN`/`MAX`, `COUNT`/`COUNT(DISTINCT)`, and derived ratios.
- **Candidate global filters**: date cutoffs or status exclusions that scope most analysis.
- **Metadata to mine** (`DESCRIBE TABLE EXTENDED`, `DESCRIBE DETAIL`, `SHOW TBLPROPERTIES`, and the tag tables `system.information_schema.table_tags`/`column_tags` filtered to the table's catalog, schema and name; skip silently if tags aren't accessible):
  - Table/column **comments** → `comment`/`display_name`/`synonyms` (start here, before inferring).
  - **Tags**: `pii` → don't expose in a dimension or measure without approval; `deprecated` → skip; `domain` → naming/grouping.
  - **Partition/clustering keys** → strong dimension and `filter` candidates (data is physically organized by them).
  - **`refresh_frequency`/`schedule`** property → materialization hint (don't refresh faster than the source).
  - **PK/FK constraints with `RELY`** → note for join performance; **CHECK constraints** → reveal valid value sets for CASE humanization / bucketing.

**Input 2: AI/BI dashboard (ID or URL)**

Dump it per [CLI & API operations](#cli--api-operations), incl. the **empty-payload fallback** — empty ≠ no data.

What to extract and why:
- **Datasets** (`queryLines` → SQL): source tables (FROM/JOIN), aggregations (→ measures), GROUP BY (→ dimensions), WHERE (→ filters). `discover-schema` each source table.
- **Page titles** → how to group measures into separate views; **widget titles** (`spec.frame.title`) → measure naming; counter/stat widgets → single-value measures.
- **Parameters** (`parameters[]`) → **strong dimension candidates** (the axes users actively filter on); fixed value lists inform CASE expressions.
- Dataset/column `displayName`/`description` → `comment`/`display_name`.

**Input 3: Queries on gold tables (`.sql` file + `catalog.schema`)**

Read the user-provided `.sql` file (accept pasted SQL too). Get schema details as in Input 1.

What to extract and why:
- **SQL comments** (`--`, `/* */`) → naming context: a comment above a query → measure/dimension `comment`; inline column comments → `comment`/`display_name`; section headers → grouping.
- Per query: SELECT aggregations → measures, non-aggregated → dimensions, FROM/JOIN → tables, WHERE → filters, GROUP BY → confirm dimensions.
- **Cross-reference**: repeated aggregations across queries = DRY/standardization opportunities; common WHERE clauses = candidate global filters.

**Input 4: Genie Agent (Space ID)**

Dump it: fetch and parse the space per [CLI & API operations](#cli--api-operations), minding the nested-list gotchas. Understand how the space is used and which tables/queries it relies on, then pick the metrics from that.

What to extract and why:
- `title`/`description` → domain context, naming, comments.
- `data_sources.tables[]` (incl. per-column `description`/`synonyms` — prefer these over UC comments, they're tuned for NL) and any existing `data_sources.metric_views`.
- **Instructions — four types, all high-value:** `join_instructions` → use directly as YAML `joins` (author-intended paths, beat inferred FKs); `sql_instructions` → dimension/measure `expr`; `sql_query_instructions` → parse like Input 3; `text_instructions` → business rules/context.
- **Benchmark questions + their SQL answers** → what users ask (measures) and how they slice (dimensions); parse the SQL like Input 3 — these are curated, canonical patterns.

**Input 5: KPIs, measures & dimensions (`.csv`/`.yaml` file + `catalog.schema`)**

Read the user-provided `.csv`/`.yaml` file — a row/entry per KPI with a name and an aggregation `expr`; `definition`/`description` optional. Get schema details as in Input 1.

What to extract and why:
- Map each KPI to schema columns + aggregation type; if `definition` is omitted, infer the expr from the name. Use `description` directly as `comment`.
- **Validate** mappings with a quick `GROUP BY` test query.
- **Gaps**: KPIs needing joins to not-yet-identified dim tables, CASE/FILTER, or date bucketing.
- **Suggest complements** the user didn't list (e.g. "Total Revenue" → "Revenue per Customer"; filtered/time-based variants).

**Merging multiple input sources**

Merge the handlers' findings:
- **Tables**: union, dedup by FQ name, record provenance.
- **Relationships**: combine join paths; prefer a join validated by a running query over inferred FK matching.
- **Dimensions/measures**: dedup by underlying *expression* (`DATE_TRUNC('MONTH', order_date)` from a dashboard == "Order Month" from a KPI file); prefer business names from KPI/Genie over raw column names; flag the same ad-hoc aggregation recurring across sources as a standardization win.
- **Global filters**: intersect common conditions; flag conflicts (one query excludes cancelled orders, another includes them).
- **Comments/metadata**: reconcile per the priority box above. Flag *semantic* conflicts (UC "amount before tax" vs KPI "including tax") to the user.
- **Cross-source enrichment**: use one source to fill another — schema columns ⨯ KPI names (map business names on), dashboard/Genie filters ⨯ schema (high-value filter dimensions), Genie questions ⨯ any field (NL synonyms), repeated query patterns ⨯ KPIs (DRY).

**Common analysis patterns**

**Good dimensions** — always humanize raw codes (never expose `'O'`/`'F'`/`'P'`):

| Pattern | Expression |
|---|---|
| Direct categorical | `region` |
| Code humanization | `CASE WHEN o_orderstatus = 'O' THEN 'Open' WHEN o_orderstatus = 'F' THEN 'Fulfilled' ... END` (repeat the column in every branch) |
| Date (raw + truncated) | `order_date`, `DATE_TRUNC('MONTH', order_date)` |
| Bucketing | `CASE WHEN amount > 1000 THEN 'Large' ELSE 'Small' END` |
| Joined / extracted | `customer.segment`, `EXTRACT(YEAR FROM full_date)` |

**Good measures** — define **atomic** measures first, then compose:

| Atomic | Composed (via `MEASURE()`) |
|---|---|
| `SUM(amount)`, `COUNT(1)`, `COUNT(DISTINCT customer_id)`, `AVG(amount)` | Ratio: `MEASURE(\`Total Revenue\`) / MEASURE(\`Unique Customers\`)` |
| Filtered: `SUM(amount) FILTER (WHERE status = 'OPEN')` | Rate: `MEASURE(\`Fulfilled Orders\`) / MEASURE(\`Total Orders\`)` |

Present the merged inventory to the user in a summary table: source tables (columns, types, row counts, comments), fact vs dimension classification, join paths, candidate dimensions, measures and global filters, the metadata inventory, and cross-source insights. If multiple sources contributed to the same dimension or measure, note the provenance (e.g., "Region — from schema column + dashboard filter + Genie sample question"). Analysis is read-only — share the summary and continue to suggestions.

### Step 3 — Suggest metric views

Based on your analysis, suggest metric views that would provide value. This step has four parts, in order: (1) check for overlap with existing metric views, (2) build suggestions from all gathered metadata, (3) run a gap analysis, and (4) save + present `suggestions.yaml` and handle the user's response.

#### Pre-suggestion: check for overlap with existing metric views

If Step 1 found existing metric views, you MUST run the [overlap check](overlap-check.md) before building suggestions: it scores each candidate against them and resolves each overlap per the review preference.

#### Genie Design Rules

Structure every suggestion by the [Genie Design Rules](create-patterns.md#genie-design-rules): one fact source per metric view, a base view only for multi-fact or nested KPIs, prefer one metric view per KPI group, organized by domain.

#### Building suggestions from your analysis — use ALL gathered metadata

Every suggestion must be a holistic synthesis of what you learned across ALL input sources — not just column names and types. For each metric view you suggest, apply this checklist:

**1. Metric view naming and `comment`:**
- Use Genie Agent `title`/`description` and dashboard title to name the metric view in a business-friendly way (e.g., "wholesale_supplier_order_metrics" not "orders_mv")
- Use catalog/schema comments and table comments to write a rich top-level `comment` describing the metric view's business purpose
- If Genie text instructions describe the domain, incorporate that context

**2. For each dimension — assemble from all sources:**
- **`expr`**: Prefer Genie SQL expression instructions (canonical computed columns) > dashboard query expressions > KPI definitions > raw column references.
- **`comment`/`display_name`/`synonyms` (MUST)**: fill per the [Step 2 metadata-priority rule](#step-2--analyze-the-inputs), including its completeness rule.
- **Null safety**: if the column is nullable (from schema stats), wrap in COALESCE or CASE.
- **PII check**: if UC tags include `pii:true`, flag and exclude unless the user approves.

**3. For each measure — assemble from all sources:**
- **`expr`**: Prefer Genie SQL expression instructions > dashboard query aggregations > KPI definitions > SQL file patterns. The same aggregation across multiple sources is a strong signal it's the canonical expression.
- **`comment`/`display_name`/`synonyms` (MUST)**: as for dimensions; include units in `comment` (e.g. "in USD").
- **PII check**: as for dimensions.
- **Composed measures**: for every pair of atomic measures where a ratio makes business sense (revenue/customers, fulfilled/total), suggest a composed measure; reuse ratios already computed in SQL files, dashboards, or KPI definitions.
- **Filtered measures**: for every status/category dimension, suggest filtered variants of key measures (e.g. status 'Open'/'Fulfilled'/'Processing' → `Open Revenue`, `Fulfilled Orders`).

**4. Joins — assemble from all sources:**
- Prefer Genie join instructions (author-intended) > dashboard query JOINs > FK constraints > inferred from column name matching
- Include ALL dimension tables that enrich the fact table — even if not all input sources used them
- Prefer declarative joins; use a SQL-query `source` only when joins can't be expressed declaratively — see [Pattern 9](create-patterns.md#pattern-9-sql-query-as-source)

**5. Filters — assemble from all sources:**
- Intersect common WHERE clauses from dashboard queries, SQL files, Genie SQL query instructions, and Genie text instructions
- Check table properties for data freshness hints

**6. Gap analysis — what's missing:**
After building suggestions from existing sources, identify what's NOT yet covered:
- **Unused schema columns**: Columns no input source referenced — are any valuable dimensions or measures?
- **Missing time dimensions**: If the source has date columns, ensure granular + truncated time dimensions exist (Date, Month, Quarter, Year)
- **Missing ratio or filtered measures**: any that checklist item 3 (measures) calls for but the suggestions don't have yet
- **Cross-table measures**: If dimension tables exist, are there measures that should use joined columns?
- **Genie gaps**: If Genie benchmark questions ask about something not yet covered, add it
- **Not a metric-view gap — needs a function**: if a requested measure fails the additivity / single-pass test (non-additive at the queried grain, selection-dependent, iterative, or bundle-output), it is **not** a metric view to add — route it to a governed UC SQL function ([governed-functions.md](governed-functions.md))

**Window measures:** only suggest when the user specifically asks — see [Pattern 8](create-patterns.md#pattern-8-window-measures) for the syntax.

#### Suggestion format

Generate suggestions as a YAML file with this structure. Dimensions and measures follow the same field spec as in [`create-patterns.md` §YAML Field Reference](create-patterns.md#yaml-field-reference) — apply [Pattern 3B](create-patterns.md#pattern-3-ratios-and-composability) (atomic measures first, then composed).

```yaml
# Metric View Suggestions
# Edit this file, then provide the path back to the advisor to proceed.
# Source schema: <source catalog.schema>
# Target schema: <target catalog.schema>

metric_views:
  - name: <metric_view_name>
    source_table: <fact_table>           # becomes `source:` in the CREATE DDL
    rationale: "<why this metric view is useful>"
    filter: "<optional global filter>"
    joins:
      - name: <alias>
        source: <catalog.schema.dim_table>
        'on': "source.<fk> = <alias>.<pk>"
    dimensions:
      - name: <Display Name>
        expr: "<sql_expression>"
        comment: "<description>"
        synonyms: ["alt name 1", "alt name 2"]
    measures:
      - name: <Atomic Measure>
        expr: "<aggregate_expression>"
        comment: "<description>"
        synonyms: ["alt name 1", "alt name 2"]
      - name: <Composed Measure>
        expr: "MEASURE(`<Atomic Measure 1>`) / MEASURE(`<Atomic Measure 2>`)"

# Gap Analysis — additional coverage opportunities
gaps:
  - type: unused_column
    table: <table>
    column: <column>
    suggestion: "<why this column could be a useful dimension or measure>"
  - type: missing_ratio
    numerator: "<measure 1>"
    denominator: "<measure 2>"
    suggestion: "<business meaning of this ratio>"
  - type: genie_gap
    question: "<Genie benchmark question not covered by current suggestions>"
    suggestion: "<what dimension or measure would answer this>"
```

#### Output folder structure

Each run creates a timestamped subfolder to preserve previous runs:

```
<target_schema>_output_metric_views/
├── run_20260403_143022/       # previous run (preserved)
├── run_20260403_161500/       # current run
│   ├── suggestions.yaml
│   ├── order_metrics.sql
│   └── ...
└── latest.txt                 # name of the most recent run folder
```

**At the start of each run** (when you first need to save a file): generate a timestamp `run_<YYYYMMDD_HHMMSS>`, create `<target_schema>_output_metric_views/run_<timestamp>/`. After saving, write the current run folder name into `<target_schema>_output_metric_views/latest.txt` (a single line, e.g. `run_20260403_161500`). All paths shown to the user reference the full `run_<timestamp>/` folder.

> **Use `latest.txt`, not a `latest` symlink** (symlinks don't resolve in the Databricks Workspace filesystem where Genie Code runs). To find the newest run, read `latest.txt`; as a fallback, pick the lexicographically-largest `run_*` folder (timestamps sort chronologically).

#### What to do with the suggestions — always do all three

1. **Display the coverage summary** — Before listing individual suggestions, show how well the suggestions cover the discovered data (tables, dimensions, measures, joins, Genie questions), plus a gaps table.
2. **Display each suggested metric view** — show name, rationale, source table, dimensions, and measures in a readable summary, with provenance for `comment`/`display_name`/`synonyms`.
3. **Save the suggestions file** — write the full YAML (including the `gaps` section) to `<target_schema>_output_metric_views/run_<timestamp>/suggestions.yaml`.

After displaying and saving, tell the user:

> "I've saved the suggestions to `<path>/suggestions.yaml`.
>
> | # | Option |
> |---|--------|
> | 1 | **Approve as-is** — I'll create the metric views now |
> | 2 | **Add gaps** — tell me which gap numbers to include (e.g., `add 2, 3`) and I'll update the suggestions |
> | 3 | **Edit the file** — modify `suggestions.yaml`, then tell me to proceed and I'll read the updated file |
> | 4 | **Provide a different file** — give me a path to your own suggestions YAML and I'll use that instead |"

**Checkpoint (review-first):** wait for the user to confirm or provide an updated file before generating definitions. On option 1, go to Step 4. On option 2, add the gaps the user named, re-display the coverage summary, save the updated YAML, and ask again. On 3, re-read `suggestions.yaml` from the run folder, and on 4 read the given file as the suggestions YAML, then go to Step 4.

### Step 4 — Create metric view definitions

For each approved metric view, generate the full YAML definition using [`create-patterns.md`](create-patterns.md), save it, and present it to the user.

**Naming:** name each metric view `<subject>_metrics` (e.g. `orders_metrics`, `finance_revenue_metrics`). Do **not** use `_mv` or other ad-hoc suffixes. See the `{subdomain}_{kpi-group}` guidance in the [Genie Design Rules](create-patterns.md#genie-design-rules).

**Always save SQL files locally** (unless the user opted out — see the [Review preference](#information-this-advisor-needs-and-why) row):
- Save into the **same timestamped run folder** created in Step 3.
- Save each metric view definition as `<metric_view_name>.sql`, and also an `all_metric_views.sql` combining all definitions.
- Inform the user of the saved folder and file paths.

**⛔ Review gate — review the definition before materialization/deploy.** This is the **content review**: present the full YAML block for each definition as a fenced ` ```yaml ` block, explain each dimension and measure in plain language, and wait for explicit approval. Do not proceed to Step 5/6 until the user confirms. In auto-create mode, still show the definitions — skip the approval wait.

### Step 5 — Materialization (optional — decide before deploy)

Materialization is part of the YAML definition, so it must be settled before deploying. **Default to no materialization** — it requires serverless compute and incurs Lakeflow Declarative Pipelines charges, so don't ask about it on every view. **Only raise materialization when the view is a genuine candidate:** a large source table, a view that will be queried frequently, many joins, or the user explicitly wants pre-computed fast results. When it *is* a candidate, offer it plainly:

> "This view looks like a materialization candidate (<reason: large source / frequently queried / many joins>). Would you like to add **materialization** to pre-compute aggregations for faster queries? It requires serverless compute and incurs Lakeflow Declarative Pipelines charges. (Default: no materialization.)"

If it isn't a candidate or they decline, go to Step 6 with no materialization block. If they want it, configure it — gather these together and ask only for whatever they don't specify, rather than one prompt per item:
- **Which views** to materialize (one, several, or all).
- **Type** per view — Aggregated (pick dimension/measure combos), Unaggregated (full data model), or Both. For Aggregated/Both, suggest the most likely dimension/measure combinations based on what appeared most across input sources.
- **Refresh schedule** — e.g. `every 1 hour` / `every 6 hours` / `every 24 hours` / custom. If table properties revealed a `refresh_frequency`, note that a faster schedule won't yield fresher data.

Then **update definitions** with the `materialization:` block — see [Pattern 7](create-patterns.md#pattern-7-materialized-metric-view) and [Materialization field reference](create-patterns.md#materialization) in `create-patterns.md`. Update the saved SQL files and re-display the final YAML.

### Step 6 — Deploy

Ask the user if they want to deploy:

> | # | Option |
> |---|--------|
> | 1 | **Deploy now** — I'll create the metric views (includes materialization if configured) |
> | 2 | **Source-controlled** — commit the saved SQL and deploy it through a bundle-managed SQL job (DABs), so the definition is version-controlled and re-deployable. See [SKILL.md § Source-controlled deployment](../SKILL.md#source-controlled-deployment-with-declarative-automation-bundles) and the [`databricks-dabs`](../../databricks-dabs/SKILL.md) skill for the bundle layout. |
> | 3 | **Review only** — you already have the SQL files; you'll deploy manually later |

For option 2, use the saved `.sql` file as the bundle SQL job's source (don't hand-inline the DDL).

**⛔ Pre-deploy checklist — do NOT run the deploy command until every box is true.** This is a hard stop, not a formality; if any item is unmet, go back — do not deploy:

1. **Definition reviewed & approved** at the [Step 4 review gate](#step-4--create-metric-view-definitions). If Step 5 materialization (or any edit) changed the definition after that approval, re-show the YAML and get a fresh yes. Silence, "validate it," or an earlier "go ahead build one" is **not** approval — confirm for the definition you're about to deploy.
2. **Every dimension and every measure has a non-empty `comment` and `display_name`** ([Step 2](#step-2--analyze-the-inputs)). Fill any blank first.
3. **Materialization decided** per [Step 5](#step-5--materialization-optional--decide-before-deploy): none by default, offered and configured only for a genuine candidate or on request.
4. You are deploying via the **Statement Execution API**, not the `aitools` path.

Deploy each metric view from its saved `<metric_view_name>.sql` file (written in Step 4) with the **Statement Execution API** command in [CLI & API operations](#cli--api-operations); if the response `state` is `PENDING`, poll until terminal. If the user opted out of saving SQL files (Step 4), write the statement to a temporary `.sql` file first. If the user chose "Replace" for any overlap in Step 3, drop the old view after deploying the new one (`DROP VIEW IF EXISTS <old_view>`).

After creation, verify each metric view with a test query (one dimension + one measure, `LIMIT 5`). For deployment error codes and authoring-time gotchas, see [`create-patterns.md` §Deployment Errors](create-patterns.md#deployment-errors) and [`create-patterns.md` §Common Issues](create-patterns.md#common-issues).

If materialization was configured, also tell the user how to trigger a manual refresh (`REFRESH MATERIALIZED VIEW <name>`), check status (`DESCRIBE EXTENDED <name>`), and verify query rewrite (`EXPLAIN EXTENDED <query>` — look for `__materialization_mat___metric_view`). Report the deployment results. If anything failed, help fix it before moving on.

### Step 7 — Show sample queries

For query syntax rules (`MEASURE()`, `GROUP BY ALL`, filtering, window measures, Rules 1–3), see [`query-patterns.md`](query-patterns.md).

For each created metric view, generate 3–5 sample queries demonstrating: basic aggregation (one dim, two measures); multi-dimension slice; filtered query; time trend (if a date dimension exists); Top-N (`ORDER BY measure DESC LIMIT 10`). Backtick-quote names with spaces, use `GROUP BY ALL`, alias each `MEASURE()` call.

**Execute each sample query** to verify it works and show the results. **Save** each metric view's queries as `<metric_view_name>_sample_queries.sql` in the run folder (default: yes, unless the user opted out). Then share the next-step suggestions below.

### Next steps (suggestions)

1. **Grant access**: `GRANT SELECT ON VIEW <metric_view> TO <principal>` to share with teams
2. **Add to a Genie Agent**: metric views work natively with AI/BI Genie for natural language querying
3. **Add to AI/BI dashboards**: use as datasets for visualizations
4. **Set up SQL alerts**: threshold-based alerts on measures
5. **BI tools / JDBC**: metric views are accessible via the Databricks JDBC driver and BI connectors
6. **Compose metric views**: use an existing metric view as the source for a new one — layered metrics
7. **Inspect with metadata**: `DESCRIBE TABLE EXTENDED <metric_view> AS JSON` for the full definition
8. **Set PK/FK constraints with RELY** on underlying tables for optimal join performance

## When a metric view is not the right tool → governed function

A measure that fails the additivity / single-pass test belongs in a governed UC SQL function, not a metric view. The tests and two worked examples are in [governed-functions.md](governed-functions.md).

## Limitations

For spec-level limits (OpenSharing requirements, no data profiling, `ALTER VIEW` removing UC comments), see [`create-patterns.md` §Common Issues](create-patterns.md#common-issues).
