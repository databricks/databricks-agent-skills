# DBT Source: Project Overview

What to expect in a DBT project and which files to read during the Research phase.

## Project layout

A typical DBT project root contains:

```
<dbt_project_root>/
├── dbt_project.yml           # project config — required marker for source detection
├── profiles.yml              # connection/target config (catalog/schema hints)
├── packages.yml              # third-party DBT packages (dbt_utils, dbt_expectations, ...)
├── models/                   # SQL models — most nodes live here
│   ├── staging/
│   ├── intermediate/
│   └── marts/
├── snapshots/                # SCD Type 2 sources
├── seeds/                    # CSV reference data
├── macros/                   # custom Jinja macros
└── tests/                    # custom data tests (less common)
```

Models can be organized in arbitrary subdirectory layouts; do not assume `staging/`
/ `intermediate/` / `marts/` exists. Walk `models/**/*.sql` to enumerate.

## Files to read during Research

In order:

1. `dbt_project.yml` — project name, model paths, default materializations, `vars`.
2. `profiles.yml` — target database/schema; informs source mapping when present.
3. `packages.yml` — third-party packages used (affects which macros need expansion).
4. `models/**/*.sql` — every model. For each, extract:
   - `{{ config(...) }}` block (materialization, unique_key, on_schema_change, etc.).
   - `ref('...')` calls (intra-project dependencies).
   - `source('...', '...')` calls (external sources).
   - Jinja patterns (`{% if is_incremental() %}`, `{{ this }}`, custom macro calls).
5. `models/**/schema.yml` and `models/**/sources.yml` — column tests, source
   declarations.
6. `macros/**/*.sql` — definitions for any custom macros referenced in models.
7. `snapshots/**/*.sql` — extract `{{ config(strategy=..., unique_key=...,
updated_at=...) }}`.
8. `seeds/**/*.csv` — note paths and column headers.

## DBT artifact kinds and how they map to IR nodes

Every DBT artifact becomes one IR node:

| Artifact | Where                | IR `source_path` | Notes                                |
| -------- | -------------------- | ---------------- | ------------------------------------ |
| Model    | `models/**/*.sql`    | the file path    | Most common case                     |
| Snapshot | `snapshots/**/*.sql` | the file path    | SCD-tracked source                   |
| Seed     | `seeds/**/*.csv`     | the CSV path     | Reference data — needs Volume upload |

DBT macros and tests are NOT IR nodes — macros are expanded inline into models that
use them; tests become SDP expectations on their target model.

## Source mapping (DBT-specific)

Each `source('name', 'table')` call must resolve to a fully qualified
`catalog.schema.table` in Unity Catalog. Resolution sources, in order:

1. The `sources.yml` (or `models/**/schema.yml`) declaration's `database`/`schema`
   fields.
2. `profiles.yml` defaults under the active target (set via `--target` or the
   `target` field).

If after these resolutions a source still cannot be mapped, add the entry to
`sources[]` with the best guess and add a `manual_review` flag on every node that
references it.
