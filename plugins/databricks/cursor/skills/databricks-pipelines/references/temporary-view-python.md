Temporary Views in Spark Declarative Pipelines create temporary logical datasets without persisting data to storage. Use views for intermediate transformations that drive downstream workloads but don't need materialization.

**API Reference:**

**@dp.temporary_view() (preferred) / @dp.view() (alias) / @dlt.view() (deprecated)**
Decorator to define a temporary view. Keep existing `@dlt.view()` code unless the user asks to migrate; when they do, use `@dp.temporary_view()` — see [dlt-migration.md](dlt-migration.md).

```python
@dp.temporary_view(
  name="<name>",
  comment="<comment>"
)
def my_view():
    return spark.read.table("source.data")
```

Parameters:

- `name` (str): View name (defaults to function name)
- `comment` (str): Description for the view

**Common Patterns:**

**Pattern 1: Intermediate transformation layer**

```python
# View for shared filtering logic
@dp.temporary_view()
def valid_events():
    return spark.read.table("raw.events") \
        .filter("event_type IS NOT NULL") \
        .filter("timestamp IS NOT NULL")

# Multiple tables consume the view
@dp.materialized_view()
def user_events():
    return spark.read.table("valid_events") \
        .filter("event_type = 'user_action'")

@dp.materialized_view()
def system_events():
    return spark.read.table("valid_events") \
        .filter("event_type = 'system_event'")
```

**Pattern 2: Streaming views**

```python
# Views work with streaming DataFrames too
@dp.temporary_view()
def streaming_events():
    return spark.readStream.table("bronze.events") \
        .filter("event_id IS NOT NULL")

@dp.table()
def filtered_stream():
    return spark.readStream.table("streaming_events") \
        .filter("event_type = 'critical'")
```

**When to use a Private Table instead:**

Temporary views are the default for intermediate logic. Consider a **private streaming table** (`@dp.table(private=True)`) or **private materialized view** (`@dp.materialized_view(private=True)`) only when the intermediate computation is expensive and materializing it once would save significant reprocessing across downstream consumers or pipeline refreshes. Private tables are materialized and persist for the pipeline's lifetime, but are not published to the catalog — they remain pipeline-scoped like temporary views.

**KEY RULES:**

- Views can return either batch (`spark.read`) or streaming (`spark.readStream`) DataFrames
- Views are not materialized - they're computed on demand when referenced
- Reference views using `spark.read.table("view_name")` or `spark.readStream.table("view_name")`
- Views prevent code duplication when multiple downstream tables need the same transformation
- Views are pipeline-scoped - not published to Unity Catalog or visible outside the pipeline
- Views cannot use column masks, row filters, or `cluster_by` (they are not tables)
