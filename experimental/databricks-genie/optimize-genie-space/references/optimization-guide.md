# Genie Optimization Guide

Use this reference when tuning a Genie Space in Databricks-native workflows.

## Navigation

- `Core Principle`: repair failed benchmark evidence with the smallest structured Genie context change.
- `Benchmark Integrity`, `Benchmark Difficulty`, `Benchmark Repair`, and `Benchmark Pruning`: review, repair, or prune benchmarks before tuning.
- `Repair Decision Stack`, `Judge-Style Failure Triage`, `Failure Clustering`, and `Failure-to-Lever Routing`: classify valid failures and choose the repair lever.
- `Proactive Enrichment Before Repair` and `Text Instruction Last-Resort Rule`: prevent broad or leaky edits.
- `Evaluation Gates`, `Acceptance Decision`, `Iteration Reflection`, and `Genie Repair Plan`: run and document candidate passes.
- `Optional Unity Catalog Table Persistence`: record auditable multi-pass history only after user approval.

## Core Principle

Translate failed benchmark evidence into structured Genie context. Prefer this order:

1. Focused source scope.
2. Source, Metric View, and column descriptions.
3. Prompt matching for categorical values.
4. Raw-table join specs.
5. SQL snippets for reusable business logic.
6. Representative example SQL for complex patterns.
7. Short global text instructions.

Benchmarks evaluate quality. They do not teach Genie by themselves. Do not copy benchmark questions, answer SQL, or evaluation-note wording into sample questions, snippets, examples, or text instructions.

## Benchmark Integrity

Before tuning, review whether the benchmark is useful:

- Identify the target benchmark execution mode: Chat, Agent, or mixed. Benchmark records are shared definitions; execution mode controls whether Databricks scores SQL/result-set match or whole-response quality.
- At least 30 valid benchmark items for the target execution mode before benchmark-driven tuning.
- Chat execution needs deterministic questions with checked SQL answers.
- Agent execution needs clear questions and evaluation notes when the expected response needs grading guidance.
- Mixed execution should use one shared benchmark set with per-question SQL answers, evaluation notes, or both, based on answer shape.
- Coverage across source selection, Metric View measures, dimensions, filters, joins, date logic, ranking, aggregation grain, answer shapes, and Agent response quality when applicable.
- A meaningful challenge mix. A benchmark dominated by easy questions is insufficient for tuning even when it has 30 valid benchmark items.
- A manageable size for iterative native evaluation. An oversized benchmark with many redundant variants should be pruned before tuning when it slows iteration, obscures root causes, or overweights narrow behaviors.
- No duplicates that only change a category or date.
- No answer SQL that errors, uses stale fields, or encodes the wrong business definition.
- No Agent evaluation note that is vague, contradictory, or asks the judge to reward unsupported claims.

If benchmark quality is insufficient or the benchmark is oversized, do a dedicated benchmark repair or pruning pass first. Do not mix benchmark repair or pruning with Genie tuning.

## Benchmark Difficulty

Use this light rubric when reviewing, repairing, or pruning benchmark questions:

- Easy: direct lookup, simple count, single-table filter, or no business logic.
- Medium: reusable metric/filter, categorical mapping, date condition, grouping, basic aggregation, or Metric View measure selection.
- Hard: joins, grain handling, ratios, conditional aggregation, ranking/top-N, rolling/window logic, multi-step business logic, result-shape constraints, or Agent-style synthesis across several supporting queries.

Prefer a meaningful mix of medium and hard questions. Flag benchmarks as too easy when they are dominated by trivial counts/lookups, repeated one-table summaries, or variants that only swap a date/category.

## Benchmark Repair

Use benchmark repair when fewer than 30 valid benchmark items remain for the target execution mode, expected SQL is invalid or stale, evaluation notes are missing or unclear for Agent-style questions, questions are duplicate or trivial, the benchmark is too easy, or coverage is too narrow for benchmark-driven tuning.

Use benchmark pruning when the benchmark started with too many questions for practical iteration or contains many redundant variants. Pruning is benchmark repair: get approval first, change only benchmark definitions, and do not tune Genie configuration in the same pass.

A valid benchmark item has a current, non-trivial question plus enough ground truth for the intended execution mode:

