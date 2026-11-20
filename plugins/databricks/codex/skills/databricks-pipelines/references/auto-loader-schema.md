# Auto Loader Schema Inference, Evolution, Hints, and Type Widening

Schema-related concepts shared by `cloudFiles` (Python) and `read_files` (SQL). Option names and behaviors apply to both unless noted.

In SDP, `cloudFiles.schemaLocation` and the checkpoint are managed automatically — DO NOT set them. (Outside SDP, both are required for inference/evolution to work across restarts.)

## Schema inference defaults

| Format  | Inference behavior                             | Notes for code gen                                           |
| ------- | ---------------------------------------------- | ------------------------------------------------------------ |
| JSON    | All columns as `STRING` (incl. nested fields)  | Set `cloudFiles.inferColumnTypes=true` for real types        |
| CSV     | All columns as `STRING`                        | Same. Auto Loader assumes a header row exists when inferring |
| XML     | All columns as `STRING` (DBR 14.3 LTS+)        | Same. `rowTag` is required                                   |
| Parquet | Types from encoded Parquet schema              | `cloudFiles.inferColumnTypes` has no effect                  |
| Avro    | Types from encoded Avro schema (DBR 10.4 LTS+) | Same                                                         |
| ORC     | NOT SUPPORTED                                  | Must provide an explicit schema                              |
| Text    | Fixed: single `value: STRING` column           | Cannot be changed; partition columns are still inferred      |

Inference sample size: first 50 GB OR 1000 files (whichever is hit first). Override via SQL configs `spark.databricks.cloudFiles.schemaInference.sampleSize.numBytes` / `numFiles`.

## Schema evolution modes

Set with `cloudFiles.schemaEvolutionMode` (Python) or `schemaEvolutionMode =>` (SQL). Default is `addNewColumns` when no schema is provided, `none` otherwise.

| Mode                            | New column behavior                                                              | Type-mismatch behavior                          |
| ------------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------- |
| `addNewColumns` (default)       | Stream fails; new column appended to schema; existing types unchanged            | Goes to rescued data column                     |
| `rescue`                        | Schema does not evolve; stream never fails on schema changes                     | Goes to rescued data column                     |
| `failOnNewColumns`              | Stream fails; won't restart until schema is updated or offending file is removed | Goes to rescued data column                     |
| `none`                          | New columns ignored; data dropped unless `rescuedDataColumn` is set              | Silently dropped unless `rescuedDataColumn` set |
| `addNewColumnsWithTypeWidening` | Stream fails; new columns appended; supported widenings applied (see below)      | Unsupported widenings go to rescued data column |

**Picking a mode:**

- Default (`addNewColumns`) is correct for most pipelines — let new columns flow through and accept a one-time restart.
- `rescue` for pipelines that must never break (vendor data with frequent schema drift).
- `failOnNewColumns` for strict contract enforcement (regulated/PII data).
- `none` only when you have a fixed, permanent schema and don't want a rescued column either.
- `addNewColumnsWithTypeWidening` when sources occasionally widen numeric types (e.g., `int` → `long`).

## Schema hints

`cloudFiles.schemaHints` (Python) / `schemaHints =>` (SQL) overrides inferred types for specific columns. Only applies when Auto Loader is inferring the schema (no effect when you provide an explicit schema). Hints can also ADD columns absent from the inferred schema.

```python
.option("cloudFiles.schemaHints",
        "id INT, tags MAP<STRING,STRING>, user_info.dob DATE, prices.value INT")
```

```sql
schemaHints => 'id INT, tags MAP<STRING,STRING>, user_info.dob DATE'
```

Nested-path syntax:

- Struct field: `user_info.dob DATE`
- Array element: `users.element.id INT`
- Map key / value: `prices.key INT`, `prices.value INT`

For typed formats (Parquet/Avro), hints do NOT cast — Auto Loader asks the reader for the hinted type and rescues mismatches into the rescued data column.

## Rescued data column

Captures data that wouldn't otherwise be parsed:

- Columns missing from the schema
- Type mismatches
- Case mismatches (unless `readerCaseSensitive=false`)

Stored as a JSON blob containing the rescued fields plus the source file path of each record.

**Auto-included** when Auto Loader infers the schema (column name `_rescued_data`).

**Manual schemas — opt in** by setting `rescuedDataColumn` AND adding a `STRING` column of that name to your schema:

```python
.schema("id INT, name STRING, _rescued_data STRING")
.option("rescuedDataColumn", "_rescued_data")
```

In `none` mode, the column is NOT auto-included even with inference — opt in via `rescuedDataColumn` if you want it.

## Partition column inference

Auto Loader infers Hive-style partitions automatically (e.g., `base/event=click/date=2021-04-01/f0.json` → `event` and `date` columns).

Auto Loader does NOT evolve partition columns. If your directory layout adds a new partition key (e.g., `hour=01`), enumerate all keys explicitly:

```python
.option("cloudFiles.partitionColumns", "event,date,hour")
```

For inconsistent partition layouts, Auto Loader infers no partitions — explicit `cloudFiles.partitionColumns` is the only fix.

For Text and BinaryFile formats (fixed schema), set `cloudFiles.schemaLocation` outside SDP to avoid re-inferring partitions on every start. Inside SDP this is automatic.

## Automatic type widening

Public Preview in DBR 16.4+. Mode `addNewColumnsWithTypeWidening` evolves numeric types in place instead of rescuing them.

Supported widenings:

| From    | To                                       |
| ------- | ---------------------------------------- |
| byte    | short, int, long, decimal, double        |
| short   | int, long, decimal, double               |
| int     | long, decimal, double                    |
| long    | decimal                                  |
| float   | double                                   |
| decimal | decimal with greater precision and scale |
| date    | timestampNTZ (Parquet only)              |

Widening to `decimal` uses a starting precision of `10` for `byte`/`short`/`int` and `20` for `long`. Example: `int` reading `decimal(5,2)` widens to `decimal(12,2)`.

Unsupported changes (e.g., `int` → `string`) still go to the rescued data column.

**Prerequisites:**

- DBR 16.4+
- The Delta sink must have type widening enabled:

```sql
ALTER TABLE my_table SET TBLPROPERTIES ('delta.enableTypeWidening' = 'true')
-- or at create time:
CREATE TABLE T(c1 INT) TBLPROPERTIES ('delta.enableTypeWidening' = 'true')
```

In SDP, set `delta.enableTypeWidening` via `table_properties={...}` (Python) or `TBLPROPERTIES (...)` (SQL) on the streaming table — see [streaming-table-python](streaming-table-python.md) / [streaming-table-sql](streaming-table-sql.md).

**Limitations:**

- `prefersDecimal` is forced to `true` and cannot be disabled when this mode is on.
- `date` → `timestampNTZ` widening is Parquet-only.

## Recovery from `UnknownFieldException`

In modes that fail on schema change (`addNewColumns`, `failOnNewColumns`, `addNewColumnsWithTypeWidening`), the stream stops with `UnknownFieldException`. Auto Loader updates the schema location with the merged schema BEFORE throwing.

- **In SDP:** the pipeline runtime auto-restarts on schema-update events; the next run picks up the new schema.
- **In Lakeflow Jobs:** configure the job to auto-restart on failure; the next run continues from the schema location.
