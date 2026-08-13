---
name: transform-with-state
description: Apache Spark transformWithState (TWS) for custom stateful streaming, including the Python Row API and AsyncStatefulProcessor. Use when implementing transformWithState, AsyncStatefulProcessor, ValueState/ListState/MapState, timers vs TTL, Python async MapState access (asyncio.gather vs iterator), or TwsTester.
---

# TransformWithState (Python, including async)

`transformWithState` is the arbitrary stateful operator in Spark Structured Streaming (Spark 4.0+ / DBR 16.2+). Use it instead of `mapGroupsWithState` / `flatMapGroupsWithState`.

This reference is API facts plus copy-paste Python. For watermarks and generic RocksDB sizing, see [stateful-operations.md](stateful-operations.md). For RTM-specific TWS behavior (one row per `handleInputRows`, processing-time timers only), see [real-time-mode.md](real-time-mode.md).

## Quick Start

```python
from pyspark.sql import Row
from pyspark.sql.streaming import (
    AsyncStatefulProcessor,
    AsyncStatefulProcessorHandle,
)
from pyspark.sql.types import IntegerType, StringType, StructField, StructType

spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "org.apache.spark.sql.execution.streaming.state.RocksDBStateStoreProvider",
)

count_schema = StructType([StructField("count", IntegerType(), True)])
output_schema = StructType([
    StructField("entity_id", StringType(), True),
    StructField("count", IntegerType(), True),
])


class CountProcessor(AsyncStatefulProcessor):
    async def init(self, handle: AsyncStatefulProcessorHandle) -> None:
        self.count = handle.getValueState("count", count_schema)
        self.handle = handle

    async def handleInputRows(self, key, rows, timerValues):
        current = await self.count.get()  # None if missing — do not exists() then get()
        n = 0 if current is None else current[0]
        for _ in rows:
            n += 1
        await self.count.update((n,))  # positional tuple matching schema, not a dict
        yield Row(entity_id=key[0], count=n)

    async def close(self):
        pass


result = (
    streaming_df
    .groupBy("entity_id")
    .transformWithState(
        statefulProcessor=CountProcessor(),
        outputStructType=output_schema,
        outputMode="Update",
        timeMode="ProcessingTime",
    )
)
```

**RocksDB only.** TWS is not supported with the HDFS-backed state store. It uses RocksDB range scans and merge operators for `ListState`, `MapState`, and timers.

## StatefulProcessor methods

| Method | When called | Allowed |
|--------|-------------|---------|
| `init(handle)` | Once at operator startup | Create state variables; store the handle |
| `handleInputRows(key, rows, timerValues)` | Each micro-batch, per key with data (RTM: once per row) | Read/write state; register/delete timers; emit |
| `handleExpiredTimer(key, timerValues, expiredTimerInfo)` | When a registered timer fires | Read/write state; emit; register new timers. Cannot operate on input rows |
| `handleInitialState(key, row)` | Once per initial-state key, before any input, first run only | Pre-populate state |
| `close()` | Operator shutdown | Cleanup |

Restrictions the engine enforces:

- Do **not** register timers in `init()`.
- Do **not** create state variables outside `init()`.
- Python: default to the **Row** API (`transformWithState`), not `transformWithStateInPandas`. Pandas is unsupported in RTM and expensive at high key cardinality.

Sync processors subclass `StatefulProcessor` / `StatefulProcessorHandle`. Async processors subclass `AsyncStatefulProcessor` / `AsyncStatefulProcessorHandle` and `await` state and timer calls.

## State variable types

| Type | Use when | RocksDB property |
|------|----------|------------------|
| `ValueState` | One scalar/struct per grouping key (counters, watermarks, metadata) | Point read/write |
| `ListState` | Append-heavy collections | Merge operator — append is not read-modify-write |
| `MapState` | Sub-key lookups inside a grouping key (columns, rows, categories) | Prefix scans; point `getValue` / `updateValue` |

```python
self.meta = handle.getValueState("meta", meta_schema)
self.events = handle.getListState("events", event_schema)
self.columns = handle.getMapState(
    "columns", column_key_schema, column_value_schema
)
self.rows = handle.getMapState("rows", row_key_schema, row_value_schema)
```

