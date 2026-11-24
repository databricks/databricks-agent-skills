# Feature Views

Feature Views are a simple, powerful framework for creating Features in the latest `databricks-feature-engineering` client. The core primitive is a **`Feature`** object: a data source plus a computation function, and — for aggregations — an entity (grain) and a timeseries column. From one `Feature` object you can: **compute** its values directly, build a **training set**, **register** it to Unity Catalog, **materialize** it to an offline store (for training reuse) and/or an online store — backed by Lakebase — for low-latency serving, and **serve** it.

Use Feature Views for all feature engineering — batch, streaming, and request-time features. Use the feature-table workflow (`create_table` / `write_table` / `FeatureLookup`, see [feature-tables.md](feature-tables.md)) only when the user explicitly asks for it. When a project already has feature tables, keep them and define Feature Views over them ([Feature Views over existing feature tables](feature-tables.md#feature-views-over-existing-feature-tables)) instead of rewriting them.

Docs: [Feature Views](https://docs.databricks.com/machine-learning/feature-store/feature-views) · [API reference](https://docs.databricks.com/machine-learning/feature-store/feature-views-api-reference) · [Materialized features](https://docs.databricks.com/machine-learning/feature-store/materialized-features)

## Prerequisites

Feature Views is generally available. Use serverless or a classic cluster on Databricks Runtime 17.0 ML or above, and install the client at the top of the notebook. This file relies on behavior from client 0.18.3 and above (`SdpSource`, Sawtooth lifetime windows, `RollingWindow(window_duration=None)`):

```python
%pip install -U "databricks-feature-engineering>=0.18.3"
dbutils.library.restartPython()
```

```python
from databricks.feature_engineering import FeatureEngineeringClient
from databricks.sdk import WorkspaceClient

fe = FeatureEngineeringClient()   # every snippet below uses fe
w = WorkspaceClient()             # and w for serving endpoints and pipelines
```

## Choosing windows and features

Before defining features, use EDA to choose entities and window sizes:

- **Entities** are the natural grouping keys (e.g. `pickup_zip`, `customer_id`, `merchant_id`); confirm the timeseries column and the event frequency.
- **Window granularity follows event frequency:** high-frequency (many events/hour) → sub-daily windows (1h/3h/6h); daily → 1d/7d/14d/30d; sparse (weekly or less) → 7d/30d/90d. A quick `groupBy(entity, to_date(ts)).count()` reveals per-entity frequency.

Common problem → feature mappings:

- **Behavioral velocity** (fraud/anomaly): `Sum`/`Avg` of amount and `Count`, each across several windows; `ApproxCountDistinct` for entity diversity (distinct merchants per customer, customers per merchant).
- **RFM** (churn, lead scoring, lifetime value): Recency = `Count` over short windows (1d/3d); Frequency = `Count` over long windows (30d/90d); Monetary = `Sum` over 30d/90d.
- **Trend detection** (forecasting, behavioral shift): compare a recent window against the same window shifted back with `delay` — e.g. `RollingWindow(window_duration=timedelta(days=7))` vs `RollingWindow(window_duration=timedelta(days=7), delay=timedelta(days=7))`.
- **Static lookups**: use `ColumnSelection` for non-aggregated reference attributes instead of an aggregation.

## The Feature object

A `Feature` combines a **source**, a **function**, and (for aggregations) an **entity** and **timeseries_column**:

```python
from databricks.feature_engineering.entities import (
    Feature, DeltaTableSource, AggregationFunction, Avg, TumblingWindow,
)
from datetime import timedelta

avg_fare = Feature(
    source=DeltaTableSource(catalog_name="main", schema_name="ny", table_name="trips"),
    function=AggregationFunction(Avg(input="fare_amount"), TumblingWindow(window_duration=timedelta(days=30))),
    entity=["pickup_zip"],
    timeseries_column="tpep_pickup_datetime",
    name="avg_fare_30d",           # optional; auto-generated if omitted
)
```

There are two kinds of `function`:

- **`AggregationFunction(operator(input="col"), time_window)`** — a windowed aggregate. Requires `entity` and `timeseries_column`.
- **`ColumnSelection("col")`** — a pass-through / latest value. No `AggregationFunction` wrapper, no time window.

`entity` and `timeseries_column` live on the **`Feature`**, not on the source — so one source can back features at different grains.

## Create a Feature

### Sources

```python
from databricks.feature_engineering.entities import DeltaTableSource, StreamSource, RequestSource, FieldDefinition, ScalarDataType

# Delta table (batch)
src = DeltaTableSource(
    catalog_name="main", schema_name="ny", table_name="trips",
    filter_condition="fare_amount > 0",        # optional SQL WHERE, applied before aggregation
    # transformation_sql="...", dataframe_schema="..."  # optional column transforms
)

# Stream (real-time). Reference a Stream by three-part name; prefix columns with value./key.
stream = StreamSource(full_name="main.ny.trips_stream", filter_condition="value.event_type = 'paid'")

# Request-time input (provided in the serving payload). Scalar types only; ColumnSelection only.
req = RequestSource(schema=[FieldDefinition(name="distance_km", data_type=ScalarDataType.DOUBLE)])
```

`timeseries_column` must be `TimestampType` or `TimestampNTZType`; cast a `DateType` column with `transformation_sql` (which also needs `dataframe_schema`). `entity` columns cannot be `DATE`/`TIMESTAMP`.

### Create a Stream — prerequisite for `StreamSource`

`StreamSource(full_name=...)` **references** a Stream; it does not create one. A Stream is a governed UC entity you create once with `fe.create_stream` before any `StreamSource` can point at it. All arguments are keyword-only. It takes four configs — source, connection, schema, ingestion. Example:

```python
from databricks.feature_engineering.entities import (
    KafkaStreamConfig, KafkaSubscriptionMode, StreamConnectionConfig,
    DirectSchemas, SchemaConfig, IngestionConfig, IngestionDestination,
)

stream = fe.create_stream(
    name="main.ny.trips_stream",                                  # three-part UC name
    source_config=KafkaStreamConfig(
        subscription_mode=KafkaSubscriptionMode(subscribe="trips-topic"),  # or subscribe_pattern="trips-.*" / assign='{"trips-topic":[0,1]}'
    ),
    connection_config=StreamConnectionConfig(uc_connection_name="my-kafka-connection"),  # recommended; see mTLS below
    schema_config=DirectSchemas(                                  # ≥1 of payload_schema/key_schema required
        payload_schema=SchemaConfig(json_schema='{"type":"object","properties":{"user_id":{"type":"string"},"amount":{"type":"number"},"event_time":{"type":"string","format":"date-time"}}}'),
    ),
    ingestion_config=IngestionConfig(                             # Databricks-managed ingestion (Delta) table backing the Stream
        ingestion_destination=IngestionDestination(delta_table_name="main.ny.trips_ingestion"),
    ),
)
```

- **Auth.** `StreamConnectionConfig(uc_connection_name=...)` (recommended) needs a pre-existing UC connection (`CREATE CONNECTION` on the metastore, or ask an admin + get `USE CONNECTION`). The connection authenticates with a UC service credential (IAM, e.g. Amazon MSK; also needs `ACCESS` on the credential) or SASL (`sasl_mechanism` `PLAIN`/`SCRAM-SHA-256`/`SCRAM-SHA-512` with `user`/`password`). For direct mTLS use `DirectMtlsConfig(bootstrap_servers=..., mtls_config=MtlsConfig(keystore_location=..., keystore_password_ref=SecretScopeReference(scope=..., key=...), ...))`.
- **Schemas.** Each `SchemaConfig` takes one of `json_schema`, `avro_schema`, or `proto_schema=ProtoSchemaSpec(schema_text=..., message_name="pkg.Message")` (fully-qualified name). With Confluent Schema Registry (Avro/Protobuf only), pass `schema_config=SchemaRegistryConfig(api_secret_ref=SecretScopeReference(...), payload_schema_locator=SchemaLocator(confluent_schema=SchemaLocatorConfluentSchema(subject="<topic>-value"), format=SchemaLocatorFormat.FORMAT_AVRO))` and put the registry URL/key/secret on the UC connection.
- **Filter / exclude.** `record_type_filter="value.event_type = 'txn'"` on `create_stream` drops non-matching records from ingestion for every feature; `excluded_columns=["value.user.email"]` keeps columns out of ingestion entirely.
- **Ingestion & backfill.** The Stream maintains an ingestion Delta table (the historical copy that `create_training_set` reads). To seed history, pass `IngestionConfig(..., backfill_source=StreamBackfillSource(delta_table_name="main.ny.history"), deduplication_columns=["value.user_id"])`. The backfill table must have a `TIMESTAMP` column named `stream_record_timestamp`. Dedup columns use dot notation; the default is `(key, value, stream_record_timestamp)`.
- **Ingestion starts at the latest offset.** Events already in the topic when the Stream is created are never ingested, so training history before that point comes only from `backfill_source`. The ingestion table becomes readable a few minutes after creation; produce test events only after the ingestion pipeline is `RUNNING`. If the table stays empty, check `w.pipelines.get(pipeline_id=stream.ingestion_config.ingestion_pipeline_id).state` and call `w.pipelines.start_update(pipeline_id=...)` if it is `IDLE`.
- **Manage.** `fe.get_stream(name=...)`, `fe.list_streams(catalog_name=..., schema_name=...)`, `fe.update_stream(name=..., schema_config=DirectSchemas(...), excluded_columns=[...])` (backward-compatible direct-schema changes and exclusions only; restarts ingestion), `fe.delete_stream(name=...)` (also removes the ingestion pipeline + table). Access is governed by the ingestion table: `SELECT` reads, `MANAGE` deletes.

Once the Stream exists, define features against it with `StreamSource` (above) — `RollingWindow` or `SawtoothWindow`, `value.`/`key.`-prefixed columns — register them, then materialize with `StreamingMode()`. The destinations depend on the window:

- **`RollingWindow` (and `ColumnSelection`) → online only.** Pass `online_config`; `offline_config` is rejected.
- **`SawtoothWindow` → offline + online.** Pass **both** `offline_config` and `online_config`. One call creates the batch offline, batch online, and streaming online materializations that a sawtooth window merges on read.

`OnlineStoreConfig` requires `online_store_name` (an existing Online Feature Store) alongside `catalog_name`/`schema_name`/`table_name_prefix` — omitting it fails:

```python
from databricks.feature_engineering.entities import OfflineStoreConfig, OnlineStoreConfig, StreamingMode

online = OnlineStoreConfig(
    catalog_name="main", schema_name="ny",
    table_name_prefix="txn_serving", online_store_name="ny-online-store",
)

# RollingWindow streaming feature: online only
rolling_feat = fe.register_feature(feature=rolling_feat, catalog_name="main", schema_name="ny")
fe.materialize_features(features=[rolling_feat], online_config=online, trigger=StreamingMode())

# SawtoothWindow streaming feature: offline + online
sawtooth_feat = fe.register_feature(feature=sawtooth_feat, catalog_name="main", schema_name="ny")
fe.materialize_features(
    features=[sawtooth_feat],
    offline_config=OfflineStoreConfig(catalog_name="main", schema_name="ny", table_name_prefix="txn_offline"),
    online_config=online,
    trigger=StreamingMode(),
)
```

Streaming features cannot share a `materialize_features` call with batch features, cannot be backfilled with `backfill_features`, and are not supported by `compute_features` — inspect them with `create_training_set` (which reads the Stream's ingestion table) instead.

### Streaming from a Delta table (`DeltaTableSource` + `StreamingMode`)

A feature on a `DeltaTableSource` becomes a streaming feature when materialized with `trigger=StreamingMode()` — same `Feature` definition as batch, online-only (`online_config`, no `offline_config`). The source table must have change data feed enabled (`ALTER TABLE ... SET TBLPROPERTIES (delta.enableChangeDataFeed = true)`); Zerobus-populated tables do not set this automatically. Expect freshness of tens of seconds, versus ~200 ms p99 for a `StreamSource`. `SawtoothWindow` is not supported on a `DeltaTableSource`.

### Aggregation functions

Each operator takes `input="col"` and is wrapped in `AggregationFunction(operator, time_window)`:

```python
from databricks.feature_engineering.entities import (
    Sum, Avg, Count, Min, Max, StddevPop, StddevSamp, VarPop, VarSamp,
    ApproxCountDistinct, ApproxPercentile, First, Last,
    FirstN, LastN, FirstDistinct, LastDistinct,
)
```

There is no `CountDistinct` — use `ApproxCountDistinct(input="col", relativeSD=0.05)`. `ApproxPercentile(input="col", percentile=0.95, accuracy=100)`. `FirstN`/`LastN`/`FirstDistinct`/`LastDistinct(input="col", n=3)` return arrays of up to `n` values ordered by `timeseries_column`.

**Window ↔ function compatibility.** Every operator above works with every window type (`RollingWindow`, `SawtoothWindow`, `TumblingWindow`, `SlidingWindow`). A model whose features use `ApproxCountDistinct` or `ApproxPercentile` on a `SawtoothWindow` must be logged on Python 3.9–3.13; `fe.log_model` rejects other versions.

An operator rejected at `register_feature`/`create_feature` with `Function type '...' is not supported for ... window features. Supported types: ...` means the workspace doesn't support that pairing yet; the message lists what it accepts. Pick from that list, or move a batch feature to a `TumblingWindow`/`SlidingWindow`.

### Time windows

```python
from databricks.feature_engineering.entities import RollingWindow, TumblingWindow, SlidingWindow, SawtoothWindow

RollingWindow(window_duration=timedelta(days=7))                       # lookback from each row's time
RollingWindow(window_duration=timedelta(days=7), delay=timedelta(days=7))  # delay (>=0) shifts window back
TumblingWindow(window_duration=timedelta(days=1))                      # fixed, non-overlapping
SlidingWindow(window_duration=timedelta(days=7), slide_duration=timedelta(days=1))  # overlapping
SawtoothWindow(window_duration=timedelta(days=30))                     # StreamSource only; long lookback, kept fresh
```

**Lifetime windows** aggregate over each entity's entire history: pass `window_duration=None`.

- `SlidingWindow(window_duration=None, slide_duration=timedelta(days=1))` for batch sources.
- `SawtoothWindow(window_duration=None)` for streaming sources.
- `RollingWindow(window_duration=None)` only for a `Last` aggregation on a Delta source, materialized online-only with `TableTrigger()`.
- `TumblingWindow` has no lifetime form.

Streaming features support `RollingWindow` and `SawtoothWindow` for aggregations; `TumblingWindow` and `SlidingWindow` are for batch sources.

- **`RollingWindow`** for short streaming lookbacks: exact sub-second window edges, built from the live stream, so values are complete only after materialization has run for a full `window_duration`. On a `DeltaTableSource`, `RollingWindow` is also a batch window: `compute_features` and `create_training_set` compute it point-in-time from the source.
- **`SawtoothWindow`** for long streaming lookbacks (recommended above 7 days; `window_duration` must be > 2 days, or `None` for lifetime): the last two days come from the live stream and older days from the Stream's ingestion table, so it is ready to serve about two days after materialization starts even for multi-month windows. The trailing edge advances daily, so the effective window is slightly longer than `window_duration`. If the ingestion table holds less history than the window, set `start_time=datetime(...)` (no later than feature creation). No `delay` or `SourceLateness.settling_delay`; `StreamSource` only.

### ColumnSelection (pass-through / latest value)

```python
from databricks.feature_engineering.entities import ColumnSelection

latest_zone = Feature(
    source=src, function=ColumnSelection("vendor_zone"),
    entity=["pickup_zip"], timeseries_column="tpep_pickup_datetime", name="latest_zone",
)
```

## Compute

Use `compute_features` to compute and inspect a `Feature` (or list of features) **directly** — no labels, registration, or materialization. This is the fastest way to iterate on a batch definition, including `RollingWindow` features on a `DeltaTableSource` (features on a `StreamSource` are not supported; use `create_training_set`):

```python
feature_df = fe.compute_features(features=[avg_fare])
feature_df.display()
```

## Create Training Set

`create_training_set` joins features onto labeled data with **point-in-time correctness** — each row's features use only source data available before that row's timestamp. Works with locally-constructed (unregistered) `Feature` objects, so you can build training data before registering anything.

```python
training_set = fe.create_training_set(
    df=labeled_df,              # must contain entity + timeseries columns + the label
    features=[avg_fare],
    label="is_high_fare",
    exclude_columns=["pickup_zip", "tpep_pickup_datetime"],  # keep lookup keys out of the feature matrix
)
training_df = training_set.load_df()
```

The labeled `df` MUST contain every `entity` column and the `timeseries_column`, **matched by exact column name** to what the `Feature` definitions declare — a column that merely holds timestamps under a different name (e.g. `timestamp` when the feature declares `timeseries_column="event_timestamp"`) fails with `Training DataFrame is missing timestamp key required for join: <name>`. Before calling `create_training_set`, confirm the df's column names include the feature's `timeseries_column` and every `entity` name verbatim; `df.withColumnRenamed("timestamp", "event_timestamp")` if they differ. For streaming features, the df uses the **leaf** names (`user_id`, `event_time`), not the `value.`-prefixed source references. The label column name MUST NOT collide with a source column.

### Holdout evaluation

When scoring a separate holdout/test set, compute features from the **full** history (train ∪ test), not the holdout rows alone — otherwise the holdout's features lack the historical context they would have in production. Use a `DataFrameSource` over the union, redefine the same features against it, then build the eval training set:

```python
from databricks.feature_engineering.entities import DataFrameSource

full_history = train_df.unionByName(test_df).drop("is_high_fare")  # source rows only; labels stay in labeled_test_df
eval_src = DataFrameSource(dataframe=full_history, source_name="full_history")
# redefine the same Feature objects against eval_src (entity and timeseries_column stay on each Feature), then:
eval_set = fe.create_training_set(
    df=labeled_test_df, features=eval_features, label="is_high_fare",
    exclude_columns=["pickup_zip", "tpep_pickup_datetime"],
)
eval_df = eval_set.load_df()
```

## Register

Persist a `Feature` as a governed Unity Catalog object (requires `CREATE FEATURE` on the schema; reading later requires `READ FEATURE`).

```python
# Two-step: construct locally (above), then register when ready
avg_fare = fe.register_feature(feature=avg_fare, catalog_name="main", schema_name="ny")

# One-step: define and register together
latest_amount = fe.create_feature(
    source=src, function=ColumnSelection("fare_amount"),
    entity=["pickup_zip"], timeseries_column="tpep_pickup_datetime",
    catalog_name="main", schema_name="ny", name="latest_amount",
)

# Retrieve
f = fe.get_feature(full_name="main.ny.avg_fare_30d")
```

To delete a feature, follow [Delete a materialized feature / reset state](#delete-a-materialized-feature--reset-state).

## Materialize

`materialize_features` writes a **registered** feature to an offline store (for reuse in training) and/or an online store — backed by Lakebase — for low-latency serving, kept fresh by a trigger. Register before materializing.

`online_store_name` must name an existing Online Feature Store. Its name must be DNS-compliant: letters, digits, and single hyphens, no underscores. `get_online_store` returns `None` (it does not raise) when the store is missing:

```python
store = fe.get_online_store(name="ny-online-store")
if store is None:
    fe.create_online_store(name="ny-online-store", capacity="CU_1")
# materialize once fe.get_online_store(name="ny-online-store").state is AVAILABLE
```

```python
from databricks.feature_engineering.entities import (
    OfflineStoreConfig, OnlineStoreConfig, CronSchedule, TableTrigger, StreamingMode,
)

fe.materialize_features(
    features=[avg_fare],
    offline_config=OfflineStoreConfig(catalog_name="main", schema_name="ny", table_name_prefix="fare_features"),
    online_config=OnlineStoreConfig(
        catalog_name="main", schema_name="ny",
        table_name_prefix="fare_features_serving", online_store_name="ny-online-store",
    ),
    trigger=CronSchedule(quartz_cron_expression="0 0 * * * ?", timezone_id="UTC"),  # hourly
)
```

Pick the trigger by feature type (you cannot mix trigger types in one call):

| Feature type | Trigger | Stores |
|---|---|---|
| `TumblingWindow` / `SlidingWindow` aggregation (from `DeltaTableSource`) | `CronSchedule` or `TableTrigger()` | offline + online |
| `ColumnSelection` (from `DeltaTableSource`) | `TableTrigger()` | online only |
| `Last` with a `RollingWindow` (from `DeltaTableSource`) | `TableTrigger()` | online only |
| `RollingWindow` or `ColumnSelection` from a `StreamSource` | `StreamingMode()` | online only |
| `SawtoothWindow` from a `StreamSource` | `StreamingMode()` | offline + online (both configs required) |
| Streaming from a CDF-enabled `DeltaTableSource` | `StreamingMode()` | online only |

Other batch `RollingWindow` aggregations are not materialized: `create_training_set` and `score_batch` compute them point-in-time from the source.

### Delete a materialized feature / reset state

To tear down or reset a feature, **always `list_materialized_features(feature_name=...)` first, then delete what it returns, then `delete_feature`** — never delete the feature straight away. Listing first is harmless even when the feature was never materialized (it just returns empty), and it's the reliable path because a request to "delete a feature" is usually ambiguous about whether materializations exist. `list_materialized_features` takes a single feature's full name (keyword arg); to sweep many features, list features in a catalog/schema and call `list_materialized_features` on each. Which materialization to delete depends on the feature type: for aggregation features, including `SawtoothWindow`, delete the **offline** materialized feature (every paired online materialization, batch and streaming, is removed with it); `ColumnSelection` and `RollingWindow` streaming features are online-only, so delete the online one directly.

```python
for name in feature_names:
    mfs = fe.list_materialized_features(feature_name=name)   # required, keyword-only
    offline = [mf for mf in mfs if not mf.is_online]
    # Aggregation → delete offline (paired online goes with it).
    # ColumnSelection / RollingWindow streaming → online-only, delete those.
    for mf in (offline or mfs):
        fe.delete_materialized_feature(materialized_feature=mf)
    fe.delete_feature(full_name=name)   # remove referencing models/feature specs first
```

Deleting a feature that was never materialized needs only `delete_feature`. Guard cleanup loops so a missing feature is a no-op rather than an error (`get_feature` on an absent feature raises).

## Serving Patterns

First log a model with feature lineage (needed for batch and online model serving) — `fe.log_model` records which features the model used so they can be recomputed/looked-up at inference:

```python
import mlflow
with mlflow.start_run():
    fe.log_model(
        model=model, artifact_path="model", flavor=mlflow.sklearn,
        training_set=training_set, registered_model_name="main.ny.high_fare_model",
    )
```

### 1. Batch scoring (offline)

`score_batch` recomputes features point-in-time from the source — **no online store required**. The scoring `df` needs the entity keys, the timeseries column, and every `RequestSource` column the model was trained with (e.g. `distance_km`): request-time values come from the scoring `df`, not from a source.

`score_batch` rejects a model with any feature on a `StreamSource` (`NotImplementedError: Batch scoring with streaming sources is not yet supported`). Serve those models from a model serving endpoint (pattern 2).

```python
predictions = fe.score_batch(
    model_uri="models:/main.ny.high_fare_model/1",   # or runs:/<run_id>/model
    df=scoring_df,
)
```

### 2. Online model serving (real-time predictions)

Materialize the features to an **online store** (above), register the model in UC, then deploy it to a model serving endpoint. The endpoint looks up features from the online store automatically via lineage.

```python
from databricks.sdk.service.serving import EndpointCoreConfigInput, ServedEntityInput

w.serving_endpoints.create(
    name="high-fare-endpoint",
    config=EndpointCoreConfigInput(
        name="high-fare-endpoint",
        served_entities=[ServedEntityInput(
            entity_name="main.ny.high_fare_model", entity_version=1,
            max_provisioned_concurrency=4, min_provisioned_concurrency=0,
        )],
    ),
)

# Query: pass entity keys + timeseries (+ any RequestSource columns the model was trained with)
w.serving_endpoints.query(
    name="high-fare-endpoint",
    dataframe_records=[{"pickup_zip": "10003", "tpep_pickup_datetime": "2026-03-01T12:00:00"}],
)
```

### 3. Feature Serving (feature values, no model)

When an application needs feature **values** rather than predictions, deploy a `FeatureSpec` to a Feature Serving endpoint. Features must be registered and materialized to an online store first.

```python
from databricks.feature_engineering.entities.feature_serving_endpoint import EndpointCoreConfig, ServedEntity

agg = fe.get_feature(full_name="main.ny.avg_fare_30d")
fe.create_feature_spec(name="main.ny.fare_feature_spec", features=[agg])
fe.create_feature_serving_endpoint(
    name="fare-features",
    config=EndpointCoreConfig(served_entities=ServedEntity(
        feature_spec_name="main.ny.fare_feature_spec",
        workload_size="Small", scale_to_zero_enabled=True,
    )),
)

w.serving_endpoints.query(name="fare-features", dataframe_records=[{"pickup_zip": "10003"}])
```

Grant serving access (online lookups read the materialized table, so `SELECT` on it is what's needed): `fe.grant_feature_serving_access(grant_to=[...], model_uri=... )` (pass `dry_run=True` to preview). A `FeatureSpec` containing Feature Views cannot also contain `FeatureLookup` or `FeatureFunction` definitions.
