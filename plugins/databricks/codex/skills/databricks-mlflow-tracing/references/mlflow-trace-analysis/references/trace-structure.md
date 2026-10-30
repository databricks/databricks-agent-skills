# Trace structure and interpretation

Use the [MLflow entity API](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.entities.html) for the complete, versioned schema. This reference covers only fields whose CLI/SDK representation or interpretation commonly causes mistakes. A trace has `info` (identity, timing, location, assessments) and `data.spans` (operations linked by parent IDs); OTel clients may use GenAI, OpenInference or custom attributes.

Types below describe MLflow 3.17 CLI JSON: `?` means optional/nullable; `JSON str` contains encoded JSON. Empty maps/lists may be omitted. SDK differences are noted explicitly.

## Trace fields

| CLI JSON under `info` | Type; example | Meaning / pitfall |
|---|---|---|
| `trace_id` | str; `"tr-0123456789abcdef0123456789abcdef"` | Preserve the full ID for SDK calls, including UC `trace:/<location>/<id>` or legacy `tr-` prefix. |
| `state` | str; `"OK"` | Also `ERROR`, `IN_PROGRESS`, `STATE_UNSPECIFIED`. Success is not proof of quality; inspect child statuses. |
| `request_time` | str (RFC 3339); `"2026-10-22T12:00:00Z"` | SDK `request_time` is epoch milliseconds. Search alias: `trace.timestamp_ms`. |
| `execution_duration_ms` | int?; `125` | Wall-clock milliseconds; SDK `execution_duration`. Search alias: `trace.execution_time_ms`. |
| `request_preview`, `response_preview` | str?; `"Find my order"` | Possibly truncated summaries; inspect stored span I/O. |
| `client_request_id` | str?; `"req-42"` | Application correlation ID, distinct from trace ID. |
| `trace_location` | object; `{"type":"MLFLOW_EXPERIMENT","mlflow_experiment":{"experiment_id":"1"}}` | Alternatively UC catalog/schema/table prefix; a schema can contain several prefixes. UC `experiment_id` may be absent; use configured experiment identity. |
| `trace_metadata` | map[str, str]; `{"mlflow.trace.session":"chat-42"}` | Request context; inspect actual keys/version semantics. |
| `tags` | map[str, str]; `{"mlflow.traceName":"answer"}` | Mutable environment/version/prompt annotations. |
| `assessments` | list[object]; `[]` | Feedback/expectations; see below. |

Unexpectedly persistent `IN_PROGRESS` may indicate a producer crash or interrupted finalization; unspecified state may indicate incomplete instrumentation/export. Check request completion and application logs before concluding.

All entries below are optional keys in `trace_metadata` or `tags`; metadata values are strings, even for numbers/objects.

| Map | Key | Type; example value |
|---|---|---|
| metadata | `mlflow.trace.user`, `mlflow.trace.session` | str?; `"user-42"`, `"chat-42"` |
| metadata | `mlflow.modelId`, `mlflow.sourceRun` | str?; `"m-0123456789abcdef0123456789abcdef"`, `"0123456789abcdef0123456789abcdef"` |
| metadata | `mlflow.trace.tokenUsage` | JSON str?; `'{"input_tokens":10,"output_tokens":5,"total_tokens":15}'` |
| metadata | `mlflow.traceInputs`, `mlflow.traceOutputs` | JSON str?; `'{"question":"Hi"}'`, `'"Hello"'` |
| tags | `mlflow.traceName` | str?; `"answer"` |
| tags | `mlflow.linkedPrompts` | JSON str?; `'[{"name":"assistant","version":"1"}]'` |
| tags | `mlflow.trace.sourceScorer` | str?; `"Correctness"` (scorer-generated trace) |

Verify recorded I/O before extraction. Missing token fields mean unknown usage, not zero.

## Span fields and raw JSON

