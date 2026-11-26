# read_files Table-Valued Function

Read files from cloud storage or Unity Catalog volumes directly in SQL, with automatic format detection and schema inference.

---

## Syntax

```sql
SELECT * FROM read_files(
  path
  [, option_key => option_value ] [...]
)
```

## Core Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | STRING | Yes | URI of data location. Supports `s3://`, `abfss://`, `gs://`, `/Volumes/...` paths. Accepts glob patterns |

## Common Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `format` | STRING | Auto-detected | File format: `'csv'`, `'json'`, `'parquet'`, `'avro'`, `'orc'`, `'text'`, `'binaryFile'`, `'xml'` |
| `schema` | STRING | Inferred | Explicit schema definition in DDL format |
| `schemaHints` | STRING | None | Override subset of inferred schema columns |
| `rescuedDataColumn` | STRING | `'_rescued_data'` | Column name for data that could not be parsed. Set to empty string to disable |
| `pathGlobFilter` / `fileNamePattern` | STRING | None | Glob pattern to filter files (e.g., `'*.csv'`) |
| `recursiveFileLookup` | BOOLEAN | `false` | Search nested directories |
| `modifiedAfter` | TIMESTAMP STRING | None | Only read files modified after this timestamp |
| `modifiedBefore` | TIMESTAMP STRING | None | Only read files modified before this timestamp |
| `partitionColumns` | STRING | Auto-detected | Comma-separated Hive-style partition columns. Empty string ignores all partitions |
| `useStrictGlobber` | BOOLEAN | `true` | Strict glob pattern matching |
| `inferColumnTypes` | BOOLEAN | `true` | Infer exact column types (vs treating all as STRING) |
| `schemaEvolutionMode` | STRING | -- | Schema evolution behavior: `'none'` to drop rescued data column |

## CSV-Specific Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `sep` / `delimiter` | STRING | `','` | Field delimiter |
| `header` | BOOLEAN | `false` | First row contains column names |
| `encoding` | STRING | `'UTF-8'` | Character encoding |
| `quote` | STRING | `'"'` | Quote character |
| `escape` | STRING | `'\'` | Escape character |
| `nullValue` | STRING | `''` | String representation of null |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | Date parsing format |
| `timestampFormat` | STRING | `'yyyy-MM-dd\'T\'HH:mm:ss...'` | Timestamp parsing format |
| `mode` | STRING | `'PERMISSIVE'` | Parse mode: `'PERMISSIVE'`, `'DROPMALFORMED'`, `'FAILFAST'` |
| `multiLine` | BOOLEAN | `false` | Allow records spanning multiple lines |
| `ignoreLeadingWhiteSpace` | BOOLEAN | `false` | Trim leading whitespace |
| `ignoreTrailingWhiteSpace` | BOOLEAN | `false` | Trim trailing whitespace |
| `comment` | STRING | None | Line comment character |
| `maxCharsPerColumn` | INTEGER | None | Max characters per column |
| `maxColumns` | INTEGER | None | Max number of columns |
| `mergeSchema` | BOOLEAN | `false` | Merge schemas across files |
| `enforceSchema` | BOOLEAN | `true` | Enforce specified schema |
| `locale` | STRING | `'US'` | Locale for number/date parsing |
| `charToEscapeQuoteEscaping` | STRING | None | Character to escape the quote escape character |
| `readerCaseSensitive` | BOOLEAN | `true` | Case-sensitive column name matching |

## JSON-Specific Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `multiLine` | BOOLEAN | `false` | Parse multi-line JSON records |
| `allowComments` | BOOLEAN | `false` | Allow Java/C++ style comments |
| `allowSingleQuotes` | BOOLEAN | `true` | Allow single quotes for strings |
| `allowUnquotedFieldNames` | BOOLEAN | `false` | Allow unquoted field names |
| `allowBackslashEscapingAnyCharacter` | BOOLEAN | `false` | Allow backslash to escape any character |
| `allowNonNumericNumbers` | BOOLEAN | `true` | Allow NaN, Infinity, -Infinity |
| `encoding` | STRING | `'UTF-8'` | Character encoding |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | Date parsing format |
| `timestampFormat` | STRING | -- | Timestamp parsing format |
| `inferTimestamp` | BOOLEAN | `false` | Infer timestamp types |
| `prefersDecimal` | BOOLEAN | `false` | Prefer DECIMAL over DOUBLE |
| `primitivesAsString` | BOOLEAN | `false` | Infer all primitives as STRING |
| `singleVariantColumn` | STRING | None | Read entire JSON as single VARIANT column |
| `locale` | STRING | `'US'` | Locale for parsing |
| `mode` | STRING | `'PERMISSIVE'` | Parse mode |
| `readerCaseSensitive` | BOOLEAN | `true` | Case-sensitive column matching |
| `timeZone` | STRING | Session timezone | Timezone for timestamp parsing |

