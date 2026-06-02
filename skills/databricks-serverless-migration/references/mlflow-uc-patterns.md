# MLflow on Unity Catalog: Serverless Migration Patterns

This reference covers the MLflow patterns that change when migrating to serverless compute with Unity Catalog as the model registry. Source: 7-demo dbdemos E2E sweep (lakehouse-fsi-credit, lakehouse-fsi-fraud, lakehouse-hls-readmission, lakehouse-retail-c360, dbt-on-databricks, mlops-end2end).

Six related patterns:

- **A3**: AutoML rewrite to inline scikit-learn `Pipeline`
- **A4**: `mlflow.pyfunc.spark_udf` closure bug on Spark Connect (mlflow 2.19.0)
- **M1**: Drop `registered_model_name=` from `log_model` under UC
- **M2**: Replace `.latest_versions` access with `search_model_versions` + sort+index
- **M3**: Pass `signature=` to `log_model` under UC (required, not optional)
- **P2**: Sklearn prediction-column dtype alignment for binary classifiers

---

## A3: AutoML to inline scikit-learn Pipeline

**Problem**: `from databricks import automl` raises `ImportError` on serverless. The dbdemos fallback `DBDemos.create_mockup_automl_run` hits `TypeError: Object of type PlanMetrics is not JSON serializable` on Spark Connect.

**Detect**:
- `from databricks import automl` import line
- Calls to `automl.classify(...)`, `automl.regress(...)`, `automl.forecast(...)`
- The try/except block falling back to `DBDemos.create_mockup_automl_run`

