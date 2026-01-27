# Common Workflows and Best Practices

This guide covers end-to-end workflows and best practices for working with Databricks CLI.

## Workflow 1: Creating a New Databricks Project

### Step 1: Set Up Prerequisites

```bash
# Verify CLI is installed
databricks --version

# Check authentication
databricks auth profiles --profile my-workspace

# Verify connectivity
databricks current-user me --profile my-workspace
```

### Step 2: Initialize Project with Asset Bundle

```bash
# Create project directory
mkdir my-databricks-project
cd my-databricks-project

# Initialize git repository
git init

# Initialize bundle
databricks bundle init --profile my-workspace
```

Select template:
- `default-python` - Python project with jobs
- `dlt-pipeline` - Delta Live Tables pipeline
- `ml-project` - ML project with MLflow
- `databricks-app` - Databricks App

### Step 3: Set Up Unity Catalog Structure

```bash
# Create catalog
databricks catalogs create my_project_catalog --profile my-workspace

# Create schema
databricks schemas create my_project_catalog.data --profile my-workspace

# Create volume for data
databricks volumes create raw_data \
  --catalog-name my_project_catalog \
  --schema-name data \
  --volume-type MANAGED \
  --profile my-workspace
```

### Step 4: Configure Environments

Edit `databricks.yml`:

```yaml
bundle:
  name: my-project

variables:
  catalog:
    default: dev_catalog

targets:
  dev:
    default: true
    mode: development
    variables:
      catalog: dev_my_project_catalog
    workspace:
      root_path: /Users/${workspace.current_user.userName}/.bundle/${bundle.name}/dev

  prod:
    mode: production
    variables:
      catalog: prod_my_project_catalog
    workspace:
      root_path: /Shared/.bundle/${bundle.name}/prod

include:
  - resources/**/*.yml
```

### Step 5: Deploy and Test

```bash
# Validate configuration
databricks bundle validate --profile my-workspace

# Deploy to dev
databricks bundle deploy -t dev --profile my-workspace

# Test deployment
databricks bundle run <resource-name> -t dev --profile my-workspace
```

### Step 6: Version Control

```bash
# Create .gitignore
cat > .gitignore <<EOF
.databricks/
*.pyc
__pycache__/
.env
.env.*
*.log
EOF

# Commit initial project
git add .
git commit -m "Initial Databricks project setup"
```

## Workflow 2: Building a Data Pipeline

### Step 1: Set Up Data Infrastructure

```bash
# Create catalog structure
databricks catalogs create analytics_catalog --profile my-workspace
databricks schemas create analytics_catalog.raw --profile my-workspace
databricks schemas create analytics_catalog.processed --profile my-workspace

# Create volumes
databricks volumes create raw_data \
  --catalog-name analytics_catalog \
  --schema-name raw \
  --volume-type MANAGED \
  --profile my-workspace
```

### Step 2: Upload Source Data

```bash
# Upload data to volume
databricks fs cp data.csv \
  dbfs:/Volumes/analytics_catalog/raw/raw_data/data.csv \
  --profile my-workspace
```

### Step 3: Create DLT Pipeline

Create `src/pipelines/data_pipeline.py`:

```python
import dlt

@dlt.table(
    comment="Raw customer data"
)
def customers_raw():
    return spark.read.csv(
        "dbfs:/Volumes/analytics_catalog/raw/raw_data/customers.csv",
        header=True,
        inferSchema=True
    )

@dlt.table(
    comment="Cleaned customer data"
)
@dlt.expect_or_drop("valid_email", "email IS NOT NULL")
@dlt.expect("valid_age", "age > 0 AND age < 150")
def customers_clean():
    return dlt.read("customers_raw").select(
        "customer_id",
        "name",
        "email",
        "age",
        "created_at"
    )

@dlt.table(
    comment="Customer summary statistics"
)
def customer_summary():
    return dlt.read("customers_clean").groupBy("age_group").agg(
        count("*").alias("customer_count"),
        avg("purchase_value").alias("avg_purchase")
    )
```

### Step 4: Define Pipeline in Bundle

Create `resources/pipelines/data_pipeline.yml`:

```yaml
resources:
  pipelines:
    customer_pipeline:
      name: "Customer Data Pipeline"
      catalog: ${var.catalog}
      target: processed

      libraries:
        - notebook:
            path: ./src/pipelines/data_pipeline.py

      clusters:
        - label: default
          autoscale:
            min_workers: 2
            max_workers: 10
            mode: ENHANCED

      development: false
      continuous: false
```

### Step 5: Deploy and Run