- `single_sql_answer`: add a checked SQL answer for deterministic tabular questions.
- `deterministic_with_response_quality`: add checked SQL and an evaluation note when Chat correctness and Agent response quality both matter.
- `multi_step_agent_analysis`: add an evaluation note only when the question requires multiple investigative queries, synthesis, caveats, citations, visualizations, or supporting tables rather than one canonical result set.
- `ambiguous_or_unverifiable`: ask the user for expected behavior before adding or repairing the item.

Checked SQL should match the current schema and business definition, run successfully or have read-only validation evidence, and avoid obsolete tables, columns, filters, or Metric View assumptions. Evaluation notes should state the expected content, evidence, caveats, and response-quality criteria without prescribing a hidden one-off answer.

Before changing benchmark definitions, get user approval and keep the pass limited to benchmark definitions. Do not mix benchmark repair or pruning with Genie tuning.

For each added, replaced, retained, or pruned benchmark item, record:

- question text;
- benchmark field strategy: SQL, evaluation note, both, or excluded;
- expected SQL and validation notes, when SQL is appropriate;
- evaluation note, when Agent execution needs response-grading guidance;
- difficulty level;
- coverage category, such as source routing, Metric View measure, filter, join, time logic, ranking, aggregation grain, answer shape, multi-query investigation, evidence quality, or response synthesis;
- referenced tables, Metric Views, and columns;
- whether it adds coverage, replaces an invalid, stale, duplicate, or trivial question, or is retained as a representative item;
- pruning rationale when removed or excluded.

Repair enough benchmark items to reach at least 30 valid items for the target execution mode. When pruning, retain a compact representative set with at least 30 valid items unless the user explicitly accepts a smaller diagnostic-only set. After benchmark repair or pruning, run the relevant native benchmark evaluation, wait for completed per-question output, and use that result as the new baseline before starting Genie tuning.

## Benchmark Pruning

Prune by evidence, not by arbitrary count. Build a question inventory with fields for execution mode, field strategy, validity, difficulty, coverage category, source/table or Metric View, referenced columns, answer shape, business priority, and recent assessment.

Prefer retaining questions that:

- cover distinct sources, Metric Views, metrics, dimensions, filters, joins, date roles, grain patterns, rankings, answer shapes, and Agent response-quality expectations;
- exercise medium or hard reasoning, reusable business logic, high-value workflows, and historically fragile behavior;
- have current checked SQL, clear Agent evaluation notes, or both as required by the execution target;
- include a small number of easy smoke tests for critical sources or metrics.

Prefer pruning questions that:

- are invalid, stale, ambiguous, unscorable, or missing required ground truth;
- duplicate another item except for a date, category, region, or customer literal;
- test a narrow one-off detail with low business value and no unique failure mode;
- are trivial easy lookups when the same source or metric is already covered by stronger questions;
- overweight one source, metric, dimension, or answer shape compared with the Space's intended usage.

Use a coverage matrix before finalizing the pruned set:

```markdown
## Benchmark Pruning Matrix

| Coverage area | Retained question IDs | Difficulty mix | Pruned near-duplicates | Gap after pruning? |
|---|---|---|---|---|
| Metric View measures | q_001, q_014, q_027 | easy/medium/hard | q_002, q_003 | no |
| Time logic | q_006, q_021 | medium/hard | q_007 | fiscal quarter boundary not covered |
| Agent synthesis | q_030, q_031 | hard | q_032, q_033 | no |
```

Before applying pruning, state the retained denominator, removed or excluded question IDs, coverage preserved, coverage lost, difficulty distribution, and whether follow-up benchmark repair is needed to fill gaps. After pruning, run the relevant native benchmark evaluation and use the completed output as the new baseline.

## Repair Decision Stack

Before applying a Space/config edit, answer:

1. Is this a valid tuning failure?
   - Exclude invalid expected SQL, unclear evaluation notes, stale benchmark questions, permissions, warehouse/API failures, and incomplete eval output.
   - Record whether the result came from Chat execution, Agent execution, or a mixed run.
2. What changed in the generated SQL or answer?
   - Chat: wrong source, wrong column, wrong join, wrong filter value, missing filter, wrong aggregation, wrong time logic, wrong metric formula, wrong grain, missing output field, syntax failure, or answer-prose issue.
   - Agent: weak research plan, missing hypothesis, insufficient supporting queries, wrong source selection, incomplete evidence, unsupported claim, missing citation/table/chart, poor synthesis, missing caveat, or unclear final report.