**Rewrite procedure**:
1. Materialize training data via `.sample(0.02).toPandas()` (driver-side, avoids Spark Connect autolog paths).
2. Pick the model based on the AutoML call: `RandomForestClassifier` for `automl.classify`, `RandomForestRegressor` / `LogisticRegression` for `automl.regress`.
3. Disable `mlflow.autolog()` to prevent re-triggering the `PlanMetrics` JSON serialization bug.
4. Log via `mlflow.sklearn.log_model(...)` with **no** `registered_model_name=` kwarg (see M1 below).
5. After the run, register via `mlflow.register_model(...)` and set the UC alias (typically `prod` or `Champion`, match the demo's convention).
6. Insert an early-exit cell into any downstream `*-automl-generated-notebook-*` companion notebook that calls `dbutils.notebook.exit("skipped")` when the UC alias already exists.

**Example before** (fails with `PlanMetrics not JSON serializable` on serverless):

```python
try:
    from databricks import automl
    automl_run = automl.classify(
        dataset=features_df,
        target_col="is_fraud",
        timeout_minutes=5,
    )
except ImportError:
    DBDemos.create_mockup_automl_run(...)
```

**Example after**:

```python
import mlflow
from mlflow.tracking import MlflowClient
from sklearn.ensemble import RandomForestClassifier
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline

mlflow.autolog(disable=True)
mlflow.sklearn.autolog(disable=True)
mlflow.set_registry_uri("databricks-uc")

pdf = features_df.sample(0.02).toPandas()
numeric_cols = [...]      # detect from schema
categorical_cols = [...]

pre = ColumnTransformer([
    ("num", StandardScaler(), numeric_cols),
    ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols),
])
pipe = Pipeline([
    ("pre", pre),
    ("clf", RandomForestClassifier(n_estimators=50, random_state=42)),
])
pipe.fit(pdf[numeric_cols + categorical_cols], pdf["is_fraud"])

model_full_name = f"{catalog}.{db}.dbdemos_fsi_fraud"
with mlflow.start_run(run_name="serverless_sklearn_rewrite") as run:
    # UC requires signature= on every log_model (see M3 below)
    from mlflow.models.signature import infer_signature
    X_sample = pdf[numeric_cols + categorical_cols].head(100)
    signature = infer_signature(X_sample, pipe.predict(X_sample))
    mlflow.sklearn.log_model(
        pipe,
        artifact_path="model",
        signature=signature,
    )  # no registered_model_name= (see M1)

r = mlflow.register_model(
    model_uri=f"runs:/{run.info.run_id}/model",
    name=model_full_name,
)
MlflowClient().set_registered_model_alias(
    name=model_full_name,
    alias="prod",
    version=r.version,
)
```

**Companion fixes** when A3 is applied:
- **E2** (downstream serving): flip `force_update = False` → `force_update = True` so the existing endpoint re-binds to the rewritten signature.
- **P2** (dtype alignment): cast `prediction` column to `IntegerType` for binary classifiers (see P2 section below).

---

## A4: mlflow 2.19.0 `pyfunc.spark_udf` closure bug on Spark Connect

**Problem**: On Spark Connect, `mlflow.pyfunc.spark_udf` (mlflow 2.19.0) captures `loaded_model` as a free variable in its inner `batch_predict_fn`. Worker-side deserialization fails with `NameError: cannot access free variable 'loaded_model'`. The root cause is Spark Connect serialization semantics, not mlflow itself, but mlflow 2.19.0's UDF code triggers the bug.

**Detect**:
- `loaded_model = mlflow.pyfunc.spark_udf(spark, model_uri, ...)` followed by `df.withColumn("prediction", loaded_model(struct(*features)))`
- mlflow version pinned to `==2.19.0` in the environment spec
- Common in `04.3-Batch-Scoring-*` notebooks (lakehouse-fsi-credit, lakehouse-fsi-fraud, lakehouse-hls-readmission, mlops-end2end)

**Fix Option 1 (preferred, portable across mlflow versions)**: driver-side pandas inference.

```python
# BEFORE:
loaded_model = mlflow.pyfunc.spark_udf(spark, "models:/main.churn.model@prod")
scored = df.withColumn("prediction", loaded_model(struct(*feats)))

# AFTER (Option 1, recommended):
model = mlflow.pyfunc.load_model("models:/main.churn.model@prod")
pdf = df.select(*feats, "patient_id").toPandas()
pdf["prediction"] = model.predict(pdf[feats])
scored = spark.createDataFrame(pdf)
```

**Fix Option 2 (fallback, smaller change)**: pin `mlflow>=2.20.0` in the environment spec.

```json
{
  "environment_key": "Default",
  "spec": {
    "client": "2",
    "dependencies": ["mlflow>=2.20.0", "scikit-learn==1.3.0"]
  }
}
```

**Recommend Option 1 by default**: works on any mlflow version, no version conflicts with other dependencies in the environment spec. Use Option 2 only when the workload depends on `spark_udf` semantics that cannot be reproduced driver-side (e.g., distributed inference on TB-scale data).

---

## M1: Drop `registered_model_name=` from `log_model` under UC

**Problem**: Under UC (`mlflow.set_registry_uri("databricks-uc")`), passing `registered_model_name=` to `mlflow.<flavor>.log_model(...)` triggers an internal call to `get_model_version_by_alias(..., 'Champion')` that raises `RESOURCE_DOES_NOT_EXIST` for brand-new models (no alias yet exists).

**Detect**:
- `mlflow.set_registry_uri("databricks-uc")` anywhere in scope (notebook body or via `%run`)
- Any subsequent `mlflow.<flavor>.log_model(..., registered_model_name=<name>)` (any flavor: `sklearn`, `pytorch`, `tensorflow`, `pyfunc`, etc.)

**Fix**:
1. Drop `registered_model_name=` from `log_model(...)`.
2. After the `with mlflow.start_run()` block, call `mlflow.register_model(model_uri=f"runs:/{run.info.run_id}/model", name=<full_name>)`.
3. Use the returned `r.version` to set aliases.

**Example before** (raises `RESOURCE_DOES_NOT_EXIST` then `TypeError: 'NoneType' object is not iterable`):

```python
mlflow.set_registry_uri("databricks-uc")
with mlflow.start_run() as run:
    mlflow.sklearn.log_model(model, "model", registered_model_name=model_full_name)
client = MlflowClient()
v = max(
    client.get_registered_model(model_full_name).latest_versions,
    key=lambda x: x.creation_timestamp,
)
```

**Example after** (UC-aware):

```python
mlflow.set_registry_uri("databricks-uc")
with mlflow.start_run() as run:
    mlflow.sklearn.log_model(model, "model")  # NO registered_model_name=

r = mlflow.register_model(
    model_uri=f"runs:/{run.info.run_id}/model",
    name=model_full_name,
)
MlflowClient().set_registered_model_alias(
    model_full_name,
    "Champion",
    version=r.version,
)
```

---

## M2: Replace `.latest_versions` access with `search_model_versions` + sort+index

**Problem**: `RegisteredModel.latest_versions` is always `None` on UC. `max(None, key=...)` raises `TypeError: 'NoneType' object is not iterable`.

**Detect**:
- `mlflow.set_registry_uri("databricks-uc")` is present in scope.
- Any access to `.latest_versions` on a `RegisteredModel` (e.g., `client.get_registered_model(name).latest_versions`).

**Fix**: replace `.latest_versions` access with `client.search_model_versions(f"name='{model_name}'")` plus sort+index. Use sort+index (not `max(..., key=)`) per A2 to avoid the `from pyspark.sql.functions import *` shadow.

**Example before** (raises `TypeError: 'NoneType' object is not iterable`):

```python
client = MlflowClient()
v = max(
    client.get_registered_model(model_full_name).latest_versions,
    key=lambda x: x.creation_timestamp,
)
```

**Example after**:

```python
client = MlflowClient()
_versions = list(client.search_model_versions(f"name='{model_full_name}'"))
_versions.sort(key=lambda mv: int(mv.version), reverse=True)
v = _versions[0]
```

---

## M3: Pass `signature=` to `log_model` under UC (required, not optional)

**Problem**: Under UC (`mlflow.set_registry_uri("databricks-uc")`), `mlflow.<flavor>.log_model(...)` without a `signature=` kwarg raises `MlflowException: Model signature is required for registering a model to Unity Catalog. ...`. The error fires *during* `log_model` (before `mlflow.register_model`), so the run completes but the model artifact is invalid for UC promotion.

**Detect**:
- `mlflow.set_registry_uri("databricks-uc")` anywhere in scope.
- Any `mlflow.<flavor>.log_model(...)` call (sklearn, pytorch, pyfunc, etc.) that omits `signature=`.
- Common in `04.1-Automl-*`, `04.2-Model-Registration-*`, and any cell that builds a model inline before registration.

**Fix**: infer the signature from a sample of the training data and pass it to `log_model`.

**Example before** (raises `MlflowException` under UC):

```python
mlflow.set_registry_uri("databricks-uc")
with mlflow.start_run() as run:
    mlflow.sklearn.log_model(pipe, artifact_path="model")  # no signature= -> UC rejects
```

**Example after** (UC-aware):

```python
from mlflow.models.signature import infer_signature

mlflow.set_registry_uri("databricks-uc")

X_sample = pdf[features].head(100)
y_sample = pipe.predict(X_sample)
signature = infer_signature(X_sample, y_sample)

with mlflow.start_run() as run:
    mlflow.sklearn.log_model(
        pipe,
        artifact_path="model",
        signature=signature,
    )
```

**Notes**:
- For `mlflow.pyfunc.log_model`, infer the signature from a representative pandas input + sample prediction from the pyfunc wrapper, not from raw Spark DataFrames.
- For models with multiple outputs (e.g., classification probabilities), pass the full prediction array; `infer_signature` handles multi-column outputs.
- Combine with **M1** (no `registered_model_name=`) and **M2** (no `.latest_versions`) — all three apply together on every UC `log_model` call.

---

## P2: Sklearn prediction-column dtype alignment for binary classifiers

**Problem**: When applying the A3 rewrite (`automl.classify` → sklearn Pipeline), `model.predict()` emits `float64` by default. After `spark.createDataFrame(pdf)` round-trips this to Spark, the `prediction` column is `DoubleType`. The original AutoML demo emits `prediction` as `IntegerType` (typical for binary classifiers). Downstream notebooks that MERGE on `prediction` fail with `[DELTA_FAILED_TO_MERGE_FIELDS]: prediction (Double) vs prediction (Integer)`.

**Detect**:
- A3 rewrite has been applied.
- Original AutoML demo emits `prediction` as `IntegerType`.
- Downstream cells write to a Delta table that already has a `prediction` `IntegerType` column (e.g., lakehouse-fsi-credit's `explainability_and_fairness` task).

**Fix**: cast predictions to match the demo's original schema before writing. For binary classifiers, that is `IntegerType`.

**Example before** (in migrated sklearn cell):

```python
pdf["prediction"] = pipe.predict(pdf[features])  # emits float64
scored = spark.createDataFrame(pdf)
scored.write.format("delta").mode("append").saveAsTable(predictions_table)
# Downstream MERGE fails with DELTA_FAILED_TO_MERGE_FIELDS: prediction (Double) vs prediction (Integer)
```

**Example after**:

```python
import pyspark.sql.types as T
pdf["prediction"] = pipe.predict(pdf[features]).astype("int64")  # cast to int
scored = spark.createDataFrame(pdf)
scored = scored.withColumn("prediction", scored["prediction"].cast(T.IntegerType()))
scored.write.format("delta").mode("append").saveAsTable(predictions_table)
```

---

## Combined rewrite checklist (A3 + M1 + M2 + P2 together)

When migrating an AutoML notebook with downstream batch scoring, apply **all of these in one pass**:

1. **A3**: rewrite `automl.classify/regress/forecast` as inline sklearn `Pipeline` with `mlflow.autolog(disable=True)`.
2. **M1**: drop `registered_model_name=` from `log_model`; call `mlflow.register_model(...)` after the run.
3. **M2**: replace any `.latest_versions` access with `search_model_versions` + sort+index.
4. **M3**: pass `signature=infer_signature(X_sample, y_sample)` to every `log_model` call under UC (required, not optional).
5. **A2**: use sort+index everywhere (not `max(..., key=)`) because `from pyspark.sql.functions import *` shadows the builtin.
6. **P2**: cast `prediction` column to `IntegerType` for binary classifiers before writing to Delta.
7. **E1**: if the model is loaded inside an SDP `.py` library file via `pyfunc.spark_udf(..., env_manager='local')`, emit `%pip install -q databricks-automl-runtime` at the top of the SDP file (because cloudpickle reconstructs AutoML-trained artifacts and needs the runtime module).
8. **E2**: in any downstream `04.3-Model-serving-*` companion notebook, flip `force_update = False` → `force_update = True` so the endpoint re-binds to the rewritten signature.

**Verification (post-migration)**:
- The migrated tree contains zero `from databricks import automl` imports and zero `DBDemos.create_mockup_automl_run` calls.
- The migrated tree contains zero `registered_model_name=` kwargs on `log_model` (when UC registry is in scope).
- Every `log_model` call under UC has a `signature=` kwarg derived from `infer_signature(...)`.
- The migrated tree contains zero `.latest_versions` references.
- The migrated tree contains zero `mlflow.pyfunc.spark_udf` calls (Option 1 driver-side rewrite applied).
- Running the migrated job end-to-end on serverless produces a UC-registered model with the demo's expected alias (`prod` or `Champion`), and downstream batch-scoring and explainability tasks pass.

## Documentation

- MLflow Model Registry on UC: https://docs.databricks.com/en/machine-learning/manage-model-lifecycle/index.html
- MLflow PyFunc: https://mlflow.org/docs/latest/python_api/mlflow.pyfunc.html
- Spark Connect overview: https://docs.databricks.com/en/spark/connect-vs-classic
- Serverless ML libraries: https://docs.databricks.com/en/compute/serverless/dependencies