```bash
# Deploy pipeline
databricks bundle deploy -t prod --profile my-workspace

# Run pipeline
databricks bundle run customer_pipeline -t prod --profile my-workspace

# Monitor pipeline
databricks pipelines get --pipeline-id <pipeline-id> --profile my-workspace
databricks pipelines get-events --pipeline-id <pipeline-id> --profile my-workspace
```

## Workflow 3: Deploying an ML Model to Production

### Step 1: Register Model in Unity Catalog

Usually done via MLflow in notebooks:

```python
import mlflow

# Log model to MLflow
with mlflow.start_run():
    mlflow.sklearn.log_model(model, "model")

# Register in UC
mlflow.register_model(
    f"runs:/{run_id}/model",
    "my_catalog.models.customer_churn"
)
```

### Step 2: Create Model Serving Endpoint

Create `endpoint-config.json`:

```json
{
  "name": "customer-churn-model",
  "config": {
    "served_entities": [{
      "entity_name": "my_catalog.models.customer_churn",
      "entity_version": "1",
      "workload_size": "Small",
      "scale_to_zero_enabled": false
    }]
  }
}
```

```bash
# Create endpoint
databricks serving-endpoints create \
  --json @endpoint-config.json \
  --profile my-workspace

# Wait for endpoint to be ready
databricks serving-endpoints get --name customer-churn-model --profile my-workspace
```

### Step 3: Test Endpoint

```bash
# Query endpoint
databricks serving-endpoints query \
  --name customer-churn-model \
  --json '{"inputs": [{"feature1": 1.0, "feature2": 2.0}]}' \
  --profile my-workspace
```

### Step 4: Monitor Endpoint

```bash
# Check status
databricks serving-endpoints get --name customer-churn-model --profile my-workspace

# View logs
databricks serving-endpoints logs --name customer-churn-model --profile my-workspace

# Get metrics
databricks serving-endpoints get-metrics --name customer-churn-model --profile my-workspace
```

## Workflow 4: Setting Up Unity Catalog with Proper Governance

### Step 1: Create Catalog Hierarchy

```bash
# Production catalog
databricks catalogs create production \
  --comment "Production data catalog" \
  --profile my-workspace

# Create schemas by domain
databricks schemas create production.sales --profile my-workspace
databricks schemas create production.marketing --profile my-workspace
databricks schemas create production.finance --profile my-workspace
```

### Step 2: Create Volumes for File Storage

```bash
# Create volumes for each domain
databricks volumes create datasets \
  --catalog-name production \
  --schema-name sales \
  --volume-type MANAGED \
  --profile my-workspace

databricks volumes create models \
  --catalog-name production \
  --schema-name sales \
  --volume-type MANAGED \
  --profile my-workspace
```

### Step 3: Set Up Permissions

```bash
# Grant catalog access to data team
databricks grants update \
  --securable-type CATALOG \
  --full-name production \
  --principal data-engineering-team \
  --privilege USE_CATALOG \
  --profile my-workspace

# Grant schema access
databricks grants update \
  --securable-type SCHEMA \
  --full-name production.sales \
  --principal sales-analytics-team \
  --privilege USE_SCHEMA \
  --profile my-workspace

# Grant table read access
databricks grants update \
  --securable-type TABLE \
  --full-name production.sales.orders \
  --principal analysts-group \
  --privilege SELECT \
  --profile my-workspace
```

### Step 4: Upload Data to Volumes

```bash
# Upload datasets
databricks fs cp sales_data.csv \
  dbfs:/Volumes/production/sales/datasets/sales_data.csv \
  --profile my-workspace
```

### Step 5: Create Tables

Create via SQL in notebooks:

```sql
CREATE TABLE production.sales.orders
USING DELTA
LOCATION 'dbfs:/Volumes/production/sales/datasets/orders'
AS SELECT * FROM csv.`/Volumes/production/sales/datasets/sales_data.csv`
```

## Workflow 5: Migrating Existing Resources to Asset Bundles

### Step 1: Initialize Bundle

```bash
mkdir my-existing-project
cd my-existing-project

databricks bundle init --profile my-workspace
```

### Step 2: Generate Configuration for Existing Resources

```bash
# Generate job configuration
databricks bundle generate job <job-id> --profile my-workspace

# Generate pipeline configuration
databricks bundle generate pipeline <pipeline-id> --profile my-workspace

# Generate app configuration
databricks bundle generate app <app-name> --profile my-workspace

# Generate dashboard configuration
databricks bundle generate dashboard <dashboard-id> --profile my-workspace
```

### Step 3: Review and Organize

Organize generated files:

