---
name: transform-with-state
description: Custom stateful streaming with transformWithState (TWS). Use when implementing transformWithState, StatefulProcessor, ValueState/ListState/MapState, timers vs TTL, or TwsTester. Also use for Python AsyncStatefulProcessor (Beta, DBR 19+, not serverless).
---

# TransformWithState (Python)

`transformWithState` is the arbitrary stateful operator in Spark Structured Streaming (Spark 4.0+ / DBR 16.2+). Use it instead of `mapGroupsWithState` / `flatMapGroupsWithState`. Implement a **sync** `StatefulProcessor` unless you specifically need the Databricks async Beta.

Python `AsyncStatefulProcessor` is **Databricks-only Beta**: DBR 19+, classic/assigned compute only. It is not OSS Spark, not serverless, and not available for `transformWithStateInPandas` or Scala. See [Async (Beta)](#async-beta-dbr-19-classicassigned-compute-only).

This reference is API facts plus copy-paste Python. For watermarks and generic RocksDB sizing, see [stateful-operations.md](stateful-operations.md). For RTM-specific TWS behavior (one row per `handleInputRows`, processing-time timers only), see [real-time-mode.md](real-time-mode.md).

## Quick Start

```python
from pyspark.sql import Row
from pyspark.sql.streaming import StatefulProcessor, StatefulProcessorHandle
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


class CountProcessor(StatefulProcessor):
    def init(self, handle: StatefulProcessorHandle) -> None:
        self.count = handle.getValueState("count", count_schema)
        self.handle = handle

    def handleInputRows(self, key, rows, timerValues):
        current = self.count.get()  # None if missing — do not exists() then get()
        n = 0 if current is None else current[0]
        for _ in rows:
            n += 1
        self.count.update((n,))  # positional tuple matching schema, not a dict
        yield Row(entity_id=key[0], count=n)

    def close(self):
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
| `handleInitialState(key, initialState, timerValues)` | Once per initial-state key, before any input, first run only | Pre-populate state |
| `close()` | Operator shutdown | Cleanup |

Restrictions the engine enforces:

- Do **not** register timers in `init()`.
- Do **not** create state variables outside `init()`.
- Python: default to the **Row** API (`transformWithState`), not `transformWithStateInPandas`. Pandas is unsupported in RTM and expensive at high key cardinality.

Sync processors subclass `StatefulProcessor` / `StatefulProcessorHandle`. Creating state objects (`getValueState`, `getMapState`, `getListState`, `deleteIfExists`) is always synchronous, including on the async handle.

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

`ValueState.update` and `MapState.updateValue` are **positional**. Pass a tuple (or `Row`) whose order matches the schema. A dict is not field-name keyed. Wrong arity raises `STRUCT_ARRAY_LENGTH_MISMATCH`. A same-arity dict can succeed and silently write the **keys** as values. Zero-arg `update()` is invalid. `ValueState.update((n,))` is a TWS state write, not JVM `DeltaLog.update()`.

```python
# Correct
self.meta.update((name, watermark_ts, sequence))
self.rows.updateValue((row_id,), (row_id, payload, ts_ms))

# Wrong — dict is not field-name keyed (same-arity dict can silently store keys)
self.meta.update({"name": name, "watermark_ts": watermark_ts})

# Wrong
self.meta.update()
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

Register an **absolute** expiry in milliseconds (`now + duration`), not a bare duration. When sliding an expiry, **delete the previous timer** before registering the new one. Do not register timers in `init()`.

```python
def _replace_expiry_timer(self, previous_expiry_ms, new_expiry_ms=None):
    if previous_expiry_ms is not None and previous_expiry_ms != new_expiry_ms:
        self.handle.deleteTimer(previous_expiry_ms)
    if new_expiry_ms is not None:
        self.handle.registerTimer(new_expiry_ms)


now_ms = timerValues.getCurrentProcessingTimeInMs()
new_expiry_ms = now_ms + duration_ms
self._replace_expiry_timer(previous_expiry_ms, new_expiry_ms)
```

### TTL does not emit tombstones

Native RocksDB TTL evicts state lazily and does **not** emit deletes downstream. If sinks need physical deletes, register an explicit timer, emit tombstone rows in `handleExpiredTimer`, then `clear()` / `removeKey`. Do not rely on TTL alone for that path.

```python
# Silent GC only — no output rows when this expires
self.scratch = handle.getValueState(
    "scratch", scratch_schema, ttlDurationMs=3600000
)
```

Pass `ttlDurationMs` as an **int** on the variable (no `TTLConfig` object). TTL then expires **per ListState value** and **per MapState key-value pair** independently. TTL resets when that value (or map entry) is updated.

ListState caveat: the only way to refresh TTL on an existing list element is `put`, which overwrites the **entire** list and resets TTL for every value in it. Append does not reset TTL on older elements.

**TTL is not supported with `timeMode="EventTime"`.** Event-time timers require `timeMode="EventTime"`, a watermark, and Databricks `eventTimeColumnName` naming the output-schema timestamp column used to propagate the watermark. Event-time timers are **not** supported in RTM.

```python
(
    streaming_df
    .withWatermark("event_time", "10 minutes")
    .groupBy("entity_id")
    .transformWithState(
        statefulProcessor=CountProcessor(),
        outputStructType=output_schema,
        outputMode="Update",
        timeMode="EventTime",
        eventTimeColumnName="output_event_time",
    )
)
```

## Async (Beta, DBR 19+, classic/assigned compute only)

Use `AsyncStatefulProcessor` only on **DBR 19+** classic/assigned compute. Not OSS Spark. Not serverless. Not Pandas. Not Scala.

Async runs state ops and user logic **concurrently across grouping keys** and batches IPC (not a single round-trip). Do **not** stash per-key caches on `self` — keep them local to `handleInputRows`. Creating state variables in `init()` stays synchronous; `await` reads/writes and timers.

```python
from pyspark.sql import Row
from pyspark.sql.streaming import (
    AsyncStatefulProcessor,
    AsyncStatefulProcessorHandle,
)


class AsyncCountProcessor(AsyncStatefulProcessor):
    async def init(self, handle: AsyncStatefulProcessorHandle) -> None:
        self.count = handle.getValueState("count", count_schema)
        self.handle = handle

    async def handleInputRows(self, key, rows, timerValues):
        current = await self.count.get()
        n = 0 if current is None else current[0]
        for _ in rows:
            n += 1
        await self.count.update((n,))
        yield Row(entity_id=key[0], count=n)

    async def close(self):
        pass
```

`TwsTester` cannot drive `AsyncStatefulProcessor`. Test async processors with a real query until an async tester exists.

### Python async MapState access

Point reads that return one value use `await`. Collections (`MapState.iterator` / `keys` / `values`, `ListState.get`, `listTimers`) are **async iterators** — consume with `async for` ([Databricks async docs](https://docs.databricks.com/aws/en/stateful-applications/async)):

```python
async for key, value in self.rows.iterator():
    row = _state_row(value, _ROW_STATE_ROW)
```

If a preview returns a coroutine from `iterator()`, `await` it first (`async for k, v in await self.rows.iterator()`). Do not make `inspect.isawaitable` the primary pattern.

#### 1. Do not `exists()` then `get()`

`get()` / `getValue()` already return `None` when missing. A second IPC round-trip is wasted; treat `None`.

```python
current = await self.meta.get()
if current is None:
    current = empty_meta
```

#### 2. `asyncio.gather` independent point reads (concurrent/batched IPC)

`gather` overlaps many `getValue` calls. That is concurrent/batched IPC, not one round-trip — still far cheaper than sequential `await getValue`.

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

#### 3. Adaptive access: skew (most keys small, few huge)

The numbers below are **starting points to measure on a fixed-size cluster**, not Spark defaults. Do not always-iterator. Do not stuff a large map into `ValueState` of an array. Always set an explicit memory ceiling.

- Few keys touched this batch → `gather(getValue)`
- Wide touch, need most of the map, or delete-all-rows → `iterator()` into memory **once**
- On a ~400-entry `MapState` (for example a column catalog), measure `gather(getValue)` vs `iterator`; gather is a reasonable default at that size

```python
import asyncio

from pyspark.sql import Row

# Starting points to measure on a fixed-size cluster — not Spark defaults
POINT_READ_ROW_THRESHOLD = 64
SMALL_MAP_GATHER_DEFAULT = 400
MAX_ROWS_PER_ENTITY = 20000
MAX_CELLS_PER_ENTITY = 500000


def _ROW_STATE_ROW(row_id, payload, ts_ms):
    return Row(row_id=row_id, payload=payload, ts_ms=ts_ms)


class EntityMapProcessor(AsyncStatefulProcessor):
    async def init(self, handle: AsyncStatefulProcessorHandle) -> None:
        self.meta = handle.getValueState("meta", meta_schema)
        self.rows = handle.getMapState(
            "rows", row_key_schema, row_value_schema
        )
        # row_value_schema includes payload: array of cells (memory ceiling only)

    async def _point_read_rows(self, row_ids):
        ordered = sorted(row_ids)
        values = await asyncio.gather(
            *(self.rows.getValue((row_id,)) for row_id in ordered)
        )
        return {
            row_id: _state_row(value, _ROW_STATE_ROW)
            for row_id, value in zip(ordered, values)
        }

    async def _scan_rows_bounded(self, fallback_row_ids=None):
        cache = {}
        cell_count = 0
        iterator = self.rows.iterator()
        async for key, value in iterator:
            row = _state_row(value, _ROW_STATE_ROW)
            if row is None:
                continue
            cache[key[0]] = row
            payload = row.payload
            cell_count += 0 if payload is None else len(payload)
            if (
                len(cache) > MAX_ROWS_PER_ENTITY
                or cell_count > MAX_CELLS_PER_ENTITY
            ):
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()
                if fallback_row_ids is not None:
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
            # Need every map entry; no point-read fallback
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

Always set **explicit memory ceilings** when iterating a `MapState` into Python. Abort or fall back to point-read rather than OOM. `SMALL_MAP_GATHER_DEFAULT` (400) is only a measurement starting point for "gather is fine on a small catalog."

#### 4. Load-once / write-once per key per batch

Cache in a **local** dict (not `self`); mutate there; write back once. Do not `getValue`/`updateValue` inside the per-event loop.

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

#### 5. Hoist `ValueState` above emission loops

Entity meta, watermark, and sequence are per grouping key, not per output row. Read once, None-guard, write before yield.

```python
        meta = _state_row(await self.meta.get(), _META_ROW)
        if meta is None:
            meta = empty_meta
        watermark, sequence = meta.watermark_ts, meta.sequence
        await self.meta.update((meta.name, watermark, sequence))
        for row_id in sorted(emitted_ids):
            yield emit_row(row_cache[row_id], meta, watermark, sequence)
```

Do not re-read `ValueState` per output row.

## Benchmarks: fixed-size clusters only

A/B streaming jobs on **autoscale (for example 1–20 workers) make wall-clock meaningless**. Use a fixed worker count. The production checklist already requires a fixed-size cluster for streaming; that rule is load-bearing for TWS benchmarks. Autoscale A/B lies.

## Initial state, schema evolution, state reader

**Initial state.** `initialState=` must be **GroupedData** with the same grouping keys as the stream (`batch_df.groupBy("entity_id")`), not a raw DataFrame. `handleInitialState(key, initialState, timerValues)` runs once per key before input, on the first query start only (not on checkpoint restart).

```python
class CountWithInitialState(StatefulProcessor):
    def init(self, handle: StatefulProcessorHandle) -> None:
        self.count = handle.getValueState("count", count_schema)

    def handleInitialState(self, key, initialState, timerValues):
        self.count.update((initialState["count"],))

    def handleInputRows(self, key, rows, timerValues):
        current = self.count.get()
        n = 0 if current is None else current[0]
        for _ in rows:
            n += 1
        self.count.update((n,))
        yield Row(entity_id=key[0], count=n)

    def close(self):
        pass


initial_state = batch_df.groupBy("entity_id")
result = (
    streaming_df
    .groupBy("entity_id")
    .transformWithState(
        statefulProcessor=CountWithInitialState(),
        outputStructType=output_schema,
        outputMode="Update",
        timeMode="ProcessingTime",
        initialState=initial_state,
    )
)
```

**Schema evolution.** Add/remove state variables in `init()` (`handle.deleteIfExists("old_name")` to drop). Value-side field add/remove/widen requires Avro:

```python
spark.conf.set("spark.sql.streaming.stateStore.encodingFormat", "avro")
```

Key-side schema evolution is not supported. Renaming a state variable is delete + recreate.

**State data source reader.** Inspect variables and timers from a checkpoint path via `.load(...)`, same as [stateful-operations.md](stateful-operations.md):

```python
state_df = (
    spark.read
    .format("statestore")
    .option("operatorId", "0")
    .option("stateVarName", "meta")
    .load("/Volumes/catalog/checkpoints/query/state")
)
```

## Testing with TwsTester

Unit-test **sync** processor logic without a streaming query. TTL, checkpointing, and RocksDB optimizations are **not** simulated — use a real query for those. **Do not pass `AsyncStatefulProcessor` into `TwsTester`**; async tester support is not available yet.

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

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Query fails at start | HDFS state store | Set RocksDB provider (above) |
| `STRUCT_ARRAY_LENGTH_MISMATCH` | `update(dict)` or wrong tuple arity | Positional tuple matching schema |
| Silent wrong state | Same-arity dict to `update` | Dict keys written as values; pass a tuple |
| Extra state IPC | `exists()` then `get()` | `get()` and treat `None` |
| Slow point reads | Sequential `await getValue` | `asyncio.gather` (concurrent/batched IPC) |
| OOM in processor | Unbounded `iterator()` into Python | Row/cell ceilings; fall back to point-read; or re-key |
| Whole-array rewrite | Nested rows in `ValueState(Array)` | Use `MapState` |
| No downstream deletes on expiry | Native TTL | Timer + emit + `clear()` |
| `TTLConfig` / wrong TTL API | Python has no `TTLConfig` | `ttlDurationMs=3600000` int on the variable |
| TTL not firing per map/list entry | Assumed one TTL for the whole collection | Per ListState value / per MapState key-value pair |
| TTL + EventTime | TTL unsupported in EventTime | ProcessingTime TTL, or timers; pass `eventTimeColumnName` |
| Async on serverless / OSS / DBR &lt; 19 | Async is Databricks Beta | DBR 19+, classic/assigned compute only; else sync `StatefulProcessor` |
| `TwsTester` + async processor | Tester cannot drive async | Test a sync `StatefulProcessor`; real query for async |
| Cross-key corruption on async | Per-key cache stashed on `self` | Local dicts in `handleInputRows` (keys run concurrently) |
| `initialState` type error | Raw DataFrame | `batch_df.groupBy(same keys)` → GroupedData |
| Meaningless A/B times | Autoscale 1–N workers | Fixed-size cluster |

## Production checklist

- [ ] RocksDB state store provider
- [ ] Row API (`transformWithState`), not Pandas, unless you have a vectorized per-key exception
- [ ] Sync `StatefulProcessor` unless you need Databricks async Beta (DBR 19+, not serverless)
- [ ] State variables created only in `init()`; timers never registered in `init()`
- [ ] `ValueState.update` / `MapState.updateValue` get positional tuples
- [ ] `get()` / `getValue()` without a prior `exists()`
- [ ] `ttlDurationMs` int; per-entry List/Map TTL; no TTL with EventTime
- [ ] EventTime queries pass `eventTimeColumnName`
- [ ] Independent MapState point reads via `asyncio.gather` (async path)
- [ ] Adaptive iterator vs gather; measure 64 / 400 / 20k ceilings on a fixed-size cluster
- [ ] Explicit memory ceilings on MapState scans
- [ ] Load-once / write-once per key per batch; hoist per-key `ValueState` out of emit loops
- [ ] Async: no per-key caches on `self`
- [ ] Timers for emit-on-expiry (`now_ms + duration_ms`); TTL only for silent GC
- [ ] `initialState=` is GroupedData with the same keys
- [ ] TwsTester only on a sync processor
- [ ] Fixed-size cluster for TWS jobs and benchmarks

## Related

- [stateful-operations.md](stateful-operations.md) — watermarks, RocksDB sizing, state monitoring
- [real-time-mode.md](real-time-mode.md) — RTM TWS semantics (per-row `handleInputRows`, processing-time timers)
- [streaming-best-practices.md](streaming-best-practices.md) — fixed-size streaming clusters
- [Build a custom stateful application with transformWithState](https://docs.databricks.com/aws/en/stateful-applications)
- [Asynchronous processing with transformWithState (Beta)](https://docs.databricks.com/aws/en/stateful-applications/async)
