# Trace metrics wire reference

`POST /api/3.0/mlflow/traces/metrics` — check server/version support.

## Views, metrics and dimensions

| View (wire code) | Metric | Typical aggregation | Dimensions |
|---|---|---|---|
| TRACES (1) | `trace_count` | COUNT | `trace_name`, `trace_status` |
| TRACES (1) | `latency` (ms) | AVG, PERCENTILE | same |
| TRACES (1) | `input_tokens`, `output_tokens`, `total_tokens` | SUM, AVG, PERCENTILE | same |
| TRACES (1) | `total_cost`, `session_count` | SUM, AVG | same |
| SPANS (2) | `span_count` | COUNT | `span_name`, `span_type`, `span_status` |
| SPANS (2) | `latency` (ms) | AVG, PERCENTILE | same |
| ASSESSMENTS (3) | `assessment_count` | COUNT | `assessment_name`, `assessment_value` |
| ASSESSMENTS (3) | `assessment_value` | AVG, PERCENTILE for numeric scores | same |

Codes: COUNT=1, SUM=2, AVG=3, PERCENTILE=4, MIN=5, MAX=6.

`P95` → `{"aggregation_type": 4, "percentile_value": 95}` (0–100). Bare `PERCENTILE` lacks the required value. The helper does not validate metric/aggregation combinations.

## Filters and time

Metrics filter syntax (different from trace search):

```text
trace.status = "OK"
trace.tag.<key> = "<value>"
trace.metadata.<key> = "<value>"
span.name = "<value>"
span.type = "LLM"
assessment.name = "<value>"
```

Bounds: epoch milliseconds; interval: seconds (`3600` = hourly). Buckets require both bounds; use timezone-aware timestamps. `-f` splits commas; send a filter array for values containing commas.

## Request

```json
{
  "experiment_ids": ["1"], "view_type": 1, "metric_name": "total_tokens",
  "aggregations": [{"aggregation_type": 2}],
  "dimensions": ["trace_name"], "filters": ["trace.status = 'OK'"],
  "start_time_ms": 1737244800000, "end_time_ms": 1737331200000,
  "time_interval_seconds": 3600, "max_results": 1000
}
```

## Response (bucketed example)

```json
{
  "data_points": [{
    "metric_name": "total_tokens",
    "dimensions": {"trace_name": "chat", "time_bucket": "2025-01-19T00:00:00+00:00"},
    "values": {"SUM": 1500.0}
  }],
  "next_page_token": "<next-page-token>"
}
```

`data_points: []` ≠ measured zero. Optional `next_page_token` means partial results; helper cannot continue. HTTP timeout: 30s; no credentials.
