# Databricks Asset Bundles (DABs)

Databricks Asset Bundles provide Infrastructure-as-Code for Databricks resources, enabling version control, automated deployments, and environment management.

## What are Asset Bundles?

Asset Bundles let you define your Databricks projects as code, including:
- Jobs
- Pipelines (Delta Live Tables)
- Apps
- Models
- Dashboards
- Notebooks
- Python files
- Configuration files

## Bundle Commands

```bash
# Initialize a new bundle from template
databricks bundle init --profile my-workspace

# Validate bundle configuration
databricks bundle validate --profile my-workspace

# Deploy bundle to workspace
databricks bundle deploy --profile my-workspace

# Deploy to specific environment (dev/staging/prod)
databricks bundle deploy -t dev --profile my-workspace
databricks bundle deploy -t staging --profile my-workspace
databricks bundle deploy -t prod --profile my-workspace

# Run a resource from the bundle
databricks bundle run <resource-name> --profile my-workspace

# Generate configuration for existing resources
databricks bundle generate job <job-id> --profile my-workspace
databricks bundle generate pipeline <pipeline-id> --profile my-workspace
databricks bundle generate dashboard <dashboard-id> --profile my-workspace
databricks bundle generate app <app-name> --profile my-workspace

# Destroy bundle resources (use with caution!)
databricks bundle destroy --profile my-workspace
databricks bundle destroy -t dev --profile my-workspace
```

## Bundle Structure

A typical bundle has this structure:

```
my-project/
├── databricks.yml         # Main bundle configuration
├── resources/
│   ├── jobs/
│   │   └── my_job.yml
│   ├── pipelines/
│   │   └── my_pipeline.yml
│   ├── apps/
│   │   └── my_app.yml
│   └── models/
│       └── my_model.yml
├── src/
│   ├── notebooks/
│   │   └── process_data.py
│   └── python/
│       └── utils.py
├── tests/
│   └── test_utils.py
└── README.md
```

## Main Configuration (databricks.yml)

### Basic Example

```yaml
bundle:
  name: my-project

# Workspace configuration
workspace:
  host: https://company-workspace.cloud.databricks.com

# Define targets (environments)
targets:
  dev:
    default: true
    mode: development
    workspace:
      root_path: /Users/${workspace.current_user.userName}/.bundle/${bundle.name}/dev

  staging:
    mode: production
    workspace:
      root_path: /Shared/.bundle/${bundle.name}/staging

  prod:
    mode: production
    workspace:
      root_path: /Shared/.bundle/${bundle.name}/prod

# Include resource definitions
include:
  - resources/**/*.yml
```

### Advanced Example with Variables

```yaml
bundle:
  name: my-project

variables:
  catalog:
    description: "Unity Catalog name"
    default: dev_catalog

  warehouse_id:
    description: "SQL Warehouse ID"

workspace:
  host: https://company-workspace.cloud.databricks.com

targets:
  dev:
    default: true
    mode: development
    variables:
      catalog: dev_catalog
      warehouse_id: "abc123def456"
    workspace:
      root_path: /Users/${workspace.current_user.userName}/.bundle/${bundle.name}/dev

  prod:
    mode: production
    variables:
      catalog: prod_catalog
      warehouse_id: "xyz789uvw012"
    workspace:
      root_path: /Shared/.bundle/${bundle.name}/prod

include:
  - resources/**/*.yml
```

## Initializing a Bundle

### Using Templates

```bash
# Start initialization (interactive)
databricks bundle init --profile my-workspace
```

Available templates:
- **default-python** - Python project with jobs
- **dlt-pipeline** - Delta Live Tables pipeline
- **ml-project** - ML project with MLflow
- **databricks-app** - Databricks App

### Template Selection Example

```bash
$ databricks bundle init

Template to use [default-python, dlt-pipeline, ml-project, databricks-app]: default-python
Project name: my-analytics-project
```

## Defining Resources

### Job Resource