3. What is the smallest repair lever?
   - Source/column metadata, Metric View metadata, entity/value matching, format assistance, join spec, SQL snippet, representative example SQL, or text instruction.
4. Is there a proactive enrichment that would help multiple failures?
   - Missing descriptions, synonyms, categorical value semantics, date-role descriptions, reusable filters/measures, join specs, examples for complex grain/ranking/window logic, or response-quality guidance for Agent reports.
5. What slice proves the repair?
   - Identify affected benchmark question IDs and related previous-good regression questions.
6. What should be recorded for the next loop?
   - Cluster, attempted lever, expected impact, result, regressions, and whether to retry or avoid the approach.

Every tuning pass must name the target failure cluster and repair lever before editing the Space/config.

## Judge-Style Failure Triage

Use judge-style analysis as a mental model only. Do not implement custom judges. For each `BAD` or `NEEDS_REVIEW` question, inspect the evidence available for the execution mode. For Chat execution, inspect generated SQL, expected SQL, actual results, and assessment notes. For Agent execution, inspect the full response, research steps, supporting query outputs, citations, visualizations, evaluation note, and assessment notes.

Classify failures across these dimensions:

- `result_correctness`: Did actual results match expected results after reasonable normalization?
- `asset_routing`: Did Genie choose the right table, metric view, or configured source?
- `schema_accuracy`: Did Genie choose the right columns and aliases?
- `logical_accuracy`: Did filters, joins, aggregations, dates, windows, ranking, and grain match intent?
- `completeness`: Did the response answer all required parts?
- `syntax_validity`: Did generated SQL run?
- `agent_investigation_quality`: Did Agent mode form a useful plan, run enough relevant queries, adapt to findings, and gather enough evidence?
- `response_quality`: Was the final explanation, report structure, citation support, table/chart use, and caveat handling acceptable?
- `benchmark_validity`: Is the expected SQL valid and current, and is the evaluation note clear enough for Agent-mode judging?
- `infra_validity`: Was the eval complete and free of platform/access failures?

```markdown
## Repair Triage

| Question ID | Execution | Assessment | Valid tuning failure? | Primary failure | Evidence | Recommended lever |
|---|---|---|---:|---|---|---|
| q_001 | Chat | BAD | yes | wrong_filter_value | generated SQL uses wrong status literal | entity/value matching + column metadata |
| q_002 | Chat | BAD | no | invalid_expected_sql | expected SQL references removed column | benchmark repair, not config tuning |
| q_003 | Agent | BAD | yes | incomplete_evidence | report names drivers but cites only one aggregate query | source descriptions + representative example pattern |
```

Rules:

- Do not count invalid benchmark or infra failures as Genie repair targets.
- Do not treat an Agent-mode failure as a SQL-match failure unless the eval evidence shows the response was wrong because of a single incorrect query.
- Triage `NEEDS_REVIEW` separately from `BAD`.
- Do not infer root cause from aggregate accuracy alone.
- Use `unknown` or `manual_review` when evidence is insufficient.

## Failure Clustering

Cluster valid tuning failures before each candidate edit. Prefer one failure cluster or a small related cluster set per pass.

```markdown
## Failure Clusters

| Cluster | Question IDs | Shared root cause | Evidence | Proposed lever | Regression questions |
|---|---|---|---|---|---|
| status_value_mapping | q_001, q_004 | Genie maps active/inactive terms to wrong stored values | generated SQL filters `status = 'A'`; expected uses `status = 'ACTIVE'` | column metadata + entity/value matching | q_008, q_011 |
| customer_order_join | q_002, q_006 | missing stable customer-to-order join | generated SQL cross-joins or omits customer table | join spec | q_014 |
| revenue_driver_synthesis | q_009, q_012 | Agent report summarizes decline without segment-level evidence | final report lacks cited product or region breakdown queries | source descriptions + representative example pattern | q_016 |
```

Repair priority:

1. High-count clusters with one clear structured lever.
2. Critical/P0 benchmark questions.
3. Low-regression metadata enrichment.
4. SQL snippets for reusable logic that metadata cannot express.
5. Representative example SQL for complex grain, ranking, windows, or multi-step logic.
6. Text instructions only for global behavior that cannot be encoded structurally.

## Failure-to-Lever Routing

