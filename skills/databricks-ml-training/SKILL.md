---
name: databricks-ml-training
description: "Train ML or custom-agent models on Databricks with MLflow tracking and Unity Catalog registration. Use when asked to: train classification/regression or deep-learning models (XGBoost, scikit-learn, LightGBM, PyTorch, etc.) with Optuna tuning, register to UC and promote `@prod`/`@challenger` aliases, batch-score via `spark_udf`, build custom PyFunc models, author a custom `ResponsesAgent` with UC Function/Vector Search tools, or submit a training notebook as a serverless one-time job. NOT for: endpoint ops (databricks-model-serving), Knowledge Assistants/Supervisor Agents (databricks-agent-bricks), MLflow evaluation (databricks-mlflow-evaluation)."
compatibility: Requires databricks CLI (>= v0.294.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# ML Training on Databricks

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Train with MLflow → register to Unity Catalog → consume the **same artifact** as either a batch Spark UDF over Delta or (when low-latency is required) a real-time serving endpoint.

> **Always train on Databricks** (serverless job or notebook), never in the local Python process the agent is running in. Local training has no access to the silver tables, no MLflow tracking server, no UC registry path, and dies if the chat session drops — submit `databricks jobs submit --no-wait` (see "Train + deploy as a serverless job" below). Only fall back to local execution if the user explicitly asks for it.

If you need to deploy a real time model serving endpoint **after** the model is registered (creating endpoints, traffic config, version-swapping, querying, Foundation Model API endpoints), see [databricks-model-serving](../databricks-model-serving/SKILL.md).

| Consumption | When | How |
|---|---|---|
| **Batch UDF** | Dashboards, daily/hourly scores, predictions read by Genie/Dashboards or an app (often synced to a Lakebase table) | `mlflow.pyfunc.spark_udf(...)` → `INSERT INTO gold_predictions` |
| **Real-time endpoint** | Score on a user action (fraud at authorization, rec at page load) — sub-100ms | `mlflow.deployments.get_deploy_client()` (classical) / `agents.deploy()` (agents). Endpoint lifecycle: see [databricks-model-serving](../databricks-model-serving/SKILL.md). |

## Default Canonical flow

```
silver_<features>  +  silver_<labels>
        ▼
   notebook (as a serverless job):
   ├── train with mlflow.autolog (XGBoost / sklearn / etc.)
   ├── mlflow.register_model → UC: {catalog}.{schema}.{model}
   ├── set_registered_model_alias(name, "prod", version)
   └── spark_udf(@prod) over latest features → MERGE into gold_predictions
        ▼
gold_<entity>_predictions   ◄── dashboards, apps, Genie read this
```

One notebook, one artifact. Re-running = retraining. Gold is where truth lives — read paths never call the model directly. Keep label-window logic (`failure occurred within 7 days`) in the notebook during dev; once stable, promote to a silver materialized view in SDP.

---

## Train and register (the 90% case)

`mlflow.autolog()` captures params, metrics, code, and the model artifact for every run; `registered_model_name=...` auto-registers the best run to UC (auto-incremented version). Wrap training with **Optuna** so each trial is a child run and the best one is what gets registered.

**Always `mlflow.set_registry_uri("databricks-uc")`** — without it, models land in the deprecated workspace registry. **The experiment's parent folder must exist** — `set_experiment` does NOT auto-create it (fails with `NOT_FOUND: Parent directory does not exist`). Pre-create it once with `databricks workspace mkdirs` before the job runs.

```bash
# Once per project — create the parent folder for the MLflow experiment.
databricks workspace mkdirs /Users/me@example.com/turbine_project
```

Use the Databricks notebook source format (`# Databricks notebook source` header, `# COMMAND ----------` separators, `# MAGIC %md`/`%sql` magics for markdown/SQL cells):

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # Turbine failure prediction
# MAGIC
# MAGIC Train an XGBoost classifier on engineered turbine telemetry features.
# MAGIC ## Data exploration

# COMMAND ----------

# (basic data exploration — class balance, schema sanity, etc.)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Training the model

# COMMAND ----------

import mlflow, mlflow.xgboost, optuna
from mlflow.tracking import MlflowClient
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Users/me@example.com/turbine_project/mlflow_experiment")

CATALOG, SCHEMA, NAME = "ai_demo_gen", "wind_farm", "turbine_failure"
FULL_NAME = f"{CATALOG}.{SCHEMA}.{NAME}"

# Autolog WITHOUT registered_model_name — otherwise every Optuna trial registers a new UC
# version, and a max-by-version pick lands on the last trial to finish, not the best one.
mlflow.xgboost.autolog(log_input_examples=True)

# For imbalanced labels: stratify the split, set scale_pos_weight = neg/pos.
def objective(trial):
    params = {
        "n_estimators":  trial.suggest_int("n_estimators", 100, 400),
        "max_depth":     trial.suggest_int("max_depth", 3, 10),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
    }
    with mlflow.start_run(nested=True):
        m = XGBClassifier(**params).fit(X_train, y_train)
        return roc_auc_score(y_test, m.predict_proba(X_test)[:, 1])

with mlflow.start_run(run_name="hpo") as parent:
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=20)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Retrain best params and register

