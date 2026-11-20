# Streaming table schema evolution

## Purpose

Help the user change the columns of an existing streaming table -- add, drop, or rename a column, or
widen a column's type -- without a full refresh, a checkpoint reset, or re-ingestion. Also covers the
errors these operations produce when a prerequisite is missing.

## Availability -- confirm before promising it works

Schema evolution via `ALTER TABLE` is a **Beta** feature **for streaming tables specifically**. The
availability caveat and the full-refresh fallback in this reference apply only to streaming tables --
altering a column on a regular (non-streaming) Delta table is generally available, is not gated, and
needs no fallback, so do not apply this section's caveats there.

For streaming tables it is a gated preview. It is **not enabled in every workspace**, and enablement
is separate from the prerequisites below -- a workspace can satisfy external metadata, column
mapping, and type widening and still not have the preview turned on. Enablement is controlled by
Databricks, not a customer-settable config, so the customer cannot switch it on themselves.

Because you cannot query a workspace's preview status from here, do not assert that these commands
will work. Frame them as "supported if the preview is enabled for your workspace." When the column
`ALTER` is not available, the command fails with `STREAMING_TABLE_OPERATION_NOT_ALLOWED.INVALID_ALTER`
("To alter the schema or properties of Streaming Tables, please use the CREATE OR REFRESH command.").
That same error also covers genuinely unsupported operations, so it is not proof the preview is off:
if the prerequisites below are met and the operation is a supported one (add/drop/rename/widen), treat
this error as the preview likely not being enabled and direct the user to their Databricks account
team to enable it. Distinguish it from the prerequisite errors below, which the user *can* fix
themselves.

### Fallback when the preview is not enabled

If the preview is off, fall back to the pre-feature approach: change the column in the streaming
table's `CREATE OR REFRESH` definition (the schema or the `SELECT`) and run a **full refresh** to
rebuild the table on the new schema. This re-ingests the data and resets the checkpoint -- the very
costs the `ALTER` path avoids -- so present it as the workaround, not the preferred path. Note that a
full refresh requires the source to still hold the history being re-read; for an append-only source
that has aged out data, a full refresh loses the aged-out rows. Direct the user to their Databricks
account team to enable the preview as the better long-term fix.

## When to use

- User wants to add, drop, or rename a column on an existing streaming table.
- User wants to widen a column type, for example `INT` to `BIGINT`.
- User wants to change a column type incompatibly (for example `STRING` to `INT`) and is being told a
  full refresh is required.
- User hits `DELTA_MERGE_INCOMPATIBLE_DATATYPE`, `DELTA_FAILED_TO_MERGE_FIELDS`, or a
  "requires column mapping" / "type widening" error after altering a streaming table.

## The syntax is `ALTER TABLE`, not `ALTER STREAMING TABLE`

Column operations use `ALTER TABLE`, even though the target is a streaming table:

```sql
ALTER TABLE main.sales.orders ADD COLUMN order_channel STRING COMMENT 'web or store';
ALTER TABLE main.sales.orders DROP COLUMN legacy_region;
ALTER TABLE main.sales.orders RENAME COLUMN amt TO amount;
ALTER TABLE main.sales.orders ALTER COLUMN quantity TYPE BIGINT;
```

Two mistakes to avoid:

- **Do not use `ALTER STREAMING TABLE` to add, drop, rename, or change the type of a column.** That
  form supports only schedules, row filters, tags, owner, table properties, and column masks/comments
  -- so `ALTER COLUMN ... COMMENT` and masks still work on a streaming table, but ADD/DROP/RENAME/TYPE
  do not.
- **The type clause is `TYPE <data_type>`, not `SET DATA TYPE`.** `SET DATA TYPE` is not valid syntax.

`ALTER STREAMING TABLE` *is* correct for table properties (`SET TBLPROPERTIES`). Note that setting
properties directly on an existing streaming table may fail depending on the property; prefer setting
them in the pipeline source code (see below).

## Prerequisites -- check these before proposing an ALTER

Missing prerequisites are the most common cause of confusing errors, so establish them first.

| Operation | Requires |
| --- | --- |
| `ADD COLUMN` | External metadata |
| `DROP COLUMN` | External metadata + column mapping mode `name` |
| `RENAME COLUMN` | External metadata + column mapping mode `name` |
| `ALTER COLUMN ... TYPE` | External metadata + type widening |

