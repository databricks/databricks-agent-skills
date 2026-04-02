# Write Declarative Automation Bundles

## Bundle Structure

```
project/
├── databricks.yml           # Main config + targets
├── resources/               # Resource definitions (one YAML file per resource)
│   ├── my_job.job.yml
│   ├── my_pipeline.pipeline.yml
│   └── my_dashboard.dashboard.yml
└── src/                     # Code/dashboard files
    ├── notebook.py
    └── pipeline.py
```

**Resource file naming convention**: `<name>.<resource_type>.yml` (e.g., `my_job.job.yml`, `my_pipeline.pipeline.yml`, `my_dashboard.dashboard.yml`)

## Main Configuration (databricks.yml)

```yaml
bundle:
  name: project-name

include:
  - resources/*.yml

variables:
  catalog:
    default: 'default_catalog'
  schema:
    default: 'default_schema'
  warehouse_id:
    lookup:
      warehouse: 'Shared SQL Warehouse'

targets:
  dev:
    default: true
    mode: development
    workspace:
      profile: dev-profile
    variables:
      catalog: 'dev_catalog'
      schema: 'dev_schema'

  prod:
    mode: production
    workspace:
      profile: prod-profile
    variables:
      catalog: 'prod_catalog'
      schema: 'prod_schema'
```

## Path Resolution

**Critical**: Paths depend on file location:

| File Location            | Path Format  | Example                       |
| ------------------------ | ------------ | ----------------------------- |
| `resources/*.yml`        | `../src/...` | `../src/dashboards/file.json` |
| `databricks.yml` targets | `./src/...`  | `./src/dashboards/file.json`  |

**Why**: `resources/` files are one level deep, so use `../` to reach bundle root. `databricks.yml` is at root, so use `./`

## Dashboard Resources

**Support for dataset_catalog and dataset_schema parameters added in Databricks CLI 0.281.0 (January 2026)**

```yaml
resources:
  dashboards:
    dashboard_name:
      display_name: 'Dashboard Title'
      file_path: ../src/dashboards/dashboard.lvdash.json
      warehouse_id: ${var.warehouse_id}
      dataset_catalog: ${var.catalog}
      dataset_schema: ${var.schema}
```

## Jobs Resources

```yaml
resources:
  jobs:
    job_name:
      name: 'Job Name'
      tasks:
        - task_key: 'main_task'
          notebook_task:
            notebook_path: ../src/notebooks/main.ipynb
          new_cluster:
            spark_version: '17.3.x-scala2.13'
            node_type_id: 'i3.xlarge'
            num_workers: 2
      schedule:
        quartz_cron_expression: '0 0 9 * * ?'
        timezone_id: 'America/Los_Angeles'
```

## Volume Resources

```yaml
resources:
  volumes:
    my_volume:
      catalog_name: ${var.catalog}
      schema_name: ${var.schema}
      name: 'volume_name'
      volume_type: 'MANAGED'
```

**Volumes use `grants` not `permissions`** — different format from other resources.

## Apps Resources

**Apps resource support added in Databricks CLI 0.239.0 (January 2025)**

Apps have minimal configuration — environment variables are defined in `app.yaml` in the source directory, NOT in databricks.yml.

### Generate from Existing App (Recommended)

```bash
databricks bundle generate app --existing-app-name my-app --key my_app --profile DEFAULT
```

### Manual Configuration

**resources/my_app.app.yml:**

```yaml
resources:
  apps:
    my_app:
      name: my-app-${bundle.target}
      description: 'My application'
      source_code_path: ../src/app
```

**src/app/app.yaml:**

```yaml
command:
  - 'python'
  - 'dash_app.py'

env:
  - name: USE_MOCK_BACKEND
    value: 'false'
  - name: DATABRICKS_WAREHOUSE_ID
    value: 'your-warehouse-id'
  - name: DATABRICKS_CATALOG
    value: 'main'
  - name: DATABRICKS_SCHEMA
    value: 'my_schema'
```

| Aspect               | Apps                              | Other Resources                    |
| -------------------- | --------------------------------- | ---------------------------------- |
| **Environment vars** | In `app.yaml` (source dir)        | In databricks.yml or resource file |
| **Configuration**    | Minimal (name, description, path) | Extensive (tasks, clusters, etc.)  |
| **Source path**      | Points to app directory           | Points to specific files           |

**Important**: When source code is in project root (not src/app), use `source_code_path: ..` in the resource file.

## Generate Configuration for Existing Resources

```bash
databricks bundle generate job <job-id>
databricks bundle generate pipeline <pipeline-id>
databricks bundle generate dashboard <dashboard-id>
databricks bundle generate app <app-name>
```

## Other Resources

DABs supports schemas, models, experiments, clusters, warehouses, etc. Use `databricks bundle schema` to inspect schemas.

## Key Principles

1. **Path resolution**: `../src/` in resources/\*.yml, `./src/` in databricks.yml
2. **Variables**: Parameterize catalog, schema, warehouse
3. **Mode**: `development` for dev/staging, `production` for prod
4. **Groups**: Use `"users"` for all workspace users
