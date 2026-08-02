# Core API Reference

Call shapes for each Databricks SDK object family. Read this when you need the
exact method, arguments, or return type for a specific API.

## Core API Reference

### Clusters API
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/compute/clusters.html

```python
# List all clusters
for cluster in w.clusters.list():
    print(f"{cluster.cluster_name}: {cluster.state}")

# Get cluster details
cluster = w.clusters.get(cluster_id="0123-456789-abcdef")

# Create a cluster (returns Wait object)
wait = w.clusters.create(
    cluster_name="my-cluster",
    spark_version=w.clusters.select_spark_version(latest=True),
    node_type_id=w.clusters.select_node_type(local_disk=True),
    num_workers=2
)
cluster = wait.result()  # Wait for cluster to be running

# Or use create_and_wait for blocking call
cluster = w.clusters.create_and_wait(
    cluster_name="my-cluster",
    spark_version="14.3.x-scala2.12",
    node_type_id="i3.xlarge",
    num_workers=2,
    timeout=timedelta(minutes=30)
)

# Start/stop/delete
w.clusters.start(cluster_id="...").result()
w.clusters.stop(cluster_id="...")
w.clusters.delete(cluster_id="...")
```

### Jobs API
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/jobs/jobs.html

```python
from databricks.sdk.service.jobs import Task, NotebookTask

# List jobs
for job in w.jobs.list():
    print(f"{job.job_id}: {job.settings.name}")

# Create a job
created = w.jobs.create(
    name="my-job",
    tasks=[
        Task(
            task_key="main",
            notebook_task=NotebookTask(notebook_path="/Users/me/notebook"),
            existing_cluster_id="0123-456789-abcdef"
        )
    ]
)

# Run a job now
run = w.jobs.run_now_and_wait(job_id=created.job_id)
print(f"Run completed: {run.state.result_state}")

# Get run output
output = w.jobs.get_run_output(run_id=run.run_id)
```

### SQL Statement Execution
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/statement_execution.html

```python
# Execute SQL query
response = w.statement_execution.execute_statement(
    warehouse_id="abc123",
    statement="SELECT * FROM catalog.schema.table LIMIT 10",
    wait_timeout="30s"
)

# Check status and get results
if response.status.state == StatementState.SUCCEEDED:
    for row in response.result.data_array:
        print(row)

# For large results, fetch chunks
chunk = w.statement_execution.get_statement_result_chunk_n(
    statement_id=response.statement_id,
    chunk_index=0
)
```

### SQL Warehouses
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/sql/warehouses.html

```python
# List warehouses
for wh in w.warehouses.list():
    print(f"{wh.name}: {wh.state}")

# Get warehouse
warehouse = w.warehouses.get(id="abc123")

# Create warehouse
created = w.warehouses.create_and_wait(
    name="my-warehouse",
    cluster_size="Small",
    max_num_clusters=1,
    auto_stop_mins=15
)

# Start/stop
w.warehouses.start(id="abc123").result()
w.warehouses.stop(id="abc123").result()
```

### Unity Catalog - Tables
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/tables.html

```python
# List tables in a schema
for table in w.tables.list(catalog_name="main", schema_name="default"):
    print(f"{table.full_name}: {table.table_type}")

# Get table info
table = w.tables.get(full_name="main.default.my_table")
print(f"Columns: {[c.name for c in table.columns]}")

# Check if table exists
exists = w.tables.exists(full_name="main.default.my_table")
```

### Unity Catalog - Catalogs & Schemas
**Doc (Catalogs):** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/catalogs.html
**Doc (Schemas):** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/schemas.html

```python
# List catalogs
for catalog in w.catalogs.list():
    print(catalog.name)

# Create catalog
w.catalogs.create(name="my_catalog", comment="Description")

# List schemas
for schema in w.schemas.list(catalog_name="main"):
    print(schema.name)

# Create schema
w.schemas.create(name="my_schema", catalog_name="main")
```

### Volumes
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/volumes.html

