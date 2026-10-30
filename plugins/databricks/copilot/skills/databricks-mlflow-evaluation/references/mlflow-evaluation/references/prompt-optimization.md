# Improve a registered prompt with evaluation

Use this when the user asks to optimize a prompt, including `mlflow.genai.optimize_prompts()` with GEPA. Keep scorer design in the [bundled evaluation guide](../guide.md); this guide owns the evaluation and promotion loop. The installed MLflow version and optimizer constructor determine exact argument names, so check `mlflow.genai.optimize_prompts` and the current docs before execution.

## Prepare the optimization run

1. Register the current prompt in MLflow Prompt Registry. On Databricks, confirm its Unity Catalog `catalog.schema.name` and the registry preview/configuration described in the [bundled onboarding guide](../../../../databricks-mlflow-tracing/references/mlflow-onboarding/guide.md); do not overwrite a production alias as part of setup.
2. Create or discover a GenAI dataset with **both `inputs` and `expectations` in every training record**. An inputs-only evaluation dataset is insufficient for GEPA. Keep a separate holdout dataset that the optimizer cannot see.
3. Use a `predict_fn` that loads the registered prompt URI on each invocation, so the optimizer can substitute candidates. Verify it runs on one record before optimizing the full set.
4. Choose scorers that measure the user's actual goal. A domain-specific LLM judge should be checked against human labels first; see [judge alignment](judge-alignment.md). If a judge emits categorical `Feedback.value`, verify how the installed optimizer aggregates it before using it as a numeric objective.

The old Databricks evaluation skill used `GepaPromptOptimizer` with `mlflow.genai.optimize_prompts(predict_fn=..., train_data=..., prompt_uris=[...], optimizer=..., scorers=[...])`. Treat that as the workflow shape, not a frozen signature: inspect the installed package and use the current documented constructor and result fields. Confirm the reflection model, iteration budget, and expected cost before starting the run.

## Evaluate and promote

Compare the original and optimized prompts on holdout data using `advanced-evaluation.md`. Register the optimized prompt as a new version with links to the optimization and holdout runs. Move the production alias only if the predeclared acceptance rule passes; keep the old version available for rollback. If it fails, preserve the candidate and trace evidence without changing the alias.
