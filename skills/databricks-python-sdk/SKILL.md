---
name: databricks-python-sdk
description: "Databricks development guidance including Python SDK, Databricks Connect, CLI, and REST API. Use when working with databricks-sdk, databricks-connect, or Databricks APIs."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Databricks Development Guide

This skill provides guidance for Databricks SDK, Databricks Connect, CLI, and REST API.

**SDK Documentation:** https://databricks-sdk-py.readthedocs.io/en/latest/
**GitHub Repository:** https://github.com/databricks/databricks-sdk-py

---

## Environment Setup

- Use existing virtual environment at `.venv` or use `uv` to create one
- For Spark operations: `uv pip install databricks-connect`
- For SDK operations: `uv pip install databricks-sdk`
- Databricks CLI version should be 0.278.0 or higher

## Configuration

- Default profile name: `DEFAULT`
- Config file: `~/.databrickscfg`
- Environment variables: `DATABRICKS_HOST`, `DATABRICKS_TOKEN`

---

## Databricks Connect (Spark Operations)

Use `databricks-connect` for running Spark code locally against a Databricks cluster.

```python
from databricks.connect import DatabricksSession

# Auto-detects 'DEFAULT' profile from ~/.databrickscfg
spark = DatabricksSession.builder.getOrCreate()

# With explicit profile
spark = DatabricksSession.builder.profile("MY_PROFILE").getOrCreate()

# Use spark as normal
df = spark.sql("SELECT * FROM catalog.schema.table")
df.show()
```

**IMPORTANT:** Do NOT set `.master("local[*]")` - this will cause issues with Databricks Connect.

---

## Direct REST API Access

For operations not yet in SDK or overly complex via SDK, use direct REST API:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Direct API call using authenticated client
response = w.api_client.do(
    method="GET",
    path="/api/2.0/clusters/list"
)

# POST with body
response = w.api_client.do(
    method="POST",
    path="/api/2.0/jobs/run-now",
    body={"job_id": 123}
)
```

**When to use:** Prefer SDK methods when available. Use `api_client.do` for:
- New API endpoints not yet in SDK
- Complex operations where SDK abstraction is problematic
- Debugging/testing raw API responses

---

## Databricks CLI

```bash
# Check version (should be >= 0.278.0)
databricks --version

# Use specific profile
databricks --profile MY_PROFILE clusters list

# Common commands
databricks clusters list
databricks jobs list
databricks workspace list /Users/me
```

---

## SDK Reference

For a per-API table of method signatures and direct doc URLs (Clusters, Jobs, SQL warehouses, Unity Catalog, Serving, Vector Search, etc.), see [references/doc-index.md](references/doc-index.md). Worked examples for the main API surfaces live under [`examples/`](examples/).

## SDK Documentation Architecture

The SDK documentation follows a predictable URL pattern:

```
Base: https://databricks-sdk-py.readthedocs.io/en/latest/

Workspace APIs:  /workspace/{category}/{service}.html
Account APIs:    /account/{category}/{service}.html
Authentication:  /authentication.html
DBUtils:         /dbutils.html
```

### Workspace API Categories
| Category | Services |
|----------|----------|
| `compute` | clusters, cluster_policies, command_execution, instance_pools, libraries |
| `catalog` | catalogs, schemas, tables, volumes, functions, storage_credentials, external_locations |
| `jobs` | jobs |
| `sql` | warehouses, statement_execution, queries, alerts, dashboards |
| `serving` | serving_endpoints |
| `vectorsearch` | vector_search_indexes, vector_search_endpoints |
| `pipelines` | pipelines |
| `workspace` | repos, secrets, workspace, git_credentials |
| `files` | files, dbfs |
| `ml` | experiments, model_registry |

---

## Authentication

**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/authentication.html

### Environment Variables
```bash
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...  # Personal Access Token
```

### Code Patterns

```python
# Auto-detect credentials from environment
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

# Explicit token auth
w = WorkspaceClient(
    host="https://your-workspace.cloud.databricks.com",
    token="dapi..."
)

# Azure Service Principal
w = WorkspaceClient(
    host="https://adb-xxx.azuredatabricks.net",
    azure_workspace_resource_id="/subscriptions/.../resourceGroups/.../providers/Microsoft.Databricks/workspaces/...",
    azure_tenant_id="tenant-id",
    azure_client_id="client-id",
    azure_client_secret="secret"
)

