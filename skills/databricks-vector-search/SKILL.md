---
name: databricks-vector-search
description: "Databricks AI Search (formerly Vector Search) endpoints and indexes for RAG and semantic search; covers index types, search modes, filtering, end-to-end RAG patterns"
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Databricks AI Search (formerly Vector Search)

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Patterns for creating, managing, and querying AI Search indexes for RAG and semantic search applications.

## When to Use

Use this skill when:
- Building RAG (Retrieval-Augmented Generation) applications
- Implementing semantic search or similarity matching
- Creating vector indexes from Delta tables
- Choosing between storage-optimized and standard endpoints
- Querying vector indexes with filters

## Overview

Databricks AI Search provides managed vector similarity search with automatic embedding generation and Delta Lake integration.

| Component | Description |
|-----------|-------------|
| **Endpoint** | Compute resource hosting indexes (Standard or Storage-Optimized) |
| **Index** | Vector data structure for similarity search |
| **Delta Sync** | Auto-syncs with source Delta table |
| **Direct Access** | Manual CRUD operations on vectors |

## Endpoint Types

| Type | Latency | Capacity | Cost | Best For |
|------|---------|----------|------|----------|
| **Standard** | 20-50ms | 320M vectors (768 dim) | Higher | Real-time, low-latency |
| **Storage-Optimized** | 300-500ms | 1B+ vectors (768 dim) | 7x lower | Large-scale, cost-sensitive |

## Index Types

| Type | Embeddings | Sync | Use Case |
|------|------------|------|----------|
| **Delta Sync (managed)** | Databricks computes | Auto from Delta | Easiest setup |
| **Delta Sync (self-managed)** | You provide | Auto from Delta | Custom embeddings |
| **Direct Access** | You provide | Manual CRUD | Real-time updates |

## Installation

```bash
%pip install databricks-ai-search
```

## Quick Start

### Create Endpoint

```python
from databricks.ai_search.client import AISearchClient

client = AISearchClient()

client.create_endpoint(
    name="my-vs-endpoint",
    endpoint_type="STANDARD"  # or "STORAGE_OPTIMIZED"
)
# Note: Endpoint creation is asynchronous; check status with get_endpoint()
```

### Create Delta Sync Index (Managed Embeddings)

```python
# Source table must have: primary key column + text column
index = client.create_delta_sync_index(
    endpoint_name="my-vs-endpoint",
    source_table_name="catalog.schema.documents",
    index_name="catalog.schema.my_index",
    pipeline_type="TRIGGERED",  # or "CONTINUOUS"
    primary_key="id",
    embedding_source_column="content",
    embedding_model_endpoint_name="databricks-gte-large-en"
)
```

### Query Index

```python
index = client.get_index(
    endpoint_name="my-vs-endpoint",
    index_name="catalog.schema.my_index"
)

results = index.similarity_search(
    query_text="What is machine learning?",
    columns=["id", "content", "metadata"],
    num_results=5
)
```

## Common Patterns

### Create Storage-Optimized Endpoint

```python
# For large-scale, cost-effective deployments
client.create_endpoint(
    name="my-storage-endpoint",
    endpoint_type="STORAGE_OPTIMIZED"
)
```

### Delta Sync with Self-Managed Embeddings

```python
# Source table must have: primary key + embedding vector column
index = client.create_delta_sync_index(
    endpoint_name="my-vs-endpoint",
    source_table_name="catalog.schema.documents",
    index_name="catalog.schema.my_index",
    pipeline_type="TRIGGERED",
    primary_key="id",
    embedding_dimension=768,
    embedding_vector_column="embedding"
)
```

### Direct Access Index

```python
# Create index for manual CRUD
index = client.create_direct_access_index(
    endpoint_name="my-vs-endpoint",
    index_name="catalog.schema.direct_index",
    primary_key="id",
    embedding_dimension=768,
    embedding_vector_column="embedding",
    schema={
        "id": "string",
        "text": "string",
        "embedding": "array<float>",
        "metadata": "string"
    }
)

# Upsert data
index.upsert([
    {"id": "1", "text": "Hello", "embedding": [0.1, 0.2, ...], "metadata": "doc1"},
    {"id": "2", "text": "World", "embedding": [0.3, 0.4, ...], "metadata": "doc2"},
])

# Delete data
index.delete(primary_keys=["1", "2"])
```

### Query with Embedding Vector

```python
# When you have pre-computed query embedding
results = index.similarity_search(
    query_vector=[0.1, 0.2, 0.3, ...],  # Your 768-dim vector
    columns=["id", "text"],
    num_results=10
)
```

### Hybrid Search (Semantic + Keyword)

Hybrid search combines vector similarity (ANN) with BM25 keyword scoring. Use it when queries contain exact terms that must match — SKUs, error codes, proper nouns, or technical terminology — where pure semantic search might miss keyword-specific results. See [references/search-modes.md](references/search-modes.md) for detailed guidance on choosing between ANN and hybrid search.

