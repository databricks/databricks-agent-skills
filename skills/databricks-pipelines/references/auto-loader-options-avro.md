AVRO-Specific Options

**Key gotchas / tricks:**

- Schema inference uses the file's encoded Avro schema (NOT strings — unlike JSON/CSV/XML). `cloudFiles.inferColumnTypes` is irrelevant for Avro. Avro schema inference requires DBR 10.4 LTS+.
- `avroSchema`: provide an Avro schema string to read with an evolved/compatible schema (e.g., add a column with a default value). The reader will deserialize using the evolved schema.
- `mergeSchema` (default `false`): merges schemas across files but does NOT relax data types (different from Parquet/CSV). Use schema evolution modes for type changes.
- `datetimeRebaseMode`: `EXCEPTION`/`LEGACY`/`CORRECTED` for cross-calendar date handling.

| Option              | Type    |
| ------------------- | ------- |
| avroSchema          | String  |
| datetimeRebaseMode  | String  |
| mergeSchema         | Boolean |
| readerCaseSensitive | Boolean |
| rescuedDataColumn   | String  |
