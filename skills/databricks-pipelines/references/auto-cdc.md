# Auto CDC (apply_changes) in Spark Declarative Pipelines

The `apply_changes` API enables processing Change Data Capture (CDC) feeds to automatically handle inserts, updates, and deletes in target tables.

## Key Concepts

Auto CDC in Spark Declarative Pipelines:

- Automatically processes CDC operations (INSERT, UPDATE, DELETE)
- Supports SCD Type 1 (update in place) and Type 2 (historical tracking)
- Handles ordering of changes via sequence columns
- Deduplicates CDC records

## Language-Specific Implementations

For detailed implementation guides:

- **Python**: [auto-cdc-python.md](auto-cdc-python.md)
- **SQL**: [auto-cdc-sql.md](auto-cdc-sql.md)

## Reading SCD Type 2 Tables

For querying the history tables produced by SCD Type 2 (`__START_AT` / `__END_AT`), point-in-time queries, change analysis, and joining facts with historical dimensions, see [scd-2-querying.md](scd-2-querying.md).

**Note**: The API is also known as `applyChanges` in some contexts.