```
my-project/
├── databricks.yml
├── resources/
│   ├── jobs/
│   │   ├── daily_etl.yml
│   │   └── weekly_reports.yml
│   ├── pipelines/
│   │   └── data_pipeline.yml
│   └── apps/
│       └── analytics_dashboard.yml
└── src/
    ├── notebooks/
    └── pipelines/
```

### Step 4: Bind Existing Resources

```bash
# Bind to avoid recreating resources
databricks bundle bind --profile my-workspace
```

### Step 5: Test Deployment

```bash
# Validate
databricks bundle validate --profile my-workspace

# Deploy (should update existing resources)
databricks bundle deploy --profile my-workspace
```

### Step 6: Version Control

```bash
git init
git add .
git commit -m "Migrated to Asset Bundles"
```

## Best Practices Summary

### 1. Always Use Asset Bundles

✅ **Do**:
- Initialize projects with `databricks bundle init`
- Define resources in YAML files
- Use version control
- Deploy with `databricks bundle deploy`

❌ **Avoid**:
- Creating resources manually through UI
- Ad-hoc CLI commands for production resources
- Untracked configuration changes

### 2. Use Unity Catalog for Everything

✅ **Do**:
- Store data in UC tables and volumes
- Register models in UC
- Use UC for governance and permissions

❌ **Avoid**:
- Direct DBFS usage (prefer UC volumes)
- Workspace-scoped resources without governance

### 3. Environment Separation

✅ **Do**:
```yaml
targets:
  dev:
    mode: development
    variables:
      catalog: dev_catalog

  prod:
    mode: production
    variables:
      catalog: prod_catalog
```

❌ **Avoid**:
- Single environment for dev and prod
- Hardcoded environment values

### 4. Use Secrets for Credentials

✅ **Do**:
```bash
databricks secrets create-scope --scope prod-credentials
databricks secrets put --scope prod-credentials --key db-password
```

❌ **Avoid**:
- Hardcoding credentials
- Committing secrets to git
- Storing credentials in plain text

### 5. Descriptive Naming

✅ **Do**:
```yaml
resources:
  jobs:
    daily_customer_analytics:
      name: "Daily Customer Analytics ETL"
```

❌ **Avoid**:
```yaml
resources:
  jobs:
    job1:
      name: "Job"
```

### 6. Use --profile Flag in Claude Code

✅ **Do**:
```bash
databricks apps list --profile my-workspace
databricks jobs run-now --job-id 123 --profile my-workspace
```

❌ **Avoid**:
```bash
export DATABRICKS_CONFIG_PROFILE=my-workspace
databricks apps list  # Won't work in Claude Code!
```

### 7. Monitor and Optimize

Regularly review:
- Job run duration and success rates
- Cluster utilization
- Query performance
- Cost per workload
- Pipeline data quality metrics

### 8. Documentation

✅ **Do**:
- Add comments to bundle configs
- Document workflows in README
- Add descriptions to UC objects
- Keep runbooks for operations

### 9. Testing

✅ **Do**:
- Test in dev environment first
- Validate bundle before deploying
- Run integration tests
- Monitor after deployment

### 10. Cost Optimization

✅ **Do**:
- Use auto-termination on clusters
- Enable scale-to-zero on endpoints
- Use appropriate cluster sizes
- Clean up unused resources
- Use Spot/Preemptible instances

## Common Patterns

### Pattern: Blue-Green Deployment

```yaml
resources:
  jobs:
    etl_blue:
      name: "ETL Pipeline Blue"
      # ... configuration

    etl_green:
      name: "ETL Pipeline Green"
      # ... configuration
```

Deploy and test green, then switch traffic.

### Pattern: Canary Deployment for Models

```json
{
  "traffic_config": {
    "routes": [
      {"served_model_name": "model-v1", "traffic_percentage": 95},
      {"served_model_name": "model-v2", "traffic_percentage": 5}
    ]
  }
}
```

### Pattern: Multi-Stage Pipeline

```yaml
resources:
  pipelines:
    bronze_layer:
      target: raw_data

    silver_layer:
      target: cleaned_data

    gold_layer:
      target: analytics
```

### Pattern: Scheduled Job Chain

```yaml
resources:
  jobs:
    extract:
      schedule:
        quartz_cron_expression: "0 0 1 * * ?"

    transform:
      # Depends on extract completing
      trigger:
        file_arrival: true

    load:
      # Depends on transform completing
      trigger:
        file_arrival: true
```

## Related Topics

- [Asset Bundles](asset-bundles.md) - Infrastructure as Code
- [Unity Catalog](unity-catalog.md) - Data governance
- [Jobs](jobs.md) - Workflow orchestration
- [Model Serving](model-serving.md) - ML model deployment
- [LakeFlow](lakeflow.md) - Data pipelines
