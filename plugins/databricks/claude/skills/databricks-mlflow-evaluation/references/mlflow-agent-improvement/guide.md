---
name: mlflow-agent-improvement
description: >-
  Fix or change an AI agent's behavior using MLflow traces and regression tests.
  Use for wrong answers, missing tool calls, new business rules, or context and
  token-cost optimization. Diagnose first, prove a regression fails, implement
  the smallest fix, and verify it passes without breaking existing behavior.
---

# Fix agent behavior

Reuse the user's expected behavior, applicable conditions, trace IDs/diagnosis, project configuration, and
existing tests. Both bugs and new business rules require **EXPLORE → PLAN → IMPLEMENT → VERIFY**.
Diagnosis-only requests belong to the [bundled trace-analysis guide](../../../databricks-mlflow-tracing/references/mlflow-trace-analysis/guide.md); do not infer permission to change behavior from a request to
explain a trace.

Preserve the configured MLflow backend, experiment, and judge model. Use the project environment. Fetch exact
[regression-testing docs](https://mlflow.org/docs/latest/genai/eval-monitor/regression-testing.md) when API
details are needed and check the installed MLflow version/signatures. Use
[llms.txt](https://mlflow.org/docs/latest/llms.txt) only for missing/moved pages. If docs or sibling skills
are unavailable, use the local recipe and installed introspection; report a blocker if correctness cannot be
established, without silently replacing APIs/backend/provider.

- For multiple reported issues, repeat the loop per issue: one diagnosis and targeted change at a time.

## Step 1: Explore: trace-grounded diagnosis before edits

Consume an existing diagnosis; otherwise use the [bundled trace-analysis guide](../../../databricks-mlflow-tracing/references/mlflow-trace-analysis/guide.md). Fetch the full trace (`mlflow
traces get --trace-id <ID>`, stderr separate from JSON) and inspect LLM instructions/messages, emitted tool
calls, tool arguments/results, retrieval/filtering, and required tools that never ran. For multi-turn issues
inspect preceding turns too. If tracing is missing, use the [bundled tracing guide](../../../databricks-mlflow-tracing/references/mlflow-trace-instrumentation/guide.md) and
verify a real persisted trace before diagnosis.

Include existing `mlflow.notes`. Persist the user's complaint verbatim as a HUMAN assessment with
`mlflow.log_feedback(trace_id=..., name="user_review", value=False, rationale=...,
source=mlflow.entities.AssessmentSource(source_type="HUMAN", source_id=...))`; do not invent a complaint for a
new requirement.

State what the agent actually did, what it should do, and the evidenced root-cause hypothesis: missing
capability/tool, missing retrieval/data, wrong routing, wrong instruction, inaccessible knowledge, or a
misaligned reward. Do not edit agent code in this phase. A missing knowledge source calls for access to data,
not facts hardcoded into the system prompt.

## Step 2: Plan: write and run the failing regression

Infer global/conditional scope from the request and existing tests; clarify unresolved boundaries only.
Conditional changes need cases where the behavior **must not fire**; restrictive fixes need a legitimate
positive control. Resolve ambiguous edge verdicts before encoding them.

Extend the existing module/behavior suite using the project's test layout; avoid one file per issue. Name
cases `test_should_<guarantee>_when_<condition>` (omit the condition for global rules); paired controls should
make the flipped boundary clear. Parametrized cases need meaningful IDs because they appear as
`mlflow.test.case_id`.

Use pytest with `@mlflow.test` and `mlflow.genai.evaluate(...)`, then `assert result.passed, result.reason`.
Enable `mlflow.pytest.plugin` **once**, through `pytest_plugins = ["mlflow.pytest.plugin"]` in root
`conftest.py`, pytest configuration, or `-p mlflow.pytest.plugin`. Without it the marker raises. Install
missing pytest with the project installer; independently check `pytest-xdist` only when parallel runs are
needed. Read [regression-test-suite.md](references/regression-test-suite.md) for the concrete recipe.

Tests must invoke the **production build/invoke path**, including its actual tracing enablement. Do not
redeclare autologging or decorators in tests to manufacture traces. If tests bypass entrypoint-only
instrumentation, move enablement into the shared application build/invoke path. Destination routing may live
in the harness. Verify one nested application trace rather than disconnected top-level model traces.

Choose assertions from the user's intent, before choosing the fix:

- Use deterministic native checks / `@scorer` for exact values, patterns, formats, and structural tool
  results. `RegexMatch` covers contains/format checks; there are no generic
  `Contains`/`Excludes`/`Matches`/`Equals` scorers to invent. Verify installed constructors; `Correctness` is
  a judge, not a free deterministic equality check.
- For semantic behavior, retain a judge such as `Guidelines` even if a deterministic implementation fixes the
  observed instance. Guidelines need inputs plus outputs; lead their text with a prescriptive “should”/“must”
  requirement. Use `ExpectationsGuidelines` with per-row `expectations.guidelines` when appropriate.
- Assert at the changed layer too: direct tool tests or a scorer inspecting `trace.search_spans()` should
  prove a retrieval/tool restriction, independently of the final answer. Keep semantic coverage above it, with
  varied boundary phrasings for disclosure/safety fixes.
- Resolve the judge model from `MLFLOW_GENAI_JUDGE_DEFAULT_MODEL`, project config, or existing scorers/tests.
  Ask only if none is selected. Reuse one resolvable `provider:/model`; skip judge setup for all-deterministic
  suites. Do not invent a model or introduce another provider.
- `predict_fn` receives the nested record's `inputs` unpacked as kwargs. Return bool, numeric, or
  `"yes"`/`"no"` assessments; zero/False are valid failures, not missing scores.

**Actually run the regression against the unchanged agent and observe failure for the reported behavior.**
Import/auth/scorer errors are not a reproduced behavior failure. If it already passes, improve the
reproduction or explain that the issue was not reproduced; do not assert a fail-before result you never
observed.

Record the diagnosed layer, intended files, verification command, and regression risk before changing the
agent.

## Step 3: Implement: smallest fix at the diagnosed layer

Read callers and fix the shared cause: add missing tool/retrieval access, repair routing, or minimally change
a genuinely wrong instruction. A tool change needs its own functional assertion. Do not hardcode a
per-question response, rewrite unrelated prompts, or loosen the agreed rubric to make the implementation pass.

- A new tool needs its schema, implementation, and tool-span tracing wired into the production path.

## Step 4: Verify: execute unchanged tests after the fix

Run the new regression and relevant pre-existing suite through the production path and enabled plugin. Confirm
the same regression now passes and controls remain green. If a test fails, inspect the new trace and return to
diagnosis; do not change tests in VERIFY. A genuinely incorrect rubric requires an explicit return to PLAN,
not a quiet relaxation.

- If previously passing behavior breaks, consider reverting the change and fixing a different layer.

Fetch and read at least one **fresh persisted trace**: verify the intended tool/retrieval path and answer, not
just the judge's score. Present that evidence for user inspection. If confirmation is still pending, report it
separately from tests passed; do not claim the user approved a trace they have not seen.

## Verification

Report the diagnosis, changed files, exact commands and observed fail-before/pass-after results, existing-test
outcome, and fresh trace ID/URL. State missing verification honestly. Completion requires passing regressions,
no regressions in previously passing cases, and user confirmation of the fresh behavior. After three
nonconverging iterations on one test, stop and propose a different root-cause hypothesis.

## References

- Plugin setup, paired tests, and bounded parallel execution:
  [regression-test-suite.md](references/regression-test-suite.md).
- Excess context, tokens, latency, or context-window failures:
  [context-optimization.md](references/context-optimization.md); preserve quality under a fixed evaluation
  while reducing cost.
- Dataset-scale comparisons: use the [bundled evaluation guide](../mlflow-evaluation/guide.md); keep dataset and judge versions fixed across
  before/after runs.
- New scorer design or human disagreement: use the [bundled evaluation guide](../mlflow-evaluation/guide.md); reuse agreed criteria rather than
  restarting its interview.