| Failure pattern | Evidence to inspect | Preferred repair lever | Avoid |
|---|---|---|---|
| Wrong table/source selected | Generated SQL uses the wrong configured table or metric view | Improve source descriptions, source names/synonyms, and differentiating metadata | Broad text instruction saying "use table X" for one benchmark |
| Wrong column selected | Correct source, wrong field | Column description, synonyms/business aliases, hide or de-emphasize confusing columns if supported | Example SQL unless the pattern is complex |
| Wrong Metric View measure | Wrong measure selected or measure intent misunderstood | Space-exposed Metric View display names/descriptions when editable, or document an upstream semantic model gap | Duplicating governed measure logic in text instructions |
| Wrong metric formula outside Metric View | Wrong numerator, denominator, or aggregation | SQL snippet for reusable measure logic; representative example for complex formula | Global text instruction with metric math |
| Wrong filter value | SQL uses wrong categorical literal or status mapping | Column description with value semantics, entity/value matching, format assistance, reusable filter snippet | Copying benchmark answer filter into example SQL |
| Missing business filter | Expected SQL has a reusable business filter missing in generated SQL | Reusable filter SQL snippet or concise source/column metadata explaining default business scope | Long instruction list of every filter |
| Wrong join path | SQL omits or misuses a join | Join spec after validating keys and grain | Join spec based only on column-name similarity |
| Wrong join relationship/grain | Duplicated rows, wrong counts, many-to-many issue | Join spec with relationship/grain guidance; example SQL for grain-preserving pattern | Blind aggregation workaround |
| Wrong date field | Uses `created_at` instead of `closed_at`, `effective_date`, etc. | Column descriptions for date roles; snippet for common time filter | Text instruction listing many date rules |
| Wrong time window | Wrong interval, boundary, fiscal period, or relative date logic | SQL snippet for reusable window; representative example for complex period logic | One-off benchmark-specific example |
| Wrong aggregation grain | Counts rows instead of entities, averages at wrong level, misses distinct | SQL snippet for reusable grain logic; example SQL for representative complex query | Source description only |
| Ranking/top-N/window failure | Missing window function, wrong tie-breaker, wrong order | Representative example SQL; reusable snippet if the expression repeats | Many examples pasted into global instruction |
| Correct SQL, bad answer prose | SQL/results acceptable but final explanation weak | Short response-quality text instruction | Changing SQL surfaces |
| Weak Agent research plan | Agent response starts from a vague or narrow plan and misses obvious comparison axes | Source descriptions, Metric View descriptions, and representative examples that show useful analytic dimensions | Long text instruction that scripts every benchmark |
| Incomplete Agent evidence | Final report makes claims without enough supporting query results, citations, tables, or charts | Clarify source/metric semantics; add representative example SQL only for reusable investigative patterns | Adding a single SQL answer for a multi-step analysis question |
| Unsupported Agent synthesis | Report overstates causality, misses caveats, or ignores data limitations | Short global response-quality instruction when the behavior is truly global | Encoding one benchmark's final prose as an instruction |
| Unclear Agent benchmark rubric | LLM judge lacks enough criteria to assess the report | Benchmark repair: add or refine evaluation note | Genie config tuning |
| Syntax failure | Generated SQL invalid | Inspect exact syntax issue; repair snippets/examples only if pattern repeats | Treating syntax failure as business logic failure |
| Invalid expected SQL | Expected benchmark answer errors or is stale | Benchmark repair outside config tuning | Genie config tuning |
| Incomplete eval / permissions / API | Eval did not complete or details missing | Infrastructure/access fix | Genie config tuning |
| Space too broad / asset ambiguity | Failures scatter across many unrelated sources | Source scoping, descriptions, ambiguity reduction, possible Space split recommendation | More global instructions |

## Proactive Enrichment Before Repair

Before proposing a patch, inspect the current Space/config and failing questions for low-risk enrichments:

1. Are source descriptions missing, thin, or indistinguishable?
2. Are business terms from failed questions absent from source/column descriptions or synonyms?
3. Are low-cardinality categorical columns causing wrong literal values?
4. Are status, type, segment, region, channel, or lifecycle values undocumented?
5. Are date roles ambiguous, such as `created_at` vs `closed_at` vs `effective_date`?
6. Are repeated joins failing because join specs are missing or unclear?
7. Are repeated metrics, filters, or time windows better expressed as SQL snippets?
8. Is a representative example needed for complex grain, ranking, window, or period logic?
9. Do Agent-mode failures show missing investigation dimensions, weak evidence collection, unsupported synthesis, or missing caveats?
10. Is text instruction being used as a dumping ground for logic that belongs in metadata, snippets, examples, or joins?
11. Is the Space backed by Metric Views, and should the repair target Metric View metadata rather than raw table logic?
12. Are there too many data sources in one Space, causing routing confusion?

