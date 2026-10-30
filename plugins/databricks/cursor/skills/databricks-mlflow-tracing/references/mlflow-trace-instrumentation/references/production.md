# Production tracing configuration

Reuse deployment identity and configuration: `MLFLOW_TRACKING_URI`, actual `MLFLOW_EXPERIMENT_ID` (or supported name), and existing secret mechanisms. Databricks also needs [UC setup](databricks.md); local success does not verify deployed permissions.

For authenticated OSS servers, inject `MLFLOW_TRACKING_USERNAME`/`MLFLOW_TRACKING_PASSWORD` or `MLFLOW_TRACKING_TOKEN` through the deployment secret mechanism.

## Async export and shutdown

Python trace export uses `MLFLOW_ENABLE_ASYNC_TRACE_LOGGING=true`, not `MLFLOW_ENABLE_ASYNC_LOGGING` or `mlflow.config.enable_async_logging`. Check version/runtime defaults in [production docs](https://mlflow.org/docs/latest/genai/tracing/prod-tracing.md#asynchronous-trace-logging).

Controls include `MLFLOW_ASYNC_TRACE_LOGGING_MAX_WORKERS`, `MLFLOW_ASYNC_TRACE_LOGGING_MAX_QUEUE_SIZE` and `MLFLOW_ASYNC_TRACE_LOGGING_RETRY_TIMEOUT`. Full queues and exhausted retries can discard traces; monitor export errors.

Flush on graceful shutdown: Python `mlflow.flush_trace_async_logging()`, TypeScript `await mlflow.flushTraces()`. Abrupt exit can bypass hooks. Setup flush/retries remain within the [60-second readback deadline](../guide.md#verification).

## Sampling

`MLFLOW_TRACE_SAMPLING_RATIO=0.1` samples roughly 10% of traces in supported runtimes, retaining each selected trace's spans. Missing smoke-test traces may be sampled out; aggregate counts describe sampled traffic. Ensure an authorized isolated verification request is sampled without changing production-wide settings.

For lightweight SDK/deployment options use the [production guide](https://mlflow.org/docs/latest/genai/tracing/prod-tracing.md); instrumentation stays in [Python](python.md) / [TypeScript](typescript.md).
