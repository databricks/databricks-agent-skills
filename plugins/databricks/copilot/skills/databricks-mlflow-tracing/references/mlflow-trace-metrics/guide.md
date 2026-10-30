---
name: mlflow-trace-metrics
description: Query aggregate MLflow trace, span and assessment metrics for latency, tokens, counts and quality trends. Use for operational summaries rather than individual-trace diagnosis.
---

# Query MLflow metrics

Reuse server, experiment IDs and requested window. Select the exact metric, view, aggregation and grouping needed; token counts are not currency cost.

## Prerequisites

For aggregate queries, read the [metrics API reference](references/api_reference.md). If the task also needs individual traces, read [trace retrieval](../mlflow-trace-retrieval/guide.md) before searching; if unavailable, use the [search guide](https://mlflow.org/docs/latest/genai/tracing/search-traces.md).

## Step 1: Check the client

Resolve `scripts/fetch_metrics.py` relative to this guide; use `--help` for flags. The metrics endpoint and helper are not supported for Databricks-managed tracking. For OSS they accept HTTP(S), not `databricks://` profiles, and add no authentication headers. Use an existing supported authenticated client or report the blocker; never convert a Databricks profile to a workspace URL or request pasted tokens.

## Step 2: Choose metrics

Select TRACES (default), SPANS or ASSESSMENTS using [the API reference](references/api_reference.md). Use COUNT for entities, SUM for tokens, AVG/P95 for distributions. Do not silently substitute metrics.

## Step 3: Query the time window

Query explicit bounds: epoch milliseconds, timezone-qualified ISO timestamps, `now`, or relative values like `-24h`. Buckets are **seconds** and require both bounds.

```bash
python <GUIDE_DIR>/scripts/fetch_metrics.py -s <SERVER> -x <EXPERIMENT_ID> \
  -m total_tokens -a SUM -t 3600 --start-time="-24h" --end-time=now -o json
```

Latency: `-m latency -a AVG,P95 -d trace_name`. Numeric quality: `-v ASSESSMENTS -m assessment_value -a AVG -d assessment_name`. Status counts: `-m trace_count -a COUNT -d trace_status`. Keep the same explicit window.

## Verification

Inspect actual `metric_name`, dimensions and values; report exact experiment/window, metric, aggregation, units, filters and coverage. Empty `data_points` is not zero usage; absent token instrumentation can undercount. Quality summaries need per-scorer scales and valid/error/missing denominators: zero/false can be valid, scorer failures are not zero scores, and unrelated scorers should not be averaged.

A `next_page_token` means partial results; the helper exposes it but cannot fetch subsequent pages. Use an existing pagination-capable client or disclose incompleteness. Counts by status are not an error rate: derive ERROR / all statuses only with a complete stated denominator. Distinguish request/auth failures from empty results. Aggregates need representative trace evidence for causal diagnosis.

## References

[API reference](references/api_reference.md): wire fields, metric/view compatibility and metrics-specific filters.