## XML-Specific Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `rowTag` | STRING | **Required** | XML tag that delimits rows |
| `attributePrefix` | STRING | `'_'` | Prefix for XML attributes |
| `valueTag` | STRING | `'_VALUE'` | Tag for element text content |
| `encoding` | STRING | `'UTF-8'` | Character encoding |
| `ignoreSurroundingSpaces` | BOOLEAN | `true` | Ignore whitespace around values |
| `ignoreNamespace` | BOOLEAN | `false` | Ignore XML namespaces |
| `mode` | STRING | `'PERMISSIVE'` | Parse mode |
| `dateFormat` | STRING | `'yyyy-MM-dd'` | Date parsing format |
| `timestampFormat` | STRING | -- | Timestamp parsing format |
| `locale` | STRING | `'US'` | Locale for parsing |
| `readerCaseSensitive` | BOOLEAN | `true` | Case-sensitive matching |
| `samplingRatio` | DOUBLE | `1.0` | Fraction of rows to sample for schema inference |

## Parquet / Avro / ORC Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mergeSchema` | BOOLEAN | `false` | Merge schemas across files |
| `readerCaseSensitive` | BOOLEAN | `true` | Case-sensitive column matching |
| `rescuedDataColumn` | STRING | -- | Column for rescued data |
| `datetimeRebaseMode` | STRING | -- | Rebase mode for datetime values |
| `int96RebaseMode` | STRING | -- | Rebase mode for INT96 timestamps (Parquet only) |

## Streaming Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `includeExistingFiles` | BOOLEAN | `true` | Process existing files on first run |
| `maxFilesPerTrigger` | INTEGER | None | Max files per micro-batch |
| `maxBytesPerTrigger` | STRING | None | Max bytes per micro-batch |
| `allowOverwrites` | BOOLEAN | `false` | Allow processing of overwritten files |
| `schemaEvolutionMode` | STRING | -- | Schema evolution behavior |
| `schemaLocation` | STRING | -- | Location to store inferred schema |

## Requirements

- Databricks Runtime 13.3 LTS and above
- Databricks SQL

## Examples

```sql
-- Auto-detect format and schema from cloud storage
SELECT * FROM read_files('s3://my-bucket/data/');

-- Read CSV with explicit schema
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/sales.csv',
  format => 'csv',
  header => true,
  schema => 'order_id INT, customer_id INT, amount DOUBLE, order_date DATE'
);

-- Read CSV with schema hints (override specific columns only)
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/events/',
  format      => 'csv',
  header      => true,
  schemaHints => 'event_timestamp TIMESTAMP, amount DECIMAL(10,2)'
);

-- Read JSON with multi-line support
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/api_responses/',
  format    => 'json',
  multiLine => true
);

-- Read Parquet with merged schema across files
SELECT * FROM read_files(
  's3://my-bucket/parquet-data/',
  format      => 'parquet',
  mergeSchema => true
);

-- Read XML with row tag
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/feed.xml',
  format => 'xml',
  rowTag => 'record'
);

-- Read binary files (images, PDFs) for ai_parse_document
SELECT path, content FROM read_files(
  '/Volumes/catalog/schema/volume/documents/',
  format => 'binaryFile'
);

-- Filter files by glob pattern and modification date
SELECT * FROM read_files(
  's3://my-bucket/logs/',
  format          => 'json',
  pathGlobFilter  => '*.json',
  modifiedAfter   => '2025-01-01T00:00:00Z',
  modifiedBefore  => '2025-02-01T00:00:00Z'
);

-- Recursive directory scan with partition discovery
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/partitioned_data/',
  recursiveFileLookup => true,
  partitionColumns    => 'year,month'
);

-- Include file metadata
SELECT *, _metadata.file_path, _metadata.file_name, _metadata.file_size
FROM read_files('/Volumes/catalog/schema/volume/data/');

-- Create table from files
CREATE TABLE catalog.schema.imported_data AS
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/export.csv',
  format => 'csv',
  header => true
);

-- Streaming table from cloud storage
CREATE STREAMING TABLE catalog.schema.streaming_events AS
SELECT * FROM STREAM read_files(
  's3://my-bucket/events/',
  format              => 'json',
  includeExistingFiles => false,
  maxFilesPerTrigger   => 100
);

-- Read single VARIANT column for semi-structured JSON
SELECT * FROM read_files(
  '/Volumes/catalog/schema/volume/complex.json',
  format              => 'json',
  singleVariantColumn => 'raw_data'
);
```