| Span field / attribute | Type; example | Interpretation |
|---|---|---|
| `span_id`, `trace_id` | str; `"EjRWeJCrze8="`, `"EjRWeJCrze8SNFZ4kKvN7w=="` | CLI uses base64 IDs; SDK `span_id` is hex and `trace_id` is the MLflow ID. |
| `parent_span_id` | str?; `null` | Build the tree by IDs, not array order. Root has no parent; partial/distributed exports may omit parents. |
| `name` | str; `"retrieve"` | Function/framework operation. |
| `attributes["mlflow.spanFunctionName"]` | JSON str?; `'"retrieve_docs"'` | Underlying function name. |
| `attributes["mlflow.spanType"]` | JSON str?; `'"RETRIEVER"'` | SDK `span.span_type`; custom types are valid. |
| `start_time_unix_nano`, `end_time_unix_nano` | int (end nullable); `1792670400000000000` | Epoch nanoseconds; other exporters may use strings. Convert before subtraction; divide by 1e6 for milliseconds. |
| `status.code` | str; `"STATUS_CODE_ERROR"` | `STATUS_CODE_UNSET` alone is not an error. Handled child failure can coexist with parent success. |
| `status.message` | str?; `"timeout"` | Error description. |
| `attributes["mlflow.spanInputs"]`, `attributes["mlflow.spanOutputs"]` | JSON str?; `'{"query":"refund"}'`, `'["policy"]'` | SDK `span.inputs` / `span.outputs` decode values; not top-level CLI fields. |
| `attributes["mlflow.chat.tokenUsage"]` | JSON str?; `'{"input_tokens":10,"output_tokens":5,"total_tokens":15}'` | Per-call usage; other OTel clients may use different attributes. |
| `attributes["mlflow.chat.tools"]` | JSON str?; `'[{"type":"function","function":{"name":"search"}}]'` | Tools offered to the model. |
| `events` | list[object]; `[]` | Point-in-time records. |
| `events[].name` | str; `"exception"` | Event name. |
| `events[].attributes` | object; `{"exception.type":"ValueError","exception.message":"bad input","exception.stacktrace":"..."}` | Exception evidence; attribute types depend on producer. |
| `events[].time_unix_nano` | int; `1792670400000000000` | Epoch nanoseconds; SDK [event.timestamp](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.entities.html#mlflow.entities.SpanEvent). Compare with span timing. |

To discover an unexpected schema, inspect `jq 'keys'`, `.data.spans[0] | keys`, `.data.spans[0].attributes`, and `.data.spans[0].status` on the saved file. Preserve missing data as a limitation rather than inventing an equivalent field.

Duration is inclusive of children. Parallel child durations can sum beyond parent wall time; do not sum wrapper and child durations as independent latency. Gaps show uninstrumented time, not a proven cause. Repeated operations suggest retries only when inputs, events or code confirm them.

## Assessments

CLI JSON uses `assessment_name`; SDK entities generally expose `name`. In JSON, values live under `feedback.value` or `expectation.value` (structured expectations use `expectation.serialized_value`), and scorer failures under `feedback.error`; inspect the installed representation rather than assuming every SDK object has these nested paths.

| CLI assessment field | Type; example | Interpretation |
|---|---|---|
| `assessment_name` | str; `"Correctness"` | SDK `name`. |
| `assessment_id` | str?; `"a-42"` | May be absent before persistence. |
| `trace_id` | str?; `"tr-0123456789abcdef0123456789abcdef"` | Required when logging; optional on a standalone SDK assessment. |
| `create_time`, `last_update_time` | str (RFC 3339); `"2026-10-22T12:00:00Z"` | SDK `create_time_ms` / `last_update_time_ms`: epoch milliseconds, distinct from request time. |
| `valid` | bool?; `true` | Exclude explicitly invalid/overridden records; absent is not automatically false. |
| `overrides` | str?; `"a-41"` | Older assessment replaced by this record; does not invalidate the new record. |
| `source.source_type` | str; `"LLM_JUDGE"` | Also HUMAN or CODE; preserve provenance. |
| `source.source_id` | str?; `"reviewer@example.com"` | Reviewer/scorer identity. |
| `rationale` | str?; `"Answer matches the source"` | Top-level explanation; label polarity depends on scorer definition. |
| `span_id` | str?; `"1234567890abcdef"` | Restricts scope to one span. |
| `metadata` | map[str, str]?; `{"mlflow.assessment.sourceRunId":"0123456789abcdef0123456789abcdef"}` | Evaluation provenance, scorer context, labeling instructions/source versions. SDK `run_id` is derived from this key, not a CLI field. |
| `feedback.value` | JSON value?; `true`, `0.8`, `"yes"`, `{"answer":"Paris"}` | Judgment. |
| `expectation.value` | scalar?; `true`, `0.8`, `"Paris"` | Ground truth, not a judgment. |
| `expectation.serialized_value` | object?; `{"serialization_format":"JSON_FORMAT","value":"[1,2]"}` | Structured ground truth; decode the JSON string in `value`. |
| `feedback.error` | object?; `{"error_code":"TIMEOUT","error_message":"Judge timed out"}` | Scorer failure, not an app failure or negative score; `error_code`: str; `error_message`, `stack_trace`: str?. |

**Feedback** is a judgment, which may be numeric, boolean, categorical or structured. Zero and false can be genuine results. HUMAN feedback is evidence of a reported experience, not infallible proof of technical cause. Validate automated judgments against content and intended scorer inputs.

**Scorer errors** (timeouts, parsing failures, incompatible trace types) are not application errors or negative quality scores. Report them separately. Inspect error code/message/stack trace and, when recorded, the scorer's own trace ID in metadata. Keys vary: inspect for `mlflow.assessment.scorerTraceId` or the actual emitted equivalent instead of guessing. Other useful metadata includes `mlflow.assessment.sourceRunId`, `mlflow.assessment.judgeCost`, and `mlflow.assessment.onlineScoringSessionId`.

**Expectations** are desired-output/ground-truth labels with source, metadata and optional span scope. Compare the actual value with the appropriate exact, semantic or structural criterion; do not treat the presence of an expectation as a passing score. For requested judge alignment or labeling, use `databricks-mlflow-evaluation`.

**Session assessments** are normally attached to the first trace and marked by `mlflow.trace.session` in assessment metadata. They describe the conversation, not necessarily that first turn. If retrieval starts mid-session, the first returned trace may not be the actual first trace.

## What to inspect by operation

| Operation | Evidence to compare |
|---|---|
| LLM / CHAT_MODEL | Actual messages, instructions, history order, model parameters and response. |
| AGENT / TOOL | Offered versus selected tools, arguments, results, handoffs and errors. |
| RETRIEVER / EMBEDDING / RERANKER | Query, actual documents, model/truncation, ranking before and after. |
| CHAIN / PARSER | Data passed between steps, raw response and expected format. |
| MEMORY | History/state loaded, omitted, summarized or overwritten. |
| GUARDRAIL | Data received versus modified/blocked output. |
| Custom types | Infer role from actual names, attributes, I/O and source. |

For additional version-specific fields use the [MLflow entity API](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.entities.html) and installed SDK accessors. For non-MLflow events, consult [OTel exception conventions](https://opentelemetry.io/docs/specs/semconv/exceptions/exceptions-spans/). Local inspection remains necessary if documentation is unavailable or describes another version.
