# LakeFlow (Delta Live Tables)

LakeFlow provides declarative ETL pipelines using Delta Live Tables (DLT) for building reliable data pipelines.

## Pipelines

### List and Get Pipelines

```bash
# List pipelines
databricks pipelines list --profile my-workspace

# Get pipeline details
databricks pipelines get --pipeline-id <pipeline-id> --profile my-workspace
```

### Create Pipeline

```bash
# Create pipeline from JSON config
databricks pipelines create --json @pipeline-config.json --profile my-workspace
```

**pipeline-config.json**:
```json
{
  "name": "customer-data-pipeline",
  "storage": "/mnt/storage/pipelines/customer-data",
  "target": "my_catalog.analytics",
  "clusters": [
    {
      "label": "default",
      "node_type_id": "i3.xlarge",
      "num_workers": 2
    }
  ],
  "libraries": [
    {
      "notebook": {
        "path": "/Users/user@example.com/pipelines/customer_pipeline"
      }
    }
  ],
  "continuous": false
}
```

### Update Pipeline

```bash
# Update pipeline configuration
databricks pipelines update \
  --pipeline-id <pipeline-id> \
  --json @updated-config.json \
  --profile my-workspace
```

### Delete Pipeline

```bash
# Delete a pipeline
databricks pipelines delete --pipeline-id <pipeline-id> --profile my-workspace
```

## Running Pipelines

### Start Pipeline Update

```bash
# Start a pipeline update (run the pipeline)
databricks pipelines start-update --pipeline-id <pipeline-id> --profile my-workspace

# Start with full refresh
databricks pipelines start-update \
  --pipeline-id <pipeline-id> \
  --full-refresh \
  --profile my-workspace
```

### Stop Pipeline

```bash
# Stop a running pipeline
databricks pipelines stop --pipeline-id <pipeline-id> --profile my-workspace
```

### Get Pipeline Events (Logs)

```bash
# Get pipeline events/logs
databricks pipelines get-events --pipeline-id <pipeline-id> --profile my-workspace

# Get recent events with limit
databricks pipelines get-events \
  --pipeline-id <pipeline-id> \
  --max-results 100 \
  --profile my-workspace
```

## Pipeline Configuration

### Basic Pipeline

```json
{
  "name": "simple-pipeline",
  "storage": "/mnt/storage/pipelines/simple",
  "target": "dev_catalog.raw_data",
  "clusters": [{
    "label": "default",
    "node_type_id": "i3.xlarge",
    "num_workers": 2
  }],
  "libraries": [{
    "notebook": {
      "path": "/Workspace/pipelines/simple_pipeline.py"
    }
  }]
}
```

### Production Pipeline with Auto-Scaling

```json
{
  "name": "production-pipeline",
  "storage": "/mnt/storage/pipelines/production",
  "target": "prod_catalog.processed_data",
  "clusters": [{
    "label": "default",
    "node_type_id": "i3.xlarge",
    "autoscale": {
      "min_workers": 2,
      "max_workers": 10,
      "mode": "ENHANCED"
    }
  }],
  "libraries": [
    {
      "notebook": {
        "path": "/Workspace/pipelines/ingest.py"
      }
    },
    {
      "notebook": {
        "path": "/Workspace/pipelines/transform.py"
      }
    }
  ],
  "continuous": false,
  "development": false
}
```

### Continuous Pipeline

```json
{
  "name": "streaming-pipeline",
  "storage": "/mnt/storage/pipelines/streaming",
  "target": "prod_catalog.realtime",
  "clusters": [{
    "label": "default",
    "node_type_id": "i3.xlarge",
    "num_workers": 4
  }],
  "libraries": [{
    "notebook": {
      "path": "/Workspace/pipelines/streaming_pipeline.py"
    }
  }],
  "continuous": true
}
```

## Pipeline Development Workflow

### 1. Create Pipeline Notebook

```python
# customer_pipeline.py
import dlt

@dlt.table(
    comment="Raw customer data from source"
)
def customers_raw():
    return spark.read.format("json").load("/mnt/data/customers/")

@dlt.table(
    comment="Cleaned customer data with data quality checks"
)
@dlt.expect_or_drop("valid_email", "email IS NOT NULL")
@dlt.expect("valid_age", "age > 0 AND age < 150")
def customers_clean():
    return dlt.read("customers_raw").select(
        "customer_id",
        "name",
        "email",
        "age"
    )

@dlt.table(
    comment="Customer aggregations"
)
def customer_summary():
    return dlt.read("customers_clean").groupBy("age").count()
```

### 2. Create Pipeline Configuration

```json
{
  "name": "customer-pipeline",
  "storage": "/mnt/storage/pipelines/customers",
  "target": "analytics_catalog.customers",
  "clusters": [{
    "label": "default",
    "node_type_id": "i3.xlarge",
    "num_workers": 2
  }],
  "libraries": [{
    "notebook": {
      "path": "/Workspace/pipelines/customer_pipeline.py"
    }
  }]
}
```

### 3. Create Pipeline

```bash
databricks pipelines create --json @pipeline-config.json --profile my-workspace
```

### 4. Run Pipeline

```bash
databricks pipelines start-update --pipeline-id <pipeline-id> --profile my-workspace
```

### 5. Monitor Pipeline

