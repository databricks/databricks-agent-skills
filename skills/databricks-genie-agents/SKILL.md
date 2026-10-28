---
name: databricks-genie-agents
description: "Create, manage, and query Databricks Genie Agents (formerly Genie Spaces): curated agents over Unity Catalog tables, Metric Views, and documents in UC volumes. Use when building, migrating, tuning, or asking a specific Agent, and for document Q&A or docs + data agents (replaces the legacy Knowledge Assistant and Supervisor Agent). For data questions across the workspace, use databricks-data-discovery."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.2.0"
---

# Databricks Genie Agents

A Genie Agent is a **curated agent scoped to one business area**: its tables / Metric Views, documents (UC volumes), sample questions, and instructions. It answers by writing SQL on a warehouse and, in Agent mode, by searching its documents, so one turn can combine SQL results and cited files. Distinct from **Genie One** (`databricks-data-discovery`), which answers across your data without a curated Agent.

> **Replaces Knowledge Assistant and Supervisor Agent for docs + data.** Both are [legacy](https://docs.databricks.com/generative-ai/agent-bricks/knowledge-assistant) (*"For new low-code agents over your documents and data, use Genie Agents"*). Document Q&A (was a KA) = an Agent with a volume: no endpoint, no sync. Routing between data and docs (was a Supervisor over Genie + KA) = one Agent with tables + a volume. See [Documents](references/create-genie-agent.md#documents-uc-volumes). An Agent can also attach Databricks-provided MCP connectors (Google Drive, Microsoft 365, Slack, Jira/Confluence, GitHub, ...; [Beta](https://docs.databricks.com/genie-agents/external-tools), set up in the UI, Agent mode only). Custom MCP servers, UC functions, or other endpoints aren't supported; build a code agent (`databricks-ml-training`). To maintain an existing KA / Supervisor: [legacy-ka-supervisor.md](references/legacy-ka-supervisor.md).

## Genie Agent Lifecycle

| Phase | Reference | Load when | Typical CLI |
|-------|-----------|-----------|-------------|
| **Create / update** | [create-genie-agent.md](references/create-genie-agent.md) | Building or editing an Agent: the workflow, the `serialized_space` payload format, and the CLI | `discover-schema` → `create-space` / `update-space` |
| **Attach documents** | [create-genie-agent.md § Documents](references/create-genie-agent.md#documents-uc-volumes) | Document Q&A, docs + data, replacing a KA / Supervisor | `volumes create` → `update-space` → probe in Agent mode |
| **Query / converse / validate** | [query-genie-agent.md](references/query-genie-agent.md) | Conversation API (tables), Agent mode API (needed for documents), Metric View SQL | `start-conversation` / Agent mode `responses` |
| **Improve** (inspect / diagnose / benchmark / fix) | [improve-genie-agent.md](references/improve-genie-agent.md) | Working with an existing Agent: wrong/empty answers, quality tuning, benchmark evaluation | `get-space`; `genie-create-eval-run`; `update-space` |
| **Export / migrate** | [genie-agent-cicd.md](references/genie-agent-cicd.md) | Export, import, cross-workspace migration, batch migration, DABs/CI-CD | `get-space` → remap → `create-space` |
| Optimization history | [uc-persistence.md](references/uc-persistence.md) | Setting up UC Delta tables for multi-pass optimization history (CREATE TABLE DDL only) | |
| Legacy | [legacy-ka-supervisor.md](references/legacy-ka-supervisor.md) | Maintaining or migrating an **existing** Knowledge Assistant / Supervisor Agent | `knowledge-assistants` / `supervisor-agents` |

Typical flow: **create → query/validate → improve** (diagnose / benchmark / fix, as needed).

## Commands

An Agent is defined by a **`serialized_space`** JSON object (sources, sample questions, per-column context, instructions), kept in a local `genie_agent.json` and passed to the CLI. Core commands below; the lifecycle table points to the full workflow, payload schema, and flags.

```bash
databricks genie list-spaces                                          # find Agents
databricks genie get-space SPACE_ID --include-serialized-space        # inspect config
databricks genie create-space WAREHOUSE_ID "$(jq -c . genie_agent.json)" \
  --title "..." --parent-path /Workspace/Users/you@company.com/genie_spaces   # create
databricks genie update-space SPACE_ID --serialized-space "$(jq -c . genie_agent.json)"  # full-replace edit
databricks genie start-conversation --no-wait SPACE_ID "a question"   # converse / validate (tables only)
databricks genie trash-space SPACE_ID                                 # delete
```

## Documents (replaces KA and Supervisor)

Attach a managed UC volume in `data_sources.volumes[]`: `create-space` / `update-space` start indexing automatically, and documents are read in Agent mode only (the chat-mode `start-conversation` ignores them). Setup, waiting for indexing, adding documents to an existing Agent, permissions, limits, and evaluation: [create-genie-agent.md § Documents](references/create-genie-agent.md#documents-uc-volumes).

## Prerequisites

- **Tables / Metric Views in Unity Catalog** and/or a **managed UC volume** of documents
- **SQL Warehouse** to execute queries (auto-detected if not specified)

## Related Skills

- **[databricks-data-discovery](../databricks-data-discovery/SKILL.md)**: general natural-language data exploration / "ask Genie" (Genie One) across your data, when you are not targeting a specific curated Genie Agent
- **[databricks-metric-views](../databricks-metric-views/SKILL.md)**: governed business metrics that Genie consumes. See its [SKILL.md](../databricks-metric-views/SKILL.md) for design rules that affect Genie answer quality, and [query-patterns.md](../databricks-metric-views/references/query-patterns.md) for the `MEASURE()` query rules Genie follows.
- **[databricks-unstructured-pdf-generation](../databricks-unstructured-pdf-generation/SKILL.md)**: generate demo / eval PDFs to attach to an Agent as a volume
- **[databricks-ml-training](../databricks-ml-training/SKILL.md)**: code agents (`ResponsesAgent`) when you need orchestration Genie can't express
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)**: manage the catalogs, schemas, tables, and volumes Genie uses
