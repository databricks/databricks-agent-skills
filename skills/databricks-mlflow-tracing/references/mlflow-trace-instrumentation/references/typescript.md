# TypeScript / JavaScript tracing

## Initialize the actual destination

Reuse the application's configuration. Use `@mlflow/core` (`npm install @mlflow/core` if missing). Call `init()` before any spans, with an actual experiment ID, not its name:

```typescript
import * as mlflow from "@mlflow/core";
mlflow.init({ trackingUri, experimentId });
```

For Databricks, read [UC setup](databricks.md#typescript) first. Check the installed typings for `traceLocation`; UC requires a provisioned location and its exact catalog, schema and table prefix. Plain `trackingUri`/`experimentId` does not establish UC storage.

## Capture application work

The wrapper captures arguments and returned values, including async results. Adapt the existing function without changing behavior:

```typescript
const retrieveDocuments = mlflow.trace(
  async (query: string) => searchIndex(query),
  { name: "retrieve_documents", spanType: mlflow.SpanType.RETRIEVER },
);
```

Use `withSpan(callback, options)` for dynamic names or code without a function boundary; this retrieval lookup explicitly records both inputs and outputs:

```typescript
const result = await mlflow.withSpan(
  async (span) => {
    span.setInputs({ query });
    const result = await lookup(query);
    span.setOutputs(result);
    return result;
  },
  { name: "lookup", spanType: mlflow.SpanType.RETRIEVER },
);
```

Keep actual retrieved content and tool results subject to privacy policy, rather than only counts. Explicit setters override wrapper capture. Useful span types include `AGENT`, `CHAIN`, `LLM`, `TOOL` and `RETRIEVER`; select by the operation's role.

For OpenAI auto-tracing, `tracedOpenAI` comes from the separate `@mlflow/openai` package:

```typescript
import { tracedOpenAI } from "@mlflow/openai";
import { OpenAI } from "openai";
const openai = tracedOpenAI(new OpenAI());
```

Use that client in existing application code. An outer `mlflow.trace` may group custom retrieval and auto-traced model calls; do not duplicate spans for operations already covered by the integration.

RAG wiring: [complete example (Python)](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/llm-judge/rag.md#complete-rag-example); use the TypeScript APIs above.

## Metadata, trace ID and flushing

Within an active traced request:

```typescript
mlflow.updateCurrentTrace({
  user: userId, sessionId,
});
const span = mlflow.getCurrentActiveSpan();
if (span) {
  traceId = span.traceId; // Save outside the callback for backend readback
}
```

Use real session identifiers. `requestPreview` / `responsePreview` in `updateCurrentTrace` affect display; `setInputs` / `setOutputs` change stored data. Avoid overriding already readable chat previews.

After the request completes, `await mlflow.flushTraces()` before process exit. Flush is part of the [60-second readback budget](../guide.md#verification). Retrieve the saved trace with the configured backend's CLI/SDK (for example `mlflow traces get --trace-id <id>`), then inspect persisted application inputs, outputs and child spans. A successful flush alone is not proof of persistence.

For additional APIs use the TypeScript sections of [manual tracing](https://mlflow.org/docs/latest/genai/tracing/app-instrumentation/manual-tracing.md) and installed typings; do not substitute Python API names.
