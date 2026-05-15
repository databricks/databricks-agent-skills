> ⚠️ **Experimental — best-effort, not officially supported**
>
> The skills in this directory are imported from
> [databricks-solutions/ai-dev-kit](https://github.com/databricks-solutions/ai-dev-kit)
> on a best-effort basis. They may be useful, but they are **not officially
> supported** as part of `databricks-agent-skills`:
>
> - They do not follow the same review / quality bar as the skills in
>   [`../skills/`](../skills/).
> - They may be out of date relative to upstream `ai-dev-kit`.
> - The on-disk install path always carries a `-experimental` suffix so
>   experimental skills never collide with stable skills of the same name
>   (see the install-path note below).
> - They are not installed by `databricks experimental aitools skills install`
>   by default — you have to opt in (see the root README).
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
databricks experimental aitools skills install --experimental

# Install a single experimental skill by name (note the -experimental suffix)
databricks experimental aitools skills install databricks-iceberg-experimental --experimental
```

The names in this directory don't carry the `-experimental` suffix — that's
added at install time so the on-disk skills directory unambiguously
distinguishes experimental from stable. e.g. `databricks-iceberg` in this
repo installs to `~/.claude/skills/databricks-iceberg-experimental/`.

See the root [README](../README.md) for details on the stable install path.

## Available Skills

### 🤖 AI & Agents
- **databricks-ai-functions** - Built-in AI Functions (ai_classify, ai_extract, ai_summarize, ai_query, ai_forecast, ai_parse_document, and more) with SQL and PySpark patterns, function selection guidance, document processing pipelines, and custom RAG (parse → chunk → index → query)
- **databricks-agent-bricks** - Knowledge Assistants, Genie Spaces, Supervisor Agents
- **databricks-genie** - Genie Spaces: create, curate, and query via Conversation API
- **databricks-mlflow-evaluation** - End-to-end agent evaluation workflow
- **databricks-unstructured-pdf-generation** - Generate synthetic PDFs for RAG
- **databricks-vector-search** - Vector similarity search for RAG and semantic search

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
> Previously experimental copies of these (`databricks-bundles`, `databricks-lakebase-autoscale`, `databricks-config`) were dropped — they duplicated the stable skills without adding new content.

### 📚 Reference
- **databricks-docs** - Documentation index via llms.txt

## Provenance & sync model

These skills are imported as a snapshot from
[`databricks-solutions/ai-dev-kit/databricks-skills/`](https://github.com/databricks-solutions/ai-dev-kit/tree/main/databricks-skills).

**Source SHA**: [`7b07f18`](https://github.com/databricks-solutions/ai-dev-kit/commit/7b07f18b6efb7ff0ac011d3fe81b435eb3cd793a)
on the `experimental` branch of `databricks-solutions/ai-dev-kit` —
the merge commit of [a-d-k PR #533](https://github.com/databricks-solutions/ai-dev-kit/pull/533)
into `experimental`. The PR #533 change set, now part of `experimental`:

- `databricks-app-python` → `databricks-apps-python` rename (folder,
  baselines, manifests, install scripts, cross-skill mentions). The
  rename prevents a 3rd skill-name collision with d-a-s's own
  `databricks-apps` — alongside the two we already handle for
  `databricks-jobs` and `databricks-model-serving`.
- `databricks-apps-python/SKILL.md` leads with AppKit (TypeScript +
  React SDK) as the recommended approach for new apps; Python
  frameworks (Dash, Streamlit, Gradio, Flask, FastAPI, Reflex) are
  demoted to an explicit alternative.
- `install.sh` / `install.ps1` upstream changes wiring a-d-k to
  install d-a-s skills via a single GitHub tree call (out of scope
  for this snapshot, not imported here — only `databricks-skills/`
  content is mirrored).

**Note**: the `experimental` branch of a-d-k previously removed
`databricks-lakebase-provisioned`, which is why it is not present in
this import. `databricks-model-serving` and
`databricks-spark-declarative-pipelines` are intentionally excluded
from this snapshot — see TODOs #1b and #5 on the import PR.

The full set of paths brought in is tracked by the import commit on
this branch.

**Transition phase (until `ai-dev-kit` skills are locked):**
- Source of truth is **upstream `ai-dev-kit`**. New work and bug fixes go there.
- This directory receives **periodic manual re-syncs** — someone opens a PR
  to bring drift from upstream into `experimental/`.

**Post-lock (after `ai-dev-kit` skill contributions are stopped):**
- Source of truth is **this repo**. New work and bug fixes go directly to
  `experimental/<skill>/`.
- `ai-dev-kit/databricks-skills/` becomes read-only and points here.
