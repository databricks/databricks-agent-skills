# Step 3 — Suggest Metric Views (detailed procedure)

This is the full procedure for **Step 3** of the advisor workflow (referenced from
`SKILL.md`). Based on your analysis, suggest metric views that would provide value.

The step has four parts, in order: (1) check for overlap with existing metric views,
(2) build suggestions from all gathered metadata, (3) run a gap analysis, and
(4) save + present the suggestions and handle the user's response.

## Pre-suggestion: Check for overlap with existing metric views

**If existing metric views were discovered in Step 1e**, you MUST check for semantic overlap before generating suggestions. This prevents duplicate views from accumulating across multiple runs.

**Skip this subsection entirely if:** Step 1e found no existing metric views (fresh schema).

**Comparison logic — for each candidate metric view you are about to suggest:**

1. **Match by source table** — Find all existing metric views that use the same source table (fully qualified name). This is the primary overlap signal.
2. **Compute dimension overlap** — For each pair with the same source table, compare dimension `expr` values. Normalize before comparing (strip whitespace, lowercase, ignore trivial differences like a `source.` prefix); count dimensions with matching expressions even if names differ: `dim_overlap = matching_dims / max(candidate_dims, existing_dims)`.
3. **Compute measure overlap** — Same approach for measure `expr` values: `measure_overlap = matching_measures / max(candidate_measures, existing_measures)`.
4. **Compute coverage score** — `(matching_dims + matching_measures) / (candidate_dims + candidate_measures)`:
   - **High (>=70%)**: Existing view already covers most of what you'd suggest
   - **Medium (40-69%)**: Significant overlap worth addressing
   - **Low (<40%)**: Mostly new content — minimal overlap
5. **If multiple existing views overlap the same candidate**, pick the one with the **highest coverage score** as the primary comparison target. Mention the others as additional duplicates.

**For each overlap with coverage >= 40%, present a report to the user:**

> **Overlap detected:** Your suggested `lineitem_metrics` overlaps with existing `lineitem_analytics`
>
> | | Suggested | Existing | Shared |
> |--|-----------|----------|--------|
> | Source | ...lineitem | ...lineitem | Same |
> | Dimensions | 15 | 16 | 12 |
> | Measures | 14 | 15 | 10 |
> | **Coverage** | | | **73%** |
>
> **Only in suggested (new):** Order Date, Order Month, Total Tax Amount, Avg Unit Price
> **Only in existing:** Ship Instruction, Container, Average Discount, Total Tax
>
> | # | Action | What happens |
> |---|--------|-------------|
> | 1 | **Extend existing** `lineitem_analytics` | Add the missing items to the existing view (recommended) |
> | 2 | **Replace** with `lineitem_metrics` | Drop old view, deploy new one instead |
> | 3 | **Create alongside** | Keep both (you accept the overlap) |
> | 4 | **Skip** | Don't create a lineitem-level view at all |

**How each resolution affects downstream steps:**
- **Extend (1):** Step 4 generates a `CREATE OR REPLACE VIEW` under the **existing** view name, merging all existing dimensions/measures with the new ones. Preserve existing `comment`, `synonyms`, and `display_name` values.
- **Replace (2):** Step 4 generates a `CREATE OR REPLACE VIEW` under the **new** name. Step 6 also drops the old view after deploying the new one.
- **Create alongside (3):** Normal suggestion flow — no changes.
- **Skip (4):** Remove this candidate from the suggestions entirely.

**Auto-create mode behavior:**
- Coverage >= 70% → automatically choose **Extend existing** (safest default — no duplication, no data loss)
- Coverage 40-69% → **pause and ask the user** (too ambiguous to auto-resolve)
- Coverage < 40% or no source-table match → automatically **create alongside**

**Review-first mode:** Always present the overlap report and wait for the user's response for every overlap >= 40%.

> **Safety:** Only "Extend" or "Replace" an existing metric view when the user explicitly chooses that option for the reported overlap. Never drop or overwrite a pre-existing view the user did not ask you to change.