```bash
# Check status
databricks pipelines get --pipeline-id <pipeline-id> --profile my-workspace

# View logs
databricks pipelines get-events --pipeline-id <pipeline-id> --profile my-workspace
```

## Managing Pipelines with Asset Bundles

### Bundle Configuration

```yaml
# resources/pipelines/customer_pipeline.yml
resources:
  pipelines:
    customer_pipeline:
      name: "customer-data-pipeline"

      catalog: ${var.catalog}
      target: customer_analytics

      libraries:
        - notebook:
            path: ./src/pipelines/customer_pipeline.py

      clusters:
        - label: default
          autoscale:
            min_workers: 2
            max_workers: 10
            mode: ENHANCED

      development: false
      continuous: false
```

### Deploy with Bundle

```bash
# Validate
databricks bundle validate --profile my-workspace

# Deploy to dev
databricks bundle deploy -t dev --profile my-workspace

# Run pipeline
databricks bundle run customer_pipeline -t dev --profile my-workspace
```

## Pipeline Features

### Data Quality Checks

```python
import dlt

@dlt.table
@dlt.expect("valid_price", "price > 0")  # Warn if violated
@dlt.expect_or_drop("not_null", "id IS NOT NULL")  # Drop rows
@dlt.expect_or_fail("critical_check", "status = 'valid'")  # Fail pipeline
def processed_data():
    return spark.read.table("raw_data")
```

### Incremental Processing

```python
@dlt.table
def incremental_data():
    return (
        dlt.read_stream("source_table")
        .withWatermark("timestamp", "1 hour")
    )
```

### Change Data Capture (CDC)

```python
@dlt.table
def apply_changes():
    return dlt.apply_changes(
        target="target_table",
        source="source_stream",
        keys=["id"],
        sequence_by="timestamp",
        apply_as_deletes="operation = 'DELETE'",
        except_column_list=["operation"]
    )
```

## Pipeline Modes

### Development Mode

```json
{
  "development": true,  // Faster iterations, no optimization
  "continuous": false
}
```

- Faster pipeline updates
- No optimization
- Good for development/testing

### Production Mode

```json
{
  "development": false,  // Optimized for production
  "continuous": false
}
```

- Full optimization
- Better performance
- Recommended for production

### Continuous Mode

```json
{
  "continuous": true  // Always running, low latency
}
```

- Pipeline runs continuously
- Low latency updates
- Good for streaming data

## Best Practices

### 1. Use Unity Catalog

Always target Unity Catalog schemas:

```json
{
  "target": "prod_catalog.analytics_schema"
}
```

### 2. Implement Data Quality Checks

```python
@dlt.expect_or_drop("valid_email", "email IS NOT NULL AND email LIKE '%@%'")
@dlt.expect("reasonable_age", "age BETWEEN 0 AND 150")
```

### 3. Use Auto-Scaling

```json
{
  "autoscale": {
    "min_workers": 2,
    "max_workers": 10,
    "mode": "ENHANCED"
  }
}
```

### 4. Organize Pipeline Code

```
src/
└── pipelines/
    ├── bronze/
    │   └── ingest_raw_data.py
    ├── silver/
    │   └── clean_data.py
    └── gold/
        └── aggregate_data.py
```

### 5. Use Descriptive Names

```python
@dlt.table(
    name="customers_cleaned_with_validation",
    comment="Cleaned customer data with email and age validation"
)
```

### 6. Monitor Pipeline Health

Regularly check:
- Pipeline run duration
- Data quality metrics
- Error rates
- Resource utilization

### 7. Use Full Refresh Sparingly

```bash
# Only when necessary (reprocess all data)
databricks pipelines start-update --pipeline-id <id> --full-refresh --profile my-workspace
```

## Troubleshooting

### Pipeline Creation Fails

**Symptom**: `databricks pipelines create` fails

**Solution**:
1. Validate JSON configuration
2. Check notebook paths are correct
3. Verify target schema exists
4. Ensure storage location is accessible
5. Check cluster configuration

### Pipeline Stuck or Fails

**Symptom**: Pipeline doesn't complete or fails with error

**Solution**:
1. Check logs: `databricks pipelines get-events --pipeline-id <id>`
2. Verify source data is available
3. Check data quality expectations
4. Verify Unity Catalog permissions
5. Check cluster resources

### Data Quality Check Failures

**Symptom**: Pipeline fails due to expectation violations

**Solution**:
1. Review which expectation failed in logs
2. Check source data quality
3. Adjust expectations if needed
4. Use `expect` (warn) instead of `expect_or_fail` during development

### Performance Issues

**Symptom**: Pipeline taking too long to run

**Solution**:
1. Enable auto-scaling
2. Increase cluster size
3. Optimize data processing logic
4. Use incremental processing
5. Check for data skew

### Tables Not Created

**Symptom**: Pipeline runs but tables don't appear

**Solution**:
1. Verify target catalog/schema exists
2. Check you have CREATE TABLE permissions
3. Review pipeline logs for errors
4. Ensure @dlt.table decorators are correct
5. Check notebook is properly configured in pipeline

## Related Topics

- [Unity Catalog](unity-catalog.md) - Target schemas and manage data
- [Asset Bundles](asset-bundles.md) - Define pipelines as code
- [Jobs](jobs.md) - Schedule pipeline runs
- [Workflows](workflows.md) - Complete data engineering workflows
