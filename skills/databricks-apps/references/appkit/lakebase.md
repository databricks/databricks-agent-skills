# Lakebase in AppKit

Same `--features lakebase` plugin — **two different patterns**. Do not conflate them.

| Pattern | Capability | Guide |
|---------|------------|-------|
| **OLTP CRUD** — app-owned Postgres (forms, sessions, todos) | `writes_oltp` | [Lakebase OLTP](lakebase-oltp.md) |
| **Synced reads** — read-only Delta replicas in Postgres | `reads_synced` | [Lakebase Synced Reads](lakebase-synced-reads.md) |

**Pattern selection and gates:** [Data Patterns](data-patterns.md).

**Infrastructure** (create project, synced table pipeline, SP grants): **`databricks-lakebase`** skill.
