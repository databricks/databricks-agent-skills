# `ai_query` — Full Reference

Calls a **Databricks-hosted model service** (`system.ai.<model>`) or your **own custom, external, or provisioned-throughput Model Serving endpoint**. **Prefer task-specific AI Functions** when applicable. Use `ai_query` when no task-specific function fits, the user needs a specific endpoint, or task-specific output is insufficient and a stronger model is needed. It supports multimodal image input, cross-document reasoning, sampling-parameter control, and custom models. See the [Overview table](../SKILL.md#overview) for the signature.

## Parameters

| Parameter | Type | Runtime | Description |
|---|---|---|---|
| `endpoint` | STRING literal | — | Exact hosted model-service name from the AI Gateway listing, or a Model Serving endpoint name for custom, external, or provisioned-throughput models. See discovery below. |
| `request` | STRING or STRUCT | — | Prompt string for chat models; STRUCT for custom ML endpoints |
| `returnType` | DDL schema (optional) | 15.2+ | Structures the parsed response like `from_json` |
| `failOnError` | BOOLEAN (optional, default `true`) | 15.3+ | `false` → returns `STRUCT{response, errorMessage}` instead of raising. **Always set in batch.** |
| `modelParameters` | STRUCT (optional) | 15.3+ | Sampling params: `temperature`, `max_tokens`, `top_p` |
| `responseFormat` | JSON string (optional) | 15.4+ | Force structured output: `'{"type":"json_object"}'` |
| `files` | binary column (optional) | — | Pass JPEG/PNG bytes directly (multimodal) — no upload step |

## Model Discovery

Use the customer's specified model service or Model Serving endpoint when it supports the request. Otherwise, select an available model appropriate for the task and required output quality.

On public clouds, discover available hosted model services through AI Gateway and use the exact `system.ai.<model>` name returned:

```bash
databricks ai-gateway list-model-services --parent schemas/system.ai --view BASIC
```

Without the CLI command, use the REST API:

```text
GET /api/2.1/unity-catalog/model-services?parent=schemas/system.ai&view=BASIC
```

The response's `model_services[].name` values have the form `model-services/system.ai.<model>`. Pass only the three-part name, such as `system.ai.meta-llama-3-3-70b-instruct`, to `ai_query`. Listing a service does not grant permission to call it: the caller needs `EXECUTE`. If discovery is unavailable, ask which model service to use rather than guessing names or probing inference calls.

`serving-endpoints list` lists classic Model Serving endpoints, not hosted model services. Use it for custom, external, and provisioned-throughput endpoints, which keep their endpoint names and require `CAN QUERY`. Custom Unity Gateway model services are not yet supported by `ai_query`.

**Cloud exceptions:** `system.ai` is not available on Azure Government, Azure China, or AWS GovCloud/DoD. There, discover legacy hosted `databricks-*` endpoints with `databricks serving-endpoints list` or `GET /api/2.0/serving-endpoints`.

The SQL examples below use illustrative hosted model names. Confirm the selected model appears in the target workspace's listing and supports the requested structured output or image input. Check the [supported models](https://docs.databricks.com/aws/en/large-language-models/ai-query#supported-models) for batch optimization and multimodal support.

## Unity Gateway migration (403 PERMISSION_DENIED)

If a legacy hosted-model call fails with a 403 asking you to use Unity Gateway or Unity Catalog model services, discover its replacement using the AI Gateway listing above. A `databricks-<model>` endpoint does not always have a matching `system.ai.<model>` service.

- **Symptom:** HTTP **403 PERMISSION_DENIED** with a message like `"'databricks-claude-sonnet-4' is no longer available. Use Unity Catalog model services."` (or the variant `"... Please use Unity Gateway."`). With `failOnError => false`, that text lands in the returned STRUCT's `errorMessage` field instead of raising.
- **Fix:** use the exact listed model-service name and keep the other arguments unchanged when the replacement supports them. For a workspace listing `system.ai.meta-llama-3-3-70b-instruct`:

```sql
-- Before (fails with 403 once legacy endpoints are disabled):
SELECT ai_query('databricks-meta-llama-3-3-70b-instruct', 'Summarize: ' || text) FROM articles;
-- After:
SELECT ai_query('system.ai.meta-llama-3-3-70b-instruct', 'Summarize: ' || text) FROM articles;
```

This applies to built-in foundation models only; custom (non-foundation-model) endpoints are not affected by this migration and keep their existing name.

## Patterns

```sql
-- Structured JSON output + batch-safe error handling (the two flags you almost always want)
SELECT id, ai_response.response, ai_response.errorMessage
FROM (
  SELECT id, ai_query(
      'system.ai.meta-llama-3-3-70b-instruct',
      CONCAT('Extract invoice fields as JSON {numero, total, itens:[{codigo, qtde}]}: ', text_blocks),
      responseFormat => '{"type":"json_object"}',
      failOnError    => false,
      modelParameters => named_struct('temperature', CAST(0.0 AS DOUBLE), 'max_tokens', 500)
  ) AS ai_response
  FROM parsed_documents
);
-- Route rows WHERE ai_response.errorMessage IS NOT NULL to a sidecar table.
```

With `failOnError => false`, the STRUCT fields are `.response` and `.errorMessage`. The error field is SQL NULL on success. This handles row-level model endpoint errors; other errors, such as query validation failures, can still fail the whole query.

Parse the JSON response with `from_json`, or for multimodal pass the binary column via `files =>`:

```sql
-- Multimodal: describe images, no upload step
SELECT path, ai_query('system.ai.llama-4-maverick',
    'Describe this image.', files => content) AS description
FROM read_files('/Volumes/catalog/schema/images/', format => 'binaryFile');
```

`read_files` belongs in the `FROM` clause. `format => 'binaryFile'` exposes the `content BINARY` column passed to `files`; do not pass the table-valued function itself as an argument.

```sql
-- Reusable SQL UDF wrapping a fixed prompt + endpoint
CREATE FUNCTION catalog.schema.extract_invoice(text STRING) RETURNS STRING
RETURN ai_query('system.ai.meta-llama-3-3-70b-instruct',
    CONCAT('Extract invoice JSON from: ', text),
    responseFormat => '{"type":"json_object"}');
```

In PySpark, call inside `expr("...")` (`spark.table("t").withColumn("out", expr("ai_query(...)"))`). For SDP batch pipelines, write results and errors to two `@dp.table` stages (split on `ai_response.errorMessage IS NOT NULL`).
