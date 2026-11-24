# Feature Tables

Use this workflow only when the user explicitly asks for feature tables or `FeatureLookup`. For new feature engineering, use [Feature Views](feature-views.md). In a project that already has feature tables, keep the tables and add new features as Feature Views over them (see [Feature Views over existing feature tables](#feature-views-over-existing-feature-tables)).

Docs: [Feature tables in Unity Catalog](https://docs.databricks.com/machine-learning/feature-store/uc/feature-tables-uc) · [Point-in-time lookups](https://docs.databricks.com/machine-learning/feature-store/time-series)

## Core rules

- A Unity Catalog feature table is a Delta table with a primary key constraint. A table written only with `df.write.saveAsTable(...)` is not a feature table until a primary key constraint is added.
- Use `FeatureEngineeringClient` from `databricks.feature_engineering`. `FeatureStoreClient` is for the legacy Workspace Feature Store.
- Train with `FeatureLookup` and `fe.create_training_set(...)`; do not join feature tables onto the labels by hand.
- Log the model with `fe.log_model(..., training_set=training_set, ...)` so inference can look features up again. `mlflow.<flavor>.log_model` drops the lineage, and `score_batch` then fails.
- Primary key columns must be non-null.
- If feature values change over time, use a time series feature table and pass `timestamp_lookup_key` in `FeatureLookup`, so training joins are point-in-time correct. Without it, future values leak into training.

## Create a feature table

```python
from databricks.feature_engineering import FeatureEngineeringClient
from pyspark.sql.functions import avg, count

fe = FeatureEngineeringClient()

features_df = (
    spark.read.table("samples.nyctaxi.trips")
    .groupBy("pickup_zip")
    .agg(
        avg("fare_amount").alias("avg_fare_amount"),
        count("*").alias("trip_count"),
    )
)

fe.create_table(
    name="main.ny.zip_features",
    primary_keys=["pickup_zip"],
    df=features_df,
    schema=features_df.schema,
    description="NYC taxi features by pickup ZIP code",
)
```

Update rows later with `fe.write_table(name=..., df=..., mode="merge")`; `merge` (upsert) is the default.

To promote an existing Delta table, make the key non-null and add the constraint:

```python
spark.sql("ALTER TABLE main.ny.zip_features ALTER COLUMN pickup_zip SET NOT NULL")
spark.sql("ALTER TABLE main.ny.zip_features ADD CONSTRAINT zip_features_pk PRIMARY KEY (pickup_zip)")
```

### Time series feature tables

The timestamp column is part of `primary_keys` and is also named in `timeseries_column`:

```python
fe.create_table(
    name="main.ny.customer_features_by_time",
    primary_keys=["customer_id", "event_timestamp"],
    timeseries_column="event_timestamp",
    df=features_df,
    schema=features_df.schema,
)
```

In SQL, declare it with `PRIMARY KEY (customer_id, event_timestamp TIMESERIES)` (Databricks Runtime 13.3 LTS and above).

## Train with FeatureLookup

```python
from datetime import timedelta
from databricks.feature_engineering import FeatureLookup
import mlflow

feature_lookups = [
    FeatureLookup(table_name="main.ny.zip_features", lookup_key="pickup_zip"),
    FeatureLookup(
        table_name="main.ny.customer_features_by_time",
        lookup_key="customer_id",                 # entity keys only, without the timestamp
        timestamp_lookup_key="prediction_timestamp",
        lookback_window=timedelta(days=30),       # optional: ignore feature rows older than this
    ),
]

training_set = fe.create_training_set(
    df=labels_df,                                 # lookup keys + timestamp lookup key + label
    feature_lookups=feature_lookups,
    label="high_fare",
    exclude_columns=["pickup_zip", "customer_id", "prediction_timestamp"],
)
training_df = training_set.load_df().toPandas()

with mlflow.start_run():
    fe.log_model(
        model=model, artifact_path="model", flavor=mlflow.sklearn,
        training_set=training_set, registered_model_name="main.ny.high_fare_model",
    )
```

`create_training_set` takes either `feature_lookups` or `features` (Feature Views), not both. To combine feature-table columns with Feature Views in one model, define the table columns as Feature Views too (next section).

## Score with score_batch

For a model logged with `fe.log_model`, pass only the lookup keys (plus the timestamp lookup column, with the same name and type as in training); feature values are joined automatically:

```python
predictions_df = fe.score_batch(model_uri="models:/main.ny.high_fare_model/1", df=scoring_df)
```

## Publish to an online store

Model serving endpoints look features up from an online store (backed by Lakebase). `CONTINUOUS` and `TRIGGERED` publish modes need change data feed on the source table and a non-null primary key; `SNAPSHOT` does not.

```python
spark.sql("ALTER TABLE main.ny.zip_features SET TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')")

# Store names are DNS-compliant: letters, digits, and hyphens, no underscores.
# get_online_store returns None (it does not raise) when the store is missing.
store = fe.get_online_store(name="ny-online-store")
if store is None:
    fe.create_online_store(name="ny-online-store", capacity="CU_1")
# publish once fe.get_online_store(name="ny-online-store").state is AVAILABLE

fe.publish_table(
    online_store=fe.get_online_store(name="ny-online-store"),
    source_table_name="main.ny.zip_features",
    online_table_name="main.ny.zip_features_online",
    publish_mode="CONTINUOUS",                    # or "TRIGGERED" / "SNAPSHOT"
)
```

Once published, a model logged with `fe.log_model` looks its features up when it is served; for endpoint lifecycle see [databricks-model-serving](../../databricks-model-serving/SKILL.md).

## Feature Views over existing feature tables

A feature table is a Delta table, so Feature Views can read it without changing how it is written. Define one `ColumnSelection` feature per column you want, with the table's entity keys as `entity` and a timestamp column as `timeseries_column` (every Feature View needs one; add a timestamp column to the table if it has none):

- **A triggered Spark Declarative Pipeline writes the table:** use an `SdpSource` with the table as `output_table` and the tables the pipeline reads as `input_tables`. Feature Store runs the pipeline before each materialization.
- **Anything else writes the table:** use a `DeltaTableSource` on it.

```python
from databricks.feature_engineering.entities import ColumnSelection, SdpSource

source = SdpSource(
    pipeline_id="1234abcd-5678-90ef-1234-567890abcdef",
    output_table="main.features.user_profile",
    input_tables=["main.raw.users"],
)

user_country = fe.create_feature(
    source=source,
    function=ColumnSelection("country"),
    entity=["user_id"],
    timeseries_column="updated_at",
    catalog_name="main",
    schema_name="features",
    name="user_country",
)
```

These features train, score, and materialize like any other Feature View; see [feature-views.md](feature-views.md). `SdpSource` needs `databricks-feature-engineering>=0.18.3`. Docs: [Use feature tables that a pipeline writes](https://docs.databricks.com/machine-learning/feature-store/sdp-source#use-feature-tables-that-a-pipeline-writes).
