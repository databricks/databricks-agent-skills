---
name: "databricks"
description: "Databricks CLI operations: auth, profiles, Unity Catalog, data exploration, jobs, pipelines, clusters, model serving, bundles and more. Contains up-to-date guidelines for all Databricks CLI tasks, useful for all Databricks-related tasks."
compatibility: Requires databricks CLI (>= 0.250.0)
metadata:
  version: "0.1.0"
---

# Databricks

Core skill for Databricks CLI, authentication, and data exploration.

## Product Skills

For specific products, use dedicated skills:
- **databricks-apps** - Full-stack TypeScript app development and deployment

## Prerequisites

1. **CLI installed**: `databricks --version`
   - If not: see [CLI Installation](databricks-cli-install.md)

2. **Authenticated**: `databricks auth profiles`
   - If not: see [CLI Authentication](databricks-cli-auth.md)

## Profile Selection - CRITICAL

**NEVER auto-select a profile.**

1. List profiles: `databricks auth profiles`
2. Present ALL profiles to user with workspace URLs
3. Let user choose (even if only one exists)
4. Offer to create new profile if needed

## Claude Code - IMPORTANT

Each Bash command runs in a **separate shell session**.

```bash
# WORKS: --profile flag
databricks apps list --profile my-workspace

# WORKS: chained with &&
export DATABRICKS_CONFIG_PROFILE=my-workspace && databricks apps list

# DOES NOT WORK: separate commands
export DATABRICKS_CONFIG_PROFILE=my-workspace
databricks apps list  # profile not set!
```

## Data Exploration — Use AI Tools

**Use these instead of manually navigating catalogs/schemas/tables:**

```bash
# discover table structure (columns, types, sample data, stats)
databricks experimental aitools tools discover-schema catalog.schema.table --profile <profile>

# run ad-hoc SQL queries
databricks experimental aitools tools query "SELECT * FROM table LIMIT 10" --profile <profile>

# find the default warehouse
databricks experimental aitools tools get-default-warehouse --profile <profile>
```

See [Data Exploration](data-exploration.md) for details.

## Quick Reference

**⚠️ CRITICAL: Some commands use positional arguments, not flags**

```bash
# current user
databricks current-user me --profile <profile>

# list resources
databricks apps list --profile <profile>
databricks jobs list --profile <profile>
databricks clusters list --profile <profile>
databricks warehouses list --profile <profile>
databricks pipelines list --profile <profile>
databricks serving-endpoints list --profile <profile>

# ⚠️ Unity Catalog — POSITIONAL arguments (NOT flags!)
databricks catalogs list --profile <profile>

# ✅ CORRECT: positional args
databricks schemas list <catalog> --profile <profile>
databricks tables list <catalog> <schema> --profile <profile>
databricks tables get <catalog>.<schema>.<table> --profile <profile>

# ❌ WRONG: these flags/commands DON'T EXIST
# databricks schemas list --catalog-name <catalog>    ← WILL FAIL
# databricks tables list --catalog <catalog>           ← WILL FAIL
# databricks sql-warehouses list                       ← doesn't exist, use `warehouses list`
# databricks execute-statement                         ← doesn't exist, use `experimental aitools tools query`
# databricks sql execute                               ← doesn't exist, use `experimental aitools tools query`

# When in doubt, check help:
# databricks schemas list --help

# get details
databricks apps get <name> --profile <profile>
databricks jobs get --job-id <id> --profile <profile>
databricks clusters get --cluster-id <id> --profile <profile>

# bundles
databricks bundle init --profile <profile>
databricks bundle validate --profile <profile>
databricks bundle deploy -t <target> --profile <profile>
databricks bundle run <resource> -t <target> --profile <profile>
```

## Troubleshooting

| Error | Solution |
|-------|----------|
| `cannot configure default credentials` | Use `--profile` flag or authenticate first |
| `PERMISSION_DENIED` | Check workspace/UC permissions |
| `RESOURCE_DOES_NOT_EXIST` | Verify resource name/id and profile |

## Required Reading by Task

| Task | READ BEFORE proceeding |
|------|------------------------|
| First time setup | [CLI Installation](databricks-cli-install.md) |
| Auth issues / new workspace | [CLI Authentication](databricks-cli-auth.md) |
| Exploring tables/schemas | [Data Exploration](data-exploration.md) |
| UC permissions/volumes | [Unity Catalog](unity-catalog.md) |
| Deploying jobs/pipelines | [Asset Bundles](asset-bundles.md) |

## Reference Guides

- [CLI Installation](databricks-cli-install.md)
- [CLI Authentication](databricks-cli-auth.md)
- [Data Exploration](data-exploration.md)
- [Unity Catalog](unity-catalog.md)
- [Asset Bundles](asset-bundles.md)
- [Jobs](jobs.md)
- [LakeFlow](lakeflow.md)
- [Model Serving](model-serving.md)
- [DBSQL](dbsql.md)
- [Clusters](clusters.md)
- [Workspace](workspace.md)
- [Secrets](secrets.md)
- [DBFS](dbfs.md) (legacy - prefer UC Volumes)
- [AI/BI Dashboards](ai-bi-dashboards.md)
- [Genie](genie.md)
