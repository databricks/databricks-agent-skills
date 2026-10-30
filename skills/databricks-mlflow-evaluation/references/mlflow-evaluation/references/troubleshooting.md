# Evaluation failure index

Use the failing phase and actual error to choose a check. Keep the selected backend, experiment, model, and
records. **Stop before a full run on broken infrastructure or missing/error-only scores. Zero/False are valid
negative scores.**

## Setup and tracing

| Symptom | Check / next action |
| --- | --- |
| Missing MLflow/import/CLI | Confirm the project interpreter, installed MLflow version, and package. GenAI evaluation uses `mlflow.genai.evaluate`, not classic `mlflow.evaluate`. Use the [bundled onboarding guide](../../../../databricks-mlflow-tracing/references/mlflow-onboarding/guide.md) when connection setup is missing. |
| Invalid Databricks profile/auth | Check the selected workspace/profile and authenticated CLI/SDK context. Report missing login/access without changing backend or exposing credentials. |
| Experiment missing/inaccessible | Resolve the exact intended ID/name and distinguish permission/network failures from absence before creating anything. |
| Local server port busy | Check whether the intended server already runs; select another port only for an authorized new server. Do not kill unrelated servers. |
| Agent import fails | Use the project environment and real module path; install the project in editable mode if that is its normal setup. |
| No persisted trace | Reuse the [bundled tracing guide](../../../../databricks-mlflow-tracing/references/mlflow-trace-instrumentation/guide.md). Check destination, tracing enablement on the actual invoked path, flush, then fetch by trace ID in the intended experiment. A local ID alone is insufficient. |
| Missing framework spans | Check installed integration/library compatibility and when autologging is enabled. LangGraph uses `mlflow.langchain.autolog()`; do not invent `mlflow.langgraph`. |
| Disconnected model traces | Verify the production agent/framework instrumentation actually runs. Add a missing application boundary only when necessary; do not duplicate spans already supplied by autologging. |
| Missing session association | Call `mlflow.update_current_trace(session_id=session_id)` while a trace is active. Reuse a stable ID across turns, not a new ID per turn. |
| Empty trace search / syntax error | Bound the experiment and time window, use `filter_string=` explicitly, and inspect supported attributes. String literals use single quotes, dotted tag keys use backticks, conjunction is `AND`; do not assume `OR` support. See [trace search](https://mlflow.org/docs/latest/genai/tracing/search-traces.md). |

For tracing changes use the installed tracing skill when available. If independently installed, inspect the
framework's documented integration and confirm persisted readback; do not rely on decorator-name searches as
proof.

## Data and prediction

| Symptom | Check / next action |
| --- | --- |
| Missing inputs/schema error | Use nested `inputs` and optional `expectations`; preserve multi-key/nested values. See [dataset preparation](dataset-preparation.md). |
| Unexpected predictor keyword / missing argument | MLflow invokes `predict_fn(**inputs)`. Match wrapper keyword names and bind project configuration separately. |
| Existing-output task invokes predictor | Omit `predict_fn`, retain stored `inputs`/`outputs`, and reuse the selected dataset unchanged. |
| UC dataset unsupported fields / Spark error | Inspect backend/version support for constructor, tags, `experiment_ids`, search, and Spark requirements; use the [UC requirements](dataset-preparation.md#databricks-unity-catalog-considerations). |
| UC table missing | Check the intended fully qualified name, catalog/schema existence, and permissions. Do not default to an arbitrary accessible schema. |
| Dataset creation appeared to succeed | Read it back from the intended backend; verify identity, count, records, and supported experiment association. |
| Missing/empty agent response | Inspect predictor/tool errors, auth, timeouts, and retrieval results. Do not launch the full rerun until fixed. Preserve empty precomputed outputs as observed data. |
| Partial evaluation / rate limits | Retain errors and failing row IDs; diagnose timeout/quota/resource issues. Use bounded retries and [throughput settings](throughput-guide.md), not a loop that silently drops failures. |
| Slow development against serving endpoint | Use the local production code path when the task permits; preserve an explicitly requested deployed target for deployment comparisons/monitoring. |

- If UC dataset metadata access is unsupported, read `name`/`dataset_id`; avoid the failing `experiment_ids`/`tags` properties.
- If UC creation requires Spark, reuse the intended notebook/session or supported Databricks Connect configuration; do not require Spark for other backends.

## Scorers and results

| Symptom | Check / next action |
| --- | --- |
| Scorer not recognized | Use the native `@scorer` decorator, built-in, or `make_judge`. |
| Dict/tuple Feedback serialization error | Return a supported primitive or `Feedback`; multiple Feedbacks require unique names. See [constraints](scorers-constraints.md). |
| Missing aggregate metrics | Inspect raw values: `"pass"`/`"fail"` and other unsupported strings can be stored but omitted from aggregation. Use bool/numeric/yes-no. |
| All zero/False scores | Read outputs and rationales; genuine negatives are valid. Check known-good/bad cases and infrastructure independently. Never equate zero with null. |
| Null/skipped/error assessment | Inspect model access, required data, output type, and actual assessment error. Trace status OK does not prove scoring succeeded. |
| Judge template error | Include supported variables; `{{ trace }}` is exclusive. Check [constraints](scorers-constraints.md). |
| Model not found / wrong provider | Preserve the project model and credentials; verify `provider:/model` or supported managed-judge syntax. See [model selection](scorers.md#model-selection-for-scorers). |
| Correctness cannot score | Supply expected facts/response under `expectations`; do not invent ground truth. |
| Retrieval scorer raises | Check for RETRIEVER spans and required retrieval evidence. TOOL-only lookups do not qualify; select a suitable scorer or repair real instrumentation. |
| Guidelines missing context/constructor error | Inspect installed signature and data contract. Provide both inputs and outputs, a clear prescriptive requirement, and a name when required. |
| Unsupported aggregation | Check installed accepted names; historical `median`/`p90` support does not imply `p50`/`p99`/`sum`. |
| Scorer registration fails | Verify identifier, permissions, template, and installed CLI help. Use native Python registration for clearer errors; no legacy `--output pass/fail` fallback. |
| Monitoring serialization fails | Verify custom imports, annotations, and available dependencies in the target environment. See [online monitoring](databricks-online-monitoring.md). |
| Registered scorer never scores production | Registration is not startup. Check lifecycle state, explicit sample configuration, warehouse access, and asynchronous assessment errors. |
| High failure rate or human disagreement | Review actual verdicts against the agreed criterion; use existing human labels and held-out agreement before changing the judge. Do not loosen criteria just to improve metrics. |

A helper report is not the oracle: compare its counts to raw row-level outputs, typed scores,
skipped/missing/error assessments, and expected record IDs. Report unresolved gaps instead of calling an
empty/partial evaluation successful.

For missing API details follow the exact topic link, check installed-version compatibility, then use
[llms.txt](https://mlflow.org/docs/latest/llms.txt) only to find a missing/moved page. If docs are
unavailable, introspect the installed API and use the local minimum; stop when correctness cannot be
established.
