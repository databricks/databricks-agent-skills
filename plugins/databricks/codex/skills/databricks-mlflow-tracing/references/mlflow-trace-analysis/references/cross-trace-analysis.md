# Compare multiple traces

Use [trace retrieval](../../mlflow-trace-retrieval/guide.md) to select a time-bounded sample, then read [trace structure](trace-structure.md) for field meanings. Aggregate trends with [trace metrics](../../mlflow-trace-metrics/guide.md); use this guide to explain which spans caused them.

## Find the failure pattern

Group traces by status, agent version, prompt URI, session, and relevant tags. Compare failing traces with successful traces for the same input class. Check retrieval results, tool selection, LLM inputs/outputs, retries, and handoffs in execution order.

For multi-agent systems, identify each agent or stage from actual span names and attributes; do not assume a fixed framework schema. Compare component outcomes across traces to locate where errors first diverge. Record representative trace IDs, the affected component, the observed failure, and the expected behavior in a short report. Use `databricks-mlflow-evaluation` to turn a recurring failure into a regression test.

## Profile performance

Compare latency distributions by span type and normalized component name, excluding wrapper spans that merely enclose child work. Account for parallel spans: summing child durations can exceed wall-clock time. Use [trace metrics](../../mlflow-trace-metrics/guide.md) to check whether the bottleneck seen in representative traces is prevalent across traffic.

For recurring failures, preserve representative trace IDs and hand them to `databricks-mlflow-evaluation` for regression dataset curation.
