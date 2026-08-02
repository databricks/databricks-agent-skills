---
name: databricks-docs
description: "Databricks documentation reference via llms.txt index. Use when other skills do not cover a topic, looking up unfamiliar Databricks features, or needing authoritative docs on APIs, configurations, or platform capabilities."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Databricks Documentation Reference

This skill provides access to the complete Databricks documentation index via llms.txt - use it as a **reference resource** to supplement other skills.

## Role of This Skill

This is a **reference skill**, not an action skill. Use it to:

- Look up documentation when other skills don't cover a topic
- Get authoritative guidance on Databricks concepts and APIs
- Find detailed information to inform CLI commands and SDK usage
- Discover features and capabilities you may not know about

**Always prefer using CLI/SDK for actions** and **load specific skills for workflows** (databricks-python-sdk, databricks-pipelines, etc.). Use this skill when you need reference documentation.

## How to Use

Fetch the llms.txt documentation index:

**URL:** `https://docs.databricks.com/llms.txt`

Use WebFetch to retrieve this index, then:

1. Search for relevant sections/links
2. Fetch specific documentation pages for detailed guidance
3. Apply what you learn using the appropriate CLI commands or SDK

## Documentation Structure

The llms.txt file is organized by category:

- **Overview & Getting Started** - Basic concepts and tutorials
- **Data Engineering** - Lakeflow, Spark, Delta Lake, pipelines
- **SQL & Analytics** - Warehouses, queries, dashboards
- **AI/ML** - MLflow, model serving, GenAI
- **Governance** - Unity Catalog, permissions, security
- **Developer Tools** - SDKs, CLI, APIs, Terraform

## Example: Complementing Other Skills

**Scenario:** User wants to create a Lakeflow Spark Declarative Pipelines pipeline

1. Load `databricks-pipelines` skill for workflow patterns
2. Use this skill to fetch docs if you need clarification on specific pipeline features
3. Use `databricks pipelines create` CLI command to create the pipeline

**Scenario:** User asks about an unfamiliar Databricks feature

1. Fetch llms.txt to find relevant documentation
2. Read the specific docs to understand the feature
3. Determine which skill/tools apply, then use them

## Related Skills

- **`databricks-python-sdk`** - SDK patterns for programmatic Databricks access
- **databricks-pipelines** - Lakeflow Spark Declarative Pipelines (formerly Delta Live Tables / DLT) workflows
- **`databricks-unity-catalog`** - Governance and catalog management
- **databricks-model-serving** - Serving endpoints and model deployment
- **`databricks-mlflow-evaluation`** - MLflow 3 GenAI evaluation workflows
