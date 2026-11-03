# End-to-End RAG with AI Search

Build a complete Retrieval-Augmented Generation pipeline: prepare documents, create a vector index, query it, and wire it into an agent.

## CLI Commands Used

| Command | Step |
|---------|------|
| `databricks experimental aitools tools query` | Create source table, insert documents |
| `databricks vector-search-endpoints create-endpoint` | Create compute endpoint |
| `databricks vector-search-indexes create-index` | Create Delta Sync index with managed embeddings |
| `databricks vector-search-indexes sync-index` | Trigger index sync |
| `databricks vector-search-indexes get-index` | Check index status |
| `databricks vector-search-indexes query-index` | Test similarity search |

The Python steps below use `AISearchClient`:

```bash
pip install "databricks-ai-search>=0.79"  # In a notebook: %pip install, then dbutils.library.restartPython()
```

A bare `AISearchClient()` uses the notebook's credentials. Elsewhere, pass `workspace_url` plus a PAT or service principal credentials.

---

## Step 1: Prepare Source Table

The source Delta table needs a primary key column and a text column to embed. This walkthrough uses a Storage-Optimized endpoint; on a Standard endpoint, the table also needs Change Data Feed (included below).

```sql
CREATE TABLE IF NOT EXISTS catalog.schema.knowledge_base (
    doc_id STRING,
    title STRING,
    content STRING,
    category STRING,
    updated_at TIMESTAMP DEFAULT current_timestamp()
) TBLPROPERTIES (delta.enableChangeDataFeed = true);

INSERT INTO catalog.schema.knowledge_base VALUES
('doc-001', 'Getting Started', 'Databricks is a unified analytics platform...', 'overview', current_timestamp()),
('doc-002', 'Unity Catalog', 'Unity Catalog provides centralized governance...', 'governance', current_timestamp()),
('doc-003', 'Delta Lake', 'Delta Lake is an open-source storage layer...', 'storage', current_timestamp());
```

Or via CLI:

```bash
databricks experimental aitools tools query --warehouse WAREHOUSE_ID "
    CREATE TABLE IF NOT EXISTS catalog.schema.knowledge_base (
        doc_id STRING,
        title STRING,
        content STRING,
        category STRING,
        updated_at TIMESTAMP DEFAULT current_timestamp()
    ) TBLPROPERTIES (delta.enableChangeDataFeed = true)
"
```

## Step 2: Create AI Search Endpoint

```python
import datetime

from databricks.ai_search.client import AISearchClient

client = AISearchClient()

# Blocks until the endpoint is ONLINE; raises on OFFLINE or on timeout
client.create_endpoint_and_wait(
    name="my-rag-endpoint",
    endpoint_type="STORAGE_OPTIMIZED",
    timeout=datetime.timedelta(minutes=30),
)
print(client.get_endpoint("my-rag-endpoint")["endpoint_status"]["state"])  # ONLINE
```

## Step 3: Create Delta Sync Index

```python
index = client.create_delta_sync_index(
    endpoint_name="my-rag-endpoint",
    source_table_name="catalog.schema.knowledge_base",
    index_name="catalog.schema.knowledge_base_index",
    pipeline_type="TRIGGERED",
    primary_key="doc_id",
    embedding_source_column="content",
    embedding_model_endpoint_name="databricks-gte-large-en",
)
```

