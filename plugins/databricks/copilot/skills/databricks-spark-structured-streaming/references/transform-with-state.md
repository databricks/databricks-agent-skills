---
name: transform-with-state
description: Choose between built-in stateful operators and transformWithState, and build custom per-key state with timers, TTL, initial state, schema evolution, and the state reader. Use when the logic needs timeouts that fire without new data, max-duration sessions, per-key state machines, or several state values, or when migrating from applyInPandasWithState, flatMapGroupsWithState, or mapGroupsWithState.
---

# Stateful Processing: Built-in Operators or `transformWithState`

`transformWithState` (TWS) runs your own `StatefulProcessor` per grouping key, with typed state, timers, and TTL ([TWS docs](https://docs.databricks.com/aws/en/stateful-applications/)). It is the successor to `applyInPandasWithState`, `flatMapGroupsWithState`, and `mapGroupsWithState`. Use a built-in operator whenever one fits: it is simpler, and the engine optimises it.

## Choose the Operator

| Need | Use |
|---|---|
| Counts or sums per time window, with late data | `groupBy(window(...))` + `withWatermark` ([stateful-operations.md](stateful-operations.md)) |
| Sessions closed by inactivity, aggregate output only (including one "went quiet" row per key after a gap) | `session_window` + `withWatermark`. Append emits a key's closed session once any key's data moves the watermark past it, even if that key gets no new rows. Update is rejected; Complete runs but rewrites every session each batch |
| Drop duplicate retries (event time may differ) | `dropDuplicatesWithinWatermark` |
| Correlate two streams within a time range | Stream-stream join, watermark on **both** sides ([stream-stream-joins.md](stream-stream-joins.md)) |
| CDC / SCD into a table | Lakeflow `AUTO CDC` (`databricks-pipelines` skill) |
| Custom or repeated output while a key gets **no new data**, cap a session's length, per-key state machine, several state values, per-entry expiry | **`transformWithState`** |

- Choose TWS for what built-ins cannot do, not for speed. In one microbenchmark (same per-key logic, 50,000 keys), native `groupBy().agg()` was 4.5-12x faster than any custom API; the ratio is workload-specific, so benchmark your own.
- Use the row-based Python API (or Scala) by default. Use `transformWithStateInPandas` only when the per-key work is vectorised maths over large groups.
- For new custom state, prefer TWS when its runtime, access-mode, and checkpointing requirements are met. `applyInPandasWithState` is still documented and supported; see [when it is still the answer](#migrating-from-applyinpandaswithstate). To move existing jobs, see [Migrating](#migrating-from-applyinpandaswithstate).

## Requirements

| Item | Requirement |
|---|---|
| `transformWithStateInPandas`, Scala `transformWithState` | DBR 16.2+ |
| Python row-based `transformWithState` | Use DBR 17.3+. On DBR 16.4 LTS `GroupedData.transformWithState` is absent (only `transformWithStateInPandas` exists), although the requirements page lists Python from 16.3 |
| Standard access mode | Python (`transformWithStateInPandas`) on 16.3+, Scala on 17.3+ ([requirements](https://docs.databricks.com/aws/en/stateful-applications/examples#requirements)) |
| State store | RocksDB, the default on DBR 17.3+. On older runtimes, set it on a new checkpoint (below), or TWS fails with `UNSUPPORTED_FEATURE.STATE_STORE_MULTIPLE_COLUMN_FAMILIES` |
| Serverless jobs | `AvailableNow` trigger only; `stateStore.encodingFormat`, `stateStore.providerClass`, and `multipleWatermarkPolicy` cannot be set ([serverless limitations](https://docs.databricks.com/aws/en/compute/serverless/limitations)). Lakeflow pipelines have their own trigger modes |

TWS on serverless and on new runtime releases is still maturing. Before a production rollout or migration, check the current release notes and known issues for your runtime.

```python
# DBR 17.2 and below only, before the first run of the checkpoint
spark.conf.set("spark.sql.streaming.stateStore.providerClass",
               "com.databricks.sql.streaming.state.RocksDBStateStoreProvider")
```

## Watermarks and State

- The watermark is the max event time seen minus the delay. It is computed at the end of a micro-batch and used by the next one, and it never moves backwards.
- With several watermarked inputs, the global watermark is the **minimum** by default (`spark.sql.streaming.multipleWatermarkPolicy=min`). The policy is fixed by the checkpoint.
- Rows older than the watermark are dropped **before** the stateful operator, including a TWS in `EventTime` mode, and are counted in `numRowsDroppedByWatermark`. Capture late rows upstream if you need them.
- Without a watermark, state is never evicted. Append output mode is rejected for aggregations, and in Lakeflow pipelines the aggregation silently runs in Complete mode.

## A `StatefulProcessor` (row-based Python, event-time timers)

Sessions closed by a 30-minute gap **or** a 4-hour cap. `session_window` cannot cap a session's length. This runs under `AvailableNow`, so it suits scheduled and serverless jobs. A session closes as soon as a later row passes its deadline, so a late row inside the watermark delay can fall into a session that is already emitted; when late rows matter and no cap is needed, use `session_window`.

```python
import datetime as dt

from pyspark.sql import Row
from pyspark.sql.streaming import StatefulProcessor, StatefulProcessorHandle

GAP_MS, MAX_MS = 30 * 60 * 1000, 4 * 3600 * 1000


def to_ms(t):  # input timestamps arrive tz-aware in the session time zone; a naive one is taken as UTC
    return int((t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).timestamp() * 1000)


class CappedSessions(StatefulProcessor):
    def init(self, handle: StatefulProcessorHandle) -> None:
        self.handle = handle
        self.session = handle.getValueState("session", "start_ms long, last_ms long, events long")

    def _deadline(self, s):
        return min(s[1] + GAP_MS, s[0] + MAX_MS)  # inactivity gap or max duration

    def handleInputRows(self, key, rows, timerValues):
        cur, out = self.session.get(), []
        for t in sorted(to_ms(r.event_time) for r in rows):
            if cur is not None and t >= self._deadline(cur):
                out.append(Row(user_id=key[0], start_ms=cur[0], end_ms=self._deadline(cur), events=cur[2]))
                cur = None
            cur = (t, t, 1) if cur is None else (min(cur[0], t), max(cur[1], t), cur[2] + 1)
        for old in self.handle.listTimers():
            self.handle.deleteTimer(old)
        self.handle.registerTimer(self._deadline(cur))
        self.session.update(cur)
        return iter(out)

    def handleExpiredTimer(self, key, timerValues, expiredTimerInfo):
        cur = self.session.get()
        if cur is not None:
            self.session.clear()
            yield Row(user_id=key[0], start_ms=cur[0], end_ms=self._deadline(cur), events=cur[2])

    def close(self) -> None:
        pass


(events.withWatermark("event_time", "10 minutes")
    .groupBy("user_id")
    .transformWithState(statefulProcessor=CappedSessions(),
                        outputStructType="user_id string, start_ms long, end_ms long, events long",
                        outputMode="Append", timeMode="EventTime"))
```

Python rules:

- State values are tuples: `update((n,))`, never a scalar or dict. `get()` returns a tuple, or `None` when unset.
- `key` is a tuple of the grouping values: `key[0]` for one key.
- Store times as epoch-ms `long`s. Timestamps read back from state can be timezone-aware while input rows are naive (`TypeError: can't compare offset-naive and offset-aware datetimes`).
- Create every state variable in `init`. Read the whole iterator and write each state variable once per key per batch.
- `handleExpiredTimer` runs even when the key has no new rows; that is what built-in operators cannot do.

## Timers

| `timeMode` | Timers fire on | TTL |
|---|---|---|
| `"EventTime"` | The watermark (needs `withWatermark` upstream). A stopped job fires nothing; a timer fires once the watermark passes it, in the same `AvailableNow` run (an extra no-data batch) or a later one | Not supported |
| `"ProcessingTime"` | Wall-clock micro-batch time | Supported |
| `"None"` | No timers | Not supported |

> **Warning: `timeMode="ProcessingTime"` never lets a run-to-completion trigger finish.** The cause is the time mode, not timer registration. A `Trigger.AvailableNow` query in `ProcessingTime` mode keeps running empty micro-batches instead of stopping, even when the processor registers no timer. The same processor with `timeMode="None"` ends normally. This was observed on serverless (Spark 4.2), DBR 17.3 and DBR 19.8, and also with `applyInPandasWithState` using `ProcessingTimeTimeout`. A triggered Lakeflow pipeline update in this mode does not finish either. On serverless, a run that starts with no new data exits without firing timers that are due.
> - Use `timeMode="ProcessingTime"` (and TTL, which requires it) only in always-on queries: continuous pipelines, or classic jobs with `trigger(processingTime=...)`.
> - Scheduled jobs, serverless jobs, and triggered pipelines: use `timeMode="EventTime"` (as above) or `"None"`.

- `registerTimer(ms)` takes an **absolute** epoch-ms timestamp. A timer persists until it fires or is deleted.
- To re-arm, first sort the batch's rows by event time and handle each gap inside the batch, as `CappedSessions` does. Then delete the old timer (`listTimers()` / `deleteTimer()`) and register one timer from the last event. One timer from `max(event_time)` misses the gaps inside a batch. Gaps closed this way are emitted before the watermark passes them, so a late row inside the delay can arrive after its gap's alert (see `CappedSessions`).
- Read time from `timerValues.getCurrentWatermarkInMs()` / `getCurrentProcessingTimeInMs()`, never the system clock.
- When a key gets rows in the same batch in which its timer is due, `handleInputRows` runs first.

## State Variables and TTL

| Type | Holds per key | Main calls |
|---|---|---|
| `ValueState` | One value | `get`, `exists`, `update`, `clear` |
| `ListState` | A list | `get`, `put` (rewrite), `appendValue`, `appendList`, `clear` |
| `MapState` | A map | `getValue`, `containsKey`, `updateValue`, `removeKey`, `iterator`, `keys`, `values` |

```python
self.seen = handle.getMapState("seen", "item string", "first_seen long", ttlDurationMs=24 * 3600 * 1000)
```

TTL silently evicts a value (per list element, per map entry) and emits nothing; use a timer when expiry must produce a row. TTL is valid only in `ProcessingTime` mode, so it is unsuitable for self-terminating `AvailableNow` jobs and triggered pipelines (see the warning above) ([TTL](https://docs.databricks.com/aws/en/stateful-applications/#time-to-live-ttl-for-state-types)).

## Initial State and Schema Evolution

- `initialState` seeds state on the **first run of a checkpoint only**; later runs ignore it. It must be a `GroupedData` with the same keys as the input; a plain DataFrame is rejected. Handle each key in `handleInitialState(key, initialState, timerValues)`.
- To change a state value's schema between deploys (add, remove, or reorder fields; widen `int` to `long`), set `spark.sql.streaming.stateStore.encodingFormat=avro` **before the first run** ([schema evolution](https://docs.databricks.com/aws/en/stateful-applications/schema-evolution)).
  - Without it, a changed schema fails with `STATE_STORE_VALUE_SCHEMA_NOT_COMPATIBLE`.
  - Renaming fields, narrowing types, and changing keys are not supported.
  - Serverless cannot set this conf.
- Add or drop whole state variables without Avro: `handle.deleteIfExists("old_name")` in `init`.

## Inspect State

Load the checkpoint **root**, not `<checkpoint>/state`, which fails with `STDS_COMMITTED_BATCH_UNAVAILABLE` ([read state](https://docs.databricks.com/aws/en/structured-streaming/read-state)). Columns are `key`, `value`, `partition_id`. For TWS, `stateVarName` is required; without it the read fails with `STDS_REQUIRED_OPTION_UNSPECIFIED`. The one exception is `readRegisteredTimers`, which must be used without `stateVarName` (together they fail with `STDS_CONFLICT_OPTIONS`).

```python
ckpt = "/Volumes/main/default/checkpoints/sessions"
state = spark.read.format("statestore").option("stateVarName", "session").load(ckpt)   # TWS: stateVarName required
timers = spark.read.format("statestore").option("readRegisteredTimers", "true").load(ckpt)
ops = spark.read.format("state-metadata").load(ckpt)  # operators, minBatchId, maxBatchId
```

- `flattenCollectionTypes` (default `true`) returns one row per list or map entry.
- TTL metadata (`ttlExpirationMs`) appears inside a TTL-enabled state variable's value; there is no generic `expirationMs` column.
- Stream-stream join state needs `joinSide` (or `storeName`).
- These reads ran on serverless jobs and on classic compute, although the read-state page's compute-support notes are inconsistent.

## Migrating from `applyInPandasWithState`

The same checkpoint cannot switch operators: it fails with `STREAMING_STATEFUL_OPERATOR_NOT_MATCH_IN_STATE_METADATA`. Carry the state over instead. The state reader's output is not a drop-in initial state: read it, reshape it to the new processor's state schema, validate it, group it, and seed it on a new checkpoint.

1. Stop the legacy query at a version boundary and note `last_version`, the last source version it processed completely. A Delta source can split one large commit across batches (`maxFilesPerTrigger`, 1000 files by default), so a query stopped mid-commit holds only part of that version. An `AvailableNow` run that ends by itself stops at a boundary.
2. Read its state: `spark.read.format("statestore").load(old_ckpt)`. The user fields are under `value` (or `value.groupState`, depending on the runtime).
3. Reshape it to the columns your `handleInitialState` expects, check the keys and values (for example, row counts against the old state), and group it by the same keys as the stream.
4. Pass it as `initialState` to the new TWS query.
5. Start on a **new** checkpoint, with the source starting at `last_version + 1`, so no row is counted twice or skipped.

```python
from pyspark.sql import functions as F

legacy = spark.read.format("statestore").load(old_ckpt)
initial = legacy.select(F.col("key.user_id").alias("user_id"), "value.n", "value.total").groupBy("user_id")
(spark.readStream.option("startingVersion", last_version + 1).table(src)
    .groupBy("user_id")
    .transformWithStateInPandas(statefulProcessor=CountProcessor(),  # your processor, with handleInitialState
                                outputStructType="user_id string, n long, total long",
                                outputMode="Update", timeMode="None", initialState=initial))
```

| `applyInPandasWithState` | TWS |
|---|---|
| `state.get` / `exists` / `update` / `remove` | `get()` / `exists()` / `update()` / `clear()` on a state variable |
| `setTimeoutDuration` / `setTimeoutTimestamp` | `registerTimer(absolute_ms)` |
| `if state.hasTimedOut:` | `handleExpiredTimer` |

**When `applyInPandasWithState` is still the answer:** it is documented and supported, with no deprecation notice. Keep or choose it when:
- the runtime or access mode does not support the TWS API you need (for example, row-based Python TWS on DBR 16.4);
- you depend on **async state checkpointing**. This is `spark.databricks.streaming.statefulOperator.asyncCheckpoint.enabled`, not the `AsyncStatefulProcessor` API. On DBR 17.3 it failed with both Python TWS APIs (`Synchronous commit is not supported. Use asynchronous commit.`) but worked with `applyInPandasWithState`. It also requires a processing-time trigger;
- you need a scoped workaround while a TWS defect on your runtime is fixed. Plan to move to TWS afterwards.

## Common Issues

| Symptom | Fix |
|---|---|
| `AvailableNow` job or triggered pipeline never finishes | `timeMode="ProcessingTime"`: switch to `"EventTime"` or `"None"`, or run the query always-on |
| `UNSUPPORTED_FEATURE.STATE_STORE_MULTIPLE_COLUMN_FAMILIES` | Set RocksDB (DBR 17.2 and below), new checkpoint |
| `'GroupedData' object has no attribute 'transformWithState'` | Row-based Python TWS needs DBR 17.3+; or use `transformWithStateInPandas` |
| State grows without bound | Add TTL (always-on queries) or clear state in `handleExpiredTimer` |
| Expiry produces no output | TTL never emits; use a timer |
| `STATE_STORE_VALUE_SCHEMA_NOT_COMPATIBLE` after a deploy | Avro encoding was not set before the first run |

## Related

- [stateful-operations.md](stateful-operations.md): watermarks, state store, monitoring
- [real-time-mode.md](real-time-mode.md): TWS in Real-Time Mode (row-based only, processing-time timers)
- [Build a custom stateful application with transformWithState](https://docs.databricks.com/aws/en/stateful-applications/)