## Text Instruction Last-Resort Rule

Do not use text instructions as the default repair. If the proposed instruction names specific tables, metric views, columns, joins, filters, denominators, numerators, aliases, ranking logic, or window logic, first try to encode the rule in source/column metadata, entity/value matching, format assistance, join specs, SQL snippets, or representative example SQL.

Use text instructions only for global behavior that cannot be encoded structurally. Each text instruction edit must include:

```markdown
## Text Instruction Justification

- Exact instruction text:
- Why structured surfaces were insufficient:
- Which failures this targets:
- Which regressions this could cause:
- How the candidate eval will validate it:
```

## Evaluation Gates

Use staged evaluation inside the native benchmark loop. Do not build a new gate framework.

Gate 1: affected failure slice

- Run the affected failing questions first when practical.
- Purpose: verify the candidate fixes the target cluster.
- If it fails, revise or roll back before spending effort on the full benchmark.

Gate 2: related regression slice

- Run previous-good questions that share the same sources, joins, filters, metrics, or date logic.
- Purpose: catch localized regressions quickly.

Gate 3: full benchmark

- Run the complete relevant benchmark after the targeted and regression checks look acceptable, or when targeted evaluation is unavailable or not representative. For mixed execution goals, compare Chat and Agent runs separately instead of collapsing them into one score.

Compare question-level movement:

```text
fixed: BAD/NEEDS_REVIEW -> GOOD
regressed: GOOD -> BAD/NEEDS_REVIEW
unchanged_bad: BAD/NEEDS_REVIEW -> BAD/NEEDS_REVIEW
unchanged_good: GOOD -> GOOD
excluded: invalid benchmark, incomplete eval, infra/access issue
```

## Acceptance Decision

After comparing reports, add an explicit keep/revise/rollback decision:

```markdown
## Acceptance Decision

- Baseline report:
- Candidate report:
- Candidate config or Space version:
- Benchmark execution target:
- Benchmark field strategy:
- Valid denominator used:
- Chat accuracy delta, if run:
- Agent assessment delta, if run:
- Fixed:
- Regressed:
- Unchanged target failures:
- New syntax/access/eval issues:
- Benchmark or infra exclusions:
- Leakage review:
- Decision: KEEP / REVISE / ROLL BACK
- Reason:
- Rollback action, if needed:
```

Keep the candidate only when it improves the valid benchmark score or fixes the target cluster without unacceptable regressions. Roll back or revise when the candidate only shifts failures, creates new syntax/infra issues, or depends on benchmark leakage.

## Iteration Reflection

Write this before starting the next repair pass:

```markdown
## Iteration Reflection

- Candidate version:
- Target cluster:
- Lever attempted:
- Result:
- Fixed question IDs:
- Regressed question IDs:
- Still failing question IDs:
- Root cause update:
- Do not repeat:
- Next repair hypothesis:
```

## Genie Repair Plan

Use this template for each candidate pass:

```markdown
## Genie Repair Plan

### Validity exclusions
- Benchmark execution target:
- Benchmark field strategy:
- Invalid expected SQL, unclear evaluation notes, or stale benchmark questions:
- Permissions, platform, warehouse, or incomplete-eval issues:
- Questions excluded from tuning denominator:

### Failure triage
| Question ID | Execution | Assessment | Valid tuning failure? | Primary failure | Evidence | Recommended lever |
|---|---|---|---:|---|---|---|

### Failure clusters
| Cluster | Question IDs | Shared root cause | Evidence | Proposed lever | Regression questions |
|---|---|---|---|---|---|

### Candidate edit
- Target cluster:
- Smallest repair lever:
- Space/config surface to edit:
- Why this should fix the cluster:
- Why this is not benchmark leakage:
- Why this should not regress related questions:

### UC table persistence
- Approved catalog.schema, if any:
- Config version row written? yes/no:
- Eval result rows written? yes/no:
- Repair analysis row written? yes/no:
- Run summary row updated? yes/no:

### Evaluation gate
- Affected question IDs:
- Related previous-good regression questions:
- Full benchmark required? Why/why not:

### Acceptance decision
- Chat accuracy delta, if run:
- Agent assessment delta, if run:
- Fixed:
- Regressed:
- Still failing:
- Excluded from denominator:
- Decision: KEEP / REVISE / ROLL BACK
- Reason:

### Iteration reflection
- What was learned:
- Repair approach not to repeat:
- Next repair hypothesis:
```

