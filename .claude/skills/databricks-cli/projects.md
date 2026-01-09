# Project Scaffolding

## Overview

This guide covers creating new Databricks projects using AI-friendly templates.

## Important

**ALWAYS** use `databricks experimental aitools tools init-template` commands instead of `databricks bundle init`. The init-template commands create agent-friendly projects with AGENTS.md/CLAUDE.md guidance files and proper MCP integration.

## Project Templates

### Apps

For creating Databricks apps:

```bash
databricks experimental aitools tools init-template app --name my-app --description "My app description"
```

**Notes:**
- App name must be ≤26 characters (dev- prefix adds 4 chars, max total 30)

### Jobs

For creating Python notebook jobs with wheel packages:

```bash
databricks experimental aitools tools init-template job --name my_job
databricks experimental aitools tools init-template job --name my_job --catalog my_catalog
```

**Notes:**
- Job names: letters, numbers, underscores only
- `--catalog` defaults to workspace default catalog

### Pipelines

For creating Lakeflow Declarative Pipelines:

```bash
databricks experimental aitools tools init-template pipeline --name my_pipeline --language python
databricks experimental aitools tools init-template pipeline --name my_pipeline --language sql --catalog my_catalog
```

**Important:**
- `--language` is required (python or sql)
- Ask the user which language they prefer:
  - **SQL**: Recommended for straightforward transformations (filters, joins, aggregations)
  - **Python**: Recommended for complex logic (custom UDFs, ML, advanced processing)

**Notes:**
- Pipeline names: letters, numbers, underscores only
- `--catalog` defaults to workspace default catalog

### Custom Resources

For creating projects with custom resources (dashboards, alerts, model serving, etc.):

```bash
databricks experimental aitools tools init-template empty --name my_project
```

**Notes:**
- Use this for resources OTHER than apps, jobs, or pipelines
- Project names: letters, numbers, underscores only

## Naming Conventions

| Resource Type | Character Limit | Allowed Characters | Notes |
|---------------|----------------|-------------------|-------|
| Apps | ≤26 chars | Alphanumeric, hyphens | dev- prefix adds 4 chars (max total 30) |
| Jobs | No specific limit | Letters, numbers, underscores | No hyphens |
| Pipelines | No specific limit | Letters, numbers, underscores | No hyphens |
| Projects | No specific limit | Letters, numbers, underscores | No hyphens |

## Common Workflows

### Creating a New App

1. Choose a descriptive name (≤26 characters)
2. Run: `databricks experimental aitools tools init-template app --name my-app --description "App purpose"`
3. The command creates a project with AGENTS.md/CLAUDE.md for guidance

### Creating a Data Pipeline

1. Ask user to choose language (Python or SQL)
2. For SQL: `databricks experimental aitools tools init-template pipeline --name my_pipeline --language sql`
3. For Python: `databricks experimental aitools tools init-template pipeline --name my_pipeline --language python`
4. Optionally specify catalog: `--catalog my_catalog`

### Creating a Job

1. Choose a job name (underscores only, no hyphens)
2. Run: `databricks experimental aitools tools init-template job --name my_job`
3. Optionally specify catalog: `--catalog my_catalog`
