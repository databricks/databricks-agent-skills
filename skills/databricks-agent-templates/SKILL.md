---
name: databricks-agent-templates
description: "Build, run, and ship AI agents on the Databricks Apps platform from the agent templates (LangGraph and OpenAI Agents SDK). Use when: scaffolding or modifying an agent; adding tools (MCP servers, Genie spaces, vector search, UC functions); adding memory; running locally; deploying to Databricks Apps; enabling long-running/background execution; using the Supervisor API; load testing; or migrating an MLflow ResponsesAgent from Model Serving to Apps."
---

# Databricks Agent Templates

Build agents on the **Databricks Apps** platform starting from the agent
templates, in either **LangGraph** or the **OpenAI Agents SDK**. This skill is a
router: each topic below is a focused reference under `references/`. Open the one
that matches the task.

> These references mirror the agent templates in
> [databricks/app-templates](https://github.com/databricks/app-templates)
> (`.claude/skills/`). Where a topic overlaps a dedicated skill, the reference
> defers to it (e.g. `databricks-lakebase`, `databricks-dabs`,
> `databricks-model-serving`) rather than duplicating it.

## Getting started
- [quickstart](references/quickstart/quickstart.md) — set up the dev environment, Databricks auth, and `.env`.
- [run-locally](references/run-locally/run-locally.md) — run and test the agent locally; curl the API; hot reload.

## Tools
- [discover-tools](references/discover-tools/discover-tools.md) — find MCP servers, Genie spaces, vector search indexes, and UC functions in the workspace.
- [create-tools](references/create-tools/create-tools.md) — create the Databricks resources agents connect to as tools.
- [add-tools-langgraph](references/add-tools-langgraph/add-tools-langgraph.md) — attach tools and grant `databricks.yml` permissions (LangGraph).
- [add-tools-openai](references/add-tools-openai/add-tools-openai.md) — attach tools and grant `databricks.yml` permissions (OpenAI Agents SDK).

## Modify the agent
- [modify-langgraph-agent](references/modify-langgraph-agent/modify-langgraph-agent.md) — change the model, instructions, or tools (LangGraph).
- [modify-openai-agent](references/modify-openai-agent/modify-openai-agent.md) — change the model, instructions, or tools (OpenAI Agents SDK).

## Memory
- [agent-langgraph-memory](references/agent-langgraph-memory/agent-langgraph-memory.md) — short- and long-term memory (LangGraph checkpointer + store).
- [agent-openai-memory](references/agent-openai-memory/agent-openai-memory.md) — conversation memory (OpenAI Agents SDK sessions).
- [lakebase-setup](references/lakebase-setup/lakebase-setup.md) — configure Lakebase Postgres as the memory backend.

## Deploy & operate
- [deploy](references/deploy/deploy.md) — deploy to Databricks Apps with Databricks Asset Bundles.
- [long-running-server](references/long-running-server/long-running-server.md) — background execution for tasks beyond the HTTP timeout.
- [load-testing](references/load-testing/load-testing.md) — benchmark the app and find its max QPS.

## Supervisor API (hosted agent loop)
- [supervisor-api](references/supervisor-api/supervisor-api.md) — run the agent loop server-side with the Databricks Supervisor API.
- [supervisor-api-background-mode](references/supervisor-api-background-mode/supervisor-api-background-mode.md) — background polling for long-running tasks.
- [supervisor-api-client-function-calling](references/supervisor-api-client-function-calling/supervisor-api-client-function-calling.md) — mix client-side Python function tools with hosted tools.

## Migration
- [migrate-from-model-serving](references/migrate-from-model-serving/migrate-from-model-serving.md) — migrate an MLflow ResponsesAgent from Model Serving to Databricks Apps.
