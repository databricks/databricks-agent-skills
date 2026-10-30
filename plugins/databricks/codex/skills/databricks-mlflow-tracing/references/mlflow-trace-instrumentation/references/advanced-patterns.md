# Advanced tracing patterns

## Async and thread context

`@mlflow.trace` supports `async def`; ordinary asyncio tasks copy context automatically. Threads need an explicit context copy **per submitted task**, taken inside the active parent span. Sharing one `Context` across concurrent workers raises errors.

```python
import contextvars
from concurrent.futures import ThreadPoolExecutor
import mlflow

@mlflow.trace
def process_items(items):
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(contextvars.copy_context().run, process_one, item)
                   for item in items]
        return [future.result() for future in futures]
```

Here `process_one` is the application's traced worker. For `run_in_executor`, take the copy after entering the parent span, then pass `ctx.run` and the worker to the executor. Inspect persisted parent/child IDs to verify linkage. See [threading](https://mlflow.org/docs/latest/genai/tracing/app-instrumentation/manual-tracing.md#multi-threading) and [async examples](https://mlflow.org/docs/latest/genai/tracing/app-instrumentation/manual-tracing.md#async-support) for runtime-specific variants.

## Redact before export

Inspect actual data shapes and privacy requirements before capturing sensitive inputs/outputs. Use the installed version's public processing API; current MLflow documents `mlflow.tracing.configure(span_processors=[processor])`, where a processor mutates a span via public setters before export. Do not mutate private `_inputs` / `_outputs` fields.

Read [the registered email-redaction example](https://mlflow.org/docs/latest/genai/tracing/observe-with-traces/masking.md#example-1-redacting-e-mail-address) for the supported API. Validate redaction on representative nested dictionaries, lists, string payloads, outputs, attributes and exception events that the application records. A sample email regex is not blanket PII protection. Confirm sensitive values are absent in persisted traces; if the required hook is unavailable, do not export sensitive data while guessing an alternative.

After selecting the tracking backend, register this processor for JSON-shaped inputs/outputs; extend the key set for your schema:

```python
import mlflow

SECRET_KEYS = {"password", "api_key", "token", "secret", "credentials"}

def redact(value):
    if isinstance(value, dict):
        return {k: "[REDACTED]" if k.casefold() in SECRET_KEYS else redact(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value

def redact_span(span):
    span.set_inputs(redact(span.inputs))
    span.set_outputs(redact(span.outputs))

mlflow.tracing.configure(span_processors=[redact_span])
```

This masks named fields, not secrets embedded in free text, attributes or events; validate those separately before export.

## Attributes, errors and links

- Attach custom attributes to the existing active span with `set_attribute` / `set_attributes`. Search support for arbitrary span attributes varies; do not assume `attribute.<key>` is a valid trace-search predicate. Use supported metadata/tag filters when cross-trace filtering is needed.
- Unhandled exceptions are captured by tracing. If code catches an error and returns a fallback, deliberately record the failure/status using the installed [LiveSpan API](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.entities.html#mlflow.entities.LiveSpan), preserving application behavior and avoiding secret-bearing error text. A successful fallback is not evidence that every child operation succeeded.
- A custom `linked_trace_id` attribute is just metadata, not actual parent propagation or an OTel span link. Follow the [span-link examples](https://mlflow.org/docs/latest/genai/tracing/app-instrumentation/manual-tracing.md#span-links) for causal links and [distributed tracing](distributed-tracing.md) for cross-service parent continuity. Keep application retries bounded; tracing does not justify recursive retries.

If docs are unavailable, inspect installed signatures and preserve the local constraints above; report a blocker when the required behavior cannot be established.
