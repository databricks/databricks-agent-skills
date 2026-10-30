---
name: mlflow-trace-retrieval
description: Retrieve MLflow traces by ID or search by run, session, user, status, time, tags, feedback, or span fields. Use for trace lookup and filtering; retrieval alone does not require diagnosis.
---

# Retrieve MLflow traces

## Step 1: Select the lookup

Reuse the configured tracking URI, experiment, supplied trace ID or filters, and incident/run time window. Check installed CLI flags with `mlflow traces get --help` or `mlflow traces search --help` for the operation selected.

For Databricks UC traces, first read [Databricks tracing setup](../mlflow-trace-instrumentation/references/databricks.md): trace retrieval requires the configured SQL warehouse and workspace authentication. Do not replace missing warehouse access with direct SQL, raw REST, or pasted tokens.

## Step 2: Fetch or search

With an ID, fetch directly. Save full JSON to a file before parsing so large output is not lost to tool truncation. `get` already outputs JSON; it needs no `--output` flag.

```bash
TRACE_FILE=$(mktemp)
mlflow traces get --trace-id <TRACE_ID> > "$TRACE_FILE"
```

Without an ID, search the selected experiment and requested time window:

```bash
SEARCH_FILE=$(mktemp)
mlflow traces search --experiment-id <EXPERIMENT_ID> \
  --filter-string 'metadata.`mlflow.trace.session` = "<SESSION_ID>" AND trace.timestamp_ms >= <START_MS> AND trace.timestamp_ms <= <END_MS>' \
  --order-by 'timestamp_ms ASC' --max-results 50 --no-include-spans --output json > "$SEARCH_FILE"
```

- Replace placeholders before execution. Every UC search needs a `trace.timestamp_ms` lower bound; add an upper bound when known.
- Experiment/run/session lookups also need time bounds: a small result limit does not bound a table scan.
- Use the user's historical window or incident/run timestamps, never silently the last hour. Ask for the period if unknown before a broad UC search.

### Filters

Combine predicates with `AND`; verify operators supported by the installed backend/version.

| Selection | Predicate or flag |
|---|---|
| Run | `--run-id <RUN_ID>` (combine with time bounds) |
| Status | `trace.status = 'ERROR'` (`OK`, `IN_PROGRESS` also available) |
| Time / latency | `trace.timestamp_ms >= 1700000000000`, `trace.execution_time_ms > 1000` (milliseconds) |
| Session / user | ``metadata.`mlflow.trace.session` = 'abc'``, ``metadata.`mlflow.trace.user` = 'user1'`` |
| Tags / metadata | `tag.environment = 'production'`, ``metadata.`user.id` = 'abc'`` |
| Span | `span.name = 'lookup'`, `span.type = 'RETRIEVER'` |
| Assessments | `feedback.rating = 'positive'`, `expectation.<name> = <value>` |
| Text | `trace.text LIKE '%error%'` |

Backticks quote special characters in field names. In shell commands put the outer expression in **single quotes**, as above, or escape backticks inside double quotes to prevent command substitution. Escape filter values separately; do not interpolate untrusted values as shell syntax. `LIKE`, `ILIKE` and `RLIKE` support pattern matching where permitted; use [search docs](https://mlflow.org/docs/latest/genai/tracing/search-traces.md) for exact field/operator support.

Use `--no-include-spans` for ID and metadata searches, then fetch selected IDs when details are needed. `--extract-fields` filters client-side after retrieval and does not reduce data transferred through a UC warehouse. Follow returned continuation tokens with `--page-token` while keeping filters/order fixed; report a bounded sample as a sample, not all matches.

### Python alternative

```python
trace = mlflow.get_trace(trace_id)
# Or search when the ID is unknown:
traces = mlflow.search_traces(
    locations=[experiment_id],
    filter_string=f"trace.timestamp_ms >= {start_ms} AND trace.timestamp_ms <= {end_ms}",
    max_results=50, return_type="list", include_spans=True,
)
```

Check installed signatures; older versions may use `experiment_ids`. `search_traces()` has **no `start_time` keyword**. Use `filter_string` for timestamp predicates.

## Verification

- For setup readback, record the time immediately before the run; follow [setup verification](../mlflow-trace-instrumentation/guide.md#verification) when available.

Confirm returned IDs, experiment/location, window and filters match the request; distinguish no matches from a failed query or partial page. Return the IDs/output file and any coverage limits. Do not infer quality from status `OK` alone.

For newly added instrumentation only: enforce a **60-second wall-clock deadline** including flush/readback/internal retries, terminating the command at expiry. Fetch one captured ID or make one run-time-bounded search with `max_results=1`. Inspect expected spans and actual inputs/outputs; retry at most once after a quick concrete fix within the original budget. Stop on auth/provider-key/permission/warehouse blockers and report the failed operation and required prerequisite. No parallel searches, repeated agent runs, direct SQL, raw REST or alternate-auth fallbacks. This setup limit does not replace the scope of a dedicated retrieval/investigation request.

## References

- Additional search syntax/API options: [official search guide](https://mlflow.org/docs/latest/genai/tracing/search-traces.md), checked against installed help/signatures. Use [llms.txt](https://mlflow.org/docs/latest/llms.txt) only if the page moves; if unavailable, use installed help and stop when correctness is unresolved.
- When analysis is requested, use [trace analysis](../mlflow-trace-analysis/guide.md); retrieval alone stops with the requested evidence.
