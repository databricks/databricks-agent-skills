---
name: databricks-mlflow-tracing
description: MLflow tracing and observability on Databricks. Use when getting started with MLflow, instrumenting GenAI apps and agents, retrieving and analyzing traces, debugging chat sessions, or querying aggregate trace metrics on supported OSS servers.
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Databricks MLflow Tracing

Use this skill for MLflow observability and tracing workflows on Databricks.
Read `databricks-core` first for CLI authentication, profile selection, and
workspace discovery.
On Databricks, reuse the existing experiment ID or choose an absolute workspace
path such as `/Users/<email>/my-experiment` or `/Shared/my-experiment`; relative
names in the bundled onboarding examples are for non-Databricks tracking servers.

Read the matching guide directly:

| Request | Read this guide |
| --- | --- |
| Choose a use case or get started with MLflow | [MLflow onboarding](references/mlflow-onboarding/guide.md) |
| Instrument an app or agent and verify tracing | [MLflow tracing](references/mlflow-trace-instrumentation/guide.md) |
| Retrieve traces by ID, time, status, or metadata | [Retrieve traces](references/mlflow-trace-retrieval/guide.md) |
| Inspect one trace or explain an agent failure | [Analyze a trace](references/mlflow-trace-analysis/guide.md) |
| Reconstruct or debug a multi-turn chat session | [Analyze a chat session](references/mlflow-trace-analysis/references/session-analysis.md) |
| Query token, latency, or quality metrics on a supported OSS MLflow server | [Query MLflow metrics](references/mlflow-trace-metrics/guide.md) |

For agent evaluation, scorer creation, or implementing a fix after diagnosis,
use `databricks-mlflow-evaluation`.

For work that spans multiple guides, use this order:

1. Determine the use case with [MLflow onboarding](references/mlflow-onboarding/guide.md).
2. Add or verify tracing with [MLflow tracing](references/mlflow-trace-instrumentation/guide.md).
3. Retrieve traces before [trace](references/mlflow-trace-analysis/guide.md) or [chat-session](references/mlflow-trace-analysis/references/session-analysis.md) analysis.
4. Use [Query MLflow metrics](references/mlflow-trace-metrics/guide.md) for aggregate trends.

For Databricks trace storage, read the tracing guide's [Databricks reference](references/mlflow-trace-instrumentation/references/databricks.md) before claiming that traces use Unity Catalog storage.

For a Unity Catalog trace location, verify the deployed identity rather than a
local user. It needs experiment access, `CAN USE` on the SQL warehouse,
`USE CATALOG` and `USE SCHEMA`, and explicit `MODIFY, SELECT` on each generated
spans, logs, metrics, and annotations table. `ALL PRIVILEGES` alone does not
satisfy those table grants. Confirm persistence by reading back a fresh trace
written under the deployed identity.
