> ⚠️ **Experimental: best-effort, not officially supported**
>
> This directory includes skills authored here and skills originally imported from
> [databricks-solutions/ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit)
> on a best-effort basis. **`ai-dev-kit` is now deprecated** —
> `databricks/databricks-agent-skills` is the canonical home for these skills
> going forward, and updates land here directly rather than via re-sync.
>
> Most of that snapshot has since been **promoted to the stable
> [`../skills/`](../skills/) tree** (see [Promoted to stable](#promoted-to-stable)
> below). The experimental skills here are still **not officially supported**
> as part of `databricks-agent-skills`:
>
> - They do not follow the same review / quality bar as the skills in
>   [`../skills/`](../skills/).
> - They are not installed by `databricks aitools install` by default —
>   you have to opt in (see the root README).
>
> File issues against this directory in this repo; do not file issues against
> the deprecated `ai-dev-kit` repo.

---

# Databricks Skills for Claude Code (experimental)

Skills that teach Claude Code how to work effectively with Databricks - providing patterns, best practices, and code examples that work with Databricks MCP tools.

## Installation

These experimental skills are **not** installed by default. To install them via the Databricks CLI:

```bash
# Install stable and experimental skills together
databricks aitools install --skills-only --experimental

# Install only the Lakehouse MCP skill
databricks aitools install --skills-only --experimental --skills databricks-lakehouse-mcp
```

See the root [README](../README.md) for details on the stable install path.

## Available Skills

### Notebooks

- **[databricks-lakehouse-mcp](databricks-lakehouse-mcp/SKILL.md)** - Connect to the hosted Lakehouse MCP (`system.ai.lakehouse`, private preview) and load its notebook workflow guidance. Access questions go to your Databricks account representative.

### Document Intelligence

- **[lakeflow-unstructured](lakeflow-unstructured/SKILL.md)** - Create and deploy Document Intelligence workflow folders from existing volume files or Delta tables, with AI Function tasks and a UI handoff for evaluation and improvements. Source ingestion and connector setup are outside scope.

### 🔧 Data Engineering
- **spark-python-data-source** - Python data sources for Spark (custom connectors)

## Promoted to stable

Most of the original ai-dev-kit snapshot now lives in the stable
[`../skills/`](../skills/) tree and installs by default (no `--experimental`
flag). See the root [README](../README.md#available-skills) for the full list.
Promoted skills include `databricks-ai-functions`,
`databricks-aibi-dashboards`, `databricks-apps-python`, `databricks-dbsql`,
`databricks-docs`, `databricks-execution-compute`, `databricks-genie-agents`,
`databricks-iceberg`,
`databricks-lakeflow-connect`, `databricks-metric-views`, `databricks-ml-training`,
`databricks-mlflow-evaluation`, `databricks-python-sdk`,
`databricks-spark-structured-streaming`, `databricks-synthetic-data-gen`,
`databricks-unity-catalog`, `databricks-unstructured-pdf-generation`, and
`databricks-zerobus-ingest`. `databricks-data-discovery` (Genie One data
discovery / NL data Q&A / SQL generation) was also promoted to stable.

[`databricks-ai-runtime`](../skills/databricks-ai-runtime/) (AI Runtime GPU
training workloads and custom Docker images) now lives in stable
and installs by default.

Earlier experimental copies of `databricks-bundles`, `databricks-lakebase-autoscale`,
and `databricks-config` were merged into the stable
[`databricks-dabs`](../skills/databricks-dabs/),
[`databricks-lakebase`](../skills/databricks-lakebase/), and
[`databricks-core`](../skills/databricks-core/) skills.

The experimental `databricks-metric-view-advisor` was folded into the stable
[`databricks-metric-views`](../skills/databricks-metric-views/) skill — it now
lives there as the [`references/metric-view-advisor.md`](../skills/databricks-metric-views/references/metric-view-advisor.md)
reference and ships with that skill (no separate install).

## Provenance

`spark-python-data-source` was imported as a snapshot from
[`databricks-solutions/ai-dev-kit/databricks-skills/`](https://github.com/databricks-solutions/ai-dev-kit/tree/main/databricks-skills).

**Source SHA**: [`20a92a3`](https://github.com/databricks-solutions/ai-dev-kit/commit/20a92a38144ca5228f1dfe4cc0be46da40ec9177)
on the `experimental` branch of `databricks-solutions/ai-dev-kit`.

`lakeflow-unstructured` is authored in this repository. Experimental skills are
maintained here; changes are not automatically re-synced from `ai-dev-kit`.
