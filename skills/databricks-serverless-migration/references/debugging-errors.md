# Debugging Failed Serverless Runs

Error → fix table for serverless runs. Pattern IDs (A1, M1, ...) are defined in [Analyze Checklist](analyze-checklist.md).

Always get the actual error with `w.jobs.get_run_output(run_id=...)` before guessing. Common errors:

| Error | Fix |
|-------|-----|
| `INFINITE_STREAMING_TRIGGER_NOT_SUPPORTED` | Add `.trigger(availableNow=True)` |
| `UNRESOLVED_COLUMN` | Temp view name collision — use unique names |
| `TABLE_OR_VIEW_NOT_FOUND` | DBFS/HMS table not accessible — migrate to UC |
| `Py4JError: ... is not available` | SparkContext/RDD used — rewrite to DataFrame |
| Package installation timeout | Pin versions; do NOT install PySpark as a dependency |
| `ModuleNotFoundError: No module named 'mlflow'` | Add to environment spec `dependencies` — ML runtime is NOT available on serverless |
| `SparkContext.getOrCreate() is NOT supported` / `RuntimeError: Only remote Spark sessions` | Replace with `spark.createDataFrame()` or `spark.range()` |
| `UC_FILE_SCHEME_FOR_TABLE_CREATION_NOT_SUPPORTED` | Use managed tables or `/Volumes/...` paths |
| `PERMISSION_DENIED: CREATE SCHEMA on Catalog 'main'` | Add `spark.sql("USE CATALOG <your_catalog>")` before CREATE statements |
| `DATA_SOURCE_NOT_FOUND: Failed to find data source` | Category 3 blocker — custom JAR data source needs classic compute |
| `NoSuchMethodError: scala.Predef$.wrapRefArray` / `NoClassDefFoundError: scala/Serializable` on a JAR run | Scala version mismatch — JAR compiled against 2.12; serverless is 2.13.16. Recompile against 2.13.16. See [JAR Migration](jar-migration.md) |
| `NoClassDefFoundError` for `org/apache/spark/...` on a JAR run | Spark bundled instead of provided. Mark `databricks-connect % Provided` (and rewrite any `SparkContext`/RDD source). See [JAR Migration](jar-migration.md) |
| `SyntaxError` after migration | Ensure comments are inside MAGIC blocks, not straddling cell delimiters |
| `File './<name>' not found` from `%run` (or `%run` fires as IPython line magic) | A1: a plain-Python comment is preceding `# MAGIC %run` in the same cell. Move the comment to its own `# MAGIC %md` cell above. |
| `TypeError: max() got an unexpected keyword argument 'key'` | A2: `from pyspark.sql.functions import *` shadowed builtin `max`. Use sort+index instead of `max(..., key=)`. |
| `TypeError: Object of type PlanMetrics is not JSON serializable` | A3: `automl.classify/regress/forecast` not supported; the `DBDemos.create_mockup_automl_run` fallback hits this on Spark Connect. Rewrite as inline sklearn Pipeline. |
| `NameError: cannot access free variable 'loaded_model'` | A4: mlflow 2.19.0 `pyfunc.spark_udf` closure bug on Spark Connect. Use driver-side `pyfunc.load_model` + `toPandas()` + `spark.createDataFrame`, or pin `mlflow>=2.20.0`. |
| `ModuleNotFoundError: No module named 'databricks.automl_runtime'` | E1: SDP image missing `databricks-automl-runtime`. Emit `%pip install -q databricks-automl-runtime` at top of the SDP `.py` library file. |
| `HTTP 400: Failed to enforce schema of data ... Model is missing inputs ['id']` | E2: AutoML → sklearn rewrite changed model signature; flip downstream `force_update = False` → `True`. |
| `RESOURCE_DOES_NOT_EXIST` from `get_model_version_by_alias(..., 'Champion')` during `log_model` | M1: drop `registered_model_name=` from `log_model` under UC; call `mlflow.register_model(...)` after the run. |
| `TypeError: 'NoneType' object is not iterable` from `.latest_versions` | M2: `RegisteredModel.latest_versions` is always `None` on UC. Use `client.search_model_versions(...)` + sort+index. |
| `MlflowException: Model signature is required for registering a model to Unity Catalog` | M3: UC requires `signature=` on `log_model`. Infer via `infer_signature(X_sample, model.predict(X_sample))` and pass to `log_model(..., signature=signature)`. See [MLflow on UC](mlflow-uc-patterns.md). |
| 404 on `ai_query(endpoint => 'databricks-meta-llama-3-1-405b-instruct')` | D1: retired Foundation Model endpoint. Replace with `databricks-meta-llama-3-3-70b-instruct` via content scan across all migrated files. |
| `PERMISSION_DENIED: User does not have CREATE CATALOG on Metastore` (even when catalog exists) | B2: priv check fires before `IF NOT EXISTS` short-circuits. Guard with `SHOW CATALOGS LIKE '...'` probe. Apply recursively, including `_resources/` and `config*` files. |
| `Table is already managed by pipeline <pipeline-id>` on SDP parallel deploy | H2: suffix the migrated pipeline's target `schema` (e.g., `<orig>_skill_migrated`). |
| `DELTA_FAILED_TO_MERGE_FIELDS: prediction (Double) vs prediction (Integer)` | M4: AutoML → sklearn rewrite emits `float64` predictions; cast to `IntegerType` for binary classifiers before writing. See [MLflow on UC](mlflow-uc-patterns.md). |

See [Configuration Guide](configuration-guide.md) for the full error reference and SDK code examples.
