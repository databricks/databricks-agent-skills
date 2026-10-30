# Score production traces on Databricks

Apply registered scorers to a sample of production traces on Databricks. Set up and verify the trace destination with the [bundled tracing guide](../../../../databricks-mlflow-tracing/references/mlflow-trace-instrumentation/guide.md) first.

## Configure

1. Confirm the experiment, workspace/profile, scorer owner, expected traffic, and a SQL warehouse for Databricks monitoring. Discover a usable warehouse through the authenticated workspace; ask the user only if none is available. Set `MLFLOW_TRACING_SQL_WAREHOUSE_ID` when the installed setup requires it. Confirm warehouse access before registration.
2. Run each scorer on a small, representative trace set. Check quality, latency, cost, and serialization. Built-ins and deterministic checks can often sample more traffic than expensive LLM judges. For custom scorers, verify imports and type annotations serialize in the target environment.
3. Register the scorer to the intended experiment, then **start** it with an explicit sampling configuration. Registration alone does not begin online scoring. Use `mlflow.genai.scorers`' installed `ScorerSamplingConfig` and scorer lifecycle methods; inspect signatures and current docs before running because they change across versions.
4. Emit a test trace, wait for asynchronous scoring, and confirm an assessment from the registered scorer appears on that trace. Check the sample rate and any assessment errors. Increase traffic gradually only after this verification.

## Operate

List registered scorers and their states, retrieve a named scorer, and update its sample rate deliberately. To pause scoring while keeping registration, stop it. Delete the registration only when it is no longer needed. Keep an aligned judge's version associated with its monitoring period; comparing raw scores across judge revisions is misleading. Use the [bundled trace-metrics guide](../../../../databricks-mlflow-tracing/references/mlflow-trace-metrics/guide.md) for aggregated quality and cost trends on supported OSS servers, and inspect the underlying traces for failures.
