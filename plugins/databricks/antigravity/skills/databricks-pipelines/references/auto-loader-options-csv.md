CSV-Specific Options

**Key gotchas / tricks:**

- `header`: even though the CSV reader's default is `false`, Auto Loader's schema inference assumes files HAVE headers by default. If your CSV files have no headers, explicitly set `.option("header", "false")` (Auto Loader will then name columns `_c0`, `_c1`, ... or use your provided schema).
- `inferSchema`: do NOT use this for Auto Loader — use `cloudFiles.inferColumnTypes` instead. `inferSchema` is the batch reader's option.
- `mergeSchema`: enabled by default for Auto Loader (merges schemas across files in the inference sample).
- `multiLine` (default `false`): set to `true` if records contain quoted fields with embedded newlines. Disables `UTF-16`/`UTF-32`.
- `mode` (default `PERMISSIVE`): combined with `rescuedDataColumn`, type/schema mismatches go to the rescued column rather than dropping/failing. Only truly malformed CSV (unclosed quotes, etc.) trigger `DROPMALFORMED`/`FAILFAST`.
- `escape` defaults to `\`, `quote` defaults to `"`. Use `unescapedQuoteHandling` (`STOP_AT_DELIMITER` etc.) for messy vendor CSVs.
- `skipRows`: useful for files with non-data preamble lines before the header.

| Option                    | Type    |
| ------------------------- | ------- |
| badRecordsPath            | String  |
| charToEscapeQuoteEscaping | Char    |
| columnNameOfCorruptRecord | String  |
| comment                   | Char    |
| dateFormat                | String  |
| emptyValue                | String  |
| encoding / charset        | String  |
| enforceSchema             | Boolean |
| escape                    | Char    |
| header                    | Boolean |
| ignoreLeadingWhiteSpace   | Boolean |
| ignoreTrailingWhiteSpace  | Boolean |
| inferSchema               | Boolean |
| lineSep                   | String  |
| locale                    | String  |
| maxCharsPerColumn         | Int     |
| maxColumns                | Int     |
| mergeSchema               | Boolean |
| mode                      | String  |
| multiLine                 | Boolean |
| nanValue                  | String  |
| negativeInf               | String  |
| nullValue                 | String  |
| parserCaseSensitive       | Boolean |
| positiveInf               | String  |
| preferDate                | Boolean |
| quote                     | Char    |
| readerCaseSensitive       | Boolean |
| rescuedDataColumn         | String  |
| sep / delimiter           | String  |
| skipRows                  | Int     |
| timestampFormat           | String  |
| timeZone                  | String  |
| unescapedQuoteHandling    | String  |
