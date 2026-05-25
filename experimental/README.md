> ⚠️ **Experimental: best-effort, not officially supported**
>
> The skills in this directory are imported from
> [databricks-solutions/ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit)
> on a best-effort basis. They may be useful, but they are **not officially
> supported** as part of `databricks-agent-skills`:
>
> - They do not follow the same review / quality bar as the skills in
>   [`../skills/`](../skills/).
> - They may be out of date relative to upstream `ai-dev-kit`.
> - They are not installed by `databricks aitools install` by default —
>   you have to opt in (see the root README).
>
> File issues against this directory in this repo; do not file issues against
> `ai-dev-kit` for skills installed via `databricks-agent-skills`.

---

# Databricks Skills for Claude Code

Skills that teach Claude Code how to work effectively with Databricks - providing patterns, best practices, and code examples that work with Databricks MCP tools.

## Installation

These experimental skills are **not** installed by default. To install them via the Databricks CLI:

```bash
# Install all experimental skills at once
databricks aitools install --experimental

# Install a single experimental skill by name
databricks aitools install databricks-iceberg --experimental
```

See the root [README](../README.md) for details on the stable install path.

## Available Skills

### 🤖 AI & Agents
- **databricks-ai-functions** - Built-in AI Functions (ai_classify, ai_extract, ai_summarize, ai_query, ai_forecast, ai_parse_document, and more) with SQL and PySpark patterns, function selection guidance, document processing pipelines, and custom RAG (parse → chunk → index → query)
- **databricks-agent-bricks** - Knowledge Assistants, Genie Spaces, Supervisor Agents
- **databricks-mlflow-evaluation** - End-to-end agent evaluation workflow
- **databricks-unstructured-pdf-generation** - Generate synthetic PDFs for RAG

### 📊 Analytics & Dashboards
- **databricks-aibi-dashboards** - Databricks AI/BI dashboards (with SQL validation workflow)
- **databricks-metric-views** - Metric Views for governed metrics
- **databricks-unity-catalog** - System tables for lineage, audit, billing

### 🔧 Data Engineering
- **databricks-dbsql** - Databricks SQL warehouse patterns
- **databricks-iceberg** - Apache Iceberg tables (Managed/Foreign), UniForm, Iceberg REST Catalog, Iceberg Clients Interoperability
- **databricks-spark-structured-streaming** - Spark Structured Streaming patterns
- **databricks-synthetic-data-gen** - Realistic test data with Faker
- **databricks-zerobus-ingest** - Zerobus ingest patterns
- **spark-python-data-source** - Python data sources for Spark

### 🚀 Development & Deployment
- **databricks-apps-python** - Databricks apps. Prefers AppKit (TypeScript + React SDK) for new apps; falls back to Python frameworks (Dash, Streamlit, Gradio, Flask, FastAPI, Reflex) when Python is required
- **databricks-python-sdk** - Python SDK, Connect, CLI, REST API
- **databricks-execution-compute** - Execute on Databricks compute

> **Use the stable skill instead** for:
> - **DABs / bundles** — use stable [`databricks-dabs`](../skills/databricks-dabs/)
> - **Lakebase Postgres** (projects, branching, synced tables, autoscaling) — use stable [`databricks-lakebase`](../skills/databricks-lakebase/)
> - **CLI auth / profiles / workspace config** — use stable [`databricks-core`](../skills/databricks-core/)
>
> Previously experimental copies of these (`databricks-bundles`, `databricks-lakebase-autoscale`, `databricks-config`) were already merged with the stable skills.

### 📚 Reference
- **databricks-docs** - Documentation index via llms.txt

## Provenance

These skills are imported as a snapshot from
[`databricks-solutions/ai-dev-kit/databricks-skills/`](https://github.com/databricks-solutions/ai-dev-kit/tree/main/databricks-skills).

**Source SHA**: [`20a92a3`](https://github.com/databricks-solutions/ai-dev-kit/commit/20a92a38144ca5228f1dfe4cc0be46da40ec9177)
on the `experimental` branch of `databricks-solutions/ai-dev-kit`.

While `ai-dev-kit` is the upstream source, this directory receives periodic
manual re-syncs.
