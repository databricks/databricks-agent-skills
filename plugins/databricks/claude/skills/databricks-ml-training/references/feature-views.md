# Feature Views

> **Public Preview** (rolled out June 2026). Requires `databricks-feature-engineering>=0.16.0` and **Databricks Runtime 17.0 ML or above**, on **serverless OR a classic cluster**. Workspace admins enable it on the **Previews** page.
>
> **Verified end-to-end on 0.16.0 / serverless DBR 17.3 ML (2026-06)**: batch + streaming Feature Views, training sets, offline + online (Lakebase) materialization. Notes flagged **[Verified 0.16.0]** below were confirmed against that release.
>
> Docs: [Feature Views](https://docs.databricks.com/aws/en/machine-learning/feature-store/declarative-apis) · [Materialize Feature Views](https://docs.databricks.com/aws/en/machine-learning/feature-store/materialized-features)

A **Feature View** declares *what* a feature is — "7-day rolling average of `amount` per `user_id`" — and lets Databricks compute it point-in-time for training, materialize it to Delta (offline) and/or Lakebase (online), and keep it fresh. Batch (Delta) and streaming (Kafka) sources use the same `Feature` object and the same `fe.create_training_set(features=...)` → `fe.log_model(training_set=...)` → `fe.score_batch()` path as the standard API in [feature-store.md](feature-store.md).

> **Naming.** A Feature View's materialized output is a **Materialized Feature** (offline and/or online tables). The Python API has no `FeatureView` class: you work with `Feature` objects and `FeatureEngineeringClient`. (If you used the beta API, see [Migrating from the beta API](#migrating-from-the-beta-api--feature-views).)

## Why use Feature Views?

**The problem it solves — rolling feature boilerplate.** Writing Spark window functions for temporal features is verbose and brittle:

```python
# What you'd write manually — once per feature, per entity, per time window:
F.avg("value").over(
    W.partitionBy("user_id").orderBy(F.col("ts").cast("long")).rangeBetween(-7*86400, 0)
)
```

Across 5 features × 3 time windows × 2 entity types = 30 near-identical blocks to keep synchronized between training and serving. Declare them instead, and Databricks handles backfill, incremental refresh, materialization, and online publishing from one definition.

**Use Feature Views when you have:**
- Multiple rolling/window aggregations on the same source table
- Features that must stay identical offline (training) AND online (serving)
- Real-time features off an event stream (Kafka) — see [Streaming features](#streaming-features)

**Use the standard `FeatureLookup` API ([feature-store.md](feature-store.md)) instead when:**
- Your features are already-computed columns you just want to look up
- You need non-aggregation transforms beyond row-wise SQL (`transformation_sql` is row-wise only; cross-row aggregation must go through an `AggregationFunction`)

---

## Setup

```python
%pip install databricks-feature-engineering>=0.16.0
dbutils.library.restartPython()
```

```python
from databricks.feature_engineering import FeatureEngineeringClient
from databricks.feature_engineering.entities import (
    DeltaTableSource, Feature, AggregationFunction, ColumnSelection,
    Sum, Avg, Count, Min, Max, First, Last,               # aggregation operators
    StddevPop, StddevSamp, VarPop, VarSamp,               # std-dev / variance
    ApproxCountDistinct, ApproxPercentile,                # approximate aggregates
    SlidingWindow, TumblingWindow, RollingWindow,          # window types
    OfflineStoreConfig, OnlineStoreConfig,
    CronSchedule, TableTrigger, StreamingMode,             # materialization triggers
)
from datetime import timedelta

fe = FeatureEngineeringClient()

# --- Replace with your own values ---
catalog  = "my_catalog"
schema   = "my_schema"
PROJECT  = "my_project"    # table_name_prefix + endpoint names (underscores fine here)
ONLINE_STORE = "my-project-online-store"   # Lakebase instance name — DNS-compliant: lowercase alnum + hyphens, NO underscores
# ------------------------------------
```

### Aggregation operators

Wrap an operator + window in `AggregationFunction(operator=..., time_window=...)`. Operators carry their input column(s).

| Operator | Notes |
|---|---|
| `Sum(input="col")` / `Avg(input="col")` / `Count(input="col")` | totals / mean / row count |
| `Min(input="col")` / `Max(input="col")` | extrema |
| `First(input="col")` / `Last(input="col")` | first/last value in the window |
| `StddevPop` / `StddevSamp` / `VarPop` / `VarSamp` | std-dev / variance (population & sample) |
| `ApproxCountDistinct(input="col")` | approximate distinct count (HLL) |
| `ApproxPercentile(input="col")` | approximate percentiles |
| `ColumnSelection("col")` | **no aggregation, no window** — latest value of `col` per entity (`LAST()` as-of timestamp) |

Nested fields use dot notation: `Sum(input="value.amount")` reads the `amount` field of the `value` struct.

### Window types

| Type | Behaviour | Materializable? |
|---|---|---|
| `SlidingWindow(window_duration=, slide_duration=)` | overlapping rolling windows (7-day avg recomputed daily); `slide_duration` must be `< window_duration` | batch (offline/online) |
| `TumblingWindow(window_duration=)` | non-overlapping fixed buckets (weekly totals) | batch (offline/online) |
| `RollingWindow(window_duration=, delay=None)` | continuous lookback ending at evaluation time; `delay` shifts the window back (e.g. "the 7 days *ending a week ago*") | **streaming only** — for batch it's computed point-in-time in `create_training_set`/`compute_features`, but cannot be *materialized* to a store |

---

## Batch features

### 1. Define the source

`DeltaTableSource` carries only the table reference (plus optional row-level filter / SQL). `entity` and `timeseries_column` live on the **feature**, not the source — so one source can feed features at different entity grains.

```python
source = DeltaTableSource(
    catalog_name=catalog,
    schema_name=schema,
    table_name="silver_events",
    # filter_condition="amount > 0",                       # optional: WHERE predicate, applied first
    # transformation_sql="*, amount * qty AS gross",       # optional: projection list ONLY (what sits between SELECT and FROM) — no SELECT/FROM/WHERE
    # dataframe_schema=<Spark StructType JSON>,            # REQUIRED when transformation_sql is set (e.g. df.schema.json())
)
```

### 2. Declare features — two equivalent patterns

**Pattern A — construct locally, then register** (handy when you build features from config and want to preview before persisting):

```python
avg_amount_30d = Feature(
    source=source,
    entity=["user_id"],
    timeseries_column="ts",
    function=AggregationFunction(operator=Avg(input="amount"),
                                 time_window=TumblingWindow(window_duration=timedelta(days=30))),
    name="user_avg_amount_30d",                            # omit to auto-name from col+func+window
)

sum_amount_7d = Feature(
    source=source,
    entity=["user_id"],
    timeseries_column="ts",
    function=AggregationFunction(operator=Sum(input="amount"),
                                 time_window=SlidingWindow(window_duration=timedelta(days=7),
                                                           slide_duration=timedelta(days=1))),
)

# Preview point-in-time values before persisting — prototyping only, no lineage/materialization.
fe.compute_features(features=[avg_amount_30d, sum_amount_7d]).display()

# Persist the definitions to Unity Catalog.
avg_amount_30d = fe.register_feature(feature=avg_amount_30d, catalog_name=catalog, schema_name=schema)
sum_amount_7d  = fe.register_feature(feature=sum_amount_7d,  catalog_name=catalog, schema_name=schema)
```

**Pattern B — define and register in one call** with `create_feature()`:

```python
# Latest non-aggregated value per entity (ColumnSelection still needs entity + timeseries).
latest_tier = fe.create_feature(
    source=DeltaTableSource(catalog_name=catalog, schema_name=schema, table_name="entity_attributes"),
    function=ColumnSelection("loyalty_tier"),
    entity=["user_id"],
    timeseries_column="ts",
    catalog_name=catalog, schema_name=schema,
    name="user_loyalty_tier",
)
```

> `AggregationFunction(operator, time_window)` also accepts positional args:
> `AggregationFunction(Avg(input="amount"), TumblingWindow(window_duration=timedelta(days=30)))`.

### 3. Training set (point-in-time correct automatically)

The Feature Views `create_training_set()` takes `features=` (a list of `Feature` objects), **not** `feature_lookups=`. The join is point-in-time on each feature's `timeseries_column`.

```python
labeled_df = spark.table(f"{catalog}.{schema}.silver_events") \
    .select("record_id", "label", "user_id", "ts")

training_set = fe.create_training_set(
    df=labeled_df,
    features=[avg_amount_30d, sum_amount_7d, latest_tier],
    label="label",
    exclude_columns=["record_id", "user_id", "ts"],   # drop row id + entity key + event-time; keep only features
)
training_df = training_set.load_df()
```

Train and log exactly like the standard API — `fe.log_model(model=..., flavor=mlflow.sklearn, training_set=training_set, registered_model_name=...)` (see [feature-store.md](feature-store.md#3-train-and-register-with-feature-lineage)). Lineage and feature resolution at `score_batch()` come for free.

### 4. Materialize with `materialize_features()`

Provisions a serverless **Lakeflow Spark Declarative Pipeline** that writes the feature values to offline Delta tables and/or the online (Lakebase) store. `materialize_features()` is the canonical materialization API for Feature Views (`>=0.16.0`).

> **[Verified 0.16.0] Aggregation features require a `CronSchedule` for offline materialization.** Passing `TableTrigger()` for an aggregation feature is rejected server-side with `BadRequest: Cron schedule must be specified for aggregation feature '<name>'`. `TableTrigger()` is only valid for `ColumnSelection`. The cron also runs an **initial backfill immediately** on creation (the offline tables populate right away), then refreshes on the schedule, so a far-future cron (e.g. monthly) still backfills now.

```python
PREFIX = f"{PROJECT}_features"

# Aggregation features → offline and/or online, on a cron.
fe.materialize_features(
    features=[avg_amount_30d, sum_amount_7d],
    offline_config=OfflineStoreConfig(
        catalog_name=catalog, schema_name=schema, table_name_prefix=PREFIX,
    ),
    online_config=OnlineStoreConfig(                       # optional — add for real-time serving
        catalog_name=catalog, schema_name=schema, table_name_prefix=f"{PREFIX}_serving",
        online_store_name=ONLINE_STORE,       # Lakebase store; create it first if needed
    ),
    trigger=CronSchedule(quartz_cron_expression="0 0 0 * * ?", timezone_id="UTC"),  # daily 00:00 UTC
)
```

`ColumnSelection` features materialize to the **online store only**, triggered on every source commit with `TableTrigger`:

```python
fe.materialize_features(
    features=[latest_tier],                                # ColumnSelection only
    online_config=OnlineStoreConfig(
        catalog_name=catalog, schema_name=schema, table_name_prefix=f"{PREFIX}_serving",
        online_store_name=ONLINE_STORE,
    ),
    trigger=TableTrigger(),
)
```

> The online store is a Databricks Online Feature Store (Lakebase) instance. Create it once with `fe.create_online_store(name=ONLINE_STORE, capacity="CU_1")` — see [feature-store.md](feature-store.md#5-online-store-real-time-feature-serving). Its **name must be DNS-compliant** (lowercase alphanumeric + hyphens, **no underscores**), which is why `ONLINE_STORE` is kept separate from `PROJECT`.

---

## Streaming features

Define features off a **Kafka** event stream for real-time use cases. Streaming features materialize to the **online store only** (no offline), advertise ~**200ms p99** freshness to serving, and auto-maintain a Delta **ingestion table** that doubles as the offline copy for training.

**Constraints (Public Preview):**
- **Kafka only**, **JSON-serialized** messages; provide the schema directly as JSON Schema (Confluent/Glue schema registries are not formally supported — but pipelines can read topics governed by one if you supply the schema).
- **`RollingWindow` only** for streaming aggregations.
- Operators limited to **`Count`, `Avg`, `Sum`, `StddevPop`, `Max`, `Min`, `Last`**.
- Online materialization only; cannot be mixed with batch features in one `materialize_features()` call (different trigger types).
- `compute_features()` does **not** support streaming features.
- **Enterprise-tier** workspace in a region that supports Lakebase; standard catalog on your own cloud storage (default storage unsupported). Streaming pipelines restart ~twice weekly (≤1 min delay each).

### 1. Register the Kafka source as a governed `Stream`

A **Stream** is a Unity Catalog object (`catalog.schema.stream`); SELECT on its ingestion table grants read access. Authenticate via a **UC Kafka connection** (`ConnectionType.KAFKA`, cleanest) or **direct mTLS** (`DirectMtlsConfig`). `create_stream`'s `StreamConnectionConfig` takes **only** `uc_connection_name` or `direct_mtls_config` — it does **not** accept a UC service credential (that was the old `create_kafka_config` path). So an MSK/IAM stream that used `AuthConfig(uc_service_credential_name=...)` must be re-fronted with a UC Kafka connection before `create_stream` will work. (The Spark Kafka *writer* still uses `.option("databricks.serviceCredential", ...)` — only the FE read-side needs the connection.)

```python
from databricks.feature_engineering.entities import (
    KafkaStreamConfig, KafkaSubscriptionMode, StreamConnectionConfig,
    DirectSchemas, SchemaConfig, IngestionConfig, IngestionDestination,
    # StreamBackfillSource, DirectMtlsConfig,   # optional: backfill / mTLS auth
)

fe.create_stream(
    name=f"{catalog}.{schema}.events_stream",
    source_config=KafkaStreamConfig(
        subscription_mode=KafkaSubscriptionMode(subscribe="events-topic"),  # or subscribe_pattern=, assign=
        extra_options={"maxOffsetsPerTrigger": "10000"},
    ),
    # Auth: a UC connection holding the Kafka bootstrap + credentials...
    connection_config=StreamConnectionConfig(uc_connection_name="my-kafka-connection"),
    # ...or direct mTLS:  connection_config=DirectMtlsConfig(...)
    schema_config=DirectSchemas(
        payload_schema=SchemaConfig(json_schema='''
            {"type":"object","properties":{
              "user_id":{"type":"integer"},
              "amount":{"type":"number"},
              "event_type":{"type":"string"},
              "event_time":{"type":"string","format":"date-time"}}}'''),
        # key_schema=SchemaConfig(json_schema='...'),     # at least one of payload/key required
    ),
    ingestion_config=IngestionConfig(
        ingestion_destination=IngestionDestination(
            delta_table_name=f"{catalog}.{schema}.events_ingest"   # auto-maintained Delta copy
        ),
        deduplication_columns=["value.user_id"],          # dedup key; dot notation for nested
        # backfill_source=StreamBackfillSource(delta_table_name=f"{catalog}.{schema}.events_history"),
    ),
)
```

> **[Verified 0.16.0] The ingestion consumer starts at the _latest_ offset.** Events already in the topic *before* the stream's ingestion pipeline comes online are **not** ingested, and `startingOffsets=earliest` in `extra_options` does **not** backfill them. To include pre-existing/historic events, supply `backfill_source=StreamBackfillSource(delta_table_name=...)` in `IngestionConfig` (a Delta table the pipeline replays), or produce events only *after* the ingestion pipeline is `RUNNING`. The pipeline takes ~5-7 min to provision; poll its `ingestion_pipeline_id` (from `fe.get_stream(name).ingestion_config.ingestion_pipeline_id`) until `RUNNING` before producing.

> **[Verified 0.16.0 — live workspace test 2026-06]** `create_kafka_config()` is the predecessor and is now **rejected server-side** — it returns `BadRequest: CreateKafkaConfig is no longer supported. Use CreateStream instead.` Older notebooks built on `create_kafka_config` + `KafkaSource(name=...)` must be migrated to `create_stream` + `StreamSource(full_name=...)`.

### 2. Declare streaming features

Reference the stream with `StreamSource`. The Kafka payload is exposed under `value.*` (and key under `key.*`); use dot notation for nested JSON.

```python
from databricks.feature_engineering.entities import StreamSource

stream_source = StreamSource(
    full_name=f"{catalog}.{schema}.events_stream",
    # filter_condition="value.event_type = 'purchase'",   # optional
)

purchase_sum_1h = Feature(
    name="user_purchase_sum_1h",
    source=stream_source,
    entity=["value.user_id"],
    timeseries_column="value.event_time",
    function=AggregationFunction(operator=Sum(input="value.amount"),
                                 time_window=RollingWindow(window_duration=timedelta(hours=1))),
)

# Latest value off the stream (ColumnSelection works on streams too):
last_event_type = Feature(
    name="user_last_event_type",
    source=stream_source,
    entity=["value.user_id"],
    timeseries_column="value.event_time",
    function=ColumnSelection("value.event_type"),
)
```

### 3. Materialize (online only, `StreamingMode`)

```python
fe.materialize_features(
    features=[purchase_sum_1h, last_event_type],
    online_config=OnlineStoreConfig(
        catalog_name=catalog, schema_name=schema,
        table_name_prefix=f"{PROJECT}_stream_serving",
        online_store_name=ONLINE_STORE,
    ),
    trigger=StreamingMode(),                               # continuous Structured Streaming
)
```

At serving time, request/response payloads use **leaf-node names** (`amount`, `user_id`) rather than the dotted source paths (`value.amount`). Build the training set the same way as batch — the auto-maintained ingestion table supplies point-in-time history.

### 4. Build a training set (point-in-time from the ingestion table)

Build it exactly like a batch Feature View: pass the streaming `Feature` objects to `create_training_set(features=...)`. You never reference the ingestion table directly; the engine reads it behind the scenes and performs the point-in-time as-of join per label row.

```python
# Labels carry the entity key plus an event-time column matching the feature defs.
labeled_df = spark.table(f"{catalog}.{schema}.purchase_labels") \
    .select("user_id", "event_time", "label")

training_set = fe.create_training_set(
    df=labeled_df,
    features=[purchase_sum_1h, last_event_type],   # Feature objects, NOT FeatureLookup
    label="label",
    exclude_columns=["user_id", "event_time"],     # keep raw entity key + event-time out of the feature matrix
)
training_df = training_set.load_df()
```

Train and log identically to batch: `fe.log_model(model=..., flavor=mlflow.sklearn, training_set=training_set, registered_model_name=...)` (see [feature-store.md](feature-store.md#3-train-and-register-with-feature-lineage)). Lineage and feature resolution at `score_batch()` and serving come for free.

**Watch for:**
- **`features=[Feature, ...]`, not `feature_lookups=[FeatureLookup, ...]`.** The Feature Views signature differs from the standard `FeatureLookup` API in [feature-store.md](feature-store.md).
- **The `label` column must not exist in the stream's ingestion table**, or it collides on the join.
- **Entity and timeseries column names must match the feature definitions and be globally unique** across all sources in the training set. **[Verified 0.16.0]** Streaming features declare `entity=["value.user_id"]` / `timeseries_column="value.event_time"` (dotted source paths), but the **labeled DataFrame uses leaf names** (`user_id`, `event_time`), e.g. `spark.table(ingest).selectExpr("value.user_id AS user_id", "value.event_time AS event_time", ...)`. Leaf names give a correct point-in-time join and matching feature columns; dotted names in the labeled df are wrong.
- **[Verified 0.16.0] During stream startup the ingestion table is registered in UC before its Delta path is materialized.** A `spark.table(<ingest>).count()`, or even `spark.catalog.tableExists(<ingest>)`, issued in that window throws `[DELTA_PATH_DOES_NOT_EXIST] ... doesn't exist, or is not a Delta table`. When polling for the ingestion table to fill, wrap the read in `try/except` and treat any exception as "not ready yet"; do not gate on `tableExists`.

### Where do the historic events live?

Streaming features materialize **online only**, so there is no offline feature table to read at training time. The history lives in the **Delta ingestion table the Stream auto-maintains** — the `delta_table_name` you set in `IngestionConfig` (e.g. `catalog.schema.events_ingest`). That table is a continuous, governed copy of everything the Kafka stream ingested.

It does double duty:
- **Serving:** the live tail feeds the online (Lakebase) store at ~200ms freshness.
- **Training:** `create_training_set` recomputes each streaming feature **point-in-time per label row** by replaying events from the ingestion table up to that row's timestamp — exactly what serving would have produced at that instant, with no offline/online skew. This is why offline materialization is unnecessary.

To find or inspect them: `SELECT ... FROM catalog.schema.events_ingest` (SELECT on the ingestion table is the access grant for the `Stream`). The Kafka payload is under `value.*`, the key under `key.*`. Events from before the stream existed come from whatever `StreamBackfillSource(delta_table_name=...)` you supplied in `IngestionConfig`.

---

## Feature Serving Endpoint

Exposes raw feature values as a REST API — use when the scoring model lives outside Databricks and only needs the features, not a prediction. Pass `Feature` objects straight into the spec.

> **Prerequisite:** every feature in the spec must already be materialized to the **online store** (the `online_config` block shown above); the endpoint serves from the online store, so the aggregation features need online materialization, not just offline.

```python
from databricks.feature_engineering.entities.feature_serving_endpoint import (
    ServedEntity, EndpointCoreConfig,
)

ENDPOINT_NAME = f"{PROJECT}-feature-endpoint"
FEATURE_SPEC  = f"{catalog}.{schema}.{PROJECT}_feature_spec"

fe.create_feature_spec(name=FEATURE_SPEC, features=[avg_amount_30d, sum_amount_7d, latest_tier])

fe.create_feature_serving_endpoint(
    name=ENDPOINT_NAME,
    config=EndpointCoreConfig(
        served_entities=ServedEntity(                          # a SINGLE ServedEntity, NOT a list — Feature Serving Endpoints differ from Model Serving here
            feature_spec_name=FEATURE_SPEC, workload_size="Small", scale_to_zero_enabled=True,
        )
    ),
)

# Query: pass entity keys → get feature values back.
import mlflow.deployments
client = mlflow.deployments.get_deploy_client("databricks")
client.predict(endpoint=ENDPOINT_NAME, inputs={"dataframe_records": [{"user_id": 42}]})
```

> A `FeatureSpec` containing Feature Views cannot also contain `FeatureLookup` / `FeatureFunction` entries — keep them in separate specs.
>
> **Docs:** for a Feature Serving Endpoint, `served_entities` is a **single** `ServedEntity` (not a list). See the [feature-serving endpoint API](https://api-docs.databricks.com/python/feature-store/latest/ml_features.feature_serving_endpoint.html) and the [Feature Serving tutorial](https://docs.databricks.com/aws/en/machine-learning/feature-store/feature-serving-tutorial).

---

## Migrating from the beta API → Feature Views

Beta features were registered as **both** a `Feature` object and a same-named UC function; Public Preview Feature Views exist **only** as a `Feature` object. Per the [Feature Views API reference](https://docs.databricks.com/aws/en/machine-learning/feature-store/declarative-api-reference): "Existing beta features must be migrated before **July 22, 2026**."

```python
# Find beta Feature Views that still need migration (optionally scope to a catalog/schema).
beta = fe.list_beta_feature_views(catalog_name=catalog, schema_name=schema)
for f in beta:
    print(f.name)

fe.is_beta_feature_view(full_name=f"{catalog}.{schema}.user_avg_amount_30d")  # True if still beta
```

Re-create migrated features with `create_feature()` / `register_feature()` and re-run `materialize_features()`. (Features materialized before **April 20, 2026** must be deleted and re-materialized to pick up the current pipeline.)

### Migration gotchas

| Trap | Fix |
|---|---|
| `create_pipeline()` not found / deprecated | `create_pipeline()` is **deprecated and not supported for Feature Views (Public Preview)**. Use `materialize_features()`, the canonical materialization API. |
| `create_kafka_config()` rejected server-side (`BadRequest: CreateKafkaConfig is no longer supported`) | Beta streaming entry point. Use `create_stream()` + `StreamSource(full_name=...)` — see [Streaming features](#streaming-features). |
| `ContinuousWindow` import fails | Renamed to `RollingWindow`. Per the [Feature Views API reference](https://docs.databricks.com/aws/en/machine-learning/feature-store/declarative-api-reference): "`RollingWindow` was previously named `ContinuousWindow`. If you are migrating from an earlier SDK version, update your imports accordingly." |

---

## Feature View gotchas

| Trap | Fix |
|---|---|
| Feature View calls fail on an unsupported runtime | Public Preview requires **DBR 17.0 ML+** with `databricks-feature-engineering>=0.16.0`, on **serverless or classic** compute. |
| `time_window=` passed to `create_feature()` | The window now lives **inside** `AggregationFunction(operator=..., time_window=...)`; `create_feature` has no `time_window` arg |
| `entity` / `timeseries_column` set on `DeltaTableSource` | They belong on the `Feature` / `create_feature()` call; the source only carries table + optional `filter_condition` / `transformation_sql` |
| `RollingWindow` batch feature won't materialize | `RollingWindow` is point-in-time (training) for batch and **streaming-only** for materialization; use `Tumbling`/`Sliding` to materialize batch features |
| Feature Views `create_training_set()` signature mismatch | Pass `features=[Feature, ...]`, not `feature_lookups=[FeatureLookup, ...]` |
| Entity column is DATE or TIMESTAMP | Not allowed — use a string or numeric entity key |
| Label column also present in a feature source table | The `label` column must not exist in any feature source — drop/rename before defining features |
| `ColumnSelection` feature sent to offline store / `CronSchedule` | `ColumnSelection` is **online-only**; trigger with `TableTrigger` (batch) or `StreamingMode` (stream) |
| Streaming feature with `Sliding`/`Tumbling`, a non-supported operator, or offline config | Streaming = `RollingWindow` + `{Count,Avg,Sum,StddevPop,Max,Min,Last}`, **online only**, `trigger=StreamingMode()`; never mix with batch in one call |
| Streaming feature on a catalog in default storage | **Streaming** Feature Views require a **standard UC catalog in your own cloud object storage** (S3/ADLS/GCS); catalogs created in **default storage** are not supported. |
| Kafka payload fields not found | Reference them as `value.<field>` (and `key.<field>`); messages must be JSON with a JSON-Schema you supply |
| Mixed entity/timeseries column names between labels and features | Names must match across the labeled df and feature definitions, and be globally unique across all sources in a training set/endpoint |
| Dropping a feature's source table (or the feature) without removing its materialization | Strands the materialization job, which loops failing forever on the now-missing source and is hard to find. UC table drops do **not** cascade to FE objects. Verified param names (0.16.0), tear down in order: (1) `fe.list_materialized_features(feature_name=full_name)` → `fe.delete_materialized_feature(materialized_feature=<MaterializedFeature obj>)` (takes the SDK object, **not** a string); (2) `fe.delete_feature(full_name=<str>)` (param is `full_name=`, not `feature_name=`); (3) `fe.delete_stream(name=<str>)`; (4) `fe.delete_online_store(name=<str>)`; (5) `DROP TABLE`. Use `list_features` / `list_streams` to discover names dynamically instead of hardcoding. |
| Throwaway test materialization on a recurring `CronSchedule` | If the run is interrupted before its teardown cell, the cron materialization survives and silently loops. Use a one-shot trigger (or none) for tests, and put teardown in `try/finally`. |
| `transformation_sql` rejected, or adding a computed column "doesn't work" | `transformation_sql` takes **only the projection list** — the part between `SELECT` and `FROM`, e.g. `"*, amount * qty AS gross"` — applied after `filter_condition` (the WHERE). A full `SELECT ... FROM ... WHERE ...` statement fails. It also **requires `dataframe_schema`** (post-transform schema as Spark StructType JSON, `df.schema.json()`). No derived table needed. |
| `fe.create_online_store(name=...)` raises `InvalidParameterValue: DatabaseInstance name must be DNS compliant` | The Lakebase instance name must be **lowercase alphanumeric + hyphens only, no underscores**. `f"{PROJECT}-online-store"` with `PROJECT="my_project"` silently yields an invalid name; keep the store name separate and DNS-safe (`ONLINE_STORE` in Setup). |
| `register_feature()` / `create_feature()` raises `AlreadyExists` on rerun | Feature definitions persist in UC across runs. Wrap in try/except: on `AlreadyExists`, call `fe.get_feature(full_name=f"{catalog}.{schema}.{name}")` to fetch the existing definition and continue (idempotent reruns). |
| Ingestion pipeline stays `IDLE` after `create_stream()` | It does not always auto-start. With `from databricks.sdk import WorkspaceClient; w = WorkspaceClient()`, check `w.pipelines.get(pipeline_id).state`; if `IDLE`, call `w.pipelines.start_update(pipeline_id=pipeline_id)`. Allow ~5-7 min to reach `RUNNING`. |
| Kafka topic does not exist (`UnknownTopicOrPartitionException`) | MSK and most managed Kafka default to `auto.create.topics.enable=false`. Create the topic (MSK console / Kafka CLI) **before** `create_stream()` or producing events. `.option("kafka.allow.auto.create.topics", "true")` on the Spark writer has no effect when broker-side auto-creation is disabled. |
| Python session resets mid-poll on serverless (imports/variables cleared) | A long blocking poll (e.g. waiting on pipeline provisioning) can outlast the serverless session and detach it, clearing state. Keep poll loops short and bounded (≤~15 min, e.g. 30 × 30s) and re-run the import/config cells if the session resets. |