```yaml
# resources/jobs/daily_job.yml
resources:
  jobs:
    daily_analytics:
      name: "Daily Analytics Job"

      tasks:
        - task_key: "extract_data"
          notebook_task:
            notebook_path: "./src/notebooks/extract.py"
            source: WORKSPACE
          new_cluster:
            spark_version: "13.3.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 2

        - task_key: "transform_data"
          depends_on:
            - task_key: "extract_data"
          notebook_task:
            notebook_path: "./src/notebooks/transform.py"
            source: WORKSPACE
          new_cluster:
            spark_version: "13.3.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 2

      schedule:
        quartz_cron_expression: "0 0 2 * * ?"  # Daily at 2 AM
        timezone_id: "UTC"
```

### Pipeline Resource (DLT)

```yaml
# resources/pipelines/data_pipeline.yml
resources:
  pipelines:
    customer_pipeline:
      name: "Customer Data Pipeline"

      catalog: ${var.catalog}
      target: customer_analytics

      libraries:
        - notebook:
            path: ./src/notebooks/customer_pipeline.py

      clusters:
        - label: default
          autoscale:
            min_workers: 1
            max_workers: 5
            mode: ENHANCED
```

### App Resource

```yaml
# resources/apps/my_app.yml
resources:
  apps:
    dashboard_app:
      name: "analytics-dashboard"
      description: "Customer analytics dashboard"
      source_code_path: ./src/app
```

### Model Resource

```yaml
# resources/models/my_model.yml
resources:
  registered_models:
    customer_churn:
      name: "${var.catalog}.${var.schema}.customer_churn_model"
      description: "Customer churn prediction model"
```

## Working with Environments

### Environment Configuration

Environments (targets) allow you to deploy the same code to different workspaces with different configurations.

```yaml
targets:
  dev:
    default: true
    mode: development
    variables:
      catalog: dev_catalog
      cluster_size: "Small"
    workspace:
      root_path: /Users/${workspace.current_user.userName}/.bundle/${bundle.name}/dev

  staging:
    mode: production
    variables:
      catalog: staging_catalog
      cluster_size: "Medium"
    workspace:
      root_path: /Shared/.bundle/${bundle.name}/staging
      host: https://staging-workspace.cloud.databricks.com

  prod:
    mode: production
    variables:
      catalog: prod_catalog
      cluster_size: "Large"
    workspace:
      root_path: /Shared/.bundle/${bundle.name}/prod
      host: https://prod-workspace.cloud.databricks.com
```

### Deploying to Different Environments

```bash
# Deploy to dev (default)
databricks bundle deploy --profile my-workspace

# Deploy to staging
databricks bundle deploy -t staging --profile my-workspace

# Deploy to production
databricks bundle deploy -t prod --profile my-workspace
```

## Bundle Workflow

### Complete Development Workflow

1. **Initialize bundle**:
   ```bash
   databricks bundle init --profile my-workspace
   ```

2. **Develop locally**:
   - Edit `databricks.yml` and resource files
   - Write notebooks, Python scripts, SQL queries
   - Configure jobs, pipelines, apps

3. **Validate configuration**:
   ```bash
   databricks bundle validate --profile my-workspace
   ```

4. **Deploy to development**:
   ```bash
   databricks bundle deploy -t dev --profile my-workspace
   ```

5. **Test your deployment**:
   ```bash
   # Run a job
   databricks bundle run my-job -t dev --profile my-workspace

   # Start a pipeline
   databricks bundle run my-pipeline -t dev --profile my-workspace
   ```

6. **Deploy to production**:
   ```bash
   databricks bundle deploy -t prod --profile my-workspace
   ```

## Generating Bundle from Existing Resources

If you have existing resources in your workspace, you can generate bundle configuration:

### Generate Job Configuration

```bash
# Get job ID from list
databricks jobs list --profile my-workspace

# Generate configuration
databricks bundle generate job 12345 --profile my-workspace
```

This creates:
- Job configuration file in `resources/`
- Downloads associated notebooks/files

### Generate Pipeline Configuration

```bash
databricks bundle generate pipeline <pipeline-id> --profile my-workspace
```

### Generate App Configuration

```bash
databricks bundle generate app my-app --profile my-workspace
```

This generates:
- App configuration file
- Downloads app source code

### Generate Dashboard Configuration

