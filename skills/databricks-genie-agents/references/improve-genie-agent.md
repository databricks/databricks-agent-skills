# Improve a Genie Agent

How to work with an existing Agent room: inspect it, reproduce and diagnose failures, evaluate it against benchmarks, and apply fixes. These are techniques, not a fixed pipeline — **the flow follows the request.** Common entry points:

- *"Why did it answer X wrong?"* → [Inspect](#inspect-the-agent) + [Reproduce](#reproduce-a-failure), [Diagnose](#diagnose-the-failure). Stop there if a diagnosis is all that's wanted.
- *"Fix it"* → diagnose, then [Apply a fix](#apply-a-fix) through the smallest structured surface.
- *"Make it more reliable / raise the score"* → run [Benchmark evaluation](#benchmark-evaluation) for a baseline, then diagnose→fix→re-evaluate in focused passes.

## Ground rules

- **Inspecting and diagnosing is read-only.** Reproduce with the Conversation API, inspect config/feedback, run bounded read-only SQL (`SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, `information_schema`). Don't modify source tables/views/Metric Views or data.
- **Diagnose first, then apply as a separate step.** The diagnostic pass proposes the fix; applying it mutates a live Agent (`update-space`), so do that after the user OKs the *proposed* change (skip only when durably authorized). A request to apply a different fix (e.g. "hardcode it in the instructions") isn't an OK for the one you recommend instead.
- **Fix through the smallest structured surface**, not a text-instruction dump — see [Failure → lever](#failure--lever).
- **One focused pass at a time.** Don't mix benchmark repair/pruning with Agent tuning; re-evaluate after each change.
- **Don't tune against a weak benchmark.** If it's too small or mostly easy questions, recommend [repair](#benchmark-repair--pruning) first: representative, non-trivial questions (including reworded variants of the target failure) with validated ground truth. If the user already described the benchmark (size, difficulty, coverage), flag the gaps in your first response; order an advisory plan as benchmark review → repair → [staged gates](#benchmark-evaluation).
- Prefer concrete evidence (generated SQL, eval output, feedback, profiled data) over generic best-practice advice.

## Inspect the Agent

`databricks genie get-space SPACE_ID --include-serialized-space -o json` — read the full config: sources (tables / Metric Views), per-column descriptions/synonyms/matching/hidden fields, join specs, SQL snippets, example SQL, text instructions, sample questions, and benchmarks.

**Health signals worth flagging while you read:** too many overlapping sources; generic/missing descriptions; categorical filters without entity matching; raw tables exposed together with no join specs; example SQL copied from benchmark answers; a text-instruction rulebook holding logic that belongs in metadata/snippets/joins; a benchmark set that's too small, too easy, too redundant, or missing checked SQL / evaluation notes.

**Feedback (Monitor tab)** is evidence for *clustering* failures, not a fix surface. The aggregate dashboards (thumbs/trends/digest) are UI-only; from the CLI use per-item conversation data and the audit log, and state the limitation:

```bash
databricks genie list-conversations SPACE_ID
databricks genie list-conversation-messages ...   # + list-conversation-comments / list-message-comments
```
```sql
-- audit-log substitute for feedback events (keep the window narrow)
SELECT event_time, user_identity.email, action_name, request_params
FROM system.access.audit
WHERE service_name = 'genie'
  AND action_name IN ('updateConversationMessageFeedback', 'createConversationMessageComment')
  AND event_date >= current_date() - INTERVAL 30 DAYS
ORDER BY event_time DESC LIMIT 200;
```

When conversations are private, use only visible prompt/status/rating/timestamp/trend metadata and lower confidence accordingly.

## Reproduce a failure

Re-run the failing question in the **same mode it failed in**, to see the generated SQL / error firsthand. **Document or mixed questions** (Agent has a volume), and any failure seen in Agent mode: reproduce through the [Agent mode API](query-genie-agent.md#agent-mode-api) with the original `execution_mode` (`STANDARD`/`FLASH`), and read the `function_call` events (`execute_sql`, `search_context_files`). Chat mode ignores volumes, so it would show a missing-context failure rather than the original one. Chat-mode SQL questions: `start-conversation` returns `conversation_id` + `message_id`; **poll `get-message` until `.status` is terminal** (`COMPLETED` / `FAILED` / `CANCELLED`) before reading attachments — `--no-wait` returns before generation finishes, so an immediate read gets empty/partial evidence:

```bash
databricks genie start-conversation --no-wait SPACE_ID "the failing question"   # → {conversation_id, message_id}
# poll until terminal, then inspect:
databricks genie get-message SPACE_ID CONV_ID MSG_ID | jq '{status, error, sql: [.attachments[]?.query.query]}'
```

For a case you're handed, you need: the **question**, the **observed** behavior, and the **expected** behavior (often inferable from context — state the assumption). Take these from the request/context; ask only if a piece is missing and a user is available. See [query-genie-agent.md](query-genie-agent.md) for the full Conversation / Agent-mode API.

## Diagnose the failure

Classify the primary failure (and secondary contributors) from the evidence. The classes below map symptom → cause; each links to the fix lever in the next section.

| Failure class | Symptoms |
|---|---|
| **Wrong source / field** | Wrong table/Metric View/column/measure; raw table used where a Metric View should answer; source omitted. |
| **Wrong Metric View measure / grain** | Wrong `MEASURE()`, invalid grouping, missed persistent filter, wrong time dimension, wrong scope/grain. |
| **Wrong filter value** | Invalid category, wrong code/label, casing mismatch, misunderstood business term. |
| **Wrong join** | Missing table, wrong key, duplicated rows, changed grain, unsupported bridge/self-join. |
| **Business / time logic** | Wrong numerator/denominator/aggregation, fiscal period, date boundary, window, ranking, or answer shape. |
| **Weak Agent-mode report** | Thin research plan, too few supporting queries, unsupported claims, missing citations/tables/caveats, poor synthesis. |
| **Benchmark ground truth** | Invalid/missing SQL answer, unclear Agent evaluation note, multi-step question forced into one SQL answer. |
| **Instruction conflict / overload** | Examples/snippets/instructions conflict, or a long source-specific rulebook in text instructions. |

**Not every failure is a defect.** First decide whether the question is *in scope* for this room. A question about data the room doesn't cover, or unrelated to its domain, is **expected to fail** — the room is deliberately scoped, and stretching it to answer everything dilutes the sources and hurts the questions it's actually for. For out-of-scope failures: leave them, or (if they keep coming up) point the user to the right room or recommend a separate Agent — don't add sources or instructions to chase them. Only in-scope failures (the data is there, the room should answer, but got it wrong) are tuning targets.

Rules: don't count invalid-benchmark or infra/permission failures as Agent-tuning targets (that's benchmark repair or an infra fix). Triage `NEEDS_REVIEW` separately from `BAD`. Don't infer root cause from aggregate accuracy alone. If the case only needs a diagnosis, write up the finding (question, observed/expected, primary cause + contributors, evidence, confidence, recommended surface) and stop — no edit required.

## Failure → lever

Fix through the smallest structured surface that prevents the failure class. Preference order (most governed first): **source scope → source/column descriptions → entity/value matching → Metric View metadata → join specs → SQL snippets / functions → representative example SQL → short global text instruction.**

| Failure | Preferred lever | Avoid |
|---|---|---|
| Wrong source selected | Better source descriptions, names/synonyms, differentiating metadata | "Use table X" text instruction for one case |
| Wrong column | Column description + synonyms; hide confusing columns | Example SQL unless the pattern is complex |
| Wrong Metric View measure | Metric View display names/descriptions, or flag an upstream semantic gap | Duplicating governed measure logic in text |
| Wrong filter value | **Prompt matching** (entity matching / format assistance) + synonyms mapping the user's term to the stored value; column value semantics; reusable filter snippet | **Hardcoding the mapping in a text instruction**; copying a benchmark filter into example SQL |
| Missing business filter | Reusable filter snippet, or metadata stating the default scope | A long instruction list of every filter |
| Wrong join / grain | Join spec **after validating keys + grain** | A join spec based only on name similarity |
| Wrong date field / window | Column descriptions for date roles; snippet for the reusable window | Many date rules in a text instruction |
| Wrong aggregation / ranking | Reusable snippet; one representative example for the shape | Many near-duplicate examples |
| Correct SQL, weak answer prose | Short global response-quality text instruction | Changing SQL surfaces |
| Weak / incomplete Agent report | Source & Metric View descriptions + representative examples that show useful analytic dimensions | A text instruction that scripts one benchmark |
| Document question unanswered / wrong file | Ask via Agent mode (chat ignores volumes); let indexing finish; sharper volume `description` + routing text instruction; dedicated volume | Pasting document content into instructions |
| Unclear Agent benchmark grading | Benchmark repair: add/refine the `evaluation_note` | Agent config tuning |
| Invalid/stale expected SQL, infra/permission | Benchmark repair, or an infra/access fix | Agent config tuning |

**Text instructions come last**, for genuinely global behavior only (disambiguation, caveats, response-quality expectations). If the rule maps to a structured surface (a synonym, prompt matching, a filter snippet), use that instead; an instruction naming specific tables/columns/joins/filters/values is the wrong lever. **Wrong filter values** (e.g. `cancelled` vs the stored code/casing): propose prompt matching / synonyms that map the user's term to the stored value. They cover every phrasing and value, while a hardcoded instruction covers one mapping and drifts as data changes. If asked to "just add it to the instructions", don't apply it in the same pass: explain this, recommend the structured fix, and add the instruction only if the user still wants it after reading why. `text_instructions` holds at most one item.

Enrichments often fix several failures at once — thin/indistinguishable source descriptions, undocumented status/type/segment values, ambiguous date roles (`created_at` vs `closed_at`), missing join specs, repeated logic better expressed as a snippet, or too many sources in one Agent (routing confusion → consider splitting).

## Apply a fix

Edit `genie_agent.json`, validate any new SQL read-only (or `EXPLAIN`) first, then push. `--serialized-space` is a full replacement:

```bash
databricks genie update-space SPACE_ID --serialized-space "$(jq -c . genie_agent.json)"
```

Get the user's OK first when one is in the loop. After applying, re-run the affected question (Reproduce, above) or the benchmark slice (below) to confirm the fix and watch for regressions.

## Benchmark evaluation

Benchmarks turn "is it better?" into a measured answer. Use them when the goal is reliability / a score, not a single-question fix. Benchmarks *evaluate* quality — they don't teach Genie by themselves, and copying their SQL/notes into the Agent's own surfaces is leakage: the score rises without real improvement.

**Real failing questions are the best benchmark source.** When a genuine, in-scope question fails (from feedback, a reproduced failure, or the diagnosis at hand), add it as a benchmark item with the correct answer — that's how a fix gets locked in and future regressions get caught. Harvest these from Monitor feedback and failed conversations; skip out-of-scope failures (see [Diagnose](#diagnose-the-failure)).

**Readiness:** aim for **≥30 valid items** for the target execution mode, a mix of medium/hard questions (not trivial lookups), and coverage across the sources, measures, filters, joins, time logic, and answer shapes that matter. If the set is too small/easy/redundant, do a dedicated [benchmark repair or pruning](#benchmark-repair--pruning) pass **first** (separate from Agent tuning), then re-baseline. If the Agent routes to a governed methodology function, clear the [methodology parity gate](#methodology-parity-gate) first.

**Execution modes:** *Chat* scores SQL/result-set match (needs a checked SQL `answer`); *Agent* judges the whole synthesized response (needs a clear `evaluation_note`). Infer the target from the goal and existing benchmarks; ask only if genuinely ambiguous.

Run via the **Beta** `genie-*-eval-run` CLI:

```bash
# Launch — SCOPE IT. {"benchmark_question_ids":[...]} runs only those.
# ⚠️ empty body {} runs ALL; a MISSPELLED field ALSO runs all (only a warning, no abort) — check the name is exactly benchmark_question_ids.
databricks genie genie-create-eval-run SPACE_ID --json '{"benchmark_question_ids":["<id>", ...]}'
databricks genie genie-get-eval-run SPACE_ID EVAL_RUN_ID      # poll until eval_run_status = DONE (async)
databricks genie genie-list-eval-runs SPACE_ID                # find a prior run for baseline
```

⚠️ `genie-create-eval-run` is **Chat mode only** (compares SQL result sets). For Agent-mode / synthesis questions, use the Agent mode API loop in [query-genie-agent.md § Agent Mode API](query-genie-agent.md#agent-mode-api). Treat absent/changed Beta commands as a limitation and fall back to a fixed-question `start-conversation`/`get-message` loop with manual comparison, stating you're approximating native scoring.

**Inspect results** — pull generated + expected SQL and results from the eval detail (not the Conversation API when an eval run exists):

```bash
databricks genie genie-list-eval-results SPACE_ID EVAL_RUN_ID          # result_id per question
databricks genie genie-get-eval-result-details SPACE_ID EVAL_RUN_ID RESULT_ID
# → actual_response[0].response (generated SQL) + .sql_execution_result; same for expected_response
```

**Stage the gates via `benchmark_question_ids`** so the signal is cheap and clean: (1) the affected failing questions — does the candidate fix the cluster? (2) related previously-passing questions — any regression? (3) full benchmark (empty body `{}`) once 1–2 look good. For mixed goals, compare Chat and Agent runs separately. Track per-question movement: `fixed` (BAD→GOOD), `regressed` (GOOD→BAD), `unchanged`, `excluded` (invalid/infra).

**Keep the candidate** only if it improves the valid score or fixes the target cluster without unacceptable regressions, and the fix holds on reworded variants of the target pattern that weren't used as tuning evidence. Roll back if it only shifts failures, adds syntax/infra issues, or relies on benchmark leakage.

## Methodology parity gate

When the Agent routes to a **registered SQL function** implementing an external methodology (a customer's own measure, an industry-standard calculation, a spec the business already computes elsewhere), validate its **numbers** against that reference **before** benchmarking. Benchmarks measure NL→SQL *routing* accuracy, not the function's math; a correctly routed but wrong function passes and ships wrong answers. (1) Pick the reference (source tool output, published spec, or an independent query). (2) Run both on the same inputs and diff to an agreed tolerance (N-decimal parity for ratios, exact for integer matrices). (3) Only then add benchmark questions that route to it. Author the function with `databricks-dbsql`; whether a measure needs a function at all (vs a Metric View) is decided in `databricks-metric-views` ([metric-view-advisor.md](../../databricks-metric-views/references/metric-view-advisor.md#when-a-metric-view-is-not-the-right-tool--governed-function)).

## Benchmark repair & pruning

A change to benchmark *definitions* only — not source data or Agent surfaces; get the user's OK, keep it a separate pass, then re-baseline.

- **Repair** when <30 valid items, expected SQL is invalid/stale, Agent evaluation notes are missing/unclear, or coverage is too narrow. A valid item = a current, non-trivial question + enough ground truth for its mode.
- **Prune** when the set is too large for practical iteration or full of near-duplicates. Prune by evidence, not a target count: keep questions that cover distinct sources/measures/joins/time-logic/answer-shapes and medium/hard reasoning; drop invalid, stale, or date/category-swap duplicates. Preserve ≥30 valid items unless the user accepts a smaller diagnostic-only set.

**`benchmarks` schema** — a top-level key (not under `instructions`) holding a `questions` array. Each question: unique 32-hex `id`, `question` (string array), `answer` (array of `{format, content}`; `format` must be `"SQL"`; `content` is the SQL string array, or `[]` when there's no canonical SQL), optional `evaluation_note` (string array, Agent-mode grading). `answer` is always required, so a pure Agent-mode question uses `content: []` (cleaner than a `SELECT 1` placeholder; `get-space` returns it as `[{"format": "SQL"}]` and that re-imports fine):

```json
{"benchmarks": {"questions": [
  {"id": "40000000000000000000000000000001", "question": ["Q1 sales by region?"], "answer": [{"format": "SQL", "content": ["SELECT region, SUM(amount) FROM sales WHERE quarter='2026-Q1' GROUP BY region"]}]},
  {"id": "40000000000000000000000000000002", "question": ["What's driving the revenue decline?"], "answer": [{"format": "SQL", "content": []}], "evaluation_note": ["Must investigate multiple dimensions, cite ≥2 queries, name the primary driver with evidence."]}
]}}
```

## Persisting optimization history (optional)

For long-running, auditable multi-pass tuning, you can log runs / config snapshots / per-question results / repair analysis to user-approved Unity Catalog Delta tables. This is optional — the native benchmark output is enough on its own. For the table design and full CREATE TABLE DDL, see [uc-persistence.md](uc-persistence.md).

## See Also

- **[create-genie-agent.md](create-genie-agent.md)** — build a new Agent; the `serialized_space` surfaces you edit here are defined there.
- **[query-genie-agent.md](query-genie-agent.md)** — Conversation API, Agent-mode API, and `MEASURE()` query rules for Metric View sources.
- **`databricks-metric-views`** — for Metric View failures, fix the semantic model here (design rules + `MEASURE()`/`MISSING_AGGREGATION`) rather than working around it with broad instructions.