# COMMAND ----------
# Retrain on the winning trial's params explicitly, then register that single model.
with mlflow.start_run(run_name="best"):
    best = XGBClassifier(**study.best_params).fit(X_train, y_train)
    mlflow.log_metric("val_auc", study.best_value)
    info = mlflow.xgboost.log_model(best, name="model", registered_model_name=FULL_NAME)

# Stages are deprecated — UC uses movable aliases. Repoint @prod at the version we just registered.
client = MlflowClient(registry_uri="databricks-uc")
client.set_registered_model_alias(FULL_NAME, "prod", info.registered_model_version)
```

**Framework autolog**: `mlflow.{sklearn,xgboost,lightgbm,pytorch,tensorflow,spark}.autolog()`.

**Aliases, not stages**: UC dropped `Staging`/`Production`. Use movable `@prod`/`@challenger`; load with `models:/{full_name}@prod`. Promoting a new version is one `set_registered_model_alias` call.

---

## Consume: batch scoring over Delta

The cheap, default path. Load the registered model as a Spark UDF and score a Delta table; write predictions to a gold table that downstream consumers read.

```python
# COMMAND ----------
# MAGIC %md
# MAGIC ## Score and save to a gold predictions table

# COMMAND ----------
import mlflow
from pyspark.sql import functions as F

# env_manager rules:
#   "local"     → same runtime as training (same notebook/job). Fastest, default in dev/demo.
#   "virtualenv"→ different runtime than training; rebuilds the model's env.
#   "uv"        → same as virtualenv but faster (MLflow ≥ 2.22).
predict = mlflow.pyfunc.spark_udf(
    spark,
    model_uri=f"models:/{FULL_NAME}@prod",
    env_manager="local",
)

features = spark.table(f"{CATALOG}.{SCHEMA}.silver_turbine_features_latest")
feature_cols = [c for c in features.columns if c != "turbine_id"]   # exclude the join key
scored = features.withColumn("risk_score", predict(*[features[c] for c in feature_cols]))

# Overwrite-per-run pattern for "latest score per entity":
scored.select("turbine_id", "risk_score", F.current_timestamp().alias("scored_at")) \
    .write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.gold_turbine_predictions")
```

For incremental scoring with history, MERGE into the predictions table instead of overwrite.

---

## Real-time serving (when required)

After registering a model to UC, deploy it behind a Model Serving endpoint. The dev-side call is `mlflow.deployments.get_deploy_client("databricks").create_endpoint(...)` for classical ML or `agents.deploy(...)` for `ResponsesAgent`s. First deploy is ~5 min for classical ML.

For endpoint create / update / version-swap, traffic config, AI Gateway, querying, the `state.ready` + `state.config_update` two-field readiness check, and Foundation Model API endpoints, see **[databricks-model-serving](../databricks-model-serving/SKILL.md)**.

---

## Train + deploy as a serverless job

Training notebooks run a few minutes (Optuna + UC register; endpoint warmup adds 5–15 min if you also deploy). Submit as a serverless one-time run so the CLI doesn't block. The notebook ends with `dbutils.notebook.exit(json.dumps({...}))` so the structured result (`model_version`, `val_auc`, `endpoint_name`) reaches `.notebook_output.result`.

```bash
# 1. Upload the training notebook
databricks workspace import /Workspace/Users/me@example.com/turbine_project/train \
  --file ./train_notebook.py --format SOURCE --language PYTHON --overwrite

# 2. Submit as serverless one-time run (returns {"run_id": N} immediately with --no-wait)
RUN_ID=$(databricks jobs submit --no-wait --json '{
  "run_name": "turbine-train-and-deploy",
  "tasks": [{
    "task_key": "train",
    "notebook_task": {"notebook_path": "/Workspace/Users/me@example.com/turbine_project/train"},
    "environment_key": "ml_env"
  }],
  "environments": [{
    "environment_key": "ml_env",
    "spec": {
      "client": "4",
      "dependencies": ["mlflow==3.1.0", "xgboost==2.1.3", "optuna==4.1.0", "scikit-learn==1.5.2"]
    }
  }]
}' | jq -r .run_id)

# 3. Poll until a terminal life_cycle_state.
for _ in $(seq 60); do
  STATE=$(databricks jobs get-run "$RUN_ID" | jq -r '.state.life_cycle_state // "UNKNOWN"')
  echo "$(date +%H:%M:%S) $STATE"
  [[ "$STATE" =~ ^(TERMINATED|SKIPPED|INTERNAL_ERROR)$ ]] && break
  sleep 30
