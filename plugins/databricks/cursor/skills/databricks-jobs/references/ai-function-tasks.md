# AI Function tasks

Use native `ai_function_task` tasks to apply Document Parsing, AI Extract, or
Classification to files or table rows and write results to Unity Catalog.
Each task has exactly one source and one function. These tasks manage their
own execution; do not attach SQL warehouse, cluster, or serverless environment
settings. Verify availability of the task type in the target workspace.

## Inputs and destinations

| Setting | Use |
| --- | --- |
| `volume.volume_path` | Existing Unity Catalog volume directory; Document Parsing only |
| `delta_table.table_name` | Fully qualified input Delta table |
| `delta_table.input_column` | Column containing the document content or text |
| `delta_table.merge_key_columns` | Up to three columns identifying a row across runs |
| `output.catalog`, `output.schema` | Required destination catalog and schema |
| `output.table` | Optional explicit destination table name; otherwise a stable name is generated |

For mutable table inputs, use verified merge keys or Delta row tracking to
identify changes across runs. Without either, a run processes the full source
table. Append-only tables use incremental ingestion. A task's table source
has no row-filter setting: use a deliberately scoped input table for a bounded
test. AI Extract and Classification read table columns; chain Document Parsing
first when starting from binary files in a volume.

## Function configuration

| Function field | Configuration |
| --- | --- |
| `ai_parse_document` | `version: "2.0"`; optional `image_output_path` and `page_range` |
| `ai_extract` | `version: "2.1"`, inline `schema` as a JSON string, and optional `instructions`, `mode: MODE_PRECISION`, `enable_citations`, `enable_confidence_scores` |
| `ai_classify` | `version: "2.1"`, `inline_labels.labels`, and optional `instructions`, `multilabel`, `enable_confidence_scores`, `enable_rationales` |

An extraction schema is a field map, for example
`{"document_id":{"type":"string"}}`. Use the `databricks-ai-functions` skill
for field-map types and direct SQL syntax. Set the task's schema inline rather
than referring to an AI Extract asset ID.

Classification labels are objects with a unique, non-empty `name` and optional
`description`. Use at most ten inline labels, with at least two for single-label
classification. Multilabel classification also accepts one label. The native
task uses inline labels rather than a SQL label table.

## Direct table extraction

This bundle fragment reads an existing text table. Replace the illustrative
source, key, destination, and field map with the workload's confirmed values.

```yaml
resources:
  jobs:
    document_extraction:
      name: document_extraction
      tasks:
        - task_key: extract_fields
          ai_function_task:
            delta_table:
              table_name: main.documents.source_text
              input_column: text
              merge_key_columns: [document_id]
            output:
              catalog: main
              schema: documents_dev
            ai_extract:
              version: "2.1"
              schema: |
                {"document_id":{"type":"string","description":"Identifier printed on the document"}}
              instructions: Leave absent values empty.
```

## Chaining tasks

A downstream task reads the upstream output using
`{{tasks.<task_key>.output.table_name}}`, adds the upstream task to `depends_on`,
and sets `input_column: response` for parsed document content. Use the upstream
identity columns as merge keys; the volume-parsing output uses `id`.

```yaml
tasks:
  - task_key: parse_documents
    ai_function_task:
      volume:
        volume_path: /Volumes/main/documents/source/
      output:
        catalog: main
        schema: documents_dev
      ai_parse_document:
        version: "2.0"
  - task_key: classify_documents
    depends_on:
      - task_key: parse_documents
    ai_function_task:
      delta_table:
        table_name: "{{tasks.parse_documents.output.table_name}}"
        input_column: response
        merge_key_columns: [id]
      output:
        catalog: main
        schema: documents_dev
      ai_classify:
        version: "2.1"
        inline_labels:
          labels:
            - name: contract
              description: An agreement between parties.
            - name: report
              description: A document reporting findings or results.
```

AI Extract can read the parsing output in the same way. Classification writes
labels, so an extraction task needs the corresponding source content. A task
output reference selects a table; it does not join or filter rows. For
class-specific extraction, use a routing pipeline to maintain persistent input
tables with source identity and change data feed enabled. Each extraction
task reads its class's content table and depends on the routing task. Use
`databricks-pipelines` for pipeline configuration and incremental routing.

## Inspect task outputs

The output table contains identity columns and two VARIANT columns:

- `response`: the function's result, including its function-level status.
- `error`: a request-level failure with `type` and `message`.

Inspect raw rows before projecting fields. Both columns are already VARIANT.
For AI Extract `"2.1"`, a top-level field is at
`response:response.<field>.value`. For single-label Classification `"2.1"`, the
label is at `response:response[0].value`. Function-level errors are at
`response:error_message`. Document Parsing instead reports function errors at
`response:error_status`.

```sql
SELECT
  response:response.document_id.value::STRING AS document_id,
  response:error_message::STRING AS function_error,
  error
FROM <resolved_extraction_output_table>;
```

Select request failures with `error IS NOT NULL`. Check extraction or
classification errors with `response:error_message::STRING IS NOT NULL`, and
parsing errors with `response:error_status::STRING IS NOT NULL`. Casting the
status to STRING gives JSON null the SQL NULL semantics needed for that check.
Validate projected values against the raw responses and source documents.
