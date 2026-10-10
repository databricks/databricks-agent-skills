# Schema management

Read this before creating the target table, when records are rejected, when the data shape changes, or when the user asks how Zerobus handles missing, extra, or mistyped fields. Everything here comes from the Zerobus docs (schema management and rescue column pages), so you don't need to fetch them.

## The table is the contract
"Your Delta table schema is the authoritative contract for what Zerobus Ingest accepts."
- **Zerobus gates the data.** "It validates every record against the target table and rejects anything that doesn't fit. It never guesses or drops columns silently."
- **You define the contract** by marking columns required (`NOT NULL`) or nullable, and optionally adding a **rescue column**.
- **Zerobus never augments your table.** "It does not add columns, change types, or evolve the schema to accommodate a record. You evolve what Zerobus Ingest accepts by evolving the table."
- The table must exist **before** any producer sends data. It must be a **managed Delta table** in the workspace's region. Table and column names must use **ASCII letters, digits, and underscores** only. Zerobus doesn't support **recreating** a target table.

## Who validates
| Where | What happens |
|-------|--------------|
| **Server (Zerobus)** | Validates **every record** against the target table schema and returns an error for records that don't fit. This is the authoritative check |
| **Client SDK (Protobuf)** | Pass the compiled message descriptor (for example `TableProperties(table, descriptor_proto=MyMessage.DESCRIPTOR)` in Python) so the SDK can validate and encode records against your schema before sending (Python README). Use the **same proto schema** for stream creation and ingest |
| **Client SDK (JSON)** | Records are sent as JSON; validation happens on the server |

Rejected records surface as ingest errors: an exception, or `on_error` in an ack callback (see [how-it-works.md](how-it-works.md#how-the-sdk-processes-records)).

## How records are matched
A record must contain **at minimum every non-nullable column**. Nullable columns can be omitted and are written as `NULL`.

Zerobus **rejects** a record when it has:
- a **missing non-nullable** column
- a **column name that doesn't exist** in the table (unless a rescue column is configured)
- a **value whose type isn't compatible** with the column (type mappings: [protobuf-schema.md](protobuf-schema.md))

## Choose how strict the contract is
| Scenario | Table design | Accepts | Rejects |
|----------|--------------|---------|---------|
| **1. All columns optional** | Every column nullable | Any subset of columns; omitted ones become `NULL` | Records with a column the table doesn't have |
| **2. Required columns** | `NOT NULL` on must-have fields | Records with all required columns | Records missing a required column |
| **3. Rescue column (Beta)** | Add a tagged, nullable `VARIANT` column | Extra fields, and type mismatches on **nullable** columns, captured as JSON | Records missing a required column |

### Scenario 1: all columns optional
```sql
CREATE TABLE main.default.air_quality (device_name STRING, temp INT, humidity INT);
```
Accepts: all fields, subset (others NULL), any combo. Rejects: unknown fields.

### Scenario 2: required columns
```sql
CREATE TABLE main.default.air_quality (device_name STRING NOT NULL, temp INT NOT NULL, humidity INT);
```
Accepts: required fields present. Rejects: missing required field.

### Scenario 3: rescue column (Beta, JSON only)
**JSON only.** Add **nullable `VARIANT`** column tagged `zerobus-rescue`. Captures non-conforming fields as JSON.
```sql
CREATE TABLE main.default.air_quality (device_name STRING NOT NULL, temp INT, rescue VARIANT);
SET TAG ON COLUMN main.default.air_quality.rescue `zerobus-rescue`;
```
**Verify:** tag in Catalog Explorer (5 min to take effect). Only one column should be tagged. **Routing:** matched → column; unmatched → rescue; type mismatch on nullable → NULL + rescue. **Query:** `SELECT rescue:extra_field::string FROM ... WHERE rescue IS NOT NULL;`

## Evolve the schema safely
**Change table first, then producers.** Zerobus doesn't auto-evolve.

| Change | Safe? | How |
|--------|-------|-----|
| Add nullable | ✓ | `ALTER TABLE ... ADD COLUMN <name> <TYPE>` (old producers → NULL) |
| Add NOT NULL | ✗ | Add as nullable, update producers, then tighten |
| Rename / drop / type change | ✗ | Breaking; coordinate cutover. Rescue column (JSON) catches old fields |
| Protobuf | | Regenerate `.proto` after change ([protobuf-schema.md](protobuf-schema.md)) |

**Verify:** `databricks experimental aitools tools discover-schema <table>` shows new column with correct type/nullability.

If data was made **durable before** a schema change and can't be written afterward, Zerobus puts it in `_zerobus/table_rejected_parquets/` under the table root. Reprocess it with the steps in [recovery.md](recovery.md).

## Protobuf schema rules
- Message must contain every non-nullable column (may omit nullable)
- **Max 2000 columns** per proto schema
- **ASCII letters, digits, underscores** only for table and column names
- Use **same proto schema** for stream creation and ingest calls
- Generate `.proto` from the table; see type mappings in [protobuf-schema.md](protobuf-schema.md)

## Common issues
| Symptom | Fix |
|---------|-----|
| Unknown column | Add column (nullable) or rescue column (JSON) |
| Missing column (NOT NULL) | Send it, or make nullable |
| Column NULL, value sent | Type mismatch; check `rescue` for original; fix producer type |
| Rescue empty | Tag missing, not VARIANT, not nullable, or waiting on tag (5 min max) |
| Rejected for setting `rescue` | Remove `rescue` from payload (reserved) |
| TIMESTAMP rejected | Send epoch microseconds (integer), not string |

## Sources
- [Zerobus schema management](https://docs.databricks.com/ingestion/zerobus-schema-management)
- [Zerobus rescue column](https://docs.databricks.com/ingestion/zerobus-rescue-column)
- [Zerobus Ingest quotas](https://docs.databricks.com/ingestion/zerobus-quotas) (table requirements)
- [SET TAG](https://docs.databricks.com/sql/language-manual/sql-ref-syntax-ddl-set-tag)
- [Python SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/python/README.md) (descriptor validation)