```python
from databricks.sdk.service.catalog import VolumeType

# List volumes
for vol in w.volumes.list(catalog_name="main", schema_name="default"):
    print(f"{vol.full_name}: {vol.volume_type}")

# Create managed volume
w.volumes.create(
    catalog_name="main",
    schema_name="default",
    name="my_volume",
    volume_type=VolumeType.MANAGED
)

# Read volume info
vol = w.volumes.read(name="main.default.my_volume")
```

### Files API
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/files/files.html

```python
# Upload file to volume
w.files.upload(
    file_path="/Volumes/main/default/my_volume/data.csv",
    contents=open("local_file.csv", "rb")
)

# Download file
with w.files.download(file_path="/Volumes/main/default/my_volume/data.csv") as f:
    content = f.read()

# List directory contents
for entry in w.files.list_directory_contents("/Volumes/main/default/my_volume/"):
    print(f"{entry.name}: {entry.is_directory}")

# Upload/download with progress (parallel)
w.files.upload_from(
    file_path="/Volumes/main/default/my_volume/large.parquet",
    source_path="/local/path/large.parquet",
    use_parallel=True
)

w.files.download_to(
    file_path="/Volumes/main/default/my_volume/large.parquet",
    destination="/local/output/",
    use_parallel=True
)
```

### Serving Endpoints (Model Serving)
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/serving/serving_endpoints.html

```python
# List endpoints
for ep in w.serving_endpoints.list():
    print(f"{ep.name}: {ep.state}")

# Get endpoint
endpoint = w.serving_endpoints.get(name="my-endpoint")

# Query endpoint
response = w.serving_endpoints.query(
    name="my-endpoint",
    inputs={"prompt": "Hello, world!"}
)

# For chat/completions endpoints
response = w.serving_endpoints.query(
    name="my-chat-endpoint",
    messages=[{"role": "user", "content": "Hello!"}]
)

# Get OpenAI-compatible client
openai_client = w.serving_endpoints.get_open_ai_client()
```

### Vector Search
**Doc (Indexes):** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_indexes.html
**Doc (Endpoints):** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/vectorsearch/vector_search_endpoints.html

```python
# List vector search indexes
for idx in w.vector_search_indexes.list_indexes(endpoint_name="my-vs-endpoint"):
    print(idx.name)

# Query index
results = w.vector_search_indexes.query_index(
    index_name="main.default.my_index",
    columns=["id", "text", "embedding"],
    query_text="search query",
    num_results=10
)
for doc in results.result.data_array:
    print(doc)
```

### Pipelines (Delta Live Tables)
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/pipelines/pipelines.html

```python
# List pipelines
for pipeline in w.pipelines.list_pipelines():
    print(f"{pipeline.name}: {pipeline.state}")

# Get pipeline
pipeline = w.pipelines.get(pipeline_id="abc123")

# Start pipeline update
w.pipelines.start_update(pipeline_id="abc123")

# Stop pipeline
w.pipelines.stop_and_wait(pipeline_id="abc123")
```

### Secrets
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/workspace/workspace/secrets.html

```python
# List secret scopes
for scope in w.secrets.list_scopes():
    print(scope.name)

# Create scope
w.secrets.create_scope(scope="my-scope")

# Put secret
w.secrets.put_secret(scope="my-scope", key="api-key", string_value="secret123")

# Get secret (returns GetSecretResponse with value)
secret = w.secrets.get_secret(scope="my-scope", key="api-key")

# List secrets in scope (metadata only, not values)
for s in w.secrets.list_secrets(scope="my-scope"):
    print(s.key)
```

### DBUtils
**Doc:** https://databricks-sdk-py.readthedocs.io/en/latest/dbutils.html

```python
# Access dbutils through WorkspaceClient
dbutils = w.dbutils

# File system operations
files = dbutils.fs.ls("/")
dbutils.fs.cp("dbfs:/source", "dbfs:/dest")
dbutils.fs.rm("dbfs:/path", recurse=True)

# Secrets (same as w.secrets but dbutils interface)
value = dbutils.secrets.get(scope="my-scope", key="my-key")
```

---
