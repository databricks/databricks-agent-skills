# Temporary Views (Python)

Pipeline-scoped logical datasets — not materialized, not published to UC. Used for shared intermediate transformations that drive multiple downstream tables.

`@dp.temporary_view()` is the current decorator. Legacy `@dlt.view()` (and `@dp.view()` if present in older code) should be migrated — see [SKILL.md Legacy DLT Syntax](../SKILL.md#legacy-dlt-syntax--always-migrate).

```python
@dp.temporary_view(name="<name>", comment="<comment>")     # both optional
def my_view():
    return spark.read.table("source.data")          # batch — or spark.readStream.table(...) for streaming
```

Downstream tables reference the view by name via `spark.read.table("my_view")` or `spark.readStream.table("my_view")`.

## Example

```python
@dp.temporary_view()
def valid_events():
    return (spark.read.table("raw.events")
                 .filter("event_type IS NOT NULL")
                 .filter("timestamp IS NOT NULL"))

@dp.materialized_view()
def user_events():
    return spark.read.table("valid_events").filter("event_type = 'user_action'")
# Other downstream MVs follow the same shape.
```

Streaming variant: return `spark.readStream.*` from the temp view; downstream `@dp.table()` reads it via `spark.readStream.table(...)`.

## Key rules

- Computed on demand — not materialized.
- Either batch or streaming, depending on the returned DataFrame type.
- Pipeline-scoped — not visible outside the pipeline.
- Cannot apply column masks, row filters, or `cluster_by` (it's not a table).
