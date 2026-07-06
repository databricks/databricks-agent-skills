---
name: optimize-genie-agent
description: "Optimize Databricks Genie Agent quality through approved iterative tuning. Works inside Databricks Genie Code (native UI) or from an external agent via the Databricks CLI/MCP. Use to make reviewed Agent edits, repair or prune benchmarks, launch native Chat-mode or Agent-mode benchmark evaluations, compare baseline-to-candidate results, analyze regressions, and run one focused configuration pass at a time with bounded read-only data inspection."
---

# Optimize Genie Agent

Improve a Genie Agent iteratively: inspect Agent context, make reviewed edits, launch benchmark evaluation, wait for completed output, and compare behavior across tuning passes — one focused pass at a time. Distinguish the **agent host** running this skill from Genie benchmark **Agent mode**, where benchmark execution judges the whole Genie response.

> **Naming:** "Genie Agent" is the current name for what was formerly called a **Genie Space**. The two terms are interchangeable — "Genie Space" still appears in the Databricks UI, CLI (`create-space`, `serialized_space`, …), and API, and remains valid for backward compatibility.

## Execution Context

This skill runs in either of two contexts. **The iterative tuning workflow below is identical; only the *mechanism* differs.**

- **(a) Inside Databricks Genie Code (native UI)** — inspect Agent context, make reviewed edits in the native editor, and launch native benchmark evaluation from the UI.
- **(b) Outside Databricks via CLI/MCP** (e.g. Claude Code) — use the Databricks CLI as the default. Benchmark evaluation runs via the **Beta** `genie-*-eval-run` commands (CLI-only; not wrapped by `manage_genie`/`ask_genie`). See [Mechanism Map](#mechanism-map-cli--mcp).

**Prerequisites (context b):** authenticated `databricks` CLI, a running SQL warehouse with `CAN USE`, edit access to the Agent, and benchmark questions already defined in the Agent.

## Hard Rules

- Never mutate underlying tables, views, Metric Views, schemas, or source data.
- Keep SQL inspection read-only and bounded.
- Make one focused tuning pass at a time. Do not mix benchmark repair or pruning with Genie tuning in the same pass.
- Do not copy benchmark questions, answer SQL, or evaluation-note wording into sample questions, snippets, examples, or text instructions.
- Benchmarks evaluate quality; they do not teach Genie by themselves.
- Benchmark questions are shared definitions; Chat or Agent scoring is determined by benchmark execution mode.
- Benchmark evaluation can be asynchronous. Do not compare a run until it has completed and produced per-question output.
- Prefer structured Genie context over broad text instructions.
- Get explicit user approval before applying Agent edits, changing benchmark definitions, launching native benchmark evaluations, or writing Unity Catalog optimization history.
- Benchmark repair or pruning changes only benchmark definitions, never source data or Genie tuning surfaces.
- Before applying an Agent/config edit, classify failed and needs-review benchmark questions using the repair decision stack in `references/optimization-guide.md`.
- Every tuning pass must name the target failure cluster, selected repair lever, Agent/config surface, expected fixes, related previous-good regression questions, and evaluation gate.
- If durable multi-pass history is needed, write only to user-approved Unity Catalog optimization-history tables. Persistence is optional and must never modify source data or source schemas.

## Workflow

1. Confirm the target Agent and optimization goal: higher benchmark score, a failure cluster, a specific user question pattern, or a general quality pass.
2. Determine the benchmark execution target: Chat, Agent, or mixed. Infer it from the user's goal, benchmark UI/eval context, existing SQL answers, evaluation notes, and latest eval output. If it is ambiguous or the Agent has no benchmark questions, ask the user whether to bootstrap or optimize for Chat execution, Agent execution, or both.
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
12. Apply approved Agent edits using the selected structured surface:
   - data source or column descriptions
   - Metric View metadata exposed in the Agent or an upstream semantic model recommendation
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
# Genie Agent Optimization: <space>

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
- Agent/config surface:
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

## Mechanism Map (CLI / MCP)

Per-step mapping for context (b). Inside Databricks you use native benchmark execution and the per-question scoring UI; outside, you keep the same one-pass-at-a-time methodology and approval gates but drive evaluation with the **Beta** `genie-*-eval-run` CLI commands.

| Step | Native (Genie Code) | CLI substitute (default outside) |
|------|---------------------|----------------------------------|
| Launch a benchmark run (Steps 5, 13–14) | native "Run benchmark" button | `databricks genie genie-create-eval-run SPACE_ID --json '{...}'` *(Beta)*. **Scope it:** `{"benchmark_question_ids":["<id>", ...]}` runs only those questions. ⚠️ An **empty body `{}` runs ALL questions**, and a **misspelled field also runs ALL questions** — the CLI only prints `Warning: unknown field` and then falls through to the all-questions default (it does **not** abort). Always double-check the field name is exactly `benchmark_question_ids` before launching, or you will silently kick off a full-benchmark run that consumes warehouse compute. |
| Wait for / fetch run status | eval UI | `databricks genie genie-get-eval-run SPACE_ID EVAL_RUN_ID` — poll until complete (eval is asynchronous; do not compare until done) |
| List prior runs (baseline) | eval history | `databricks genie genie-list-eval-runs SPACE_ID` |
| Per-question results (Step 15 compare) | per-question scoring grid | `databricks genie genie-list-eval-results SPACE_ID EVAL_RUN_ID`, then `genie-get-eval-result-details SPACE_ID EVAL_RUN_ID RESULT_ID` |
| Apply an Agent edit (Step 12) | native editor | `databricks genie update-space` with the edited config (see parent [databricks-genie-agent SKILL.md](../SKILL.md)) — present for approval first |
| UC optimization-history persistence (Steps 6, 11, 16) | notebook/SQL | `databricks experimental aitools tools query` to create/append the approved history tables in `references/optimization-guide.md` |

**Staged evaluation gates via scoping.** Use `benchmark_question_ids` to keep the gates cheap and the regression signal clean:

- **Gate 1 (affected slice):** `genie-create-eval-run` with `benchmark_question_ids` = the failing question IDs only.
- **Gate 2 (regression slice):** a run scoped to related previously-passing question IDs.
- **Gate 3 (full benchmark):** empty body `{}` to run everything, only after Gates 1–2 look acceptable.

Poll each run with `genie-get-eval-run` until `eval_run_status` is `DONE` (it advances `num_done`/`num_questions` while `RUNNING`), then compare per-question `assessment` / `assessment_reasons` from `genie-list-eval-results` + `genie-get-eval-result-details`.

> The Beta `genie-*-eval-run` commands may change without notice. Treat absent/changed eval commands as a limitation and fall back to a fixed-question-set loop (`start-conversation` / `ask_genie`) with manual SQL/result comparison, stating that you are approximating native scoring.

All hard rules still hold: get explicit approval before applying edits, changing benchmark definitions, or launching eval runs; make one focused pass; never mutate source data.

## Related Skills

- **`diagnose-genie-agent`** — plan-only root-cause analysis; precede a tuning pass with it when the failure cause is unclear.
- **`optimize-genie-query`** — for query performance/cost issues rather than answer quality.
- **`create-genie-agent`** — initial Agent design and bootstrap.
- **`databricks-metric-views`** — `genie-agent-integration.md` (Metric View design) and `query-patterns.md` (`MEASURE()` query rules). Recommend upstream semantic-model fixes with this skill instead of working around gaps with broad text instructions.
- **`databricks-genie`** — the parent orchestration hub for the full Agent lifecycle (create, query, export, import, migrate) and the verified `serialized_space` field schema; route there for the end-to-end CLI/MCP command surface.
