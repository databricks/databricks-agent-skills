# Evaluation datasets, comparisons, and continuous checks

Use this guide after the basic evaluation workflow in `../guide.md`. Check the installed MLflow API and the current GenAI documentation before running examples: dataset and trace fields vary across MLflow versions and tracking backends.

## Build a representative dataset from production traces

1. Use the [bundled trace-retrieval guide](../../../../databricks-mlflow-tracing/references/mlflow-trace-retrieval/guide.md) to search the intended experiment for candidate traces within a bounded time window, then inspect them and their assessments. Select real failures, successes, slow requests, and distinct user journeys.
2. Mark selected traces with a project-specific tag such as `eval_candidate=regression` or `eval_candidate=edge_case`. If using MLflow MCP tools, discover their actual tagging/assessment methods before writing and fetch each trace again to verify the annotation. Otherwise use the installed SDK or retain the IDs for later curation. Remove sensitive data before reusing production requests.
3. Discover existing GenAI datasets before creating one. Convert each selected trace into a record with `inputs` matching the agent's `predict_fn` parameters. Add `expectations` only when ground truth is known; preserve outputs only when assessing the original response rather than rerunning the agent. Use `dataset.merge_records(...)` from `dataset-preparation.md` and retain a trace ID or source tag for provenance.
4. Keep known failures as a regression subset and review the final records before a full run. See `dataset-preparation.md` for dataset schema, Unity Catalog setup, and coverage guidance.

When converting a trace search DataFrame, inspect its actual columns: some versions expose `request`/`response`, whereas `merge_records()` expects records with `inputs` and optionally `outputs`/`expectations`. Do not rename columns by assumption or silently store a stringified trace as an input.

## Compare agent or prompt versions

Run the **same dataset and scorer definitions** against each candidate, in named MLflow runs. Record the code revision, model, prompt URI or version, dataset version, and judge version with each run. Compare per-scorer metrics, but also join row-level results by stable input or dataset record ID to find `pass → fail` regressions. Inspect the corresponding traces and rationales; an aggregate mean can improve while a critical user journey degrades.

For an A/B prompt test, change only the prompt version if possible. Keep the agent, model, dataset, and scorer suite fixed. Define the acceptance rule before looking at results (for example, no safety regression and improved task success), and use an aligned judge or human review for subjective criteria. A lower score from a newly aligned judge is not evidence that the agent regressed; compare candidates under the **same** judge version.

For precomputed responses, evaluate the `inputs` and `outputs` already in the records without a `predict_fn`. Use a `predict_fn` when the goal is to rerun the current agent. Do not mix these modes within one comparison.

## Continuous evaluation

Keep a small, versioned regression dataset of failures and a larger representative dataset for scheduled checks. In CI, first validate auth and tracing, then run a small dry run with the installed scorer suite. Fail on an explicit, stable quality threshold or a critical regression, and attach the MLflow run URL plus failing trace IDs to the CI result. Reserve expensive LLM-judge suites and broad production samples for scheduled runs; pin judge/model and dataset versions so comparisons remain meaningful. Use `throughput-guide.md` to set worker concurrency instead of writing a custom evaluation loop.
