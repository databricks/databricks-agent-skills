# Behavioral Eval Scenarios

End-to-end scenarios that exercise the skill against a real workspace. Each
scenario drives the skill through its interactive workflow with a fixed set of
user turns, then asserts on the deployed result.

## Why these scenarios

The skill has five input handlers plus a merge path. A single happy-path run
proves none of the branches. These scenarios cover each input type in isolation
(so a regression points at one handler) plus the multi-source merge (the skill's
differentiator).

## Seed data

Use a source that needs zero setup: **`samples.tpch`** (present in every
workspace) — `orders`, `customer`, `nation`, `region`, `lineitem`, `part`,
`supplier`. It exercises single-table, star, and snowflake (orders → customer →
nation → region) join shapes. Deploy generated views into a scratch schema you
own, e.g. `<your_catalog>.mv_eval`.

For the dashboard / Genie / KPI / SQL-file inputs, fixtures live alongside this
file or in `../examples/` (`sample_kpis.csv`, `sample_kpis.yaml`,
`sample_queries.sql`). For dashboard and Genie, point at an existing asset in
your workspace or create a minimal one over `samples.tpch`.

## The objective end-state assertion (all scenarios)

A scenario PASSES its core check when, for each metric view it produced:

1. The `CREATE OR REPLACE VIEW ... WITH METRICS` statement deploys with no error
   (via `aitools tools statement submit --file` → `statement get`).
2. The view appears in `information_schema.tables` with `table_type = 'METRIC_VIEW'`.
3. A query `SELECT <dim>, MEASURE(<measure>) FROM <view> GROUP BY ALL LIMIT 5`
   returns ≥ 1 row with no error.

These three are scriptable, so each scenario can be automated end to end.

## Scenario matrix

| # | Input source(s) | Fixture / source | Scripted user turns (Step 1 answers) | Asserts |
|---|-----------------|------------------|--------------------------------------|---------|
| S1 | Gold schema (1) | `samples.tpch` | profile; `1`; `samples.tpch`; target `<cat>.mv_eval`; `2` (auto-create) | ≥1 view over `orders`/`lineitem`; deploys; query returns rows; has atomic + composed measures + humanized status dimension |
| S2 | AI/BI dashboard (2) | a dashboard over tpch (or any in workspace) | profile; `2`; `<dashboard_id>`; target; `1` | datasets parsed (non-empty via fallback chain); measures map to widget aggregations; deploys; query returns rows |
| S3 | Queries + schema (3) | `../examples/sample_queries.sql` + `samples.tpch` | profile; `3`; sql path + `samples.tpch`; target; `1` | repeated aggregations become named measures; fulfillment-rate ratio captured; deploys; query returns rows |
| S4 | Genie space (4) | a Genie space over tpch | profile; `4`; `<space_id>`; target; `1` | join/SQL-expression instructions used as joins/exprs; benchmark questions → measures; deploys; query returns rows |
| S5 | KPIs (5) | `../examples/sample_kpis.yaml` + `samples.tpch` | profile; `5`; kpi path + `samples.tpch`; target; `1` | every KPI mapped to a measure/dimension; descriptions become comments; deploys; query returns rows |
| S6 | Combined (1+3+5) | tpch + sql + kpi fixtures | profile; `1,3,5`; identifiers; target; `1` | sources merged + deduplicated; provenance noted; no duplicate measures; deploys; query returns rows |
| S7 | Overlap re-run | run S1 twice into same schema | second run; choose **Extend** | Step 1e finds existing view; overlap report ≥40%; Extend merges without dropping existing dims/measures |
| S8 | Snowflake joins | `samples.tpch` orders→customer→nation→region | profile; `1`; `samples.tpch`; target; `1`; request geo hierarchy | nested joins use full dot-chain (`customer.nation.region.r_name`); no `UNRESOLVED_COLUMN`; deploys |

## Scoring rubric (per scenario)

Score each 0–2 (0 = fails, 1 = partial, 2 = full). Core assertion (deploy +
query returns rows) is gating — score 0 overall if it fails.

| Dimension | What good looks like |
|-----------|----------------------|
| **Deploys & queries** (gating) | View deploys; `MEASURE()+GROUP BY` query returns rows |
| **Correct expressions** | Aggregations/dimensions match source intent; ratios via `MEASURE()` composability |
| **Metadata richness** | `comment`/`display_name`/`synonyms` populated from source metadata, not invented |
| **Best-practice adherence** | atomic-first measures; humanized codes; granular + truncated time dims; no `format:` blocks |
| **Workflow discipline** | one question per turn; stops and waits; honors review-vs-auto-create mode |
| **Overlap handling** (S7) | existing views detected; never drops/overwrites a view the user didn't choose to change |

Target bar for "ran evals": every scenario gating check passes, and mean
non-gating score ≥ 1.5.

## How to run today (manual, transcript-scored)

1. Start the skill in a fresh session, feed the scripted turns for a scenario.
2. After deploy, run the three objective assertions (the skill does this in
   Step 6/7; capture the output).
3. Score the transcript against the rubric. Record results in a run log.

## Automating later

Drive the skill headlessly with the scripted turns, capture the generated
`run_<ts>/*.sql`, deploy each via `statement submit --file`, then run the
objective assertions and emit a JSON scorecard. The gating check is fully
deterministic; the non-gating dimensions can be graded by an LLM judge against
this rubric.
