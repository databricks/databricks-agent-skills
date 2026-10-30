# Analyze an MLflow chat session

Reuse the configured backend, experiment, session ID, relevant time window and reported/expected behavior. Session traces share metadata key `mlflow.trace.session`; verify how the application assigns that ID so unrelated conversations are not combined.

## Prerequisites

Before searching session traces, read [trace retrieval](../../mlflow-trace-retrieval/guide.md) for filters, time bounds and pagination. If that skill is not installed, use the [search guide](https://mlflow.org/docs/latest/genai/tracing/search-traces.md) and installed CLI help.

## Step 1: Discover the schema

Check installed `mlflow traces search --help`. Search chronologically with an explicit experiment and time bounds; save JSON before parsing it:

```bash
FIRST_TRACE_FILE=$(mktemp)
mlflow traces search --experiment-id <EXPERIMENT_ID> \
  --filter-string 'metadata.`mlflow.trace.session` = "<SESSION_ID>" AND trace.timestamp_ms >= <START_MS> AND trace.timestamp_ms <= <END_MS>' \
  --order-by 'timestamp_ms ASC' --max-results 1 --no-include-spans --output json > "$FIRST_TRACE_FILE"
```

Replace placeholders with the incident/session window. On Databricks with UC, even `max-results 1` requires a timestamp predicate. If the period is unknown, resolve it before searching. Single outer shell quotes protect backticks from command substitution. Distinguish an empty result from a query failure; do not fetch a null ID.

## Step 2: Fetch the first trace

Fetch that first trace's full JSON once: `TRACE_DETAIL_FILE=$(mktemp); mlflow traces get --trace-id <ID> > "$TRACE_DETAIL_FILE"`. Find the root by `parent_span_id == null`. Inspect actual attribute keys and data shapes; MLflow I/O is typically serialized JSON under `mlflow.spanInputs` / `mlflow.spanOutputs`, while external OTel sources may differ. If root I/O is empty, walk descendants to the closest meaningful chat-turn span. Do not assume immediate children suffice.

## Step 3: Interpret assessments

Session-level assessments normally live on the first session trace and have `mlflow.trace.session` in assessment metadata; other records may apply only to a turn or span. A time-window's first result may be mid-session: disclose missing earlier context or obtain the relevant earlier window. Read source, value and top-level `rationale`. Separate HUMAN reports from automated LLM_JUDGE/CODE judgments. Exclude explicit invalid/overridden judgments and `feedback.error` from quality conclusions, while reporting scorer failures separately. Zero/false scores may be genuine; expectations are labels, not results. Session feedback does not locate a bad turn by itself.

## Step 4: Reconstruct the conversation

Search the same bounded session with a suitable page size, `--order-by 'timestamp_ms ASC'`, and `--no-include-spans` for IDs and metadata. `--extract-fields` filters client-side and does not reduce data transferred through a UC warehouse. Fetch selected full traces to inspect turn I/O. Some clients expose `info.trace_metadata.\`mlflow.traceInputs\`` / `mlflow.traceOutputs`; do not assume these exist. Nested span extraction can be incomplete: fetch full traces only where required data is missing or a turn needs deeper inspection. Follow continuation tokens, preserving bounds and ordering. A first page is not the whole conversation.

Redirect CLI JSON to a file before parsing it. Large trace output can exceed an agent shell's output limit and make a direct pipe appear empty.

## Step 5: Find the first bad turn

Compare actual inputs, outputs and expectations chronologically; trace how an earlier error enters later history, summaries, memory, retrieval or tool arguments. Fetch the decisive turn and necessary neighbors in full. Check actual model messages to establish propagation rather than assuming later turns saw every previous response.

## Step 6: Check the source

Correlate with session assignment, history truncation/summarization, and state read/write code. Read source to confirm the explanation; do not edit the agent, add scorers, or build a regression suite for a diagnosis-only request.

### Worked example: refund-policy propagation

Illustrative evidence; trace/span IDs are abbreviated:

| Turn / trace | Recorded evidence | Conclusion |
|---|---|---|
| 3 / `t3` | `retrieve` returns shipping terms with no refund policy; `answer` says “Refunds within 30 days.” | First unsupported claim is in `t3/answer`; inspect retrieval scope before blaming generation alone. |
| 4 / `t4` | LLM input history contains that exact claim; output tells the user to request a refund. | The earlier error reached the model and influenced the next answer. |
| 5 / `t5` | User reports rejection; LLM input still contains the claim and output repeats it. | The complaint occurs after the divergence; cite `t3`–`t5`, not only the complained-about turn. |

## Verification

Return the reconstructed sequence or concise relevant turns, first divergence with trace/span IDs, downstream propagation, likely cause and confidence. State pagination/window/schema gaps and distinguish application failures from failed scorers. `OK` is execution status, not proof of quality; `STATUS_CODE_UNSET` alone is not an error.

## References

- Detailed field semantics: [trace structure](trace-structure.md). The essential assessment rules above remain usable standalone.
- More filter/API options: [official search guide](https://mlflow.org/docs/latest/genai/tracing/search-traces.md), matched to installed CLI help. If unavailable, use installed help and report unresolved compatibility.
- Existing helpers are optional, resolved relative to this guide: `../scripts/discover_schema.sh <EXPERIMENT_ID> <SESSION_ID> <START_TIME_MS> <END_TIME_MS>` performs bounded schema discovery, and `../scripts/inspect_turn.sh <TRACE_ID>` inspects one turn. Both use temporary files and report only `STATUS_CODE_ERROR` spans as errors.
- If implementation is requested, pass the diagnosis and trace IDs to `databricks-mlflow-evaluation`.
