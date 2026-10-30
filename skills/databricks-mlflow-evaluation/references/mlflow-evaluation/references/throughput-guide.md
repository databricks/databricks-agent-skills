# Evaluation throughput

Read when pilot measurements show the full evaluation needs concurrency tuning. Estimate runtime from the
**actual pilot**, dataset size, selected scorers, and rate limits; do not assume a fixed latency from a model
family. Report the estimate and budget before starting.

## Bound concurrency

`mlflow.genai.evaluate()` uses internal thread pools. Inspect the installed MLflow environment-variable
definitions for supported settings/defaults; do not invent a `max_workers` function parameter.

| Variable | Purpose |
| --- | --- |
| `MLFLOW_GENAI_EVAL_MAX_WORKERS` | Concurrent data items |
| `MLFLOW_GENAI_EVAL_MAX_SCORER_WORKERS` | Concurrent scorers per item |
| `MLFLOW_GENAI_EVAL_ASYNC_TIMEOUT` | Async predictor timeout in seconds |
| `MLFLOW_GENAI_EVAL_ENABLE_SCORER_TRACING` | Scorer execution tracing for diagnostics |
| `MLFLOW_GENAI_EVAL_SKIP_TRACE_VALIDATION` | Version-dependent suppression of predictor trace validation |

Each data worker may run up to `min(scorer workers, scorer count)` scorer calls, so peak scorer calls are
roughly their product, plus the agent's own model/tool calls. Tune within provider and host resource limits.
On rate limits reduce workers before retrying. Registration enables reuse; it does not intrinsically improve
execution reliability.

Do not skip trace validation until the real predictor's tracing has been verified and the installed flag
semantics understood. Do not claim it saves N calls without measurement. Changing to a cheaper judge changes
the measurement: validate agreement first, and keep the judge fixed for comparisons.

## Async and process isolation

Use an async predictor only if the application already supports it:

```python
async def predict(query):
    return await agent.arun(query)
```

Keep the same kwargs/data contract and set a bounded timeout appropriate to measured latency. Do not call
`evaluate()` concurrently from multiple threads in one process; use its internal concurrency or separate
processes.

Shard only when necessary. Each process must have the same dataset/scorer versions and intended experiment,
disjoint row IDs, isolated artifact/log paths, and a bounded share of total concurrency. Record each shard's
run ID, exit status, and row count. Wait for every shard, inspect failures, then combine row-level outputs by
stable IDs; verify no omitted/duplicated rows. Do not average shard means without accounting for denominators
or hide failed shards.

### Small sharding example

Minimal sequential recipe: fixed precomputed `records` with unique `expectations.source_id`, agreed single-numeric-output `scorers`, no active run.
MLflow 3.17.1 column names are shown; verify installed output schema and apply the coverage/error safeguards above before aggregation.

```python
import mlflow
import pandas as pd

parts = []
for start in range(0, len(records), 100):
    result = mlflow.genai.evaluate(data=records[start:start + 100], scorers=scorers)
    parts.append(result.result_df.assign(shard_run_id=result.run_id))
combined = pd.concat(parts, ignore_index=True)
ids = combined["source_id/value"]
assert ids.is_unique and set(ids) == {r["expectations"]["source_id"] for r in records}
scores = combined[[f"{s.name}/value" for s in scorers]].apply(pd.to_numeric, errors="raise")
assert scores.notna().all().all(), "Inspect missing/error assessments"
print(scores.agg(["count", "mean"]))  # Row-weighted, including valid zero/False.
```

Each `evaluate()` call creates its own run. Do not execute shards concurrently against one active run.

Use the host-supported execution method; no background subagent is required. Completion means the process
exited successfully and the run/artifacts and scoring coverage were verified. Keep stdout separate from stderr
when parsing structured output.
