# AI Search Troubleshooting & Operations

Operational guidance for monitoring, cost optimization, capacity planning, and migration of Databricks AI Search resources.

## Monitoring Endpoint Status

Use `databricks vector-search-endpoints get-endpoint ENDPOINT_NAME` (CLI) or `client.get_endpoint()` (SDK) to check endpoint health.

### Endpoint fields

| Field | Description |
|-------|-------------|
| `endpoint_status.state` | `ONLINE`, `PROVISIONING`, `OFFLINE`, `YELLOW_STATE`, `RED_STATE`, `DELETED`, `STARTING`, `STOPPING`, `STOPPED` |
| `endpoint_status.message` | Human-readable status or error message |
| `endpoint_type` | `STANDARD` or `STORAGE_OPTIMIZED` |
| `num_indexes` | Number of indexes hosted on this endpoint |
| `scaling_info` | Standard only: `requested_target_qps` and `state` (`SCALING_CHANGE_IN_PROGRESS` / `SCALING_CHANGE_APPLIED`) |
| `creation_timestamp` | When the endpoint was created |
| `last_updated_timestamp` | When the endpoint was last modified |

### Example

```python
from databricks.ai_search.client import AISearchClient

client = AISearchClient()
endpoint = client.get_endpoint(name="my-endpoint")

print(endpoint["endpoint_status"]["state"])   # ONLINE, PROVISIONING, ...
print(endpoint["endpoint_type"], endpoint["num_indexes"])
```

**What to do per state:**
- `PROVISIONING` → Wait. Endpoint creation is asynchronous and can take several minutes.
- `ONLINE` → Ready to serve queries and host indexes.
- `STARTING` / `STOPPING` → Wait for the transition to finish.
- `STOPPED` → Start it before querying: `client.start_endpoint_and_wait(name)` (`databricks-ai-search` 0.80+). Endpoint stop/start is in Private Preview and available only in enrolled workspaces.
- `OFFLINE` → Check the `message` field for error details. May require recreation.
- `YELLOW_STATE` → Endpoint is degraded but still serving. Investigate the `message` field.
- `RED_STATE` → Endpoint is unhealthy. Check `message` for details; may need support intervention.

## Monitoring Index Status

Use `databricks vector-search-indexes get-index INDEX_NAME` (CLI) or `client.get_index()` (SDK) to check index health.

### Index fields

| Field | Description |
|-------|-------------|
| `status.ready` | Boolean — `True` when ready for queries, `False` when provisioning/syncing |
| `status.message` | Status details or error information |
| `status.index_url` | Index API URL for queries. High-QPS traffic must use it, with service principal OAuth |
| `status.indexed_row_count` | Number of rows currently indexed |
| `delta_sync_index_spec.pipeline_id` | DLT pipeline ID (Delta Sync indexes only) — useful for debugging sync issues |
| `index_type` | `DELTA_SYNC` or `DIRECT_ACCESS` |

### Example

```python
index = client.get_index(
    endpoint_name="my-endpoint",
    index_name="catalog.schema.my_index"
)

status = index.describe()["status"]
print(status.get("ready"), status.get("indexed_row_count"))
print(status.get("message"))

# Or block until the index is serving. ready means it serves some version: ONLINE_PIPELINE_FAILED is
# ready=True but the latest sync failed, so also check detailed_state for "FAILED" afterwards:
# index.wait_until_ready()
```

## Pipeline Type Trade-offs

Delta Sync indexes use a DLT pipeline to sync data from the source Delta table. The pipeline type determines sync behavior:

| Pipeline Type | Behavior | Cost | Best for |
|---------------|----------|------|----------|
| **TRIGGERED** | Manual sync via `index.sync()` | Lower — runs only when triggered | Batch updates, periodic refreshes, cost-sensitive workloads |
| **CONTINUOUS** | Auto-syncs on source table changes | Higher — always running | Real-time freshness on Standard endpoints (not available on Storage-Optimized) |

### Triggering a sync

```python
index = client.get_index(
    endpoint_name="my-vs-endpoint",
    index_name="catalog.schema.my_index"
)
index.sync()
```