# Use a named profile from ~/.databrickscfg
w = WorkspaceClient(profile="MY_PROFILE")
```

---

## Core API Reference

Read [Core API Reference](references/core-api-reference.md) when you need the
call shape for a specific SDK object family: clusters, jobs, SQL statement
execution, SQL warehouses, Unity Catalog tables, catalogs and schemas,
volumes, the Files API, serving endpoints, Vector Search, pipelines, secrets,
and dbutils.

## Common Patterns

### CRITICAL: Async Applications (FastAPI, etc.)

**The Databricks SDK is fully synchronous.** All calls block the thread. In async applications (FastAPI, asyncio), you MUST wrap SDK calls with `asyncio.to_thread()` to avoid blocking the event loop.

```python
import asyncio
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# WRONG - blocks the event loop
async def get_clusters_bad():
    return list(w.clusters.list())  # BLOCKS!

# CORRECT - runs in thread pool
async def get_clusters_good():
    return await asyncio.to_thread(lambda: list(w.clusters.list()))

# CORRECT - for simple calls
async def get_cluster(cluster_id: str):
    return await asyncio.to_thread(w.clusters.get, cluster_id)

# CORRECT - FastAPI endpoint
from fastapi import FastAPI
app = FastAPI()

@app.get("/clusters")
async def list_clusters():
    clusters = await asyncio.to_thread(lambda: list(w.clusters.list()))
    return [{"id": c.cluster_id, "name": c.cluster_name} for c in clusters]

@app.post("/query")
async def run_query(sql: str, warehouse_id: str):
    # Wrap the blocking SDK call
    response = await asyncio.to_thread(
        w.statement_execution.execute_statement,
        statement=sql,
        warehouse_id=warehouse_id,
        wait_timeout="30s"
    )
    return response.result.data_array
```

**Note:** `WorkspaceClient().config.host` is NOT a network call - it just reads config. No need to wrap property access.

---

### Wait for Long-Running Operations
```python
from datetime import timedelta

# Pattern 1: Use *_and_wait methods
cluster = w.clusters.create_and_wait(
    cluster_name="test",
    spark_version="14.3.x-scala2.12",
    node_type_id="i3.xlarge",
    num_workers=2,
    timeout=timedelta(minutes=30)
)

# Pattern 2: Use Wait object
wait = w.clusters.create(...)
cluster = wait.result()  # Blocks until ready

# Pattern 3: Manual polling with callback
def progress(cluster):
    print(f"State: {cluster.state}")

cluster = w.clusters.wait_get_cluster_running(
    cluster_id="...",
    timeout=timedelta(minutes=30),
    callback=progress
)
```

### Pagination
```python
# All list methods return iterators that handle pagination automatically
for job in w.jobs.list():  # Fetches all pages
    print(job.settings.name)

# For manual control
from databricks.sdk.service.jobs import ListJobsRequest
response = w.jobs.list(limit=10)
for job in response:
    print(job)
```

### Error Handling
```python
from databricks.sdk.errors import NotFound, PermissionDenied, ResourceAlreadyExists

try:
    cluster = w.clusters.get(cluster_id="invalid-id")
except NotFound:
    print("Cluster not found")
except PermissionDenied:
    print("Access denied")
```

---

## When Uncertain

If I'm unsure about a method, I should:

1. **Check the documentation URL pattern:**
   - `https://databricks-sdk-py.readthedocs.io/en/latest/workspace/{category}/{service}.html`

2. **Common categories:**
   - Clusters: `/workspace/compute/clusters.html`
   - Jobs: `/workspace/jobs/jobs.html`
   - Tables: `/workspace/catalog/tables.html`
   - Warehouses: `/workspace/sql/warehouses.html`
   - Serving: `/workspace/serving/serving_endpoints.html`

3. **Fetch and verify** before providing guidance on parameters or return types.

---

## Quick Reference Links

| API | Documentation URL |
|-----|-------------------|
| Authentication | https://databricks-sdk-py.readthedocs.io/en/latest/authentication.html |
| Clusters | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html |
| Jobs | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html |
| SQL Warehouses | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/warehouses.html |
| Statement Execution | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html |
| Tables | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/tables.html |
| Catalogs | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/catalogs.html |
| Schemas | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/schemas.html |
| Volumes | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/volumes.html |
| Files | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/files/files.html |
| Serving Endpoints | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html |
| Vector Search | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_indexes.html |
| Pipelines | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/pipelines/pipelines.html |
| Secrets | https://databricks-sdk-py.readthedocs.io/en/latest/workspace/workspace/secrets.html |
| DBUtils | https://databricks-sdk-py.readthedocs.io/en/latest/dbutils.html |

## Related Skills

- **databricks-core** - profile and authentication setup
- **databricks-dabs** - deploying resources via DABs
- **databricks-jobs** - job orchestration patterns
- **`databricks-unity-catalog`** - catalog governance
- **databricks-model-serving** - serving endpoint management
- **`databricks-vector-search`** - vector index operations
- **databricks-lakebase** - managed PostgreSQL with autoscaling + branching
