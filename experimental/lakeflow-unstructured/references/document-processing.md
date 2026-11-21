# Document processing

Select only the stages the user's result needs. A simple workflow is:

```text
Existing volume → Document Parsing → AI Extract → Output table
```

The [starting bundle](../assets/workflow/databricks.yml) implements that chain.
For native task fields, result envelopes, and output references, use the
`databricks-jobs` skill's `references/ai-function-tasks.md`.

## Choose the input

| Existing input | First processing step |
| --- | --- |
| Binary documents in a Unity Catalog volume | Document Parsing with `volume.volume_path` |
| A Delta table containing document content | Document Parsing with `delta_table.table_name` and `input_column`; inspect the column type first |
| A Delta table containing text or parsed document content | AI Extract directly; parsing is unnecessary |

Reuse existing source access. Do not add Auto Loader, a connector, or a bronze
table for files that are already in a volume. For table input, confirm the
fully qualified name, content column, and stable row identity. Distinguish
reference material from the documents the user wants processed.

When adapting the starting bundle to a table, replace the parsing task's
`volume` source with `delta_table`, or remove parsing and point extraction at
the existing text/parsed-content table. Set merge keys from verified input
columns. Replace the input variable as well; do not leave two source settings
on one task. The Jobs task reference includes a direct table example.

Define the processing unit: a file, a page range, or a logical document. If one
file holds several documents, agree on splitting before treating its contents
as one record. Preserve source identity through downstream outputs.

## Define extraction

Reuse an existing extraction schema when supplied. Otherwise inspect a small
sample and propose the fields the workload needs, with types and descriptions.
Confirm what to do with missing or conflicting values and which checks matter
to the business. Keep unsupported values empty rather than guessing them.

Use the AI Extract field-map format, with the field name at the root:

```json
{
  "document_id": {"type": "string", "description": "Identifier printed on the document"},
  "amount": {"type": "number", "description": "The stated total amount; empty when absent"}
}
```

Nested objects use `{"type": "object", "properties": {...}}` inside a named
field, and arrays use `{"type": "array", "items": {...}}`. The root remains a
field map, rather than a JSON Schema root with `type` and `properties`.
The `ai_extract.schema` task setting contains this map as a **JSON string**.
Use a YAML block scalar or a string variable to preserve that distinction.

Record the confirmed field map and instructions in SPEC.md. Use the
`databricks-ai-functions` skill for additional schema types and direct SQL
previews. SQL previews and native Job tasks have different result wrappers;
inspect the configured task's output before writing downstream projections.

## Build the task chain

Use a separate native AI Function task for each parsing, classification, and
extraction operation. Use version `"2.0"` for Document Parsing and `"2.1"` for
AI Extract and Classification. Connect dependent tasks with `depends_on` and
`{{tasks.<task_key>.output.table_name}}`; for parsed input, set the input column
to `response` and use the verified identity columns.

Outputs are Delta tables in the selected catalog/schema. Keep development
outputs separate from existing production results. Resolve generated table
names from task metadata or the task's run details, then record the actual
names in the workflow files. Business-facing projections or validation SQL can
live in src/ when required; retain the underlying responses and errors.

## Optional classification

Add Classification when labels affect processing or are part of the requested
output. Define meaningful labels and descriptions with the user. Ask how to
handle documents that fit no label.

Classification produces labels. Extraction still needs the corresponding
document content. For one extraction schema, extraction can continue reading
the parsing output. For class-specific schemas, join labels to source content
using stable document identity and maintain a persistent input table per class;
each extraction task reads its class's table and depends on the routing task.
Use `databricks-pipelines` for the routing pipeline and verify additions,
updates, class changes, and removals. Record the routes in the manifest using
the supplied schema. Add this branch only when the workload requires it.

## Functional verification and UI handoff

Before running native tasks, establish the number of files or rows in their
configured source. A SQL `LIMIT` used in a preview does not limit a Job task's
input. Use an agreed sample source for a bounded test, or confirm the full
source size with the user before running it.

Inspect task-level failures, function errors, row counts, raw responses, and
projected values. Confirm missing fields stay empty, required source identity
is preserved, and a repeat run behaves as intended. Record evidence in AGENTS.md.

For extraction-quality evaluation, iterative improvements, and visual
debugging, open the workflow in Document Intelligence and continue with Genie
Code. Carry over the workflow's inputs, confirmed schema, sample locations,
and outstanding quality questions. Functional execution checks do not replace
quality evaluation.
