# Observability

Read this when the user asks how to **confirm records were accepted**, **check that rows reached Delta**, **find ingestion errors**, **monitor latency or throughput**, or **set up a dashboard or alerts**. Start new users with the **monitoring dashboard bundle**. It installs in one command and reads the system tables directly.

## What to check, and where
- **Records durable?** Ack callbacks / `flush()` returning ([In-flight](#in-flight-ack-callbacks))
- **Rows in table?** Query the target table ([Rows landed](#rows-landed-and-freshness))
- **Healthy across tables?** Monitoring dashboard or `system.lakeflow` ([Dashboard](#monitoring-dashboard-start-here), [System tables](#system-tables-beta))
- **Fast?** Ack latency / end-to-end freshness ([Latency](#latency))
- **Failures?** `on_error`, logs, system tables errors, fallback location ([Errors](#errors-and-rejected-records))

## Monitoring dashboard (start here)
Databricks publishes a ready-made **Zerobus Ingest Monitoring Dashboard** (DAB) that deploys an AI/BI dashboard from `system.lakeflow` system tables: weekly overview (streams, tables, GB), last hour, throughput trends, top tables, error breakdown, protocol distribution, and a **Table** filter per target.

**Prerequisites:** Databricks CLI v0.200+ (bundles); `USE`+`SELECT` on `system.lakeflow` (ask metastore/workspace admin); SQL warehouse.

**Deploy:**
```bash
git clone --depth 1 https://github.com/databricks-solutions/zerobus-ingest-examples.git
cd zerobus-ingest-examples/observability/zerobus_ingest_monitoring_dashboard
# Edit databricks.yml: set workspace host and warehouse name (or pass --var="warehouse_id=...")
databricks bundle deploy --profile <PROFILE>
```
**Verify:** dashboard appears in workspace. **Expected:** panels populate for tables with Zerobus data. Empty panels = no `system.lakeflow` access (ask metastore admin).

For dashboards over the **ingested data itself** (the events or telemetry), use the `databricks-aibi-dashboards` skill.

## In-flight: ack callbacks
**Ack callbacks** report progress and errors without blocking. From `on_ack` / `on_error` (or the language equivalent), count acknowledged offsets, log errors, or emit metrics. Supported in Python, Java, Rust, C++, and pure Go. Where there's no callback (TypeScript, CGO Go, .NET), call `flush()` on an interval and record progress. Keep callbacks fast (SDK background threads). See [SKILL.md Step 4](../SKILL.md#step-4-build-the-producer) for the ladder of which calls use acks.

## SDK logging
- **Python / Go:** `export RUST_LOG=debug` (or `RUST_LOG=zerobus_sdk=debug` for SDK only)
- **Java:** Add SLF4J impl (slf4j-simple, Logback), set `-Dorg.slf4j.simpleLogger.log.com.databricks.zerobus=debug`
- **TypeScript:** Log from code; not in README

## System tables (Beta)
Zerobus writes operational history to two system tables, with **365-day retention**, **regional** in scope. They don't need to be enabled, but reading them needs `USE` and `SELECT` on `system.lakeflow`.

| Table | What it records | Useful columns |
|-------|-----------------|----------------|
| `system.lakeflow.zerobus_stream` | Stream lifecycle | `stream_id`, `table_name`, `opened_time`, `closed_time`, `protocol`, `data_format`, `errors` |
| `system.lakeflow.zerobus_ingest` | Commits into the target table | `stream_id`, `table_name`, `commit_version`, `commit_time`, `committed_records`, `committed_bytes`, `errors` |

**Recent commits and errors for a table:**
```bash
databricks experimental aitools tools query \
  "SELECT commit_time, committed_records, committed_bytes, errors FROM system.lakeflow.zerobus_ingest WHERE table_name = '<catalog.schema.table>' ORDER BY commit_time DESC LIMIT 20" \
  --profile <PROFILE>
```
**Expected:** recent rows with `committed_records` > 0 and empty `errors`.

**Open streams for a table** (adapted from the docs sample query):
```bash
databricks experimental aitools tools query \
  "SELECT count(stream_id) AS open_streams FROM system.lakeflow.zerobus_stream WHERE table_name = '<catalog.schema.table>' AND closed_time IS NULL" \
  --profile <PROFILE>
```
**Expected:** the number of producer streams that are open.

If a `table_name` filter returns nothing, check the value format against the [Zerobus Ingest system tables](https://docs.databricks.com/admin/system-tables/zerobus-ingest) page.

## Rows landed and freshness
**Rows landed:**
```bash
databricks experimental aitools tools query \
  "SELECT count(*) AS row_count, max(event_time) AS latest_event FROM <catalog.schema.table>" \
  --profile <PROFILE>
```
**Expected:** `row_count` rises after each batch, and `latest_event` is recent.

## Latency
Zerobus documents two latencies (typical, region-dependent): durable in about **150 ms**, queryable in about **5 seconds** (see [how-it-works.md#the-data-path](how-it-works.md#the-data-path)). Measure both. Keep producers **in the workspace's region** to avoid cross-region latency and egress cost ([networking.md](networking.md)).

**Ack latency (producer side):** record send time in the ack callback:

Fragment (`record_metric` is your metrics client; register the callback with `StreamConfigurationOptions(ack_callback=LatencyCallback())`):
```python
import time
from collections import deque
from zerobus.sdk.shared import AckCallback

sent: deque[tuple[int, float]] = deque()  # (offset, send time); append after each ingest call

class LatencyCallback(AckCallback):
    def on_ack(self, offset: int):  # acks are cumulative: everything up to offset is durable
        now = time.monotonic()
        while sent and sent[0][0] <= offset:
            _, sent_at = sent.popleft()
            record_metric("zerobus_ack_latency_ms", (now - sent_at) * 1000)  # your metrics client

    def on_error(self, offset: int, error_message: str):
        record_metric("zerobus_ack_errors", 1)

# In the send loop: sent.append((stream.ingest_record_offset(record), time.monotonic()))
```
**Expected:** around 150 ms in-region. Sustained growth = backpressure.

**End-to-end (table side):** have the producer write a `client_timestamp` column (epoch microseconds), then:
```sql
SELECT current_timestamp() - max(event_time) AS lag FROM <catalog.schema.table>;
```
**Expected:** a few seconds lag while producers run. Growing lag = producers falling behind or failing.

## Errors and rejected records
| Signal | Where |
|--------|-------|
| Per-submission failures | `on_error` in the ack callback, or exceptions from ingest, `flush()`, and `close()` |
| Stream-level and batch-level errors | `errors` in `system.lakeflow.zerobus_stream` and `system.lakeflow.zerobus_ingest`; the dashboard's Errors section |
| Records that became durable but couldn't be written after a schema change | The **durable fallback** location `_zerobus/table_rejected_parquets/`, relative to the **table's root storage location**. Inspect and reprocess it with [recovery.md](recovery.md) |
| Auth, network, and schema causes | [troubleshooting.md](troubleshooting.md) |

## Alerts
Create Databricks SQL alerts on queries like these. Schedule them on the same warehouse.
| Alert when | Query |
|------------|-------|
| **No new data** for N minutes | `SELECT current_timestamp() - max(event_time) AS lag FROM <catalog.schema.table>`; alert when `lag` > threshold |
| **Ingest errors** appear | `SELECT count(*) AS error_batches FROM system.lakeflow.zerobus_ingest WHERE table_name = '<catalog.schema.table>' AND commit_time >= current_timestamp() - INTERVAL 1 HOUR AND size(errors) > 0`; alert when > 0 |
| **Streams drop** below the expected count | The open-streams query above; alert when below the producer fleet size |

## Sources
- [Zerobus Ingest Monitoring Dashboard](https://raw.githubusercontent.com/databricks-solutions/zerobus-ingest-examples/main/observability/zerobus_ingest_monitoring_dashboard/README.md) (databricks-solutions/zerobus-ingest-examples)
- [Zerobus Ingest system tables](https://docs.databricks.com/admin/system-tables/zerobus-ingest)
- [Zerobus Ingest quotas: latency](https://docs.databricks.com/ingestion/zerobus-quotas)
- [Zerobus recovery: durable fallback](https://docs.databricks.com/ingestion/zerobus-recovery)
- SDK READMEs (logging): [python](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/python/README.md), [go](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/go/README.md), [java](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/java/README.md)
