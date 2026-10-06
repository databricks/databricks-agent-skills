---
name: databricks-dabs
description: 'Create, configure, validate, deploy, run, and manage Declarative Automation Bundles (DABs, formerly Databricks Asset Bundles). Use when working with Databricks resources via DABs including dashboards, jobs, pipelines, alerts, volumes, and apps.'
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
7. **Namespace App names** - App names are workspace-global and limited to 30 characters. With Databricks CLI 0.270.0 or later, shared-development defaults should include the app and `${workspace.current_user.domain_friendly_name}`; override production with a stable name, and persist an explicit local value when the default is invalid, collides, or must distinguish multiple non-production targets in one workspace. On older CLI versions, require an explicit `app_name` value instead

## Required App Completion Contract

Before validating any bundle that creates or changes an App, re-read the final bundle YAML and confirm all of the following structural requirements:

- Each App resource uses a dedicated name variable, such as `name: ${var.app_name}`, while preserving an existing equivalent variable when present.
- For Databricks CLI 0.270.0 or later, each App name variable defaults to a recognizable App prefix plus `${workspace.current_user.domain_friendly_name}` for development, and the production target overrides it with a stable name. On older CLI versions, App name variables have no default and each developer must provide values.
- No development App name uses `${workspace.current_user.short_name}`, a bare `${bundle.target}`, or a hardcoded value.

Only after this check, run `databricks bundle validate --strict --target <target> --output json` and inspect each resolved `resources.apps.<key>.name`. Each name must contain only lowercase letters, digits, and hyphens and be at most 30 characters. If a resolved name is invalid, collides after normalization, or multiple non-production targets share a workspace, persist a shorter, distinct value in the uncommitted `.databricks/bundle/<target>/variable-overrides.json` file and validate again. Successful validation alone does not satisfy this contract because validation does not catch every invalid or non-namespaced App name.

## Documentation

- [Declarative Automation Bundles](https://docs.databricks.com/dev-tools/bundles/)
- [Bundle Examples Repository](https://github.com/databricks/bundle-examples) - official end-to-end example bundles (jobs, pipelines, dashboards, apps, and more); use as working references for patterns not covered by the reference files above
