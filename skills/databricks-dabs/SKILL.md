---
name: databricks-dabs
description: 'Create, configure, validate, deploy, run, and manage DABs — Declarative Automation Bundles (formerly Databricks Asset Bundles) — for Databricks resources including dashboards, jobs, pipelines, alerts, volumes, and apps'
---

# Declarative Automation Bundles (DABs)

Use this skill for any bundle-related request including creating, configuring, validating, deploying, running, and managing Databricks resources through DABs.

## Reference Documentation

The following reference files provide detailed guidance for specific bundle tasks:

- **[Bundle Structure](references/bundle-structure.md)** - Bundle structure, databricks.yml configuration, resource definitions, path resolution, variables, and multi-environment targets
- **[SDP Pipelines](references/sdp-pipelines.md)** - Spark Declarative Pipeline configurations for DABs
- **[SQL Alerts](references/alerts.md)** - SQL Alert schemas and configuration (critical - API differs from other resources)
- **[Deploy and Run](references/deploy-and-run.md)** - Validation, deployment, running resources, monitoring logs, and troubleshooting common issues
- **[Resource Permissions](references/resource-permissions.md)** - Permission levels and access control for bundle resources, per-resource-type levels, grants vs permissions

## When to Use This Skill

Load this skill for any request involving:

- Creating new bundle projects or resources
- Configuring databricks.yml or resource YAML files
- Setting up multi-environment deployments (dev/prod targets)
- Deploying or running bundle resources
- Managing permissions for bundle resources
- Troubleshooting bundle validation or deployment errors
- Working with specific resource types (dashboards, jobs, pipelines, alerts, volumes, apps)

## General Guidelines

1. **Always validate after configuration changes** - Use `bundle validate --strict --target <target>` after any change
2. **Use reference documentation** - Consult the appropriate reference file for detailed patterns and examples
3. **Follow naming conventions** - Resource files should use `<name>.<resource_type>.yml` format
4. **Path resolution is critical** - Paths differ based on file location (see Bundle Structure reference)
5. **Preserve existing structure** - Keep user comments and structure when editing YAML files
6. **Use variables** - Parameterize catalog, schema, and warehouse for multi-environment support