All operations additionally require the streaming table to publish to Unity Catalog.

### External metadata

Column operations require external metadata on the pipeline that owns the streaming table; without it
the command fails. Set it in the pipeline configuration, then run one pipeline update:

```json
{
  "configuration": {
    "pipelines.externalMetadata.enabled": "true"
  }
}
```

### Column mapping (table-level only)

Column mapping mode `name` is a **table property** -- there is no pipeline-level equivalent. It must
be set in the streaming table's `CREATE OR REFRESH STREAMING TABLE` definition, in its
`TBLPROPERTIES`:

```sql
CREATE OR REFRESH STREAMING TABLE orders
TBLPROPERTIES ('delta.columnMapping.mode' = 'name')
AS SELECT * FROM STREAM(main.schema.raw_events);
```

Do **not** try to turn it on with `ALTER TABLE orders SET TBLPROPERTIES ('delta.columnMapping.mode' =
'name')` -- setting column mapping mode this way does not work on a streaming table. Put it in the
table definition and run a pipeline update.

Warn the user that enabling column mapping is **irreversible** and raises the table's reader/writer
protocol versions, so older DBR versions and external readers may no longer be able to read it.

### Type widening (pipeline-level or table-level)

Type widening can be set once for the whole pipeline with `pipelines.enableTypeWidening`:

```json
{
  "configuration": {
    "pipelines.enableTypeWidening": "true"
  }
}
```

Or per table with the `delta.enableTypeWidening` table property:

```sql
CREATE OR REFRESH STREAMING TABLE orders
TBLPROPERTIES ('delta.enableTypeWidening' = 'true')
AS SELECT * FROM STREAM(main.schema.raw_events);
```

Tables with type widening enabled require DBR 15.4 LTS or above to read.

### The multi-hop footgun

The prerequisite must hold on the **specific table being altered**, and every table in a multi-hop
chain is a separate Delta table with its own metadata. Setting a property on only the first table
makes the *downstream* table fail. Since column mapping has no pipeline-level switch, it must be
repeated in each table's `TBLPROPERTIES`:

```sql
CREATE OR REFRESH STREAMING TABLE bronze_events
TBLPROPERTIES ('delta.columnMapping.mode' = 'name')
AS SELECT * FROM STREAM(main.schema.raw_events);

-- The downstream table needs the SAME property. Omitting it here is the usual bug.
CREATE OR REFRESH STREAMING TABLE silver_events
TBLPROPERTIES ('delta.columnMapping.mode' = 'name')
AS SELECT * FROM STREAM(bronze_events);
```

Type widening, by contrast, can cover the whole chain in one line via `pipelines.enableTypeWidening`.

## Keep the table definition in sync

`ALTER TABLE` changes the table, not its defining query. If the streaming table declares an explicit
schema, the same change must be made in its definition, or the next refresh reconciles the table back
toward the declared schema.

Make the change in the pipeline source code and run the `ALTER` together, before the next pipeline
update runs.

For an implicit-schema table (`CREATE OR REFRESH STREAMING TABLE st AS SELECT * FROM ...`), no
definition change is needed.

## Changing a type incompatibly (narrowing, or STRING to INT)

`ALTER COLUMN ... TYPE` can only widen. For an incompatible change, migrate the column in place
instead of recommending a full refresh:

```sql
-- 1. Add a column with the new type.
ALTER TABLE main.bronze.users ADD COLUMN user_id_new INT;

-- 2. Backfill it from the old column.
UPDATE main.bronze.users SET user_id_new = CAST(user_id AS INT);

-- 3. Drop the old column.
ALTER TABLE main.bronze.users DROP COLUMN user_id;

-- 4. Rename the new column into place.
ALTER TABLE main.bronze.users RENAME COLUMN user_id_new TO user_id;
```

Then update the pipeline source code to declare the new type and re-run
it. This avoids a checkpoint reset and a full refresh.

Step 2 is DML against a streaming table, which has its own requirements. The `UPDATE` produces a
change commit on the table, so any downstream flow that streams from it will fail when it reaches the
backfilled data unless it reads with `skipChangeCommits`.