```python
# Combines vector similarity with keyword matching
results = index.similarity_search(
    query_text="SPARK-12345 executor memory error",
    query_type="hybrid",
    columns=["id", "content"],
    num_results=10
)
```

## Filtering

Filter syntax differs by endpoint type. See [references/filtering.md](references/filtering.md) for the full operator reference.

### Standard Endpoint Filters (Dictionary)

```python
results = index.similarity_search(
    query_text="machine learning",
    columns=["id", "content"],
    num_results=10,
    filters={"category": "ai", "status": ["active", "pending"]}
)
```

### Storage-Optimized Filters (SQL-like string)

```python
results = index.similarity_search(
    query_text="machine learning",
    columns=["id", "content"],
    num_results=10,
    filters="category = 'ai' AND status IN ('active', 'pending')"
)
```

### Trigger Index Sync

```python
# For TRIGGERED pipeline type, manually sync
index = client.get_index(
    endpoint_name="my-vs-endpoint",
    index_name="catalog.schema.my_index"
)
index.sync()
```

### Scan All Index Entries

```python
# Retrieve all vectors (for debugging/export)
index.scan(num_results=100)
```

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Index Types | [references/index-types.md](references/index-types.md) | Detailed comparison of Delta Sync (managed/self-managed) vs Direct Access |
| End-to-End RAG | [references/end-to-end-rag.md](references/end-to-end-rag.md) | Complete walkthrough: source table → endpoint → index → query → agent integration |
| Search Modes | [references/search-modes.md](references/search-modes.md) | When to use semantic (ANN) vs hybrid search, reranker, decision guide |
| Filtering | [references/filtering.md](references/filtering.md) | Full filter operator reference for Standard (dict) and Storage-Optimized (SQL string) endpoints |
| Operations | [references/troubleshooting-and-operations.md](references/troubleshooting-and-operations.md) | Monitoring, cost optimization, capacity planning, migration, performance targets |

## CLI Quick Reference

```bash
# List endpoints
databricks vector-search-endpoints list-endpoints

# Create endpoint (positional args: NAME ENDPOINT_TYPE)
databricks vector-search-endpoints create-endpoint my-endpoint STANDARD

# List indexes on endpoint (positional arg: ENDPOINT_NAME)
databricks vector-search-indexes list-indexes my-endpoint

# Get index status (positional arg: INDEX_NAME)
databricks vector-search-indexes get-index catalog.schema.my_index

# Sync index (positional arg: INDEX_NAME)
databricks vector-search-indexes sync-index catalog.schema.my_index

# Delete index (positional arg: INDEX_NAME)
databricks vector-search-indexes delete-index catalog.schema.my_index
```

## Common Issues

| Issue | Solution |
|-------|----------|
| **Index sync slow** | Use Storage-Optimized endpoints (20x faster indexing) |
| **Query latency high** | Use Standard endpoint for <100ms latency |
| **Filters not working** | Standard endpoints use a dict (`filters={"col": "val"}`); Storage-Optimized use a SQL string (`filters="col = 'val'"`). See [references/filtering.md](references/filtering.md) |
| **Embedding dimension mismatch** | Ensure query and index dimensions match |
| **Index not updating** | Check pipeline_type; use `index.sync()` for TRIGGERED |
| **Out of capacity** | Upgrade to Storage-Optimized (1B+ vectors) |
| **`query_vector` truncated** | Large vectors (e.g. 1024-dim) can be truncated when serialized as JSON. Use `query_text` instead (for managed embedding indexes), or use the Databricks SDK to pass raw vectors |

## Embedding Models

Databricks provides built-in embedding models:

| Model | Dimensions | Context Window | Use Case |
|-------|------------|----------------|----------|
| `databricks-gte-large-en` | 1024 | 8192 tokens | English text, high quality |
| `databricks-bge-large-en` | 1024 | 512 tokens | English text, general purpose |

```python
# Use with managed embeddings
index = client.create_delta_sync_index(
    ...
    embedding_source_column="content",
    embedding_model_endpoint_name="databricks-gte-large-en"
)
```

## Notes

- **Storage-Optimized is newer** — better for most use cases unless you need <100ms latency
- **Delta Sync recommended** — easier than Direct Access for most scenarios
- **Hybrid search** — available for both Delta Sync and Direct Access indexes
- **`columns_to_sync` matters** — only synced columns are available in query results; include all columns you need
- **Filter syntax differs by endpoint** — Standard uses a dict, Storage-Optimized uses a SQL-like string. See [references/filtering.md](references/filtering.md)
- **Management vs runtime** — CLI and SDK handle lifecycle management; for agent tool-calling at runtime, use `VectorSearchRetrieverTool`

## Related Skills

- **databricks-model-serving** - Deploy agents that use VectorSearchRetrieverTool
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - Knowledge Assistants use RAG over indexed documents
- **[databricks-unstructured-pdf-generation](../databricks-unstructured-pdf-generation/SKILL.md)** - Generate documents to index in Vector Search
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Manage the catalogs and tables that back Delta Sync indexes
- **databricks-pipelines** - Build Delta tables used as Vector Search sources
