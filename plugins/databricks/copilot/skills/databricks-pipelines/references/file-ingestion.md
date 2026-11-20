# Ingest and process files in SDP

Use this reference to build a Lakeflow Spark Declarative Pipeline (SDP) that ingests files
with Auto Loader / `read_files()` — from Unity Catalog volumes, cloud object storage (S3,
ADLS, GCS), SFTP, Google Drive, SharePoint, or OneDrive — and for **follow-up unstructured AI
processing** of ingested files (parsing documents with `ai_parse_document`).

## IMPORTANT: Prefer managed ingestion for Google Drive and SharePoint

Google Drive and SharePoint have **managed Lakeflow Connect connectors**. For ingesting
from either, **prefer a managed ingestion pipeline** over hand-writing SDP code:

- **New or existing managed pipeline:** use the `databricks-lakeflow-connect-saas` skill to
  create or update the managed ingestion pipeline for the source.

The managed pipeline handles browse/selection, incremental sync, and schema handling for
the user. Write the code-first `read_files()` pipeline for these two sources only when the
user explicitly wants to author the SDP pipeline themselves — for example, custom
in-pipeline transformations the managed setup does not offer. The recommended flow is:
**create a managed ingestion pipeline** to land the raw files, **then come back here** to
build an SDP pipeline for follow-up processing such as `ai_parse_document`.

Volumes, cloud storage, SFTP, and OneDrive have no managed connector; ingest them with the Auto
Loader patterns below.

## Workflow

1. Identify the source and its path / connection requirements from **Sources**. If a
   connection-based source (SFTP, Google Drive, SharePoint, OneDrive) has no Unity Catalog
   connection yet, tell the user how to create one (see **Sources**) and continue.
2. Pick the dataset shape (streaming table or materialized view) and write the ingestion
   code from **Auto Loader**.
3. If the user wants to extract text, tables, or layout from documents, add the
   **Parse unstructured** step.
4. Substitute the user's real path, URL, and Unity Catalog connection name into the code: the
   path or URL is the literal argument to `.load(...)` / `read_files(...)`, and the connection
   name is the literal `databricks.connection` value. Don't move them into `spark.conf.get(...)`
   or pipeline configuration parameters unless the user asks to parameterize the pipeline.
   Never emit a placeholder path (`/path/to/folder`, `[YOUR_URL]`) or a comment asking the
   user to fill one in, and never drop a required `databricks.connection` option.

## Sources

Which paths each source takes, what access it needs (UC volume, external location, or UC
connection, including how to create a connection), and per-source examples and pitfalls: `references/file-ingestion/sources.md`.

## Auto Loader

The single guide for building the ingestion datasets: streaming table vs. materialized
view, SQL and Python templates, the `binaryFile` schema and `_metadata` column, file
filtering, schema handling, and triggers: `references/file-ingestion/auto-loader.md`.

## Parse unstructured

Parse ingested binary files (PDFs, Office documents, images) with `ai_parse_document`,
either in one materialized view or incrementally downstream of a streaming table:
`references/file-ingestion/parse-unstructured.md`.
