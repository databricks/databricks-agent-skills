#### Core SQL Statements

- `CREATE MATERIALIZED VIEW` - Batch processing with full refresh or incremental computation
- `CREATE STREAMING TABLE` - Continuous incremental processing
- `CREATE TEMPORARY VIEW` - Non-materialized views (pipeline lifetime only)
- `CREATE VIEW` - Non-materialized catalog views (Unity Catalog only)
- `AUTO CDC INTO` - Change data capture flows
- `CREATE FLOW` - Define flows or backfills for streaming tables

#### Critical Rules

- ✅ Use `CREATE OR REFRESH` syntax to define/update datasets
- ✅ Use `STREAM` keyword when reading sources for streaming tables
- ✅ Use `read_files()` function for Auto Loader (cloud storage ingestion)
- ✅ Look up documentation for statement parameters when unsure
- ❌ NEVER use `LIVE.` prefix when reading other datasets (deprecated)
- ❌ NEVER use `CREATE LIVE TABLE` or `CREATE LIVE VIEW` (deprecated - use `CREATE STREAMING TABLE`, `CREATE MATERIALIZED VIEW`, or `CREATE TEMPORARY VIEW` instead)
- ❌ Do not use `PIVOT` clause (unsupported)

#### SQL-Specific Considerations

**Streaming vs. Batch Semantics:**

- Omit `STREAM` keyword for materialized views (batch processing)
- Use `STREAM` keyword for streaming tables to enable streaming semantics

**GROUP BY Best Practices:**

- Prefer `GROUP BY ALL` over explicitly listing individual columns unless the user specifically requests explicit grouping
- Benefits: more maintainable when adding/removing columns, less verbose, reduces risk of missing columns in the GROUP BY clause
- Example: `SELECT category, region, SUM(sales) FROM table GROUP BY ALL` instead of `GROUP BY category, region`

**Python UDFs:**

- You can use Python user-defined functions (UDFs) in SQL queries
- UDFs must be defined in Python files before calling them in SQL source files

**Configuration:**

- Use `SET` statements and `${}` string interpolation for dynamic values and Spark configurations

#### Auto Loader Rules

Auto Loader (`read_files()`) is recommended for ingesting from cloud storage.

**Relevant APIs:**

- `read_files()`

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read ALL the following reference files:

1. [auto-loader-sql.md](auto-loader-sql.md)
2. Always look up format-specific options for the format being loaded
3. [streaming-table-sql.md](streaming-table-sql.md) (when Auto Loader is used with streaming tables)

NO exceptions — always read these reference files first.

#### Materialized View Rules

Materialized Views enable batch processing with full refresh or incremental computation on serverless pipelines.

**Relevant APIs:**

- `CREATE MATERIALIZED VIEW`
- `CREATE OR REFRESH MATERIALIZED VIEW`

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read the following reference file:

1. [materialized-view-sql.md](materialized-view-sql.md)

NO exceptions — always read this reference file first.

#### Streaming Table Rules

Streaming Tables enable incremental processing of continuously arriving data.
Backfilling allows retroactively processing historical data using flows with `INSERT INTO ONCE` - see "streamingTable" API guide for details.

**Relevant APIs:**

- `CREATE STREAMING TABLE`
- `CREATE OR REFRESH STREAMING TABLE`
- `CREATE FLOW` with `INSERT INTO`

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read the following reference file:

1. [streaming-table-sql.md](streaming-table-sql.md)

NO exceptions — always read this reference file first.

#### Temporary View Rules

Temporary views are non-materialized views that exist only during pipeline execution and are private to the pipeline.

**Relevant APIs:**

- `CREATE TEMPORARY VIEW`
- `CREATE TEMPORARY LIVE VIEW` (deprecated)

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read the following reference file:

1. [temporary-view-sql.md](temporary-view-sql.md)

NO exceptions — always read this reference file first.

#### View Rules

Views are non-materialized catalog views published to Unity Catalog (Unity Catalog pipelines only, default publishing mode required).

**Relevant APIs:**

- `CREATE VIEW`

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read the following reference file:

1. [view-sql.md](view-sql.md)

NO exceptions — always read this reference file first.

#### Auto CDC/Apply Changes Rules

Auto CDC in Spark Declarative Pipelines processes change data capture (CDC) events from streaming sources. Use Auto CDC when:

- Tracking changes over time or maintaining current/latest state of records
- Processing updates, upserts, or modifications based on a sequence column (timestamp, version)
- Need to "replace old records" or "keep only current/latest version"
- Handling change events, database changes, or CDC feeds
- Working with out-of-sequence records or slowly changing dimensions (SCD Type 1/2)

**Relevant APIs:**

- `AUTO CDC INTO`
- `CREATE FLOW` with `AUTO CDC`
- `APPLY CHANGES` (deprecated)

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read ALL the following reference files:

1. [auto-cdc-sql.md](auto-cdc-sql.md)
2. [streaming-table-sql.md](streaming-table-sql.md) (since Auto CDC always requires a streaming table as a target)

NO exceptions — always read these reference files first.

**NOTE:** SQL only supports Auto CDC from streaming sources. Auto CDC from database snapshots is NOT supported in SQL - use Python `dp.create_auto_cdc_from_snapshot_flow()` or `dlt.create_auto_cdc_from_snapshot_flow()` instead.

#### Sink Rules

**NOTE:** Sinks are NOT supported in SQL. Sinks are a Python-only feature in Spark Declarative Pipelines. To write data to event streaming services (Apache Kafka, Azure Event Hubs), external Delta tables, or custom data sources, use Python with `dp.create_sink()` and `@dp.append_flow()` APIs. See [sink-python.md](sink-python.md) for details.

#### Data Quality Expectations Rules

Expectations in SQL Declarative Pipelines apply data quality constraints using SQL Boolean expressions in the `CONSTRAINT` clause. Use them to validate records in tables and views.

**Relevant APIs:**

- `CONSTRAINT` clauses with expectations

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read ALL the following reference files:

1. [expectations-sql.md](expectations-sql.md)
2. The corresponding dataset definition guide ("materializedView"/"streamingTable"/"temporaryView"/"view") to ensure the expectations are correctly defined for the particular dataset definition

NO exceptions — always read these reference files first.