**Do not collapse a large `MapState` into `ValueState` of an array.** Every mutation rewrites the whole array. At tens of thousands of nested rows this dominates batch time. Keep nested entities as `MapState` entries.

**`groupBy` key granularity.** A fat key that holds an entire 20k-row entity in one grouping key needs iterator-on-wide-touch (below). If keys can grow to 100k+ nested rows, **re-key** (finer grouping) rather than loading the whole map into Python memory.

## Python write contract: `update` takes a tuple

`ValueState.update` and `MapState.updateValue` are **positional**. Pass a tuple (or `Row`) whose order matches the schema. A dict raises `STRUCT_ARRAY_LENGTH_MISMATCH`. Zero-arg `update()` is invalid.

```python
# Correct
await self.meta.update((name, watermark_ts, sequence))
await self.rows.updateValue((row_id,), (row_id, payload, ts_ms))

# Wrong — dict is not field-name keyed
await self.meta.update({"name": name, "watermark_ts": watermark_ts})

# Wrong — not a TWS state write; also a different API (see DeltaLog below)
await self.meta.update()
```

Reads are not uniformly `Row`-shaped: `ValueState.get()` may return a plain tuple while `MapState.getValue` may return a `Row`. Normalize before attribute access; `getattr(tuple_value, "field", None)` silently returns `None`.

```python
def _state_row(value, factory):
    if value is None or isinstance(value, Row):
        return value
    return factory(*value)
```

## Timers vs TTL

Use **timers** when expiry must emit output (session close, tombstones). Use **TTL** when state should disappear silently.

```python
async def _replace_expiry_timer(self, previous_expiry_ms, new_expiry_ms=None):
    if previous_expiry_ms is not None and previous_expiry_ms != new_expiry_ms:
        await self.handle.deleteTimer(previous_expiry_ms)
    if new_expiry_ms is not None:
        await self.handle.registerTimer(new_expiry_ms)
```

Register absolute timestamps (`timerValues.getCurrentProcessingTimeInMs() + duration_ms`), not relative offsets from epoch. When sliding an expiry, **delete the previous timer** before registering the new one. Do not register timers in `init()`.

### TTL does not emit tombstones

Native RocksDB TTL evicts state lazily and does **not** emit deletes downstream. If sinks need physical deletes, register an explicit timer, emit tombstone rows in `handleExpiredTimer`, then `clear()` / `removeKey`. Do not rely on TTL alone for that path.

```python
from pyspark.sql.streaming import TTLConfig

# Silent GC only — no output rows when this expires
self.scratch = handle.getValueState(
    "scratch", scratch_schema, TTLConfig(ttlDurationMs=3600000)
)
```

TTL is per state variable, not per MapState/ListState entry. Event-time timers require `timeMode="EventTime"` and a watermark; they are **not** supported in RTM.

## Python async MapState access

These rules are from production TWS processors. Follow them literally.

### 1. Do not `exists()` then `get()`

`get()` / `getValue()` already return `None` when missing. A second IPC round-trip is wasted; treat `None`.

```python
current = await self.meta.get()
if current is None:
    current = empty_meta
```

### 2. `asyncio.gather` independent point reads (one IPC vs sequential awaits)

```python
import asyncio

ordered = sorted(column_ids)
values = await asyncio.gather(
    *(self.columns.getValue((column_id,)) for column_id in ordered)
)
column_cache = {
    column_id: _state_row(value, _COLUMN_STATE_ROW)
    for column_id, value in zip(ordered, values)
}
```

Same pattern for `MapState` rows:

```python
async def _point_read_rows(self, row_ids):
    ordered = sorted(row_ids)
    values = await asyncio.gather(
        *(self.rows.getValue((row_id,)) for row_id in ordered)
    )
    return {
        row_id: _state_row(value, _ROW_STATE_ROW)
        for row_id, value in zip(ordered, values)
    }
```

### 3. Adaptive access: skew (most keys small, few huge)