```bash
databricks bundle generate dashboard <dashboard-id> --profile my-workspace
```

## Binding Existing Resources

You can link bundle-defined resources to existing resources in your workspace without recreating them:

```bash
databricks bundle bind --profile my-workspace
```

This is useful when:
- Migrating existing projects to bundles
- Adopting bundle management for running resources
- Avoiding downtime during migration

## Variables and Templating

### Defining Variables

```yaml
# databricks.yml
variables:
  catalog:
    description: "Unity Catalog name"
    default: dev_catalog

  warehouse_id:
    description: "SQL Warehouse ID"

  num_workers:
    description: "Number of cluster workers"
    default: 2
```

### Using Variables

```yaml
# In resource files
resources:
  jobs:
    my_job:
      name: "Job in ${var.catalog}"

      tasks:
        - task_key: "main"
          notebook_task:
            notebook_path: "./notebook.py"
          new_cluster:
            num_workers: ${var.num_workers}
```

### Environment-Specific Variables

```yaml
targets:
  dev:
    variables:
      catalog: dev_catalog
      num_workers: 2

  prod:
    variables:
      catalog: prod_catalog
      num_workers: 10
```

## Best Practices

### 1. Use Version Control

Always commit your bundle to Git:

```bash
git init
git add databricks.yml resources/ src/
git commit -m "Initial bundle setup"
```

### 2. Separate Concerns

Organize resources by type:

```
resources/
├── jobs/
│   ├── daily_jobs.yml
│   └── hourly_jobs.yml
├── pipelines/
│   ├── ingestion.yml
│   └── transformation.yml
└── apps/
    └── dashboard.yml
```

### 3. Use Environment-Specific Configuration

```yaml
targets:
  dev:
    mode: development  # Allows in-place updates

  prod:
    mode: production   # Ensures immutable deployments
```

### 4. Validate Before Deploy

Always validate:

```bash
databricks bundle validate --profile my-workspace
```

### 5. Use Descriptive Names

```yaml
resources:
  jobs:
    daily_customer_analytics:  # Good: descriptive
      name: "Daily Customer Analytics"
```

### 6. Document with Comments

```yaml
# This job runs daily ETL for customer analytics
# Schedule: 2 AM UTC daily
# Dependencies: Unity Catalog tables in analytics schema
resources:
  jobs:
    daily_etl:
      name: "Daily ETL"
      # ...
```

### 7. Use Variables for Environment Differences

```yaml
variables:
  catalog: ${bundle.environment}  # Automatically uses env name
  cluster_size: Small

targets:
  prod:
    variables:
      cluster_size: Large  # Override for prod
```

## Troubleshooting

### Bundle Validation Errors

**Symptom**: `databricks bundle validate` shows errors

**Solution**:
1. Check YAML syntax (proper indentation, no tabs)
2. Verify all required fields are present
3. Check that resource references are correct
4. Use `databricks bundle validate --debug` for detailed errors

### Deployment Fails

**Symptom**: `databricks bundle deploy` fails

**Solution**:
1. Run validation first: `databricks bundle validate`
2. Check workspace permissions
3. Verify target configuration
4. Check for resource name conflicts
5. Review error message for specific issues

### Resources Not Found After Deploy

**Symptom**: Resources deployed but not visible in workspace

**Solution**:
1. Check target root_path in `databricks.yml`
2. Verify you're looking in the correct workspace location
3. Check deployment logs for errors
4. Ensure resources were included in deployment

### Variable Not Resolved

**Symptom**: Variable showing as `${var.name}` instead of actual value

**Solution**:
1. Check variable is defined in `databricks.yml`
2. Verify variable has value in target
3. Use correct syntax: `${var.variable_name}`
4. Check variable scope (bundle vs target)

## Related Topics

- [DBSQL](dbsql.md) - Manage SQL resources alongside bundles
- [Data Exploration](data-exploration.md) - Validate data exposed by bundle deployments
- [Secrets](secrets.md) - Configure secret-backed credentials for resources
- Apps - Define app resources (use `databricks-apps` skill for full app development)
- [Workflows](workflows.md) - Complete bundle workflows
