# AI Search Index Types

## Comparison Matrix

| Feature | Delta Sync (Managed) | Delta Sync (Self-Managed) | Direct Access |
|---------|---------------------|---------------------------|---------------|
| **Embeddings** | Databricks computes | You provide | You provide |
| **Sync** | Auto from Delta | Auto from Delta | Manual CRUD |
| **Setup** | Easiest | Medium | Most control |
| **Source** | Delta table + text | Delta table + vectors | API calls |
| **Endpoints** | Standard, Storage-Optimized | Standard, Storage-Optimized | Standard only |
| **Best for** | Quick start, RAG | Custom models | Real-time apps |

## Delta Sync with Managed Embeddings

Databricks automatically computes embeddings from your text column.

### Requirements

- Source Delta table with:
  - Primary key column (unique identifier)
  - Text column (content to embed)
  - Change Data Feed enabled, for Standard endpoints: `ALTER TABLE ... SET TBLPROPERTIES (delta.enableChangeDataFeed = true)`
- Embedding model endpoint (or use built-in)

### Create Index

```python
from databricks.ai_search.client import AISearchClient

client = AISearchClient()

index = client.create_delta_sync_index(
    endpoint_name="my-vs-endpoint",
    source_table_name="catalog.schema.documents",
    index_name="catalog.schema.docs_index",
    pipeline_type="TRIGGERED",  # or "CONTINUOUS" (Standard only)
    primary_key="doc_id",
    embedding_source_column="content",
    embedding_model_endpoint_name="databricks-gte-large-en",
    columns_to_sync=["doc_id", "content", "title", "category"]  # See the Storage-Optimized note in SKILL.md
)
```

### Pipeline Types

| Type | Behavior | Cost | Use Case |
|------|----------|------|----------|
| `TRIGGERED` | Manual sync via `index.sync()` | Lower | Batch updates; the only option on Storage-Optimized |
| `CONTINUOUS` | Auto-sync on changes | Higher | Real-time sync (Standard only) |

### Source Table Example

```sql
CREATE TABLE catalog.schema.documents (
    doc_id STRING,
    title STRING,
    content STRING,  -- Text to embed
    category STRING,
    created_at TIMESTAMP
) TBLPROPERTIES (delta.enableChangeDataFeed = true);
```

## Delta Sync with Self-Managed Embeddings

You pre-compute embeddings and store them in the source table.

### Requirements

- Source Delta table with:
  - Primary key column
  - Embedding vector column (array of floats)
  - Change Data Feed enabled, for Standard endpoints: `ALTER TABLE ... SET TBLPROPERTIES (delta.enableChangeDataFeed = true)`

### Create Index

```python
index = client.create_delta_sync_index(
    endpoint_name="my-vs-endpoint",
    source_table_name="catalog.schema.embedded_docs",
    index_name="catalog.schema.custom_index",
    pipeline_type="TRIGGERED",
    primary_key="doc_id",
    embedding_dimension=1024,  # databricks-gte-large-en output size
    embedding_vector_column="embedding"
)
```

### Compute Embeddings

```python
from databricks.sdk import WorkspaceClient
import pandas as pd
from pyspark.sql.functions import col

w = WorkspaceClient()

def get_embeddings(texts: list[str]) -> list[list[float]]:
    response = w.serving_endpoints.query(
        name="databricks-gte-large-en",
        input=texts
    )
    return [item.embedding for item in response.data]

# Add embeddings to your data
df = spark.table("catalog.schema.documents").toPandas()
df["embedding"] = get_embeddings(df["content"].tolist())

# Write back to Delta; Spark infers Python float lists as array<double>, so cast to match the table's ARRAY<FLOAT>
spark.createDataFrame(df).withColumn("embedding", col("embedding").cast("array<float>")).write.mode(
    "overwrite"
).saveAsTable("catalog.schema.embedded_docs")
# Standard endpoints need Change Data Feed on the source table
spark.sql("ALTER TABLE catalog.schema.embedded_docs SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
```

### Source Table Example

```sql
CREATE TABLE catalog.schema.embedded_docs (
    doc_id STRING,
    title STRING,
    content STRING,
    category STRING,
    created_at TIMESTAMP,
    embedding ARRAY<FLOAT>  -- Pre-computed embedding
) TBLPROPERTIES (delta.enableChangeDataFeed = true);
```

## Direct Access Index

Full control over vector data via CRUD API. No Delta table sync. Standard endpoints only; Storage-Optimized rejects `DIRECT_ACCESS`.

### Requirements

- Define schema upfront
- Manage upsert/delete operations yourself

### Create Index

```python
from databricks.ai_search.client import AISearchClient

client = AISearchClient()

index = client.create_direct_access_index(
    endpoint_name="my-vs-endpoint",
    index_name="catalog.schema.realtime_index",
    primary_key="id",
    embedding_dimension=768,
    embedding_vector_column="embedding",
    schema={
        "id": "string",
        "text": "string",
        "embedding": "array<float>",
        "category": "string",
        "score": "float"
    }
)
```

### Upsert Data

```python
# Insert or update vectors
index.upsert([
    {
        "id": "doc-001",
        "text": "Machine learning basics",
        "embedding": [0.1, 0.2, 0.3, ...],  # 768 floats
        "category": "ml",
        "score": 0.95
    },
    {
        "id": "doc-002",
        "text": "Deep learning overview",
        "embedding": [0.4, 0.5, 0.6, ...],
        "category": "dl",
        "score": 0.88
    }
])
```

### Delete Data

```python
index.delete(primary_keys=["doc-001", "doc-002"])
```

### Attach Embedding Model (Optional)

For Direct Access indexes that need to support `query_text` (rather than `query_vector`), specify an embedding model at creation time:

```python
index = client.create_direct_access_index(
    endpoint_name="my-vs-endpoint",
    index_name="catalog.schema.hybrid_index",
    primary_key="id",
    embedding_dimension=1024,  # must match the attached model's output
    embedding_vector_column="embedding",
    embedding_model_endpoint_name="databricks-gte-large-en",  # Enables query_text
    schema={...}
)
```

## Choosing the Right Type

```
Start here:
│
├─ Do you have pre-computed embeddings?
│   ├─ Yes → Do you want auto-sync from Delta?
│   │         ├─ Yes → Delta Sync (Self-Managed)
│   │         └─ No  → Direct Access (Standard endpoint)
│   │
│   └─ No → Delta Sync (Managed Embeddings)
│
└─ Do you need real-time updates (<1 sec)?
    ├─ Yes → Direct Access (Standard endpoint)
    └─ No  → Delta Sync (any type)
```

## Endpoint Selection

After choosing index type, choose endpoint:

| Scenario | Endpoint Type |
|----------|---------------|
| Need <100ms latency or high QPS | Standard |
| Direct Access or CONTINUOUS sync | Standard |
| 10M+ vectors, latency-tolerant | Storage-Optimized |
| Cost-sensitive | Storage-Optimized |
| Default choice, if none of the Standard-only needs apply | Storage-Optimized |
