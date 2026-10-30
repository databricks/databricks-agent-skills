# Distributed tracing

- For one connected trace, initialize both services with the same backend and experiment ([Python](python.md), [Databricks](databricks.md)). Check both deployed identities can export.

## Propagate the active context

On the client, obtain headers inside the active span and send them with the request:

```python
from mlflow.tracing import get_tracing_context_headers_for_http_request

with mlflow.start_span("client-request") as span:
    span.set_inputs(payload)
    response = requests.post(
        service_url, json=payload,
        headers=get_tracing_context_headers_for_http_request(), timeout=30,
    )
    response.raise_for_status()
    span.set_outputs(response.json())
```

On the server, restore headers **before creating the handler span**:

```python
from contextlib import nullcontext
from flask import Flask, request
import mlflow
from mlflow.tracing import set_tracing_context_from_http_request_headers

app = Flask(__name__)

@app.post("/handle")
def handle_request():
    payload = request.get_json()
    context = (set_tracing_context_from_http_request_headers(dict(request.headers))
               if request.headers.get("traceparent") else nullcontext())
    with context:
        with mlflow.start_span("server-handler") as span:
            span.set_inputs(payload)
            result = handle(payload)
            span.set_outputs(result)
    return result
```

Adapt the Flask example to the existing server. Keep normal authentication and request handling; trace context is not authorization. Preserve W3C trace context and verify persisted trace IDs and parent IDs connect both services before claiming one connected trace. An absent parent may indicate incomplete export or lost propagation.

- See the [complete client/FastAPI example](https://mlflow.org/docs/latest/genai/tracing/app-instrumentation/distributed-tracing.md#usage-example) for imports, request parsing, handler return and launch commands; check installed signatures.
- Follow the [bounded readback procedure](../guide.md#verification) for setup verification.
