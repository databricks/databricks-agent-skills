---
name: lakebase-sink-python
description: Write streaming records into Lakebase Postgres from RTM (or any Structured Streaming pipeline). Covers the native `format("postgresql")` sink (Public Preview, preferred when available) and a manual `foreach` sink (fallback for pre-DBR-18.3, customization, or non-Lakebase targets). Use when building realtime apps that serve from Lakebase, or any low-latency pipeline that needs transactional upserts into Postgres.
---

# Lakebase Sink

Two options for writing streaming records into Lakebase Postgres:

1. **Native `format("postgresql")` sink** — Public Preview. Workspace-managed authentication, built-in batching, automatic retries on transient JDBC errors, Unity Catalog `.toTable()` integration. The canonical choice when DBR 18.3+ and Public Preview features are acceptable.
2. **Manual `foreach` sink** (a duck-typed Python class) — fallback for DBR <18.3, environments where Public Preview is unacceptable, customization the native sink doesn't offer (composing writes, conditional routing), or non-Lakebase targets. Also useful as a worked example of the `foreach` lifecycle for sinks to other systems (Redis, Cassandra, custom REST endpoints).

For general Lakebase mechanics — projects, branches, sizing, the CU-to-connections cap, authentication methods, connection patterns from non-streaming clients — see the stable `databricks-lakebase` skill, specifically [connectivity.md](../databricks-lakebase/references/connectivity.md) and [computes-and-scaling.md](../databricks-lakebase/references/computes-and-scaling.md). For RTM cluster setup, see [real-time-mode.md](real-time-mode.md). This file covers only the sink-specific patterns.

## Prerequisites