**Tip:** CONTINUOUS pipelines cannot be synced manually — they sync automatically. Calling `index.sync()` on a CONTINUOUS index will raise an error.

## Cost Optimization

### Endpoint type selection

| Factor | Standard | Storage-Optimized |
|--------|----------|-------------------|
| Query latency | 20-50ms | 300-500ms |
| Cost | Higher | Up to 7x lower |
| Max capacity | 320M vectors (768 dim) | 1B+ vectors (768 dim) |
| Indexing speed | Slower | 10-20x faster |
| Target QPS / high QPS | Yes | No |

**Recommendation:** Start with Storage-Optimized (it suits 10M+ vectors) unless you need sub-100ms latency, high QPS, Direct Access, or CONTINUOUS sync. It handles most RAG workloads well.

### Reducing storage costs

- Use `columns_to_sync` to limit which columns are synced to the index (see the [Storage-Optimized note](../SKILL.md#notes)).
- Choose TRIGGERED pipelines for batch workloads to avoid continuous compute costs.
- `target_qps` capacity is billed whether or not traffic arrives; set it to the sustained peak you measured in a load test.

```python
index = client.create_delta_sync_index(
    endpoint_name="my-vs-endpoint",
    source_table_name="catalog.schema.documents",
    index_name="catalog.schema.my_index",
    pipeline_type="TRIGGERED",
    primary_key="id",
    embedding_source_column="content",
    embedding_model_endpoint_name="databricks-gte-large-en",
    columns_to_sync=["id", "content", "title"]  # Exclude large unused columns
)
```

## Capacity Planning

| Endpoint Type | Max Vectors (768 dim) | Guidance |
|---------------|----------------------|----------|
| Standard | ~320M | Suitable for most production workloads under 300M documents |
| Storage-Optimized | 1B+ | Large-scale corpora, enterprise knowledge bases |

**Estimating needs:**
- One document typically maps to one vector (or multiple if chunked)
- If chunking at ~512 tokens, expect 2-5 vectors per page of text
- Monitor `num_indexes` on your endpoint to understand utilization
- Index capacity is provisioned from the source table size at index creation. Starting from a small table limits growth and can cause capacity-exhausted errors, so load the expected data volume before creating the index.

## Migration Patterns

### Changing endpoint type

Endpoints are **immutable after creation** — you cannot change the type (Standard ↔ Storage-Optimized) of an existing endpoint. To migrate:

1. **Create a new endpoint** with the desired type
2. **Recreate indexes** on the new endpoint pointing to the same source tables
3. **Wait for the initial sync** (creating the index starts it): `wait_until_ready(timeout=...)`, then confirm `status.ready`
4. **Update applications** to query the new index names
5. **Delete old indexes**, then delete the old endpoint

Moving to Storage-Optimized drops support for Direct Access, CONTINUOUS sync, and `target_qps`, and changes the filter syntax (a SQL string instead of a dict).

```python
import datetime

from databricks.ai_search.client import AISearchClient

client = AISearchClient()

# Step 1: Create new endpoint and wait until it is ONLINE
client.create_endpoint_and_wait(
    name="my-endpoint-storage-optimized",
    endpoint_type="STORAGE_OPTIMIZED"
)

# Step 2: Recreate index on new endpoint (same source table)
index_v2 = client.create_delta_sync_index(
    endpoint_name="my-endpoint-storage-optimized",
    source_table_name="catalog.schema.documents",
    index_name="catalog.schema.my_index_v2",
    pipeline_type="TRIGGERED",
    primary_key="id",
    embedding_source_column="content",
    embedding_model_endpoint_name="databricks-gte-large-en"
)

# Step 3: Wait for the initial sync (index_v2.sync() is rejected while the index is provisioning).
# ready means the index serves some version; ONLINE_PIPELINE_FAILED is ready=True but the latest sync failed.
index_v2.wait_until_ready(timeout=datetime.timedelta(hours=4))
status = index_v2.describe()["status"]
state = status.get("detailed_state") or ""
if not status.get("ready") or "FAILED" in state:
    raise RuntimeError(f"New index not ready: {status.get('message')} ({status.get('detailed_state')})")
print(f"New index: {status.get('indexed_row_count')} rows")  # Compare with the source table's row count
```

Step 4: move application traffic to `catalog.schema.my_index_v2`.

Step 5: clean up only after the new index is ready with the expected row count, traffic has moved, and the user confirms. Deleting the endpoint removes the serving compute for every index still on it, so check what's left first:

```python
client.delete_index(index_name="catalog.schema.my_index")

# Skip the index just deleted: it may still be listed while its deletion finishes
remaining = [
    i["name"] for i in client.list_indexes("my-endpoint").get("vector_indexes", [])
    if i["name"] != "catalog.schema.my_index"
]
if remaining:
    print(f"Keeping my-endpoint; it still hosts {remaining}")
else:
    client.delete_endpoint(name="my-endpoint")
```

## Expanded Troubleshooting

| Issue | Likely Cause | Solution |
|-------|-------------|----------|
| **Index stuck in NOT_READY** | Sync pipeline failed or source table issue | Check `index.describe()["status"].get("message")`. On Standard, inspect the sync pipeline using `delta_sync_index_spec.pipeline_id`. |
| **Create fails on Standard: change data feed** | Source table has no Change Data Feed | `ALTER TABLE ... SET TBLPROPERTIES (delta.enableChangeDataFeed = true)` |
| **Embedding dimension mismatch** | Query vector dimensions ≠ index dimensions | Ensure your embedding model output matches the `embedding_dimension` in the index spec. |
| **Permission errors on create** | Missing Unity Catalog privileges | User needs `CREATE TABLE` on the schema and `USE CATALOG`/`USE SCHEMA` privileges. |
| **Index returns NOT_FOUND** | Wrong name format or index deleted | Index names must be fully qualified: `catalog.schema.index_name`. |
| **Sync not running (TRIGGERED)** | Sync not triggered after source update | Call `index.sync()` after updating source data. If it's rejected as already running, wait for the current update to finish. |
| **Endpoint NOT_FOUND** | Endpoint name typo or deleted | List endpoints with `client.list_endpoints()` or `databricks vector-search-endpoints list-endpoints`. |
| **Query returns empty results** | Index not yet synced, or filters too restrictive | Wait with `wait_until_ready(timeout=...)` and check `status.ready`. If the index sets `columns_to_sync`, verify it includes queried columns. Test without filters first. |
| **Filters not working** | Wrong filter syntax for endpoint type | Standard endpoints use a dict: `filters={"col": "val"}`. Storage-Optimized use a SQL string: `filters="col = 'val'"`; wrap timestamps in `TO_TIMESTAMP(...)`. |
| **Quota or capacity errors** | Too many indexes or vectors, or index sized from a small source table | Check `num_indexes` on endpoint. Recreate the index after loading the full source table, or on Storage-Optimized for higher capacity. |
| **Upsert fails on Delta Sync** | Cannot upsert to Delta Sync indexes | Upsert/delete operations only work on Direct Access indexes. Delta Sync indexes update via their source table. |
| **Rate limited (429 errors)** | Endpoint over capacity: PAT or workspace query URL, scaling in progress, target QPS too low, or the embedding endpoint (managed-embedding `query_text`) | Increase endpoint capacity (`target_qps`, Standard only). Implement client-side rate limiting with exponential backoff. Follow the checklist in [SKILL.md](../SKILL.md#production-and-high-qps) and [Troubleshoot 429 errors](https://docs.databricks.com/aws/en/ai-search/high-qps#troubleshoot-429-errors). |
| **`RESOURCE_CONFLICT` on target QPS update** | A change can be rejected while a previous change is still applying; nothing is saved, so `requested_target_qps` keeps the earlier target | Poll `client.get_endpoint(name).get("scaling_info")` with a deadline until `state` is `SCALING_CHANGE_APPLIED` (for whatever target is current), or wait the minutes the error gives. Then call `update_endpoint` again, and only then wait for the new target as in the [SKILL.md example](../SKILL.md#production-and-high-qps). |
