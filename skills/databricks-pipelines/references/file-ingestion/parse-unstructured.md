# Parse unstructured files with `ai_parse_document`

`ai_parse_document` turns binary documents (PDFs, Word, PowerPoint, Google Docs / Slides
exports, images) into structured, queryable output — extracted text, tables, layout, and
metadata — for RAG, search, classification, or document understanding.

It runs on a `FILE` column, the preferred way to land files (Beta; see **`FILE` references
(Beta)** below), or on a binary `content` column, however the files were ingested:

- **Managed ingestion pipeline** (recommended for Google Drive and SharePoint): set
  `file_ingestion_options.format` to `FILE` for a `file` column, or to `BINARYFILE` for a
  `content` column. Parse it in a new SDP pipeline that reads that table.
- **Code-first ingestion**: read the files with `format => "file"`, or with
  `format => "binaryFile"` (`references/file-ingestion/auto-loader.md`), from a volume, cloud storage,
  SFTP, Google Drive, SharePoint, or OneDrive.

The examples use a volume path. For another source, swap the path and add the source's
access options from `references/file-ingestion/sources.md` (for example
`` `databricks.connection` => "my_sharepoint_conn" ``).

## Incremental: `STREAM read_files` streaming table, then a parsing materialized view

```sql
CREATE OR REFRESH STREAMING TABLE documents
AS SELECT *, _metadata FROM STREAM read_files(
  "/Volumes/main/docs/contracts/",
  format => "binaryFile",
  pathGlobFilter => "*.{pdf,jpeg}");

CREATE OR REFRESH MATERIALIZED VIEW documents_parsed
AS SELECT *, ai_parse_document(content, MAP('version', '2.0')) AS parsed_content
FROM documents;
```

The streaming table lands only new files each update, and the materialized view parses
them on refresh, so parsed output stays in sync with incoming documents.

When the files were landed by a managed ingestion pipeline, skip the streaming table and
point the materialized view at the managed pipeline's destination table:

```sql
CREATE OR REFRESH MATERIALIZED VIEW documents_parsed
AS SELECT *, ai_parse_document(content, MAP('version', '2.0')) AS parsed_content
FROM main.sharepoint.documents;
```

## Full refresh: batch `read_files` and parse in one materialized view

```sql
CREATE OR REFRESH MATERIALIZED VIEW documents_parsed
AS SELECT *, _metadata, ai_parse_document(content, MAP('version', '2.0')) AS parsed_content
FROM read_files(
  "/Volumes/main/docs/contracts/",
  format => "binaryFile",
  pathGlobFilter => "*.{pdf,jpeg}");
```

Every refresh re-reads and re-parses all files. Use this for small, full-refresh document
sets, or to try parsing on a few sample files before setting up incremental ingestion.

## `FILE` references (Beta)

Prefer the `FILE` type when the workspace has it enabled (a workspace admin turns it on from the
**Previews** page) and the pipeline can use the Preview channel. It is in Beta, so ask before
choosing it, and fall back to `binaryFile` (the examples above) otherwise.

Reading with `format => "file"` into a `FILE MANAGED` column stores a lightweight reference
(`uri`, `size`, `content_type`, `checksum`) instead of the file's bytes, so it suits large
files. Unity Catalog copies each file into the volume set as the table's `FileSpace`.
`ai_parse_document` reads the `FILE` column directly:

```sql
CREATE OR REFRESH STREAMING TABLE documents (
  path STRING,
  size BIGINT,
  modification_time TIMESTAMP,
  file FILE MANAGED
)
TBLPROPERTIES ('databricks.filespace-preview' = '/Volumes/main/docs/filespace/')
AS SELECT * FROM STREAM read_files(
  "/Volumes/main/docs/contracts/",
  format => "file",
  pathGlobFilter => "*.{pdf,jpeg}");

CREATE OR REFRESH MATERIALIZED VIEW documents_parsed
AS SELECT *, ai_parse_document(file, MAP('version', '2.0')) AS parsed_content
FROM documents;
```

## When to recommend this

- The user has PDFs, Office documents, Google Docs / Slides, or images and needs their
  text, tables, or layout for RAG, search, or document understanding.
- An SDP pipeline exists or is being built, so parsing fits as a materialized view downstream of
  the ingestion streaming table, or, for small document sets, as one that reads and parses in
  one step.

Scope the ingestion table to the file types the user wants parsed with `pathGlobFilter`.

## Related skills

- Function syntax, options, output shape, and compute requirements for `ai_parse_document`,
  and multi-stage document workflows — classifying (`ai_classify`), extracting fields
  (`ai_extract`) — belong to the `databricks-ai-functions` skill. Run each AI function as its
  own step; do not chain `ai_parse_document`, `ai_classify`, and `ai_extract` in one step.