- Few keys touched this batch → `gather(getValue)`
- Wide touch, need most of the map, or delete-all-rows → `iterator()` into memory **once**
- On ≤400-entry `MapState` (for example a column catalog), `asyncio.gather(getValue)` ≈ `MapState.iterator`. Keep gather as the default. Do **not** ship "always iterator" for that size. Iterator does not win.

```python
import inspect

POINT_READ_ROW_THRESHOLD = 64
MAX_ROWS_PER_ENTITY = 20000
MAX_CELLS_PER_ENTITY = 500000


async def _scan_rows_bounded(self, fallback_row_ids=None):
    cache = {}
    cell_count = 0
    iterator = self.rows.iterator()
    if inspect.isawaitable(iterator):
        iterator = await iterator
    async for key, value in iterator:
        row = _state_row(value, _ROW_STATE_ROW)
        cache[key[0]] = row
        cell_count += len(row.payload or [])
        if (
            len(cache) > MAX_ROWS_PER_ENTITY
            or cell_count > MAX_CELLS_PER_ENTITY
        ):
            if fallback_row_ids is not None:
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    close_result = close()
                    if inspect.isawaitable(close_result):
                        await close_result
                return await self._point_read_rows(fallback_row_ids)
            raise RuntimeError(
                "MapState scan exceeded the explicit memory ceiling: "
                + str(len(cache))
                + " rows / "
                + str(cell_count)
                + " cells"
            )
    return cache


async def _load_rows(self, touched_row_ids, delete_all=False):
    wide_touch = len(touched_row_ids) > POINT_READ_ROW_THRESHOLD
    if delete_all:
        row_cache = await self._scan_rows_bounded()
        for row_id in touched_row_ids:
            row_cache.setdefault(row_id, None)
    elif wide_touch:
        row_cache = await self._scan_rows_bounded(
            fallback_row_ids=touched_row_ids
        )
        for row_id in touched_row_ids:
            row_cache.setdefault(row_id, None)
    else:
        row_cache = await self._point_read_rows(touched_row_ids)
    return row_cache
```

Always set **explicit memory ceilings** when iterating a `MapState` into Python. Abort or fall back to point-read rather than OOM.

### 4. Load-once / write-once per key per batch

Cache in a Python dict; mutate there; write back once. Do not `getValue`/`updateValue` inside the per-event loop.

```python
row_cache = await self._point_read_rows(touched_row_ids)
original_rows = dict(row_cache)

for event in events:
    row_id = event.row_id
    row_cache[row_id] = apply_event(row_cache.get(row_id), event)

for row_id, current in row_cache.items():
    original = original_rows.get(row_id)
    if current is None:
        if original is not None:
            await self.rows.removeKey((row_id,))
    elif current != original:
        await self.rows.updateValue((row_id,), row_tuple(current))
```

### 5. Hoist `ValueState` above emission loops

Entity meta, watermark, and sequence are per grouping key, not per output row. Read once, then emit.

```python
meta = await self.meta.get()
watermark, sequence = meta.watermark_ts, meta.sequence
for row_id in sorted(emitted_ids):
    yield emit_row(row_cache[row_id], meta, watermark, sequence)
await self.meta.update((meta.name, watermark, sequence))
```

Do not re-read `ValueState` per output row.

## Benchmarks: fixed-size clusters only

A/B streaming jobs on **autoscale (for example 1–20 workers) make wall-clock meaningless**. Use a fixed worker count. The production checklist already requires a fixed-size cluster for streaming; that rule is load-bearing for TWS benchmarks. Autoscale A/B lies.

## DBR 19 Py4J: `DeltaLog.update()` may not exist

Do not confuse JVM `DeltaLog.update()` with `ValueState.update(tuple)`.

On DBR 19, Java `deltaLog().update()` / `update(False)` may not be Py4J-visible (`False` boxes to `java.lang.Boolean`; the Scala default-arg form is not callable). Pin a Delta version on the **driver** with:

```python
jdt = spark._jvm.io.delta.tables.DeltaTable.forName(
    spark._jsparkSession, table_name
)
version = int(jdt.deltaLog().unsafeVolatileSnapshot().version())
```

Stream-config pin only — not a substitute for `DESCRIBE HISTORY` in notebooks, and not a TWS state write.