Key decisions:
- **`embedding_source_column`**: Databricks computes embeddings automatically from the `content` column
- **`pipeline_type`**: `TRIGGERED` for manual sync (cheaper, and the only option on Storage-Optimized); `CONTINUOUS` auto-syncs on table changes (Standard only)
- **`columns_to_sync`**: not set, so every column is synced; see the [note in SKILL.md](../SKILL.md#notes) for Storage-Optimized

## Step 4: Wait for the Initial Sync

Creating the index starts its first sync. Don't call `index.sync()` yet: it is rejected while the index is still provisioning.

```python
# Polls every 30s and returns on any ONLINE* state; raises if the index goes OFFLINE or isn't online within the timeout
index.wait_until_ready(timeout=datetime.timedelta(hours=2))

# ready means the index serves some version; ONLINE_PIPELINE_FAILED is ready=True but the latest sync failed.
status = index.describe()["status"]
state = status.get("detailed_state") or ""
if not status.get("ready") or "FAILED" in state:
    raise RuntimeError(f"Index not ready: {status.get('message')} ({state})")
print(f"Ready: {status.get('indexed_row_count')} rows")
```

## Step 5: Query the Index

```python
# Semantic search
results = index.similarity_search(
    query_text="How do I govern my data?",
    columns=["doc_id", "title", "content", "category"],
    num_results=3,
)
for row in results["result"]["data_array"]:
    print(row)
```

Or via CLI:

```bash
databricks vector-search-indexes query-index catalog.schema.knowledge_base_index \
  --json '{"columns": ["doc_id", "title", "content"], "query_text": "How do I govern my data?", "num_results": 3}'
```

### With Filters

The filter syntax depends on the endpoint type used when creating the index.

```python
# Storage-Optimized endpoint (used in this walkthrough): SQL-like string
results = index.similarity_search(
    query_text="How do I govern my data?",
    columns=["doc_id", "title", "content"],
    num_results=3,
    filters="category = 'governance'",
)

# Standard endpoint (if you created a Standard endpoint instead): dict
standard_index = client.get_index(
    endpoint_name="my-standard-endpoint",
    index_name="catalog.schema.my_standard_index",
)
results = standard_index.similarity_search(
    query_text="How do I govern my data?",
    columns=["doc_id", "title", "content"],
    num_results=3,
    filters={"category": "governance"},
)
```

### Hybrid Search (Vector + Keyword)

```python
results = index.similarity_search(
    query_text="Delta Lake ACID transactions",
    query_type="hybrid",
    columns=["doc_id", "title", "content"],
    num_results=5,
)
```

---

## Step 6: Use in an Agent

### As a Retriever Tool

`VectorSearchRetrieverTool` from `databricks-langchain` (or `databricks-openai`) exposes the index as an agent tool:

```python
# pip install --upgrade databricks-langchain langchain
from databricks_langchain import ChatDatabricks, VectorSearchRetrieverTool
from langchain.agents import create_agent

retriever_tool = VectorSearchRetrieverTool(
    index_name="catalog.schema.knowledge_base_index",
    columns=["doc_id", "title", "content"],
    num_results=3,
    tool_name="knowledge_base_retriever",
    tool_description="Search the internal knowledge base for Databricks product questions.",
)
print(retriever_tool.invoke("How do I govern my data?"))  # Test retrieval directly

agent = create_agent(ChatDatabricks(endpoint="databricks-claude-sonnet-4-5"), [retriever_tool])
result = agent.invoke({"messages": [{"role": "user", "content": "How do I govern my data?"}]})
```

To deploy this as a `ResponsesAgent` on Model Serving, see the `databricks-ml-training` skill ([genai-agents.md](../../databricks-ml-training/references/genai-agents.md)) and [Connect agents to unstructured data](https://docs.databricks.com/aws/en/agents/custom-agents/unstructured-retrieval-tools). Log the agent by file path with Models from Code, not as an instance: an `AISearchIndex` holds a `threading.Lock` (databricks-ai-search 0.78+), so pickling an agent that holds one fails. Pin `databricks-ai-search>=0.79` in `pip_requirements`.

### Without an Agent Framework

Retrieve with `similarity_search`, then call a chat model. `serving_endpoints.query` takes `ChatMessage` objects, not dicts:

```python
from databricks.ai_search.client import AISearchClient
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

w = WorkspaceClient()
# get_index makes a control-plane call; build the index once and reuse it across questions
index = AISearchClient().get_index(
    endpoint_name="my-rag-endpoint",
    index_name="catalog.schema.knowledge_base_index",
)

question = "How do I govern my data?"
hits = index.similarity_search(columns=["title", "content"], query_text=question, num_results=3)
context_docs = "\n\n".join(f"**{row[0]}**: {row[1]}" for row in hits["result"]["data_array"])

response = w.serving_endpoints.query(
    name="databricks-claude-sonnet-4-5",
    messages=[
        # Fixed instructions in the system message; retrieved text goes in the user message
        ChatMessage(role=ChatMessageRole.SYSTEM, content="Answer only from the provided context. If it doesn't contain the answer, say so."),
        ChatMessage(role=ChatMessageRole.USER, content=f"Context:\n{context_docs}\n\nQuestion: {question}"),
    ],
)
print(response.choices[0].message.content)
```

---

## Updating the Index

### Add New Documents

```sql
INSERT INTO catalog.schema.knowledge_base VALUES
('doc-004', 'MLflow', 'MLflow is an open-source platform for ML lifecycle...', 'ml', current_timestamp());
```

Then sync, wait for the sync to start, and wait for it to finish:

```python
import time

index.sync()

updating = ("ONLINE_TRIGGERED_UPDATE", "ONLINE_UPDATING_PIPELINE_RESOURCES")
start = time.monotonic()
started = False
while True:
    status = index.describe()["status"]
    state = status.get("detailed_state") or ""
    if state in updating:
        started = True
    elif started:
        break
    elapsed = time.monotonic() - start
    if elapsed > 2 * 60 * 60 or (not started and elapsed > 10 * 60):
        raise TimeoutError(f"Sync {'did not finish' if started else 'did not start'}: {state}: {status.get('message')}")
    time.sleep(10)

message = status.get("message") or ""
# Some indexes report a failed sync only in message, with an ONLINE_NO_PENDING_UPDATE state
if not status.get("ready") or "FAILED" in state or "update failed" in message.lower():
    raise RuntimeError(f"Sync failed: {message} ({state})")
print(f"Synced: {status.get('indexed_row_count')} rows")
```

Until the new sync starts, `detailed_state` still describes the previous one: `ONLINE_NO_PENDING_UPDATE`, or a FAILED state if it failed. That is why the loop waits for an updating state before it checks for success or failure, and why `wait_until_ready(wait_for_updates=True)` alone isn't enough here (it can return before the sync starts, and it keeps waiting on `ONLINE_PIPELINE_FAILED` until its timeout). Don't use `indexed_row_count` to detect completion: UPDATE and MERGE leave it unchanged. If `sync()` is rejected because an update is already running, wait for that update to finish, then sync again.

### Delete Documents

```sql
DELETE FROM catalog.schema.knowledge_base WHERE doc_id = 'doc-001';
```

Then sync; the next sync removes deleted rows from the index.

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Index stuck in PROVISIONING** | Endpoint may still be creating. Check `client.get_endpoint("my-rag-endpoint")["endpoint_status"]["state"]` first |
| **Query returns no results** | Index may not be synced yet. Wait with `index.wait_until_ready(timeout=...)` and check `status.ready` (Step 4) |
| **"Column not found in index"** | If the index sets `columns_to_sync`, the column must be in it ([note](../SKILL.md#notes)). Recreate index with the column included |
| **Embeddings not computed** | Ensure `embedding_model_endpoint_name` is a valid serving endpoint |
| **Stale results after table update** | For TRIGGERED pipelines, call `index.sync()` after each update |
| **Filter not working** | Standard: dict in `filters`; Storage-Optimized: SQL string in `filters` |