After resolving all overlaps, proceed to generate the final suggestions list reflecting the user's choices.

---

## Building suggestions from your analysis — use ALL gathered metadata

Every suggestion must be a holistic synthesis of what you learned across ALL input sources — not just column names and types. For each metric view you suggest, apply this checklist:

**1. Metric view naming and `comment`:**
- Use Genie space `title`/`description` and dashboard title to name the metric view in a business-friendly way (e.g., "wholesale_supplier_order_metrics" not "orders_mv")
- Use catalog/schema comments and table comments to write a rich top-level `comment` describing the metric view's business purpose
- If Genie text instructions describe the domain, incorporate that context

**2. For each dimension — assemble from all sources:**
- **`expr`**: Prefer Genie SQL expression instructions (canonical computed columns) > dashboard query expressions > KPI definitions > raw column references. Use CHECK constraints to inform valid value sets for CASE expressions. Use partition/clustering keys as prioritized dimension candidates.
- **`comment`**: Prefer Genie column descriptions > UC column comments > KPI descriptions > SQL file comments > inferred from column name. Never leave `comment` empty if any source provided context.
- **`display_name`**: Prefer KPI names > Genie column `display_name` > dashboard parameter names > dashboard widget axis labels > humanized column name
- **`synonyms`**: Combine alternative names from ALL sources — Genie benchmark question phrasing, KPI file names, dashboard widget titles, UC column comment mentions of aliases.
- **Null safety**: If the column is nullable (from schema stats), wrap in COALESCE or CASE for null handling
- **PII check**: If UC tags include `pii:true`, flag and exclude unless the user approves

**3. For each measure — assemble from all sources:**
- **`expr`**: Prefer Genie SQL expression instructions > dashboard query aggregations > KPI definitions > SQL file patterns. If the same aggregation appears in multiple sources, that is a strong signal it's the canonical expression.
- **`comment`**: Same priority as dimensions. Include units if any source mentions them (e.g., "in USD").
- **`display_name`** and **`synonyms`**: Same approach as dimensions.
- **Composed measures**: For every pair of atomic measures where a ratio makes business sense (revenue/customers, fulfilled/total, etc.), suggest a composed measure. Look for ratios already computed in SQL files, dashboards, or KPI definitions.
- **Filtered measures**: For every status/category dimension, suggest filtered variants of key measures (e.g., if status has values 'Open', 'Fulfilled', 'Processing', suggest `Open Revenue`, `Fulfilled Orders`, etc.).

**4. Joins — assemble from all sources:**
- Prefer Genie join instructions (author-intended) > dashboard query JOINs > FK constraints > inferred from column name matching
- Include ALL dimension tables that enrich the fact table — even if not all input sources used them

**5. Filters — assemble from all sources:**
- Intersect common WHERE clauses from dashboard queries, SQL files, Genie SQL query instructions, and Genie text instructions
- Check table properties for data freshness hints

**6. Gap analysis — what's missing:**
After building suggestions from existing sources, identify what's NOT yet covered:
- **Unused schema columns**: Columns no input source referenced — are any valuable dimensions or measures?
- **Missing time dimensions**: If the source has date columns, ensure granular + truncated time dimensions exist (Date, Month, Quarter, Year)
- **Missing ratio measures**: For every pair of atomic measures, ask "does a ratio between these make business sense?"
- **Missing filtered measures**: For every categorical dimension, ask "would filtered versions of the key measures be useful?"
- **Cross-table measures**: If dimension tables exist, are there measures that should use joined columns?
- **Genie gaps**: If Genie benchmark questions ask about something not yet covered, add it

Present this gap analysis alongside the suggestions so the user sees both what you recommend AND what additional coverage they could add.

---

## Formatting guidelines (per Databricks best practices)