done
[[ "$STATE" =~ ^(TERMINATED|SKIPPED|INTERNAL_ERROR)$ ]] || { databricks jobs cancel-run "$RUN_ID"; exit 1; }

# life_cycle_state TERMINATED only means "the run ended" — check result_state.
RESULT=$(databricks jobs get-run "$RUN_ID" | jq -r '.state.result_state // "UNKNOWN"')
echo "result_state=$RESULT"
[[ "$RESULT" == "SUCCESS" ]] || { echo "Run did not succeed"; exit 1; }

# 4. Pull structured output via the TASK run_id (NOT the submit run_id).
TASK_RUN_ID=$(databricks jobs get-run "$RUN_ID" | jq -r '.tasks[0].run_id')
databricks jobs get-run-output "$TASK_RUN_ID" | jq '.notebook_output.result'
# → '{"model_version":"3","val_auc":0.91,"rows_scored":124,"endpoint":"turbine-risk-endpoint"}'
```

Common `jobs submit` traps to be aware of: `environments[].spec.client: "4"` is required on serverless notebook tasks; use the TASK run_id (`tasks[0].run_id`) — NOT the submit run_id — for `get-run-output`; `print()` is unreliable on serverless one-time runs (use `dbutils.notebook.exit(json.dumps(...))`); `jobs submit` rejects `tags`. For the broader `databricks-jobs` skill, see **[databricks-jobs](../databricks-jobs/SKILL.md)**.

---

## Custom pyfunc

When sklearn/XGBoost autolog isn't enough — custom preprocessing, multiple sub-models, external API calls, ensemble logic. See **[references/custom-pyfunc.md](references/custom-pyfunc.md)** for a full worked example. Two non-obvious things:

- **`python_model="path/to/file.py"`** (file path, not class instance) + `mlflow.models.set_model(MyModel())` at the end of that file. This is the "Models from Code" pattern — the file is logged verbatim, no pickling of the class.
- **`mlflow.models.predict(model_uri=..., input_data=..., env_manager="uv")`** before deploying. Catches missing deps before the endpoint does.

---

## Custom GenAI agents

Hand-rolled `ResponsesAgent` (LangGraph + UC Function tools + Vector Search retrieval) — see **[references/genai-agents.md](references/genai-agents.md)**.

Prefer no-code authoring via [databricks-agent-bricks](../databricks-agent-bricks/SKILL.md) (Knowledge Assistants, Supervisor Agents) unless the user explicitly needs a custom LangGraph agent.

---

## Gotchas (the ones that cost time)

| Trap | Fix |
|---|---|
| Model lands in workspace registry, not UC | `mlflow.set_registry_uri("databricks-uc")` *before* logging |
| Endpoint returns PERMISSION_DENIED at first query | Pass `resources=[...]` to `log_model` (covers UC functions, VS indexes, other endpoints, Lakebase) — see [references/genai-agents.md#resources-that-need-passthrough-auth](references/genai-agents.md#resources-that-need-passthrough-auth) for the full list |
| Used `transition_model_version_stage` | Stages are deprecated in UC. Use `client.set_registered_model_alias(name, "prod", version)` |
| `spark_udf` rebuilds a virtualenv on every call | Pass `env_manager="local"` when training+scoring share a runtime |
| `pip_requirements` mismatch crashes endpoint at load | Pin exact versions; or pull live with `f"mlflow=={get_distribution('mlflow').version}"` |
| `agents.deploy()` produced a weirdly-named endpoint | Pass `endpoint_name=...` explicitly. Auto-derived name is `agents_<catalog>-<schema>-<model>` |

Endpoint-lifecycle gotchas (readiness two-state, version-swap, Serving-UI SP filter) live in [databricks-model-serving](../databricks-model-serving/SKILL.md).

---

## Reference files

| File | Contents |
|---|---|
| [references/custom-pyfunc.md](references/custom-pyfunc.md) | Single end-to-end custom pyfunc example: artifacts, signature, code_paths, log → register → deploy → query. |
| [references/genai-agents.md](references/genai-agents.md) | Custom LangGraph `ResponsesAgent` with UC Function + Vector Search tools. `create_text_output_item` gotcha and the `resources=[...]` passthrough-auth list. For no-code agents prefer **databricks-agent-bricks**. |

## Related skills

- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** — serving-endpoint lifecycle (create, query, update-config, version-swap, AI Gateway, Foundation Model API endpoints).
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** — no-code Knowledge Assistants and Supervisor Agents. Prefer this over hand-rolling agents.
- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** — evaluate model/agent quality before promoting `@prod`.
- **[databricks-vector-search](../databricks-vector-search/SKILL.md)** — vector indexes used as retrieval tools in agents.
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — async deploy pattern (`--no-wait`, TASK run_id trap).
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — UC governs the registered model: permissions, lineage, audit.
