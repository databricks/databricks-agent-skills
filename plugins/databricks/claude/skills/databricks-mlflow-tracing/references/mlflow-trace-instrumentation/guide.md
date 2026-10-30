---
name: mlflow-trace-instrumentation
description: Add or repair MLflow tracing in Python or TypeScript applications, including tracing required for evaluation. Covers framework autologging, custom spans, backend setup, and persisted trace verification.
---

# Instrument MLflow tracing

Reuse working tracing for investigation or evaluation.

## Prerequisites

- Check entry point, language/framework, SDK version, tracking URI, experiment, and deployment identity.
- Preserve destinations and providers. Explicit application destinations override inherited environment values; assistant telemetry may use another experiment.
- Read [Python](references/python.md) or [TypeScript](references/typescript.md) for the runtime.

## Step 1: Check the destination (Databricks only)

For OSS or SageMaker, keep the configured backend and proceed to Step 2.

- Read [UC setup](references/databricks.md) **before editing**; validate auth/workspace.
- Reuse the explicit destination; otherwise resolve schema choice before provisioning.
- Discover an accessible warehouse automatically. Default to UC; legacy storage requires an explicit request.

## Step 2: Enable framework tracing

- Enable the matching integration before execution. LangGraph uses `mlflow.langchain.autolog()`, not `mlflow.langgraph.autolog()`.
- Do not wrap automatically traced nodes, tools, or models again. Reserve manual spans for uncaptured work or an outer application boundary.

## Step 3: Capture application work

- Trace meaningful root, LLM, retrieval, tool, routing, and external I/O (files/queues).
  Skip utility, configuration, and logging noise.
- Capture actual relevant inputs/outputs explicitly for manual spans; redact before export.

## Step 4: Run one request

- Run one representative request; record start/end epoch milliseconds.
- Save its trace ID immediately in-process: `mlflow.get_last_active_trace_id()` in Python; the active span's ID in TypeScript.
- Write/flush the trace ID to a file or captured stdout before readback; retain it if the process is cancelled.
  Do not rerun to recover an ID.

<a id="verification"></a>

## Verification

- Fetch a **persisted application trace**, not a local span or old trace.
- Set a **60-second wall-clock process deadline** for readback, including flush, SDK retries, requests, and backoff.
  Terminate at expiry unless the user explicitly requests deeper troubleshooting.
- Tool yields/thread-wait timeouts do not cancel calls. Without cancellation, report backend verification as unperformed.

- Flush once (`mlflow.flush_trace_async_logging()` / `await mlflow.flushTraces()`); fetch the saved ID.
- Without an ID, search once in the configured experiment with run-time bounds, `max_results=1`, and spans included.
- Every UC search needs `trace.timestamp_ms`; result limits do not bound scans. Python `search_traces()` has no `start_time` keyword.

For Python readback, put this recipe in a separate `verify_trace.py` process. Pass the saved
trace ID and run-time bounds to it through arguments or a file:

```python
mlflow.flush_trace_async_logging()
if trace_id:
    trace = mlflow.get_trace(trace_id)
else:
    traces = mlflow.search_traces(
        locations=[experiment_id],
        filter_string=(f"trace.timestamp_ms >= {run_start_ms} "
                       f"AND trace.timestamp_ms <= {run_end_ms}"),
        max_results=1, return_type="list", include_spans=True,
    )
    trace = traces[0] if traces else None
assert trace is not None, "No persisted trace read back"
assert run_start_ms <= trace.info.request_time <= run_end_ms
assert trace.data.spans, "No spans captured"
```

Invoke the readback process with an actual deadline. `subprocess.run` terminates the child
on timeout; checking elapsed time after a blocking MLflow call does not:

```python
import subprocess
import sys

try:
    subprocess.run([sys.executable, "verify_trace.py"], timeout=60, check=True)
except subprocess.TimeoutExpired:
    print(f"Trace {trace_id}: persisted readback unverified after 60 seconds")
```

- Inspect expected root/graph, model, retrieval, and tool spans and actual I/O. Confirm the application's request, not scorer or assistant telemetry.
- Check experiment/location from returned metadata, or the bound UC location if no experiment ID exists.
- Reuse returned spans; stop after success.

- Retry at most once after a concrete quick fix **within the original budget**.
- Stop on missing provider keys, auth/permission errors, warehouse timeouts, or `RESOURCE_EXHAUSTED`/429.
- No parallel searches, repeated agent runs, direct UC SQL, raw REST, alternate credentials, or warehouse fallbacks.
- Report operation/error, captured ID, successes, and unverified results. Request the missing prerequisite, not secrets.
- Keep instrumentation changes if backend verification is blocked; pause evaluation until tracing is verified.

Return the verified trace ID/link and observed spans. For Databricks use the [verified trace URL rules](references/databricks.md#link-to-the-verified-trace), not an experiment-only link. Do not label an unverified link as proof.

## References

- Deployment, async export, sampling: [production](references/production.md).
- Async/thread context, redaction, caught errors or links: [advanced patterns](references/advanced-patterns.md).
- Cross-service parent propagation: [distributed tracing](references/distributed-tracing.md).
- User ratings tied to traces: [feedback collection](references/feedback-collection.md).
- Unreadable non-chat root previews: [root span previews](references/root-span-previews.md).
- Explaining captured behavior: `mlflow-trace-analysis`; implementing a requested behavior fix: `mlflow-agent-improvement`, carrying the trace evidence. These are optional follow-on tasks.

- Other integrations: [automatic tracing docs](https://mlflow.org/docs/latest/genai/tracing/app-instrumentation/automatic.md). Check installed signatures/types.
- Missing/moved topic: [llms.txt](https://mlflow.org/docs/latest/llms.txt). Docs unavailable: use local recipes and installed API introspection; stop if correctness remains uncertain.
