---
name: databricks-dabs
description: "Create, configure, validate, deploy, run, and manage DABs -- Declarative Automation Bundles (formerly Databricks Asset Bundles) -- for Databricks resources including dashboards, jobs, pipelines, alerts, volumes, and apps. Use when the user asks about DABs, Databricks bundles, deploying Databricks resources, or managing bundle configurations."
compatibility: Requires databricks CLI (>= v0.292.0)
metadata:
  version: "0.1.0"
---

# Declarative Automation Bundles (DABs)

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

## Quick-Start Workflow

```bash
# 1. Create a new bundle project
databricks bundle init --profile <PROFILE>

# 2. Configure databricks.yml and resource YAML files
#    Resource files: resources/<name>.<resource_type>.yml

# 3. Validate
databricks bundle validate --strict --target <target> --profile <PROFILE>

# 4. Deploy
databricks bundle deploy -t <target> --profile <PROFILE>

# 5. Run a specific resource
databricks bundle run <RESOURCE> -t <target> --profile <PROFILE>
```

### Minimal databricks.yml

```yaml
bundle:
  name: my-project

workspace:
  host: https://my-workspace.cloud.databricks.com

variables:
  catalog:
    default: dev_catalog
  schema:
    default: my_schema

targets:
  dev:
    default: true
  prod:
    variables:
      catalog: prod_catalog
```

## Guidelines

1. **Always validate after changes** -- `bundle validate --strict --target <target>`
2. **Follow naming conventions** -- Resource files use `<name>.<resource_type>.yml`
3. **Path resolution is critical** -- Paths differ based on file location (see Bundle Structure reference)
4. **Preserve existing structure** -- Keep user comments and structure when editing YAML
5. **Use variables** -- Parameterize catalog, schema, and warehouse for multi-environment support

## Reference Documentation

- **[Bundle Structure](references/bundle-structure.md)** -- databricks.yml configuration, resource definitions, path resolution, variables, multi-environment targets
- **[SDP Pipelines](references/sdp-pipelines.md)** -- Spark Declarative Pipeline configurations for DABs
- **[SQL Alerts](references/alerts.md)** -- SQL Alert schemas and configuration (API differs from other resources)
- **[Deploy and Run](references/deploy-and-run.md)** -- Validation, deployment, running resources, monitoring, troubleshooting
- **[Resource Permissions](references/resource-permissions.md)** -- Permission levels, access control, grants vs permissions
