> ⚠️ **Experimental: best-effort, not officially supported**
>
> The skills in this directory were originally imported from
> [databricks-solutions/ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit)
> on a best-effort basis. **`ai-dev-kit` is now deprecated** —
> `databricks/databricks-agent-skills` is the canonical home for these skills
> going forward, and updates land here directly rather than via re-sync.
>
> Most of that snapshot has since been **promoted to the stable
> [`../skills/`](../skills/) tree** (see [Promoted to stable](#promoted-to-stable)
> below). The few skills that remain here are still **not officially supported**
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
# Install all experimental skills at once
databricks aitools install --experimental

# Install a single experimental skill by name
databricks aitools install databricks-genie --experimental
```

See the root [README](../README.md) for details on the stable install path.

## Available Skills

### 📊 Analytics & Dashboards
- **databricks-genie** - Genie Spaces: natural-language data Q&A, space authoring, and tuning (example questions, instructions)

### 🔧 Data Engineering
- **spark-python-data-source** - Python data sources for Spark (custom connectors)

## Promoted to stable

Most of the original ai-dev-kit snapshot now lives in the stable
[`../skills/`](../skills/) tree and installs by default (no `--experimental`
flag). See the root [README](../README.md#available-skills) for the full list.
Promoted skills include `databricks-ai-functions`, `databricks-agent-bricks`,
`databricks-aibi-dashboards`, `databricks-apps-python`, `databricks-dbsql`,
`databricks-docs`, `databricks-execution-compute`, `databricks-iceberg`,
`databricks-lakeflow-connect`, `databricks-metric-views`, `databricks-ml-training`,
`databricks-mlflow-evaluation`, `databricks-python-sdk`,
`databricks-spark-structured-streaming`, `databricks-synthetic-data-gen`,
`databricks-unity-catalog`, `databricks-unstructured-pdf-generation`, and
`databricks-zerobus-ingest`. `databricks-data-discovery` (Genie One data
discovery / NL data Q&A / SQL generation) was also promoted to stable.

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

These skills are imported as a snapshot from
[`databricks-solutions/ai-dev-kit/databricks-skills/`](https://github.com/databricks-solutions/ai-dev-kit/tree/main/databricks-skills).

**Source SHA**: [`20a92a3`](https://github.com/databricks-solutions/ai-dev-kit/commit/20a92a38144ca5228f1dfe4cc0be46da40ec9177)
on the `experimental` branch of `databricks-solutions/ai-dev-kit`.

While `ai-dev-kit` is the upstream source, this directory receives periodic
manual re-syncs.
