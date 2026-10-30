---
name: mlflow-trace-analysis
description: Analyze MLflow traces, agent failures, and multi-turn chat sessions. Explain errors, unexpected output, quality issues, latency, or cross-turn propagation without editing application code.
---

# Analyze MLflow traces

Use the trace ID or session ID, configured backend, reported behavior and expected outcome. Reuse traces already fetched. For a multi-turn conversation, read [session analysis](references/session-analysis.md).

## Prerequisites

Before searching for an unknown trace ID, read [trace retrieval](../mlflow-trace-retrieval/guide.md) for filters, time bounds and pagination. Reuse an already fetched trace. If that skill is not installed, use the [search guide](https://mlflow.org/docs/latest/genai/tracing/search-traces.md) and installed CLI help.

Prefer existing evidence. Only when no usable trace exists, reproduce once through the normal instrumented entry point when safe; otherwise report the missing evidence. Record HUMAN feedback only when authorized and attached to an identified trace.

## Step 1: Fetch the trace

Fetch full JSON once to a file; large piped CLI output can be truncated by the execution tool. `get` needs no `--output` flag. Avoid `--extract-fields` for nested span diagnosis.

```bash
TRACE_FILE=$(mktemp)
mlflow traces get --trace-id <TRACE_ID> > "$TRACE_FILE"
```

## Step 2: Inspect the span tree

Summarize state, assessments and parent links:

```bash
jq '{state: .info.state,
     spans: [.data.spans[] | {span_id, parent_span_id, name, status}],
     error_spans: [.data.spans[] | select(.status.code == "STATUS_CODE_ERROR") | .name],
     assessments: .info.assessments}' "$TRACE_FILE"
```

## Step 3: Read feedback

Read feedback **source, value, top-level rationale, validity and scope** before forming a hypothesis. HUMAN feedback describes the reported experience; corroborate it with spans. LLM_JUDGE/CODE feedback may be wrong or misconfigured. `feedback.error` means scoring failed, not that the application failed; exclude errored/overridden judgments from quality conclusions. Genuine zero/false values remain valid. Expectations are desired-output labels, not scores.

## Step 4: Follow inputs and outputs

Follow actual inputs and outputs from root to the first divergence, then downstream effects. Raw MLflow span I/O is usually serialized JSON in `attributes["mlflow.spanInputs"]` / `attributes["mlflow.spanOutputs"]`; parse it before interpreting it. If the root is an empty wrapper, inspect descendants. For other OTel sources or versions, inspect raw keys instead of assuming this schema.

## Step 5: Check errors and performance

Check exception events and status messages. `OK` means execution success, not correct output; `STATUS_CODE_UNSET` is not itself an error. For performance, distinguish enclosing wrappers, overlapping child work and uninstrumented gaps; repeated names alone do not prove retries. Inspect recorded token usage rather than inventing cost or assuming a token spike proves injection.

## Step 6: Check the source

Correlate the decisive span's observed data with relevant source/configuration when available. Function names are clues; autologged names follow framework conventions. Separate observed facts, plausible causes and missing evidence. Do not edit code, create scorers or run an evaluation for diagnosis alone.

See the [refund-policy evidence table](references/session-analysis.md#worked-example-refund-policy-propagation) for a retrieval miss, unsupported answer and later propagation.

## Verification

Report observed versus expected behavior, trace and decisive span IDs, the evidence chain, confidence and the smallest likely remedy. Confirm claims against actual span I/O and feedback semantics, not previews alone. If evidence is missing, say what would resolve the uncertainty; do not promote a hypothesis to a confirmed root cause.

## References

- Fields, units, CLI versus SDK representation, OTel attributes or assessment interpretation: [trace structure](references/trace-structure.md).
- Bounded batches, recurring failures or component bottlenecks: [cross-trace analysis](references/cross-trace-analysis.md).
- Multi-turn propagation: [session analysis](references/session-analysis.md).
- A user-requested implementation: pass diagnosis and trace ID to `databricks-mlflow-evaluation`; investigation itself stops at evidence and recommendations.
