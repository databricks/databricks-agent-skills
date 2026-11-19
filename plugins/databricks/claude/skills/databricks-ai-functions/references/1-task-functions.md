# Task-Specific AI Functions — Full Reference

Deep reference for each task-specific function: full options, schemas, and non-trivial examples. For the at-a-glance signature/input/output/prereqs index, see the function table in [SKILL.md](../SKILL.md#overview). These functions need no model endpoint selection — they call pre-configured Foundation Model APIs optimized for each task.

---

## `ai_analyze_sentiment`

Returns one of: `positive`, `negative`, `neutral`, `mixed`, or `NULL`.

```sql
SELECT ai_analyze_sentiment(review_text) AS sentiment
FROM customer_reviews;
```

```python
from pyspark.sql.functions import expr
df = spark.table("customer_reviews")
df.withColumn("sentiment", expr("ai_analyze_sentiment(review_text)")).display()
```

---

## `ai_classify`

**Syntax:** `ai_classify(content, labels [, options])`
- `content`: VARIANT | STRING — raw text, or VARIANT from `ai_parse_document` / `ai_extract`
- `labels`: STRING — JSON labels definition:
  - Simple array: `'["urgent", "not_urgent", "spam"]'`
  - With descriptions: `'{"billing_error": "Payment, invoice, or refund issues", "product_defect": "Any malfunction or bug"}'` (descriptions up to 1000 chars each)
  - 2–500 labels, each 1–100 characters
- `options`: optional MAP\<STRING, STRING\>:
  - `version`: `"2.1"` (recommended), `"2.0"`, or `"1.0"` for backward compatibility. Pin the version in new code; the default depends on input types and can fall back to v1.
  - `instructions`: task context to improve accuracy (max 20,000 chars)
  - `multilabel`: `"true"` to return multiple matching labels (default `"false"`)
  - `enableConfidenceScores`: `"true"` to include a per-label `confidence_score` (0–1); requires v2.1
  - `enableRationales`: `"true"` to include a short, input-grounded `rationale`; requires v2.1

Version 2.1 returns VARIANT `{"response": [{"value": "label"}], "metadata": {"version": "2.1"}, "error_message": null}`. Every returned label has a `value` field, even when confidence scores and rationales are disabled. Those optional fields appear only when enabled. Read a single-label result with `result:response[0].value::STRING`; explode the response array to read multiple labels. Returns SQL `NULL` if content is SQL `NULL`. On success, `error_message` is a JSON null: check it with `is_variant_null(result:error_message)`.

**Compatibility:** v2.0 returns `response` as an array of strings. Existing v2.0 queries remain supported; update their projections to read `value` when upgrading to v2.1. The legacy v1 interface accepts `ARRAY<STRING>` labels (2–20) and returns a `STRING`.

**Constraints:** total input + labels context capped at **128,000 tokens**; not available on Databricks SQL Classic.

```sql
-- simple labels
SELECT ticket_text,
       ai_classify(ticket_text, '["urgent", "not urgent", "spam"]', MAP('version', '2.1')) AS priority
FROM support_tickets;
-- {"response": [{"value": "urgent"}], "metadata": {"version": "2.1"}, "error_message": null}

-- labels with descriptions
SELECT ticket_text,
       ai_classify(
           ticket_text,
           '{"billing_error": "Payment, invoice, or refund issues",
             "product_defect": "Any malfunction, bug, or breakage",
             "account_issue": "Login failures, password resets"}',
           MAP('version', '2.1', 'instructions', 'Customer support tickets for a SaaS product')
       ) AS category
FROM support_tickets;
```

```python
from pyspark.sql.functions import expr
df = spark.table("support_tickets")
df.withColumn(
    "priority",
    expr("ai_classify(ticket_text, '[\"urgent\", \"not urgent\", \"spam\"]', MAP('version', '2.1'))")
).display()
```

**Tips:**
- Use label descriptions for ambiguous categories — they significantly improve accuracy
- `multilabel: "true"` enables multi-label classification without running multiple calls
- Up to 500 labels supported
- For PDF, image, or Office documents, pass the `ai_parse_document` VARIANT directly to preserve document structure. For plain text or Markdown files, use `read_files(..., format => 'text', wholetext => true)` and classify the `value` column; otherwise each line becomes a separate input.

---

## `ai_decide`

Answers several questions over one `state` in a **single** inference — a probability (`noul`), a label (`choice`), or a scaled score (`score`) per question, with confidence/probabilities. Combines `ai_classify` + boolean judgment + rubric scoring; no endpoint selection. Prefer one `ai_decide` over chaining separate functions.

**Requires:** Databricks SQL (not SQL Classic) or DBR **15.4 LTS+** (18.2+ recommended). **Beta** — admin-enabled via **Previews**; region-restricted.

**Syntax:** `ai_decide(state, questions [, options])`
- `state`: STRING | VARIANT — text/JSON/VARIANT (e.g. from `ai_parse_document`) to reason over.
- `questions`: STRING — **constant** JSON mapping question IDs → definitions `{type, instructions, criteria}` (`instructions`: string/object/array). Not row-varying.
- `options`: MAP — `version`: `"1.0"` (default).

Returns VARIANT `{response:{answers:{<id>:<answer>}}, metadata:{version}, error_message}`; `response` null + `error_message` set on failure.

| `type` | `criteria` | Answer fields |
|---|---|---|
| `noul` (likelihood true) | optional `{true, false}` descriptions | `{type, probability}` — 0–1 |
| `choice` (pick a label) | **required** 1–255 `label → description` | `{type, choice, probabilities, confidence}` |
| `score` (rubric) | **required** array of 2–10 ordered descriptions | `{type, score, legend, probabilities, confidence}` — `score` = probability-weighted mean of indices, `0`→(n−1), fractional |

```sql
SELECT ai_decide(description, '{
  "category":      {"type":"choice", "instructions":"Best product category?",
                    "criteria":{"outerwear":"Jackets, coats","footwear":"Shoes, boots","accessories":"Bags, hats"}},
  "is_waterproof": {"type":"noul",   "instructions":"Is it waterproof?"},
  "sustainability":{"type":"score",  "instructions":"Rate material sustainability.",
                    "criteria":["Not","Somewhat","Highly"]}
}') AS decision
FROM products;
-- read: decision:response:answers:category:choice::STRING,
--       decision:response:answers:is_waterproof:probability::DOUBLE,
--       decision:response:answers:sustainability:score::DOUBLE
```

PySpark — pass the JSON as a literal (an apostrophe in a question would break SQL interpolation): `df.withColumn("decision", call_function("ai_decide", col("description"), lit(questions_json)))`.

---

## `ai_extract`

**Syntax:** `ai_extract(content, schema [, options])`
- `content`: VARIANT | STRING — raw text, or VARIANT from `ai_parse_document`
- `schema`: STRING literal — the JSON schema format supported by `ai_extract`:
  - Simple (field names only): `'["invoice_id", "vendor_name", "total_amount"]'`
  - Advanced (with types and descriptions):
    ```json
    {
      "invoice_id": {"type": "string"},
      "total_amount": {"type": "number"},
      "currency": {"type": "enum", "labels": ["USD", "EUR", "GBP"]},
      "line_items": {"type": "array", "items": {"type": "object", "properties": {...}}}
    }
    ```
  - Supported types: `string`, `integer`, `number`, `boolean`, `enum`, `object` (with `properties`), `array` (with `items`)
  - Use these lowercase types and supported keywords (`type`, `description`, `properties`, `items`, `labels`). Standard JSON Schema keywords such as `required`, `anyOf`, and `additionalProperties`, and SQL types such as `DECIMAL(12,2)` or `DATE`, are unsupported. Use `number` and cast downstream for decimals; use `string` with a description for dates. Enum fields use `"type": "enum"` with `"labels": [...]`.
  - Max 256 fields, field names up to 150 chars, 12 nesting levels, 500 enum values, 128,000 token total context
- `options`: optional MAP\<STRING, STRING\>:
  - `version`: `"2.1"` (recommended) / `"2.0"` / `"1.0"`
  - `instructions`: task context to improve extraction quality (max 20,000 chars)
  - `mode`: `"precision"` for extraction involving long documents, many output items, or complex schemas
  - `enableCitations`: `"true"` to attach `citation_ids` to each extracted field; requires v2.1
  - `enableConfidenceScores`: `"true"` to attach a per-field `confidence_score` (0–1); requires v2.1

Version 2.1 returns VARIANT `{"response": {"field": {"value": ...}}, "metadata": {...}, "error_message": null}`. Nested objects and arrays keep their structure, and every scalar leaf is an object with a `value` field, even when citations and confidence scores are disabled. `citation_ids` and `confidence_score` appear only when enabled. A field that cannot be extracted has a null `value`. Returns SQL `NULL` if content is SQL `NULL`. On success, `error_message` is a JSON null: check it with `is_variant_null(result:error_message)`.

**Compatibility:** v2.0 returns scalar values directly, such as `result:response:total_amount::DECIMAL(12,2)`. Existing v2.0 queries remain supported. When upgrading to v2.1, update the projection to `result:response:total_amount:value::DECIMAL(12,2)`. The legacy v1 interface accepts `ARRAY<STRING>` entity names and returns a `STRUCT` of string fields.

```sql
-- simple schema
SELECT ai_extract(
    'Invoice #12345 from Acme Corp for $1,250.00',
    '["invoice_id", "vendor_name", "total_amount"]',
    MAP('version', '2.1')
) AS extracted;
-- {"response": {"invoice_id": {"value": "12345"}, "vendor_name": {"value": "Acme Corp"}, ...}, "error_message": null}

-- composable with ai_parse_document
WITH parsed AS (
  SELECT ai_parse_document(content, MAP('version', '2.0')) AS parsed
  FROM READ_FILES('/Volumes/finance/invoices/', format => 'binaryFile')
)
SELECT ai_extract(
    parsed,
    '["invoice_id", "vendor_name", "total_amount"]',
    MAP('version', '2.1', 'instructions', 'These are vendor invoices.')
) AS invoice_data
FROM parsed;
```

```python
from pyspark.sql.functions import expr
df = spark.table("messages")
df = df.withColumn(
    "entities",
    expr("ai_extract(message, '[\"person\", \"location\", \"date\"]', MAP('version', '2.1'))")
)
df.display()
```

### Version 2.1: citations and confidence scores

Pass `MAP('version', '2.1', ...)` with `enableCitations` and/or `enableConfidenceScores` to attach provenance and reliability metadata to each extracted field. Useful for review queues and downstream filtering by confidence. For more demanding extraction, add `'mode', 'precision'` to the same options map.

```sql
SELECT ai_extract(
    document_text,
    '["invoice_id", "vendor_name", "total_amount"]',
    MAP(
        'version', '2.1',
        'enableCitations', 'true',
        'enableConfidenceScores', 'true'
    )
) AS extracted
FROM parsed_documents;

-- Each scalar field is now an object: {value, citation_ids, confidence_score}
-- Access:
SELECT
    extracted:response:invoice_id:value::STRING       AS invoice_id,
    extracted:response:invoice_id:confidence_score::DOUBLE AS invoice_id_conf,
    extracted:response:total_amount:value::DOUBLE     AS total_amount,
    extracted:metadata                                AS metadata
FROM extracted_invoices;
```

---

## `ai_fix_grammar`

**Syntax:** `ai_fix_grammar(content)` — Returns corrected STRING.

Optimized for English. Useful for cleaning user-generated content before downstream processing.

```sql
SELECT ai_fix_grammar(user_comment) AS corrected FROM user_feedback;
```

```python
from pyspark.sql.functions import expr
df = spark.table("user_feedback")
df.withColumn("corrected", expr("ai_fix_grammar(user_comment)")).display()
```

---

## `ai_gen`

**Syntax:** `ai_gen(prompt)` — Returns a generated STRING.

Use for free-form text generation where the output format doesn't need to be structured. For structured JSON output, use `ai_query` with `responseFormat`.

```sql
SELECT product_name,
       ai_gen(CONCAT('Write a one-sentence marketing tagline for: ', product_name)) AS tagline
FROM products;
```

```python
from pyspark.sql.functions import expr
df = spark.table("products")
df.withColumn(
    "tagline",
    expr("ai_gen(concat('Write a one-sentence marketing tagline for: ', product_name))")
).display()
```

---

## `ai_mask`

**Syntax:** `ai_mask(content, labels)`
- `content`: STRING — text with sensitive data
- `labels`: ARRAY\<STRING\> — entity types to redact

Returns text with identified entities replaced by `[MASKED]`.

Common label values: `'person'`, `'email'`, `'phone'`, `'address'`, `'ssn'`, `'credit_card'`

```sql
SELECT ai_mask(
    message_body,
    ARRAY('person', 'email', 'phone', 'address')
) AS message_safe
FROM customer_messages;
```

```python
from pyspark.sql.functions import expr
df = spark.table("customer_messages")
df.withColumn(
    "message_safe",
    expr("ai_mask(message_body, array('person', 'email', 'phone'))")
).write.format("delta").mode("append").saveAsTable("catalog.schema.messages_safe")
```

---

## `ai_similarity`

**Syntax:** `ai_similarity(expr1, expr2)` — Returns a FLOAT between 0.0 and 1.0.

Use for fuzzy deduplication, search result ranking, or item matching across datasets.

```sql
-- Deduplicate company names (similarity > 0.85 = likely duplicate)
SELECT a.id, b.id, a.name, b.name,
       ai_similarity(a.name, b.name) AS score
FROM companies a
JOIN companies b ON a.id < b.id
WHERE ai_similarity(a.name, b.name) > 0.85
ORDER BY score DESC;
```

```python
from pyspark.sql.functions import expr
df = spark.table("product_search")
df.withColumn(
    "match_score",
    expr("ai_similarity(search_query, product_title)")
).orderBy("match_score", ascending=False).display()
```

---

## `ai_summarize`

**Syntax:** `ai_summarize(content [, max_words])`
- `content`: STRING — text to summarize
- `max_words`: INTEGER (optional) — word limit; default 50; use `0` for uncapped

```sql
-- Default (50 words)
SELECT ai_summarize(article_body) AS summary FROM news_articles;

-- Custom word limit
SELECT ai_summarize(article_body, 20)  AS brief   FROM news_articles;
SELECT ai_summarize(article_body, 0)   AS full    FROM news_articles;
```

```python
from pyspark.sql.functions import expr
df = spark.table("news_articles")
df.withColumn("summary", expr("ai_summarize(article_body, 30)")).display()
```

---

## `ai_translate`

**Syntax:** `ai_translate(content, to_lang)`
- `content`: STRING — source text
- `to_lang`: STRING — target language. Accepts an IETF BCP 47 / ISO 639-1 code (`'es'`), the full language name (`'Spanish'`), or a descriptive phrase — the examples below use codes.

**Supported languages (8):** English (`en`), French (`fr`), German (`de`), Hindi (`hi`), Italian (`it`), Portuguese (`pt`), Spanish (`es`), Thai (`th`).

For unsupported languages, use `ai_query` with a multilingual model endpoint.

```sql
-- Single language
SELECT ai_translate(product_description, 'es') AS description_es FROM products;

-- Multi-language fanout
SELECT
    description,
    ai_translate(description, 'fr') AS description_fr,
    ai_translate(description, 'de') AS description_de
FROM products;
```

```python
from pyspark.sql.functions import expr
df = spark.table("products")
df.withColumn(
    "description_es",
    expr("ai_translate(product_description, 'es')")
).display()
```

---

## `ai_parse_document`

**Requires:** DBR 17.3+ (serverless env v3+ for VARIANT). Region-restricted — check feature availability.

**Syntax:** `ai_parse_document(content [, options])`
- `content`: BINARY — document content loaded from `read_files()` or `spark.read.format("binaryFile")`
- `options`: MAP\<STRING, STRING\> (optional) — parsing configuration

**Supported formats:** PDF, JPG/JPEG, PNG, TIFF/TIF, DOC/DOCX, PPT/PPTX

Returns a VARIANT with pages, elements (text, tables, figures, titles, captions, section headers, page headers/footers, page numbers, footnotes), bounding boxes, confidence scores, and error metadata.

**Options:**

| Key | Values | Description |
|-----|--------|-------------|
| `version` | `'2.0'` | Output schema version |
| `imageOutputPath` | Volume path | Save rendered page images to a UC Volume |
| `descriptionElementTypes` | `''`, `'figure'`, `'*'` | AI-generated descriptions (default: `'*'` for all). Set to `''` to disable and reduce cost. |
| `pageRange` | e.g. `'1,3,5-10'` | Restrict parsing to a subset of pages (1-indexed) |

**Output schema (v2.0):**

```
document
├── pages[]          -- id, image_uri
└── elements[]       -- extracted content
    ├── id           -- per-element id
    ├── type         -- text | table | figure | title | caption | section_header
    │                --   | page_header | page_footer | page_number | footnote
    ├── content      -- extracted text
    ├── confidence   -- DOUBLE 0–1
    ├── bbox         -- [{coord:[...], page_id}]
    └── description  -- AI-generated figure description (when enabled)
metadata             -- id, version, file_metadata
error_status[]       -- {error_message, page_id} per page (if any)
```

**Limits:** max 500 pages per document, max 100 MB file size.

```sql
-- Parse and retain the structured result for extraction or classification
SELECT
    path,
    parsed AS parsed_content,
    parsed:error_status AS parse_error
FROM (
    SELECT path, ai_parse_document(content, MAP('version', '2.0')) AS parsed
    FROM read_files('/Volumes/catalog/schema/landing/docs/', format => 'binaryFile')
)
WHERE is_variant_null(parsed:error_status);

-- Parse with options (image output + descriptions)
SELECT ai_parse_document(
    content,
    map(
        'version', '2.0',
        'imageOutputPath', '/Volumes/catalog/schema/volume/images/',
        'descriptionElementTypes', '*'
    )
) AS parsed
FROM read_files('/Volumes/catalog/schema/volume/invoices/', format => 'binaryFile');

-- Parse only specific pages (cheaper for large documents)
SELECT ai_parse_document(
    content,
    map('version', '2.0', 'pageRange', '1,3,5-10')
) AS parsed
FROM read_files('/Volumes/catalog/schema/volume/contracts/', format => 'binaryFile');
```

```python
from pyspark.sql.functions import expr

df = (
    spark.read.format("binaryFile")
    .load("/Volumes/catalog/schema/landing/docs/")
    .withColumn("parsed", expr("ai_parse_document(content, MAP('version', '2.0'))"))
    .selectExpr(
        "path",
        "parsed AS parsed_content",
        "parsed:error_status AS parse_error",
    )
    .filter("is_variant_null(parse_error)")
)

# Preserve document structure when chaining extraction and classification
df = (
    df.withColumn("entities", expr("ai_extract(parsed_content, '[\"date\",\"amount\",\"vendor\"]', map('version','2.1'))"))
      .withColumn("category", expr("ai_classify(parsed_content, '[\"invoice\",\"contract\",\"report\"]', map('version','2.1'))"))
)
df.display()
```

**Limitations:**
- Max 500 pages per document, max 100 MB file size
- Processing is slow for dense or low-resolution documents
- Suboptimal for non-Latin alphabets (e.g., Japanese, Korean in images) and digitally signed PDFs
- Custom models not supported — always uses the built-in parsing model

On success, `error_status` is a JSON null inside the VARIANT. Use `is_variant_null(parsed:error_status)` to select successful parses; SQL `IS NULL` does not recognize JSON null. Pass the complete parsed VARIANT into `ai_extract` or `ai_classify` to preserve layout and provenance. Plain-text and Markdown files can be read with `format => 'text', wholetext => true` and processed directly, without parsing.

---

## `ai_prep_search`

**Requires:** DBR **18.2+** (serverless env v3+ for VARIANT support).

Takes the VARIANT output of `ai_parse_document`, or a plain-text or Markdown STRING, and returns RAG-ready chunks. The function performs:
1. **Semantic chunking** — splits document content into retrieval-sized chunks at natural boundaries (paragraphs, sections, tables).
2. **Context enrichment** — adds document title, section headers, page numbers, and captions to each chunk's embedding text so Vector Search can match on context, not just chunk content.

Use this instead of hand-rolled `variant_get` + `explode` + `md5` chunking when feeding `ai_parse_document` output into Databricks Vector Search.

**Syntax:** `ai_prep_search(parsed [, options])`
- `parsed`: VARIANT output from `ai_parse_document`, or a STRING containing plain text or Markdown
- `options`: optional MAP\<STRING, STRING\>:
  - `version`: output schema version (major.minor; minor upgrades are backward-compatible)
  - `schema`: JSON string in the same schema format as `ai_extract`, defining document-level metadata fields to extract. Each chunk exposes the typed values in `metadata`, and the fields also enrich `chunk_to_embed`.

**Returns:** VARIANT with chunks ready for Vector Search. Chunks live under the top-level `document` key — access them via `$.document.contents`, NOT `$.chunks`:

```
document
├── contents[]
│   ├── chunk_id            -- unique id (document_id + position) — use as PK
│   ├── chunk_position      -- 0-based position of the chunk in the document
│   ├── chunk_to_retrieve   -- raw chunk text (return this to the LLM)
│   ├── chunk_to_embed      -- context-enriched text (use this as the embedding source)
│   ├── metadata            -- typed fields requested by the schema option
│   └── pages[]             -- page_id + image_uri for this chunk
├── pages[]                 -- page index + image_uri (when imageOutputPath was set on ai_parse_document)
└── source_uri              -- input document path
error_status                -- per-page error info, if any
```

**End-to-end SQL — parse, prep, persist for Vector Search:**

```sql
CREATE OR REPLACE TABLE catalog.schema.parsed_chunks AS
WITH parsed AS (
  SELECT
    path AS source_path,
    ai_parse_document(content, MAP('version', '2.0')) AS parsed
  FROM read_files('/Volumes/catalog/schema/docs/', format => 'binaryFile')
),
prepped AS (
  SELECT
    source_path,
    ai_prep_search(parsed) AS prep
  FROM parsed
),
chunks AS (
  SELECT
    source_path,
    explode(variant_get(prep, '$.document.contents', 'ARRAY<VARIANT>')) AS chunk
  FROM prepped
)
SELECT
  variant_get(chunk, '$.chunk_id',          'STRING') AS chunk_id,
  variant_get(chunk, '$.chunk_position',    'INT')    AS chunk_position,
  variant_get(chunk, '$.chunk_to_retrieve', 'STRING') AS chunk_to_retrieve,
  variant_get(chunk, '$.chunk_to_embed',    'STRING') AS chunk_to_embed,
  source_path,
  current_timestamp() AS prepped_at
FROM chunks;

-- Enable CDF so Vector Search Delta Sync picks up incremental changes
ALTER TABLE catalog.schema.parsed_chunks
SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
```

**PySpark equivalent:**

```python
from pyspark.sql.functions import expr, current_timestamp

chunks_df = (
    spark.read.format("binaryFile")
    .load("/Volumes/catalog/schema/docs/")
    .withColumn("parsed", expr("ai_parse_document(content, MAP('version', '2.0'))"))
    .withColumn("prep",   expr("ai_prep_search(parsed)"))
    .withColumn("chunk",  expr("explode(variant_get(prep, '$.document.contents', 'ARRAY<VARIANT>'))"))
    .selectExpr(
        "variant_get(chunk, '$.chunk_id',          'STRING') AS chunk_id",
        "variant_get(chunk, '$.chunk_position',    'INT')    AS chunk_position",
        "variant_get(chunk, '$.chunk_to_retrieve', 'STRING') AS chunk_to_retrieve",
        "variant_get(chunk, '$.chunk_to_embed',    'STRING') AS chunk_to_embed",
        "path AS source_path",
    )
    .withColumn("prepped_at", current_timestamp())
)

chunks_df.write.format("delta").mode("overwrite").saveAsTable("catalog.schema.parsed_chunks")
```

**Vector Search integration:** Point a Delta Sync index at this table with `chunk_to_embed` as the embedding source column and `chunk_id` as the primary key. The `chunk_to_retrieve` column is what you return to the LLM at query time.

**Plain-text or Markdown input with metadata extraction:**

```sql
SELECT _metadata.file_path AS path,
       ai_prep_search(value, MAP('schema', '["document_type", "vendor_name"]')) AS prep
FROM read_files('/Volumes/catalog/schema/notes/', format => 'text', wholetext => true);
```

`wholetext => true` keeps each file in one row. The `schema` option controls extracted metadata; it does not change the fixed chunk output structure.

**Tips:**
- Pass `imageOutputPath` on the upstream `ai_parse_document` call if you want page image URIs available in the prep output for multimodal retrieval.
- Schema is versioned major.minor; minor upgrades are backward-compatible — pin `version` only if you need to lock schema across deployments.
- On DBR < 18.2, fall back to manual chunking via `variant_get` + `explode` on `ai_parse_document` output.
