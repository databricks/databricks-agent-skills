# Reduce context cost without losing quality

Use this after traces show excessive input tokens, latency, or context-window failures. Measure a baseline with the [bundled trace-metrics guide](../../../../databricks-mlflow-tracing/references/mlflow-trace-metrics/guide.md) and inspect the costly spans with the [bundled trace-analysis guide](../../../../databricks-mlflow-tracing/references/mlflow-trace-analysis/guide.md). Keep an evaluation dataset and scorer suite fixed while testing each change; lower token usage alone is not success.

## Choose the smallest change that fixes the measured cause

| Trace evidence | Candidate change | Regression risk to check |
| --- | --- | --- |
| Oversized tool responses | Return only needed fields, cap result count, or summarize results before the next LLM call | Lost facts or citations |
| Repeated conversation history | Keep a bounded recent window plus a concise state summary | Lost user constraints or earlier commitments |
| Same instructions repeated across agents | Move stable rules to a shared prompt or pass structured state | Missing role-specific instructions |
| Large static prompt | Remove redundant text or assemble optional sections only when relevant | Changed policy or tool behavior |
| Repeated identical retrieval | Cache safe, stable results with a validity period | Stale or cross-user data |
| Multiple independent LLM calls | Batch or parallelize only when semantics permit | Ordering, rate limits, and cost spikes |

Prefer structured state for facts the agent must retain exactly, and summaries for narrative history. Trigger compression from measured token pressure or task boundaries; avoid a static threshold that discards important instructions. Never put secrets or another user's data into shared caches. For multi-agent workflows, inspect each handoff payload and remove duplicate context before redesigning the whole architecture.

Run the same evaluation before and after, including edge cases that depend on long-range memory, retrieval citations, tool arguments, and safety rules. Compare quality, p95 latency, and tokens by span; inspect at least one new trace to confirm the intended context changed. If quality regresses, restore the prior behavior and try a narrower reduction.