- A Lakebase Autoscaling project, branch, and endpoint. Default database is `databricks_postgres`.
- A target table with a primary key for upserts. See [Target table](#target-table) below.
- **For the native sink (Option A):** Databricks Runtime 18.3 or later, Classic compute (Dedicated or Standard access mode). Public Preview features must be acceptable for the workload. Per the [native sink docs](https://docs.databricks.com/aws/en/structured-streaming/lakebase): *"Serverless compute and Lakeflow Spark Declarative Pipelines are not supported"* — the native sink runs only inside a standalone Structured Streaming query on classic compute, not from a Lakeflow SDP pipeline.
- **For the manual `foreach` sink (Option B):** the Lakebase instance must permit native Postgres password login. If the instance is configured to require OAuth only, executor-side logins are rejected. See [connectivity.md](../databricks-lakebase/references/connectivity.md) for the authentication-method matrix. You'll also need a Postgres role with a password (created via driver-side admin connection), stored in a Databricks secret scope.

## Target table

Create the Lakebase table once, outside the stream. Both sink options upsert against a primary key.

```sql
CREATE TABLE IF NOT EXISTS events (
    id        TEXT PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS events_ts_idx ON events (timestamp DESC);
```

The descending timestamp index supports the "give me the latest N" query a downstream app will run. Add business columns (metric, category, payload JSON) as your app needs. Pick a key type that matches the upstream payload — the wiring example below extracts the raw Kafka value as a UTF-8 string, so `TEXT` is the natural choice; for numeric IDs, use `BIGINT` and cast through string in the SELECT (`CAST(CAST(value AS STRING) AS BIGINT)`).

## Option A: Native Lakebase sink (preferred when available)

`format("postgresql")` is documented at [Connect to Lakebase](https://docs.databricks.com/aws/en/structured-streaming/lakebase) (Public Preview). It handles connection management, batching, retries on transient JDBC errors, and workspace-managed authentication (no manual password handling).

### Unity Catalog form (simplest)

```python
df.writeStream \
    .format("postgresql") \
    .outputMode("update") \
    .option("checkpointLocation", "/Volumes/main/demo/checkpoints/lakebase") \
    .trigger(realTime="5 minutes") \
    .toTable("main.demo.events")
```

The connector uses the query runner's identity for authentication; no password or secret scope required. The sink auto-creates the target table if it doesn't exist, and infers the upsert key from the table's PRIMARY KEY — so `upsertkey` is optional when a PK is already on the table.

### Explicit endpoint form (non-UC tables)

```python
df.writeStream \
    .format("postgresql") \
    .outputMode("update") \
    .option("endpoint", "<project-id>.<branch-id>") \
    .option("dbtable", "events") \
    .option("checkpointLocation", "/Volumes/main/demo/checkpoints/lakebase") \
    .trigger(realTime="5 minutes") \
    .start()
```

Notes on the example above:

- **`endpoint`** can be either `project_id.branch_id` (auto-selects the branch's single read-write endpoint) or `project_id.branch_id.endpoint_id` (explicit). Read these from `databricks postgres get-endpoint` or the Lakebase UI's **Compute** tab → **Get ID**.
- **`dbtable`** is `schema.table`; if the schema is omitted, it defaults to `public`. Schema and table names must be simple identifiers (letter or underscore + letters/digits/underscores) — quoted names or hyphens aren't supported.
- **`database`** is omitted here because it defaults to `databricks_postgres`.
- **`upsertkey`** is omitted because the table's PRIMARY KEY is used automatically.

### Options

| Option | Default | Description |
|---|---|---|
| `endpoint` | — | Required for the explicit-endpoint form. `project_id.branch_id` or `project_id.branch_id.endpoint_id`. |
| `dbtable` | — | Required for the explicit-endpoint form. `schema.table`; schema defaults to `public`. Simple identifiers only — no quoted names or hyphens. |
| `database` | `databricks_postgres` | Target database. |
| `upsertkey` | (inferred from table PK) | Optional. Comma-separated column names that form the upsert key. If omitted, the sink uses the table's PRIMARY KEY. If specified, the columns must match the PK exactly or the query fails. If neither is set, the sink performs plain `INSERT` (append-only). |
| `batchsize` | 1000 | Optional. Max rows per database transaction. |
| `batchinterval` | `100 milliseconds` | Optional. Max buffer hold time before flushing. **Must be a Spark interval string using long-form unit names** — `"100 milliseconds"`, `"1 second"`, `"5 minutes"`. `"100"` fails with `INVALID_INTERVAL_FORMAT.MISSING_UNIT`; `"100 ms"` fails with `INVALID_INTERVAL_FORMAT.INVALID_UNIT` (the parser does not accept the `ms` abbreviation). |
| `checkpointLocation` | — | Required. UC volume path or other writable cloud storage; must be unique per query. |

Flush triggers when the buffer reaches `batchsize` rows or `batchinterval` elapses, whichever comes first. For low-latency workloads, decrease `batchinterval`. For high throughput, increase `batchsize`.

The sink raises `JDBC_STREAMING_SINK_INVALID_OPTIONS` for unrecognized options — useful for catching typos in option names early.

### Connection behavior

The sink uses connection pooling on executors with **one connection per task** by default. Databricks recommends keeping the default; raising the ratio causes connection contention and hurts latency for high-throughput connections. If the target endpoint has a low connection cap (see the connection budget below), reduce the number of shuffle partitions or set:

```python
spark.conf.set("spark.databricks.sql.streaming.jdbc.tasksPerConnection", "2")  # or higher
```

The sink **automatically retries transient JDBC errors — connection failures, deadlocks, rate limiting**. If retries exhaust, the query fails. Backpressure is propagated upstream to the source when the database can't keep up.

### Triggers and output modes

All Structured Streaming triggers are supported: `realTime`, `processingTime`, `availableNow`, `once`. Output modes: `update` and `append` (not `complete`) — and **`append` behaves identically to `update`** when the table has a primary key (both upsert via `INSERT … ON CONFLICT`); plain inserts only occur when there's no PK and no `upsertkey`.

For RTM cluster setup (autoscaling/Photon/spot off, the enable conf, slot math), see [real-time-mode.md](real-time-mode.md). The native sink's compute floor (DBR 18.3+) is stricter than RTM's general floor; the intersection is DBR 18.3+ Classic compute.

## Option B: Manual `foreach` sink (fallback / customization)

Use this when the native sink isn't available or sufficient:

- DBR <18.3, or environments where Public Preview features aren't acceptable
- Writing to a non-Lakebase target (Cassandra, Redis, custom REST endpoint, etc.) — the duck-typed Python class is a worked example of the `foreach` lifecycle
- Customization the native sink doesn't offer: composing writes, conditional routing per row, side effects (see [Performance & longevity → Reconnect instead of failing the query](#reconnect-instead-of-failing-the-query))

### Two non-obvious rules (manual sink only)

1. **The sink class is duck-typed in Python — no base class.** Official Databricks docs show the foreach pattern as a Scala `ForeachWriter` subclass. Translate to Python — `foreach()` accepts duck-typed objects with `open`/`process`/`close` methods, so no base class is involved. The `pyspark.sql.streaming.ForeachWriter` symbol is a Scala class with no exported Python equivalent.
2. **For the executor-side sink, use native Postgres password auth, not OAuth.** OAuth refresh requires Databricks SDK context that executors don't have — executors are separate Python processes with no SDK state. Use the Postgres role's password, pulled from a Databricks secret scope at driver startup and serialized into the sink instance. (Driver-side admin setup — `CREATE ROLE`, `CREATE DATABASE`, `GRANT` — is different; that runs on the driver where the SDK is available, so use an SDK-minted JWT for those.) See [connectivity.md](../databricks-lakebase/references/connectivity.md) for the two auth methods.

### The `LakebaseSink` class

```python
import time

import psycopg


# PySpark's `foreach()` accepts any object that implements the
# `open(partition_id, epoch_id) -> bool`, `process(row)`, `close(error)`
# lifecycle. There is no exported base class to extend — the
# `pyspark.sql.streaming.ForeachWriter` symbol is a Scala class, not a
# Python one. Duck-typing is the documented Python pattern.
class LakebaseSink:
    """
    Streaming sink that upserts rows into a Lakebase Postgres table.

    Buffers in-memory and commits in time-based windows. Each process(row)
    appends to the buffer and flushes only if at least max_dwell_ms have
    passed since the last flush. Effective Lakebase TX/s ceiling per
    partition is 1000 / max_dwell_ms; at higher source rates more rows
    accumulate per flush.

    Uses INSERT ... ON CONFLICT for upsert semantics. One transaction per
    flush. Authenticates with Postgres password — OAuth is incompatible
    with executor-side custom sinks.
    """

    def __init__(self, host: str, database: str, user: str, password: str,
                 table: str, port: int = 5432, key_col: str = "id",
                 max_dwell_ms: int = 10):
        self.host = host
        self.database = database
        self.user = user
        self.password = password
        self.table = table
        self.port = port
        self.key_col = key_col
        self.max_dwell_ms = max_dwell_ms

    def open(self, partition_id, epoch_id):
        self.conn = psycopg.connect(
            host=self.host, port=self.port, dbname=self.database,
            user=self.user, password=self.password,
            sslmode="require", autocommit=False,
        )
        self.buffer = []
        self.last_flush_ms = self._now_ms()
        return True

    def process(self, row):
        self.buffer.append(row)
        if self._now_ms() - self.last_flush_ms >= self.max_dwell_ms:
            self._flush()

    def close(self, error):
        try:
            if self.buffer:
                self._flush()
        finally:
            if self.conn is not None:
                self.conn.close()
                self.conn = None

    def _flush(self):
        if not self.buffer:
            return
        sample = self.buffer[0].asDict()
        cols = list(sample.keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_list = ", ".join(f'"{c}"' for c in cols)
        update_set = ", ".join(
            f'"{c}" = EXCLUDED."{c}"' for c in cols if c != self.key_col
        )
        sql = (
            f'INSERT INTO "{self.table}" ({col_list}) '
            f'VALUES ({placeholders}) '
            f'ON CONFLICT ("{self.key_col}") DO UPDATE SET {update_set}'
        )
        try:
            with self.conn.cursor() as cur:
                rows = [tuple(r.asDict()[c] for c in cols) for r in self.buffer]
                cur.executemany(sql, rows)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            self.buffer.clear()
            self.last_flush_ms = self._now_ms()

    @staticmethod
    def _now_ms():
        return int(time.monotonic() * 1000)
```

### Wiring into a stream

```python
# Set defensively at the top — required before any .repartition(N) in RTM.
# See the "Repartition" example in the RTM docs:
# https://docs.databricks.com/aws/en/structured-streaming/real-time/examples
spark.conf.set("spark.sql.execution.sortBeforeRepartition", "false")

sink = LakebaseSink(
    host=dbutils.secrets.get("lakebase", "host"),
    database="databricks_postgres",
    user=dbutils.secrets.get("lakebase", "user"),
    password=dbutils.secrets.get("lakebase", "password"),
    table="events",
    key_col="id",
    max_dwell_ms=10,
)

stream = (
    spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", brokers)
        .option("subscribe", input_topic)
        .load()
        .selectExpr("CAST(value AS STRING) AS id", "timestamp")
        .writeStream
        .foreach(sink)
        .outputMode("update")
        .option("checkpointLocation", checkpoint_path)
        .trigger(realTime="5 minutes")  # long-running batch duration; see real-time-mode.md
        .start()
)
```

See [real-time-mode.md](real-time-mode.md) for the RTM cluster setup and the `outputMode("update")` requirement; see [kafka-streaming.md](kafka-streaming.md) for source-specific Kafka options.

### Tuning `max_dwell_ms`

`max_dwell_ms = 10` is the default. It controls the minimum interval between Postgres commits.

| `max_dwell_ms` | Latency to Postgres | Max sustained TX/s per partition | When to use |
|---|---|---|---|
| 1 | Lowest (~1 ms) | ~1000 | Tightest demos; cheap workloads only |
| 10 (default) | Low (~10 ms) | ~100 | Most realtime apps |
| 100 | Moderate | ~10 | High source rates where per-commit overhead matters more than per-row latency |
| 1000 | Visible (~1 s) | ~1 | Effectively micro-batch — only if Lakebase is the bottleneck |

The effective Lakebase TX/s ceiling per partition is `1000 / max_dwell_ms`. With N source partitions writing to Lakebase, your cluster can drive up to `N × 1000 / max_dwell_ms` transactions per second.

**Why time-based and not count-based?** A count-based buffer (flush every K rows) has unpredictable latency: at low source rates, K rows can take seconds to accumulate. Time-based dwell bounds worst-case latency directly.

**Caveat:** the dwell check only fires on row arrival. If no rows arrive for a long stretch, the last buffered row stays in memory until either the next row arrives or `close()` is called. Fine for steady streams, less ideal for bursty sources with long quiet gaps.

(The native sink in Option A applies an analogous trade-off via `batchinterval` and `batchsize` — see Option A's Options table.)

## Delivery semantics

Both sink options are **at-least-once** at the boundary — see "Delivery semantics" in [real-time-mode.md](real-time-mode.md) for why and when duplicates occur. The native sink retries transient JDBC errors automatically; the manual `foreach` sink raises by default (override pattern in [Reconnect instead of failing the query](#reconnect-instead-of-failing-the-query)).

In both cases the upsert is idempotent — `INSERT … ON CONFLICT (id) DO UPDATE` produces the same final state regardless of how many times the same row arrives. If you customize the manual sink, **preserve idempotency**: keep the `ON CONFLICT` upsert (or use `MERGE`), never plain `INSERT`. If you swap in append-only inserts (event log style), include a deduplication key the consumer can use.

## Connection budget

Each Lakebase CU has a max-connections cap (see the CU-to-connections table in [computes-and-scaling.md](../databricks-lakebase/references/computes-and-scaling.md)). For a realtime app, total Postgres connections at peak =

```
(app's connection pool max × app replicas) + (streaming sink partitions)
```

Both sink options open one Postgres connection per partition writing to Lakebase. Both terms must fit under the CU's max-connections cap. At CU_1 the cap is ~209; at CU_4, ~839.

## Performance & longevity

These concerns are about the target table, not the sink, so they apply to both Option A and Option B. The sink (whether native or manual) performs well for moderate rates and short-lived or append-mostly workloads. The case that needs care is the one it's most often used for — **continuously upserting a small set of hot rows** to serve a live app — where dead-tuple churn can degrade it over a long run.

### Dead-tuple bloat on hot-key upserts

`INSERT … ON CONFLICT DO UPDATE` rewrites a row on every flush, and every UPDATE leaves a dead tuple behind. Against a handful of live rows updated several times a second, that's thousands of dead tuples a minute. Autovacuum reclaims them, but its defaults are tuned for large tables, not tiny hot ones (`autovacuum_naptime` is 60s; the scale factor waits for 20% of the table to change). Set aggressive **per-table** autovacuum so cleanup keeps pace:

```sql
ALTER TABLE events SET (
  autovacuum_vacuum_scale_factor = 0,     -- don't wait for 20% of the table
  autovacuum_vacuum_threshold    = 200,   -- vacuum after N dead tuples
  autovacuum_vacuum_cost_delay   = 0      -- don't throttle on a hot table
);
```

Watch `n_dead_tup` and `pg_total_relation_size` in `pg_stat_user_tables` — a few-row table holding tens of MB is the symptom, and it slows both the sink's writes and the app's reads.

### Do NOT put Change Data Feed on a high-churn upsert table

Lakehouse Sync / CDF holds a logical **replication slot that pins the xmin horizon**; if the slot lags even slightly, autovacuum can reclaim *nothing* and the upsert table bloats without bound (and [`REPLICA IDENTITY FULL`](https://www.postgresql.org/docs/current/sql-altertable.html#SQL-ALTERTABLE-REPLICA-IDENTITY), which CDF requires, substantially increases WAL volume per update — it logs the full old row plus the full new row instead of just primary-key + changed columns). The result is unbounded growth that degrades the whole serving path.

If you need the operational data in Delta, capture it from an **append-only event-log table**, never the upsert table:

- Keep the serving (upsert) tables `REPLICA IDENTITY DEFAULT` and **out of CDF** — autovacuum then reclaims them freely.
- Have the sink *also* insert each row into an append-only `*_events` table and point CDF only at that. Inserts create no dead tuples, so a lagging slot can never bloat it.

For Lakehouse Sync setup itself (CDF from Lakebase → Delta), see [lakehouse-sync.md](../databricks-lakebase/references/lakehouse-sync.md).

### Reconnect instead of failing the query

**Applies to Option B (manual `foreach` sink) only.** The native sink in Option A handles transient disconnects via its built-in retry mechanism.

`open()` holds one connection per partition for the epoch, and the default `_flush` re-raises on any error — so a transient disconnect (an autoscaling endpoint bounce, a CDF slot being created, a brief network blip) **kills the whole RTM query** and forces a restart (minutes of downtime plus checkpoint replay). Pull the connect into a helper and reconnect-then-skip instead of letting it propagate:

```python
def _connect(self):
    self.conn = psycopg.connect(
        host=self.host, port=self.port, dbname=self.database,
        user=self.user, password=self.password,
        sslmode="require", autocommit=False,
    )

# in _flush()'s except block:
except psycopg.OperationalError:
    try:
        self.conn.close()
    except Exception:
        pass
    self._connect()          # one tick dropped; the stream survives
```

This trades one flush window of buffered rows on each transient blip for stream availability. The strict at-least-once alternative is to keep the default `raise` and let RTM restart from checkpoint — see "Delivery semantics" above.