- **Model atomic measures first** — Define simple, foundational measures (`SUM(revenue)`, `COUNT(1)`, `COUNT(DISTINCT customer_id)`) before complex ones. Build complex measures (AOV, fulfillment rate) using **composability** — reference earlier measures via `MEASURE()`.
- **Standardize dimension values** — Convert cryptic database codes into clear business names using CASE expressions. Never expose raw codes to users.
- **Define scope with filters** — If a metric view should only ever include certain data, define a persistent `filter` in the YAML.
- **Use business-friendly naming** — Metric names should be immediately recognizable to business users. Add `display_name` for visualization-friendly labels.
- **Separate time dimensions** — Always include BOTH the **granular date** AND **truncated variants** (Month, Quarter, Year).
- **Group related metrics** into a single metric view; don't create too many narrow views.
- **Include ratio measures** built via composability; **include filtered measures** using `FILTER (WHERE ...)`.
- **Think about Genie** — clear `comment`, `synonyms`, and `display_name` fields improve Genie answers.
- **Star schema joins** — if dimension tables exist, include them. Recommend PK/FK constraints with `RELY` on underlying tables for optimal join performance.

## Suggestion format

Generate suggestions as a YAML file with this structure:

```yaml
# Metric View Suggestions
# Edit this file to add, remove, or modify suggestions, then provide the path back to the skill.
# Source schema: <source catalog.schema>
# Target schema: <target catalog.schema>

metric_views:
  - name: <metric_view_name>
    source_table: <fact_table>
    rationale: "<why this metric view is useful>"
    filter: "<optional global filter expression>"
    joins:
      - table: <dimension_table>
        'on': "<join condition>"
    dimensions:
      - name: <Display Name>
        expr: "<sql_expression>"
        comment: "<description>"
        display_name: "<visualization label>"
        synonyms: ["alt name 1", "alt name 2"]
    measures:
      # Define atomic measures first
      - name: <Atomic Measure>
        expr: "<aggregate_expression>"
        comment: "<description>"
        display_name: "<visualization label>"
        synonyms: ["alt name 1", "alt name 2"]
      # Then composed measures referencing atomic ones (backtick-quote names with spaces)
      - name: <Composed Measure>
        expr: "MEASURE(`<Atomic Measure 1>`) / MEASURE(`<Atomic Measure 2>`)"
        comment: "<description>"

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

## Output folder structure

Each run creates a timestamped subfolder to preserve previous runs:

```
<target_schema>_output_metric_views/
├── run_20260403_143022/       # previous run (preserved)
├── run_20260403_161500/       # current run
│   ├── suggestions.yaml
│   ├── order_metrics.sql
│   └── ...
└── latest.txt                 # plain text file: name of the most recent run folder
```

**At the start of each run** (when you first need to save a file): generate a timestamp `run_<YYYYMMDD_HHMMSS>`, create `<target_schema>_output_metric_views/run_<timestamp>/`. After saving, write the current run folder name into `<target_schema>_output_metric_views/latest.txt` (a single line, e.g. `run_20260403_161500`). All paths shown to the user reference the full `run_<timestamp>/` folder. This ensures previous runs are never overwritten.

> **Do NOT create a `latest` symlink.** Symbolic links work on a local POSIX filesystem but do **not** resolve in the Databricks Workspace filesystem (where Genie Code runs) — the link is created but cannot be navigated or read through. A plain `latest.txt` pointer file works in every environment. To find the newest run, read `latest.txt`; as a fallback, pick the lexicographically-largest `run_*` folder (timestamps sort chronologically).

## What to do with the suggestions — always do all three

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

**STOP — wait for the user to respond before proceeding.** Do NOT generate YAML definitions until the user confirms or provides an updated file.

## Handling the user's response

- **"Approve" / "1" / "looks good"** → proceed to Step 4 using the suggestions as generated
- **"Add gaps" / "2" / "add 2, 3"** → add the specified gaps, re-display the updated coverage summary, save the updated YAML, ask for approval again
- **"Proceed" / "updated" / "3"** → re-read `suggestions.yaml` from the run folder, then proceed to Step 4
- **User provides a file path** → read that file, parse it as the suggestions YAML, then proceed to Step 4
