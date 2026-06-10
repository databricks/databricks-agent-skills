---
name: optimize-genie-space
description: "Optimize Databricks Genie Space quality through approved iterative tuning in Databricks Genie Code Agent mode. Use inside Databricks when users ask to make reviewed Space edits, repair or prune benchmarks, launch native Chat-mode or Agent-mode benchmark evaluations, compare baseline-to-candidate results, analyze regressions, and run one focused configuration pass at a time with bounded read-only data inspection."
---

# Optimize Genie Space For Genie Code

Improve a Genie Space iteratively inside Databricks. Use Genie Code Agent mode to inspect Space context, run approved read-only SQL, make reviewed Space edits, launch native benchmark evaluation, wait for completed output, and compare behavior across tuning passes. Distinguish Genie Code Agent mode, where this skill runs, from Genie benchmark Agent mode, where benchmark execution judges the whole Genie response.

## Hard Rules

- Never mutate underlying tables, views, Metric Views, schemas, or source data.
- Keep SQL inspection read-only and bounded.
- Make one focused tuning pass at a time. Do not mix benchmark repair or pruning with Genie tuning in the same pass.
- Do not copy benchmark questions, answer SQL, or evaluation-note wording into sample questions, snippets, examples, or text instructions.
- Benchmarks evaluate quality; they do not teach Genie by themselves.
- Benchmark questions are shared definitions; Chat or Agent scoring is determined by benchmark execution mode.
- Benchmark evaluation can be asynchronous. Do not compare a run until it has completed and produced per-question output.
- Prefer structured Genie context over broad text instructions.
- Get explicit user approval before applying Space edits, changing benchmark definitions, launching native benchmark evaluations, or writing Unity Catalog optimization history.
- Benchmark repair or pruning changes only benchmark definitions, never source data or Genie tuning surfaces.
- Before applying a Space/config edit, classify failed and needs-review benchmark questions using the repair decision stack in `references/optimization-guide.md`.
- Every tuning pass must name the target failure cluster, selected repair lever, Space/config surface, expected fixes, related previous-good regression questions, and evaluation gate.
- If durable multi-pass history is needed, write only to user-approved Unity Catalog optimization-history tables. Persistence is optional and must never modify source data or source schemas.

## Workflow

1. Confirm the target Space and optimization goal: higher benchmark score, a failure cluster, a specific user question pattern, or a general quality pass.
2. Determine the benchmark execution target: Chat, Agent, or mixed. Infer it from the user's goal, benchmark UI/eval context, existing SQL answers, evaluation notes, and latest eval output. If it is ambiguous or the Space has no benchmark questions, ask the user whether to bootstrap or optimize for Chat execution, Agent execution, or both.
3. Review benchmark quality before tuning:
   - count valid benchmark items for the target execution mode
   - for Chat execution, require deterministic questions with checked SQL answers
   - for Agent execution, require clear questions and evaluation notes when the expected response needs grading guidance
   - exclude missing, invalid, duplicated, trivial, stale, ambiguous, or unscorable benchmark items
   - check coverage and challenge level across sources, metrics, filters, joins, time logic, ranking, answer shapes, and Agent response quality when applicable
   - if the benchmark is too large for practical iteration or dominated by near-duplicates, minor date/category variants, or low-challenge items, perform or recommend a dedicated pruning pass before tuning
   - if fewer than 30 valid items remain for the target execution mode, the benchmark is dominated by trivial/easy questions, or pruning would leave coverage gaps, perform or recommend a dedicated benchmark repair pass before tuning
4. For benchmark repair or pruning, get approval before changing benchmark definitions, change only benchmark definitions, validate expected SQL with read-only SQL where practical, add or refine evaluation notes for Agent-style questions, prune only when the retained set preserves diversity, coverage, and challenge level, run the relevant native benchmark evaluation after approval, and use the completed output as the new baseline.
5. Establish baseline behavior from the latest completed benchmark evaluation or run a native evaluation after user approval.
6. If the optimization will span multiple passes or needs auditable history, confirm an approved Unity Catalog catalog/schema for optimization history and initialize or reuse the table set described in `references/optimization-guide.md`.
7. Inspect the evidence available for the target execution mode:
   - Chat: generated SQL, expected SQL, actual results, result-shape mismatch, syntax, and assessment notes
   - Agent: final response, research plan, multi-query evidence, citations, supporting tables or charts, completeness, caveats, and assessment notes
8. Exclude invalid benchmark, stale ground-truth, unclear evaluation notes, permission, incomplete-eval, warehouse, or platform failures from tuning decisions.
9. Cluster valid tuning failures by shared root cause using `references/optimization-guide.md`.
10. Choose one failure cluster or small related cluster set and select the smallest structured repair lever.
11. Write the before config snapshot and repair analysis only when approved Unity Catalog optimization-history tables are available.
12. Apply approved Space edits using the selected structured surface:
   - data source or column descriptions
   - Metric View metadata exposed in the Space or an upstream semantic model recommendation
   - prompt matching settings
   - join specs
   - SQL snippets
   - representative example SQL
   - short global text instruction
13. After user approval, run the narrowest useful native benchmark evaluation available for affected questions and related previous-good regression questions.
14. After user approval, run the full relevant benchmark when targeted checks pass or when targeted evaluation is unavailable or not representative, then wait for completed per-question output.
15. Compare baseline and candidate behavior:
   - execution target and scoring mode
   - Chat accuracy change from SQL/result-set comparison, when run
   - Agent assessment change from whole-response judging, when run
   - fixed questions
   - regressions
   - unchanged failure clusters
   - benchmark questions excluded due to invalid or insufficient ground truth
16. Write question-level eval results, run summary metrics, acceptance decision, and reflection when approved Unity Catalog optimization-history tables are available.
17. Summarize whether to keep, revise, or roll back the pass.
18. Write an iteration reflection before starting the next repair pass.

## Output

Provide a concise optimization summary:

```markdown
# Genie Space Optimization: <space>

## Benchmark Review
- Execution target:
- Valid question count:
- Pruning recommendation:
- Benchmark field strategy:
- Exclusions:
- Coverage gaps:

## Tuning Pass
- Goal:
- Validity exclusions:
- Target cluster:
- Repair lever:
- Space/config surface:
- Changes applied:
- Why this was the smallest useful pass:
- Regression questions watched:

## Comparison
- Baseline Chat accuracy:
- Candidate Chat accuracy:
- Baseline Agent assessment:
- Candidate Agent assessment:
- Fixed:
- Regressed:
- Unchanged:
- Excluded:

## Decision
- Keep / revise / roll back:
- Iteration reflection:
- Next recommended pass:
```

## Related Skills

- **`diagnose-genie-space`** — plan-only root-cause analysis; precede a tuning pass with it when the failure cause is unclear.
- **`optimize-genie-query`** — for query performance/cost issues rather than answer quality.
- **`create-genie-space`** — initial Space design and bootstrap.
- **`databricks-metric-views`** — `genie-integration.md` (Metric View design) and `query-patterns.md` (`MEASURE()` query rules). Recommend upstream semantic-model fixes with this skill instead of working around gaps with broad text instructions.
- **`databricks-genie`** — the programmatic / MCP companion (create, query, export, import, migrate) for work outside Genie Code Agent mode.
