# AI Search Modes

Databricks AI Search supports three search modes: **ANN** (semantic, default), **hybrid** (semantic + keyword), and **FULL_TEXT** (keyword only, beta). ANN and hybrid work with Delta Sync and Direct Access indexes. FULL_TEXT works on Standard and Storage-Optimized endpoints.

`query_type` is case-insensitive — the backend upper-cases it before matching. This skill
uses `"ann"` (default), `"hybrid"` and `"FULL_TEXT"` to match the docs.

## Semantic Search (ANN)

ANN (Approximate Nearest Neighbor) is the default search mode. It finds documents by vector similarity — matching the *meaning* of your query against stored embeddings.

### When to use

- Conceptual or meaning-based queries ("How do I handle errors in my pipeline?")
- Paraphrased input where exact terms may not appear in the documents
- Multilingual scenarios where query and document languages may differ
- General-purpose RAG retrieval

### Example

```python
from databricks.ai_search.client import AISearchClient

client = AISearchClient()
index = client.get_index(endpoint_name="my-endpoint", index_name="catalog.schema.my_index")

# ANN is the default — no query_type parameter needed
results = index.similarity_search(
    query_text="How do I handle errors in my pipeline?",
    columns=["id", "content"],
    num_results=5
)
```

## Hybrid Search

Hybrid search runs ANN and full-text (keyword) search in parallel, then merges the two result lists with Reciprocal Rank Fusion (RRF). It returns documents that are semantically similar, keyword matches, or both.

### When to use

- Queries containing exact terms that must appear: SKUs, product codes, error codes, acronyms
- Proper nouns — company names, people, specific technologies
- Technical documentation where terminology precision matters
- Mixed-intent queries combining concepts with specific terms

### Example

```python
results = index.similarity_search(
    query_text="SPARK-12345 executor memory error",
    query_type="hybrid",
    columns=["id", "content"],
    num_results=10
)
```

## Decision Guide

| Mode | Best for | Trade-off | Choose when |
|------|----------|-----------|-------------|
| **ANN** (default) | Conceptual queries, paraphrases, meaning-based search | Fastest; may miss exact keyword matches; up to 10,000 results | You want documents *about* a topic regardless of exact wording |
| **hybrid** | Exact terms, codes, proper nouns, mixed-intent queries | About 4x the resources of ANN, so lower throughput; max 200 results | Your queries contain specific identifiers or technical terms that must appear in results |
| **FULL_TEXT** (beta) | Pure keyword search without vector embeddings | No semantic understanding; up to 10,000 results | You need keyword matching only, without vector similarity |

**Start with ANN.** Switch to hybrid if you notice relevant documents being missed because they don't share vocabulary with the query. Load-test with the mode production will use.

## Combining Search Modes with Filters

Both search modes support filters. The filter syntax depends on your endpoint type:

- **Standard endpoints** → `filters` as a dict
- **Storage-Optimized endpoints** → `filters` as a SQL-like string

### Standard endpoint with hybrid search

```python
results = index.similarity_search(
    query_text="SPARK-12345 executor memory error",
    query_type="hybrid",
    columns=["id", "content", "category"],
    num_results=10,
    filters={"category": "troubleshooting", "status": ["open", "in_progress"]}
)
```

### Storage-Optimized endpoint with hybrid search

```python
from databricks.ai_search.client import AISearchClient

client = AISearchClient()
index = client.get_index(
    endpoint_name="my-storage-endpoint",
    index_name="catalog.schema.my_index"
)

results = index.similarity_search(
    query_text="SPARK-12345 executor memory error",
    query_type="hybrid",
    columns=["id", "content", "category"],
    num_results=10,
    filters="category = 'troubleshooting' AND status IN ('open', 'in_progress')"
)
```

For operators and timestamp handling, see the [filtering guide](https://docs.databricks.com/aws/en/ai-search/filtering-guide).

## Using with Pre-Computed Embeddings

If you compute embeddings yourself, use `query_vector` instead of `query_text` for ANN search:

```python
# ANN with pre-computed embedding (default)
results = index.similarity_search(
    query_vector=[0.1, 0.2, 0.3, ...],  # Your embedding vector
    columns=["id", "content"],
    num_results=10
)
```

For **hybrid search with self-managed embeddings** (indexes without an associated model endpoint), you must provide **both** `query_vector` and `query_text`. The vector is used for the ANN component and the text for the keyword component:

```python
# hybrid with self-managed embeddings — requires both vector AND text
results = index.similarity_search(
    query_vector=[0.1, 0.2, 0.3, ...],  # For ANN similarity
    query_text="executor memory error",   # For keyword matching
    query_type="hybrid",
    columns=["id", "content"],
    num_results=10
)
```

**Notes:**
- For **ANN** queries: provide either `query_text` or `query_vector`, not both.
- For **hybrid** queries on **managed embedding indexes**: provide only `query_text` (the system handles both components).
- For **hybrid** queries on **self-managed indexes without a model endpoint**: provide both `query_vector` and `query_text`.
- When using `query_text` alone, the index must have an associated embedding model (managed embeddings or `embedding_model_endpoint_name` on a Direct Access index).

## Parameter Reference

| Parameter | Type | Description |
|-----------|------|-------------|
| `query_text` | `str` | Text query — requires an embedding model on the index |
| `query_vector` | `list[float]` | Pre-computed embedding vector |
| `query_type` | `str` | `"ann"` (default), `"hybrid"`, or `"FULL_TEXT"` (beta) |
| `columns` | `list[str]` | Column names to return in results |
| `num_results` | `int` | Number of results (default: 5) |
| `filters` | `dict` or `str` | Dict for Standard endpoints; SQL-like string for Storage-Optimized |
| `reranker` | `DatabricksReranker` | Optional reranker for improved quality (~10% gain, ~1.5s overhead) |
| `debug_level` | `int` | Set to `1` to return per-component latency in the response |
