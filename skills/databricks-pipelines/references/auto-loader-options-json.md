JSON-Specific Options

**Key gotchas / tricks:**

- `multiLine` (default `false`): MUST be `true` for pretty-printed JSON, JSON arrays, or any record that spans multiple lines. Single most common JSON ingestion bug. With `multiLine=true`, `UTF-16`/`UTF-32` encoding is not supported.
- `singleVariantColumn`: ingest the entire JSON document as a single Variant column with the given name. Most robust pattern for schema drift / vendor data — preserves case sensitivity, types, and nulls. Pair with the `VARIANT` type downstream.
- `inferTimestamp` and `prefersDecimal`: only take effect when `cloudFiles.inferColumnTypes=true`. Otherwise all JSON columns are inferred as `STRING`.
- `mode` (default `PERMISSIVE`): `DROPMALFORMED` and `FAILFAST` are evaluated AFTER `rescuedDataColumn` rescue — they only fire on truly malformed JSON, not on type/schema mismatches.
- `dropFieldIfAllNull`: useful with `cloudFiles.inferColumnTypes=true` to avoid `NullType` columns from sparse fields.

| Option                             | Type    |
| ---------------------------------- | ------- |
| allowBackslashEscapingAnyCharacter | Boolean |
| allowComments                      | Boolean |
| allowNonNumericNumbers             | Boolean |
| allowNumericLeadingZeros           | Boolean |
| allowSingleQuotes                  | Boolean |
| allowUnquotedControlChars          | Boolean |
| allowUnquotedFieldNames            | Boolean |
| badRecordsPath                     | String  |
| columnNameOfCorruptRecord          | String  |
| dateFormat                         | String  |
| dropFieldIfAllNull                 | Boolean |
| encoding / charset                 | String  |
| inferTimestamp                     | Boolean |
| lineSep                            | String  |
| locale                             | String  |
| mode                               | String  |
| multiLine                          | Boolean |
| prefersDecimal                     | Boolean |
| primitivesAsString                 | Boolean |
| readerCaseSensitive                | Boolean |
| rescuedDataColumn                  | String  |
| singleVariantColumn                | String  |
| timestampFormat                    | String  |
| timeZone                           | String  |
