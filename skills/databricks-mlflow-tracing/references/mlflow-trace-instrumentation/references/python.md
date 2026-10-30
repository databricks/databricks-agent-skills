# Python tracing

## Setup and integration choice

Reuse `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_ID` or existing application configuration. Install only if needed (for example, `pip install 'mlflow>=3.8.0'`). For Databricks, follow [UC setup](databricks.md), including its newer version requirement and absolute workspace experiment path; setting the tracking URI alone is insufficient.

For an unconfigured OSS destination, set the chosen server and experiment; keep any supplied configuration:

```python
import mlflow
mlflow.set_tracking_uri(tracking_uri)  # Only if not already configured
mlflow.set_experiment(experiment_id=experiment_id)
```

To create an experiment by name, use `mlflow.set_experiment(experiment_name=experiment_name)`.

Choose the framework already in use:

```python
import mlflow
mlflow.langchain.autolog()  # LangChain and LangGraph, before application execution
```

LangGraph has no `mlflow.langgraph.autolog()`. Its graph, nodes, tools and model calls are autologged: do not decorate them again. Use the matching integration for other frameworks, such as `mlflow.openai.autolog()` for the OpenAI SDK. Do not enable unrelated integrations. See [automatic tracing](https://mlflow.org/docs/latest/genai/tracing/app-instrumentation/automatic.md) for framework/version details.

## Custom application work

Prefer a decorator, which captures arguments and return values. A deliberate outer application span may group custom work with autologged calls.

```python
from mlflow.entities import SpanType

@mlflow.trace(span_type=SpanType.RETRIEVER)
def retrieve_documents(query):
    return search_index(query)  # Adapt to the existing application
```

Use `mlflow.start_span()` for dynamic names or code without a function boundary. Set both inputs and outputs explicitly:

```python
with mlflow.start_span(name="retrieve_documents", span_type=SpanType.RETRIEVER) as span:
    span.set_inputs({"query": query})
    result = search_index(query)
    span.set_outputs(result)
```

Record actual retrieved documents, messages and tool results, not just counts. Apply privacy policy before export; any content reduction should be deliberate and documented. Explicit `span.set_inputs()` / `set_outputs()` override automatic capture. For compact root values versus display-only changes, read [root previews](root-span-previews.md).

With autologging enabled, decorate the custom entry point with `@mlflow.trace(span_type=SpanType.CHAIN)` to group its retrieval and autologged model calls in one trace; do not redecorate the model calls.

RAG wiring: [complete retrieval-to-prompt example](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/rag.md#complete-rag-example).

## Session metadata and attributes

Inside the active application span, attach the real user's/session's identifiers; do not collapse unrelated conversations under a shared default session:

```python
mlflow.update_current_trace(user=user_id, session_id=session_id)
span = mlflow.get_current_active_span()
if span:
    span.set_attribute("description", "Retrieve account records")
```

For an autologged LangGraph node, setting an attribute on its existing active span is sufficient; a new decorator is unnecessary. Use a node docstring as a description only when useful.

## Verify and extend

Follow [persisted readback](../guide.md#verification), including saving `mlflow.get_last_active_trace_id()` immediately after the run in the same process. Missing traces require checking the existing destination, experiment, autolog warnings and auth before changing instrumentation.

- Threads, async, redaction or handled exceptions: [advanced patterns](advanced-patterns.md).
- Other manual API options: [manual tracing](https://mlflow.org/docs/latest/genai/tracing/app-instrumentation/manual-tracing.md), checked against the installed version.