## Optional Unity Catalog Table Persistence

Use Unity Catalog managed Delta tables only when the user approves a catalog/schema location for optimization history. This is optional. Continue the repair loop using native benchmark output when persistence is not approved or unavailable.

Write only optimization history to these tables. Do not modify source-data tables, views, Metric Views, schemas, benchmark answers, or source data as part of Genie config tuning.

Recommended default: four tables.

| Table | Grain | Purpose |
|---|---|---|
| `<catalog>.<schema>.genie_opt_runs` | one optimization pass / candidate edit | Run ledger, parent/child linkage, summary metrics, decision |
| `<catalog>.<schema>.genie_opt_config_versions` | one Space/config snapshot | Before/after snapshots, config hash, rollback reference |
| `<catalog>.<schema>.genie_opt_eval_results` | one question result per eval run | Question-level benchmark logging, triage, movement analysis |
| `<catalog>.<schema>.genie_opt_repair_analysis` | one failure cluster / repair hypothesis per pass | Root-cause analysis, chosen lever, evidence, reflection |

Use the four-table design for long-running or auditable sessions. The `genie_opt_runs` table is the coordinator that connects the candidate edit, parent run, config versions, eval rows, and keep/revise/rollback decision.

Minimum viable alternative: three tables.

```text
genie_opt_runs                 # include repair analysis JSON/Markdown in this table
genie_opt_config_versions
genie_opt_eval_results
```

Use a single append-only event table only when the user prioritizes setup simplicity over typed queries:

```text
genie_opt_events
```

Allowed event types:

```text
run_started
config_snapshot
eval_question_result
repair_analysis
candidate_decision
iteration_reflection
```

Recommended stable columns:

- `genie_opt_runs`: `run_id`, `session_id`, `space_id`, `space_name`, `benchmark_execution_target`, `benchmark_id`, `benchmark_version_or_hash`, `iteration`, `parent_run_id`, `baseline_config_version_id`, `candidate_config_version_id`, `target_cluster`, `repair_lever`, `status`, `started_at`, `ended_at`, `baseline_score`, `candidate_score`, `score_delta`, `fixed_count`, `regressed_count`, `unchanged_bad_count`, `unchanged_good_count`, `excluded_count`, `decision`, `notes`.
- `genie_opt_config_versions`: `config_version_id`, `run_id`, `space_id`, `version_label`, `parent_config_version_id`, `captured_at`, `captured_by`, `config_hash`, `config_json`, `changed_surfaces`, `change_summary`.
- `genie_opt_eval_results`: `eval_result_id`, `eval_run_id`, `run_id`, `space_id`, `benchmark_id`, `benchmark_version_or_hash`, `eval_type`, `evaluated_at`, `question_id`, `question_text`, `benchmark_field_strategy`, `assessment`, `valid_tuning_failure`, `exclusion_reason`, `primary_failure`, `secondary_signal`, `failure_cluster`, `expected_sql_hash`, `generated_sql_hash`, `generated_sql`, `evaluation_note_hash`, `expected_result_digest`, `actual_result_digest`, `judge_notes`, `latency_ms`, `error_message`.
- `genie_opt_repair_analysis`: `analysis_id`, `run_id`, `space_id`, `created_at`, `cluster_id`, `affected_question_ids`, `root_cause`, `evidence_summary`, `selected_lever`, `rejected_levers`, `config_surface`, `planned_patch_summary`, `expected_fix_count`, `regression_risk`, `benchmark_leakage_check`, `acceptance_decision`, `reflection`, `next_hypothesis`.
- `genie_opt_events`: `event_id`, `event_ts`, `event_type`, `session_id`, `run_id`, `space_id`, `config_version_id`, `eval_run_id`, `question_id`, `payload_json`.

When persistence is enabled for each candidate pass:

1. Write a run row.
2. Capture the before config snapshot.
3. Write repair analysis before editing.
4. Apply the focused Space/config edit.
5. Capture the after config snapshot.
6. Write question-level eval results.
7. Update the run summary, acceptance decision, and iteration reflection.
