---
name: databricks-genie-agents
description: "Create, manage, and query Databricks Genie Agents — curated, per-data natural-language agents (formerly Genie Spaces): build, export/import, migrate across workspaces, and ask questions of a *specific* Agent via the Conversation API. For general data questions or finding data across your workspace, use databricks-data-discovery (Genie One) instead."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.1.0"
---

# Databricks Genie Agents

Create, manage, and query Genie Agents (formerly Genie Spaces) - natural language interfaces for SQL-based data exploration.

## Overview

Genie Agents allow users to ask natural language questions about structured data in Unity Catalog. The system translates questions into SQL queries, executes them on a SQL warehouse, and presents results conversationally.

A Genie Agent is a **curated agent scoped to specific data** — its tables, sample questions, and instructions are authored for a particular business area. This is distinct from **Genie One** / the general "ask Genie" data-discovery path (see the `databricks-data-discovery` skill), which answers questions across your data without a curated, per-scope agent.

## Genie Agent Lifecycle

| Phase | Reference | Load when | Typical CLI |
|-------|-----------|-----------|-------------|
| **Design + Create** | [create-genie-agent.md](references/create-genie-agent.md) | **Always load before creating or updating.** Gather requirements, profile data, design surfaces, get approval — before any CLI | `discover-schema` → `create-space` / `update-space` |
| **Query / validate** | [query-genie-agent.md](references/query-genie-agent.md) | Querying via Conversation API or Agent mode API; authoring SQL for Metric View sources | `start-conversation` / `get-message` |
| **Diagnose** | [diagnose-genie-agent.md](references/diagnose-genie-agent.md) | Agent gives wrong/empty answers — gather space ID + failing question + observed behavior first | `get-space --include-serialized-space`; `system.query.history` |
| **Optimize** | [optimize-genie-agent.md](references/optimize-genie-agent.md) | Benchmark-driven quality tuning — gather space ID + optimization goal + benchmark target first | `genie-create-eval-run`; `update-space` |
| **Export / migrate** | [genie-agent-cicd.md](references/genie-agent-cicd.md) | Export, import, cross-workspace migration, batch migration, DABs/CI-CD | `get-space` → remap → `create-space` |
| — | [serialized-space.md](references/serialized-space.md) | Constructing or debugging `serialized_space` payloads — field schemas, constraints, Python helper | — |
| — | [uc-persistence.md](references/uc-persistence.md) | Setting up UC Delta tables for multi-pass optimization history — CREATE TABLE DDL only | — |

Typical flow: **create → query/validate → diagnose → optimize**.

## Prerequisites

- **Tables in Unity Catalog** — bronze/silver/gold tables with the data
- **SQL Warehouse** — a warehouse to execute queries (auto-detected if not specified)

## Related Skills

- **[databricks-data-discovery](../databricks-data-discovery/SKILL.md)** - General natural-language data exploration / "ask Genie" (Genie One) across your data; use it when you are not targeting a specific curated Genie Agent
- **[databricks-metric-views](../databricks-metric-views/SKILL.md)** - Build governed business metrics that Genie consumes. See [SKILL.md](../databricks-metric-views/SKILL.md) for metric-view design rules that affect Genie answer quality, and [query-patterns.md](../databricks-metric-views/references/query-patterns.md) for the `MEASURE()` query rules Genie must follow.
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - Use Genie Agents as agents inside Supervisor Agents
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Manage the catalogs, schemas, and tables Genie queries

