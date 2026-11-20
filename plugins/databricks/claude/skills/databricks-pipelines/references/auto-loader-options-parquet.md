PARQUET-Specific Options

**Key gotchas / tricks:**

- Schema inference uses the file's encoded Parquet schema (NOT strings — unlike JSON/CSV/XML). `cloudFiles.inferColumnTypes` is irrelevant for Parquet.
- When the same column has different types across files in the inference sample, Auto Loader picks the WIDEST type. Use `cloudFiles.schemaHints` to override (Auto Loader will ask the reader for the hinted type and rescue mismatches into the rescued data column).
- `mergeSchema` (default `false`): when `true`, merges schemas across all files; significantly more expensive — only enable when files have heterogeneous schemas not handled by schema evolution.
- `datetimeRebaseMode` / `int96RebaseMode`: set to `CORRECTED` to read modern dates as-is; `LEGACY` for files written by Spark 2.x with Julian-calendar dates; `EXCEPTION` to fail on ambiguity.

| Option              | Type    |
| ------------------- | ------- |
| datetimeRebaseMode  | String  |
| int96RebaseMode     | String  |
| mergeSchema         | Boolean |
| readerCaseSensitive | Boolean |
| rescuedDataColumn   | String  |