**Do not apply `skipChangeCommits` for the customer.** It is a dangerous option: it makes a stream
silently ignore every update and delete on the source, so any that matter to that consumer are lost
without warning. Surface that a downstream stream will break and that `skipChangeCommits` is the
option that addresses it, and point the customer to the `skipChangeCommits` guidance
in [streaming-table-sql](streaming-table-sql.md). Have them read up on it and decide
for themselves. Set it only if the customer explicitly asks for it after understanding what it skips
-- never add it proactively for them.

## Diagnosing `DELTA_MERGE_INCOMPATIBLE_DATATYPE`

"Failed to merge incompatible data types LongType and IntegerType" after a type change. Read the
order of the two types -- it tells you which side is wrong:

- The **first** type is the target table's current schema.
- The **second** type is the schema of the incoming data.

So `LongType and IntegerType` means the table is already `BIGINT` while the incoming data is still
`INT`. Work through these in order:

1. **Is type widening enabled on THIS table?** For a multi-hop chain, check the table that is
   failing, not the one the user altered. A downstream table missing `delta.enableTypeWidening` is
   the most common cause. The fix is to add `TBLPROPERTIES ('delta.enableTypeWidening' = 'true')` to
   that table's `CREATE OR REFRESH STREAMING TABLE` definition, or set
   `pipelines.enableTypeWidening = true` in the pipeline configuration to cover all tables at
   once. **This is NOT the ALTER TABLE beta path** — setting a table property in a
   `CREATE OR REFRESH` definition is always available and requires no beta preview. Do **not** suggest
   a full refresh for this case; a pipeline update after enabling the property resolves the error.
2. **Where does the `INT` come from?** It depends on the source format. Spark's **JSON** inference
   never produces `IntegerType` for whole numbers (it uses `LongType`), so with a JSON-inferred
   schema an `INT` was *declared* somewhere: an explicit column list in the table definition, a
   `schemaHints` or `.schema(...)` on the reader, a `CAST(... AS INT)`, or an upstream Delta table
   whose column is genuinely `INT` -- fix it at that declaration. Spark's **CSV** inference, by
   contrast, *does* produce `IntegerType` for values that fit a 32-bit int, so an `IntegerType`
   inferred from a CSV source is expected and need not be declared anywhere. (Auto Loader defaults
   every JSON/CSV column to `STRING` unless `cloudFiles.inferColumnTypes=true`; with that on, CSV can
   infer `IntegerType` the same way.)
3. **Does the stream need to restart?** With type widening enabled, the stream may fail once with a
   retryable schema-change exception and then restart on the new schema. A persistent failure asking
   to acknowledge a type change needs the `allowSourceColumnTypeChange` reader option.

## Non-additive source schema changes

When a source read by the streaming table drops or renames a column, the stream stops and reports the
change rather than guessing intent. To continue, acknowledge the change:

```json
{
  "configuration": {
    "spark.databricks.delta.streaming.allowSourceColumnDrop": "always",
    "spark.databricks.delta.streaming.allowSourceColumnRename": "always"
  }
}
```

`always` acknowledges all future changes of that kind; a specific version number acknowledges one
change. Acknowledging a source change does **not** propagate it to the streaming table -- the user
still needs `ALTER TABLE` to make the matching change on the target.

## Limitations -- state these before the user hits them

- **A full refresh discards `ALTER` operations.** The table is regenerated from its definition. Make
  the equivalent change in the definition if it needs to survive a full refresh.
- **Streaming views are not supported.** Schema evolution does not work when a streaming view sits on
  the path to the streaming table -- both flows that read from a streaming view and flows defined
  from one.
- **`AUTO CDC` flows cannot drop or rename columns.** Auto CDC tracks change data state keyed on
  column identifiers, so `DROP COLUMN` and `RENAME COLUMN` fail. `ADD COLUMN` and
  `ALTER COLUMN ... TYPE` are supported.
- **Top-level columns only.** Fields nested inside structs, arrays, or maps cannot be changed.
- **Auto Loader source schemas are not updated.** If a flow reads with Auto Loader, Auto Loader
  tracks the schema of its source files separately, and `ALTER TABLE` does not change it. For a
  source that keeps producing the column, a `DROP COLUMN` is re-added on the next update and a
  `RENAME COLUMN` keeps producing the old name. To make a drop or rename stick, also constrain what
  Auto Loader reads with an explicit reader schema that omits the column, plus the
  `rescuedDataColumn` option -- when a schema is supplied, Auto Loader does not add a rescued data
  column automatically, so without that option the field is dropped.
