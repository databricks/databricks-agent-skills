---
name: databricks-mlflow-evaluation
description: MLflow GenAI evaluation and agent improvement on Databricks. Use when running mlflow.genai.evaluate(), building scorers or datasets, aligning judges with MemAlign, optimizing prompts, or monitoring production quality.
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.2.0"
parent: databricks-core
---

# Databricks MLflow evaluation

Read `databricks-core` for authentication and workspace discovery. For tracing,
trace retrieval, observability, and trace-based debugging, use the separate
`databricks-mlflow-tracing` skill. Verify tracing when the selected evaluation mode or scorers require it; reuse
precomputed outputs or existing traces without rerunning the agent.

The guides below are references, not separately installed skills. When a guide
names an upstream MLflow skill, use the matching guide here or the tracing skill.

| Request | Read this guide |
| --- | --- |
| Define quality criteria or scorers | [Scorer design](references/mlflow-evaluation/references/scorer-design.md) |
| Create a dataset and evaluate an agent | [MLflow evaluation](references/mlflow-evaluation/guide.md) |
| Change agent behavior and verify improvement | [Improve an agent](references/mlflow-agent-improvement/guide.md) |

For MLflow API details, consult the existing `databricks-docs` skill and
https://mlflow.org/docs/latest/llms.txt.

For Databricks judge models, prefer `databricks:/system.ai.<model>` with a
`mlflow[databricks]>=3.16.0`. A 404 commonly indicates an older client that
does not understand the system model URI; a 403 on a legacy endpoint name can
mean legacy serving endpoints are disabled. Verify the installed client and
available `system.ai` model before changing credentials or permissions.

For a new evaluation, establish a baseline with a fixed dataset and scorers,
change one thing, then run the same evaluation again. Use
`databricks-mlflow-tracing` first if traces are missing or a failure needs a
trace-grounded diagnosis.