## Lakeflow / SDP

Do **not** call `DataFrame.collect()` or `DataFrame.count()` inside `@dp` functions. The SDP analyzer rejects Spark actions in pipeline definitions. Pin CDF `startingVersion` with a pipeline Spark conf or omit it and let SDP manage offsets.

## Initial state, schema evolution, state reader

**Initial state.** Pass a batch DataFrame as `initialState=`. `handleInitialState(key, row)` runs once per key before input, on the first query start only (not on checkpoint restart).

**Schema evolution.** Add/remove state variables in `init()` (`handle.deleteIfExists("old_name")` to drop). Value-side field add/remove/widen requires Avro:

```python
spark.conf.set("spark.sql.streaming.stateStore.encodingFormat", "avro")
```

Key-side schema evolution is not supported. Renaming a state variable is delete + recreate.

**State data source reader.** Inspect variables and timers from a checkpoint:

```python
state_df = (
    spark.read
    .format("statestore")
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/query")
    .option("operatorId", "0")
    .option("stateVarName", "meta")
    .load()
)
```

## Testing with TwsTester

Unit-test processor logic without a streaming query. TTL, checkpointing, and RocksDB optimizations are **not** simulated — use a real query for those.

```python
from pyspark.sql import Row
from pyspark.sql.streaming.tws_tester import TwsTester

tester = TwsTester(CountProcessor())
result = tester.test("entity-1", [Row(value="a"), Row(value="b")])
assert result == [Row(entity_id="entity-1", count=2)]

tester.updateValueState("count", "entity-1", (100,))
tester.test("entity-1", [Row(value="a")])
assert tester.peekValueState("count", "entity-1") == (101,)
```

Timer tests: `TwsTester(processor, timeMode="ProcessingTime")` then `setProcessingTime(ms)`.

## Common issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Query fails at start | HDFS state store | Set RocksDB provider (above) |
| `STRUCT_ARRAY_LENGTH_MISMATCH` | `update(dict)` or wrong tuple arity | Positional tuple matching schema |
| Extra state IPC | `exists()` then `get()` | `get()` and treat `None` |
| Slow point reads | Sequential `await getValue` | `asyncio.gather` |
| OOM in processor | Unbounded `iterator()` into Python | Row/cell ceilings; fall back to point-read; or re-key |
| Whole-array rewrite | Nested rows in `ValueState(Array)` | Use `MapState` |
| No downstream deletes on expiry | Native TTL | Timer + emit + `clear()` |
| Meaningless A/B times | Autoscale 1–N workers | Fixed-size cluster |
| SDP analysis error | `collect` / `count` in `@dp` | No Spark actions in pipeline functions |
| Py4J `update` missing | DBR 19 `DeltaLog.update()` | `unsafeVolatileSnapshot().version()` |

## Production checklist

- [ ] RocksDB state store provider
- [ ] Row API (`transformWithState`), not Pandas, unless you have a vectorized per-key exception
- [ ] State variables created only in `init()`; timers never registered in `init()`
- [ ] `ValueState.update` / `MapState.updateValue` get positional tuples
- [ ] `get()` / `getValue()` without a prior `exists()`
- [ ] Independent MapState point reads via `asyncio.gather`
- [ ] Adaptive iterator vs gather; gather default on ≤400-entry maps
- [ ] Explicit memory ceilings on MapState scans
- [ ] Load-once / write-once per key per batch; hoist per-key `ValueState` out of emit loops
- [ ] Timers for emit-on-expiry; TTL only for silent GC
- [ ] Fixed-size cluster for TWS jobs and benchmarks
- [ ] No `collect` / `count` inside `@dp` functions

## Related

- [stateful-operations.md](stateful-operations.md) — watermarks, RocksDB sizing, state monitoring
- [real-time-mode.md](real-time-mode.md) — RTM TWS semantics (per-row `handleInputRows`, processing-time timers)
- [streaming-best-practices.md](streaming-best-practices.md) — fixed-size streaming clusters
- [Apache Spark transformWithState](https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html#arbitrary-stateful-operations) (incl. TwsTester)
